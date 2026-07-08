# The analytical model, number by number (inspection document)

> **Last updated: 2026-07-08 (D10: asymmetric remote traversals).** Living document (CLAUDE.md rule 1). Every
> constant and modeling decision in the simulation, with its value,
> decomposition, what it includes/excludes per system, provenance, and the
> reasoning — so each can be inspected and vetoed individually.

## 1. The latency equations

A message's end-to-end latency = `endpoint-delay` (system JSON, per
message, route-invariant) + per-hop dimension latency (network YAML) +
`size / dimension-bandwidth` serialization. Per mode:

```
              dim0 (in-rack)                    dim1 (cross-rack)
Loom     :  fabric + t_pipe_local          wire + (t_pipe + roce_stream)      [source ToR]
           = 500 + 50        = 550 ns          + (roce_stream + t_pipe_local) [destination ToR]
                                          = 600 + 650 + 200 = 1450 ns
B1 (GPU) :  fabric           = 500 ns     wire + rdma_init_B1 = 600 + 2400 = 3000 ns
B2 (proxy): fabric           = 500 ns     wire + rdma_init_B2 = 600 + 2800 = 3400 ns  (+ rendezvous)
B3 (ideal): fabric           = 500 ns     wire                = 600 ns

bandwidth: dim0 = 64 GB/s (all)   dim1 = 50 GB/s × goodput
           goodput: Loom 0.947 · baselines 0.95 · ideal 1.0
endpoint-delay: 10 ns, ALL systems (HGX-validated store-issue cost)
```

## 2. The core asymmetry (why Loom's dim1 ≠ baseline's dim1)

**The baseline creates and submits a work request for every transfer.**
Its per-op cost decomposes into:

| Component | Where it happens | Approx. share |
|---|---|---|
| WQE creation + doorbell ring | GPU kernel (B1) / CPU proxy after GPU handoff (B2) | 100s ns (B1) / µs-class incl. handoff (B2) |
| Doorbell processing + WQE fetch over PCIe | NIC | ~400–800 ns (PCIe round trip) |
| QP-context fetch/update | NIC | ~100s ns (cache-dependent) |
| Payload DMA from device/host memory over PCIe | NIC | ~400–800 ns first bytes |
| Packet build / ICRC / congestion state | NIC pipeline | ~100–200 ns |
| **Total per op (end-to-end anchors)** | | **B1 ≈ 3 µs** (IBGDA/NVSHMEM published puts) → `rdma_init_B1 = 2400` after the 600 ns wire; **B2** = ib_write_lat ≈ 1.6–2 µs + GPU→proxy handoff ≈ 1–1.5 µs → `rdma_init_B2 = 2800` |

**Loom performs none of the initiation on the data path.** Connections are
established once, at binding time, by the orchestrator's connection manager
(control path); QP context is resident in the switch; the payload is not
DMA-fetched — it streams from the fabric port through the encapsulator into
the RoCE engine. On the data path the RC connections act as pipes, bounded
by the routing pipeline's capability. What remains per traversal:

| Component | Loom pays? | Where it lives in the model |
|---|---|---|
| WQE/doorbell/QP-fetch/payload-DMA | **No** (control path did it once) | — (this is the modeled asymmetry) |
| Binding lookup, bounds, translate, encap/decap | Yes | `t_pipe` = 500 ns* per traversal |
| Packet build / ICRC / CC state (streaming share) | Yes | `roce_stream` = 150 ns per traversal |

The two ToR traversals are **asymmetric** (D10): the source runs the full
remote pipeline (lookup/validate + encap = `t_pipe`); the destination runs
RoCE RX + decap + the *same* check/translate/forward that local delivery
uses — both routes converge on the transaction generator (design §6.1) —
so it costs `t_pipe_local`, not a second `t_pipe`. Only the RoCE streaming
share is paid at both ends (the baseline pays its receive-side NIC too,
inside its end-to-end anchor). So `dim1(Loom) = 1450 ns` vs
`dim1(B1) = 3000 ns`: the gap **is** the moved-to-setup work-request
machinery, which is the paper's claim rendered as arithmetic. If the claim is wrong, the testbed
will say so: T3 measures the composite per-traversal cost through Coyote's
actual RoCE stack, and the substrate RoCE ping-pong floor isolates the
transport share. **Accounting rule: never add `roce_stream` on top of a
`t_pipe` measured inclusive of the stack — set it to 0 then.**

## 3. Constants ledger

| Constant | Value | Includes | Excludes | Provenance | Replaced by |
|---|---|---|---|---|---|
| `endpoint-delay` | 10 ns (all systems) | issuing one store toward the fabric | everything route-dependent | AstraSim `HGX-H100-validated.json` (validated) | — |
| `fabric_latency` | 500 ns | rack fabric hop incl. stock switch forwarding | Loom's added lookups | PCIe5-switch class; alt preset: HGX 936.25 ns validated | testbed floor |
| `t_pipe_local` | 50 ns* | binding lookup + bounds over stock forwarding | full remote pipeline | pipelined SRAM lookups, ASIC-class estimate | **T3** (Loom local path vs raw Coyote forwarding) |
| `t_pipe` | 500 ns* | validate/match/encap resp. decap/bounds/translate, per traversal | transport streaming share | placeholder, swept 100 ns–5 µs | **T3** (remote path) |
| `roce_stream` | 150 ns | packet build/ICRC/CC state per traversal | WQE/doorbell/QP-fetch/payload-DMA (Loom never does these on the data path) | HW packet-engine class | **Coyote RoCE floor** |
| `wire` (`--net-latency`) | 600 ns | inter-ToR cut-through switch + propagation | endpoint anything | ToR datasheets (300–800 ns class) | — |
| `rdma_init_B1` | 2400 ns | full per-op initiation (table above) minus wire | — | ≈3 µs end-to-end GPU-initiated put (IBGDA blog, NVSHMEM docs) | swept {S-4} |
| `rdma_init_B2` | 2800 ns | ib_write_lat + GPU→proxy handoff, minus wire | — | perftest + Kalia ATC'16 + NCCL proxy path | testbed CPU-verbs run |
| goodput 0.95 / 0.947 | — | Eth+IP+UDP+BTH ≈78 B on 4 KB MTU; Loom adds 12 B ⟨offset·op·len⟩ | coalescing benefit at small sizes (favors Loom, deliberately unmodeled until measured) | header arithmetic | **T2** goodput-vs-size curve |
| `peak-perf` 989 vs 839 TFLOPS | full SMs vs 20/132 statically reserved | — | dynamic SM contention | DeepSeek-V3 (20 SMs of H800's 132) | swept {8, 20, 32} |
| `read-credits` 32 | outstanding peer reads per NPU | — | per-binding granularity (approximation) | design §6.3 | **T6** + swept |
| `--uplink-oversub` 1.0 | ToR uplink aggregate = M NICs (equal wires) | equal-cost framing (Loom deletes M NICs — favors Loom, prose only) | — | fairness choice | swept S-6 |

\* = the only Loom-specific unknowns; everything else published/validated.

## 4. Decisions ledger (each individually vetoable)

- **D1 — folding technique**: switch behavior as constants inside per-dim
  latency/BW, the method of AstraSim's own validated HGX config.
- **D2 — route-split endpoint costs** *(user-identified)*: in-rack peer
  access is a plain store for every system; RDMA initiation exists only on
  the scale-out route → lives in dim1, not in `endpoint-delay` (which
  AstraSim applies to every message regardless of route).
- **D3 — the ToR is the rack switch** *(user-identified)*: stock forwarding
  is already inside `fabric_latency`; in-rack Loom pays only `t_pipe_local`.
- **D4 — composite per-traversal pipeline** *(user-identified)*: transport
  processing composes INTO the pipeline term; no separate additive NIC
  charge (double-counting guard for T3 calibration).
- **D5 — control-path vs data-path RDMA** *(user-identified)*: Loom never
  creates/submits work requests on the data path; only the streaming share
  (`roce_stream` = 150 ns) survives per traversal. The baseline pays the
  full per-op initiation every transfer.
- **D6 — SM reservation as peak-perf scaling**: production reserves SMs
  statically (DeepSeek-V3), so compute-speed scaling is the faithful model;
  applies only to B1.
- **D7 — eager = posted write; rendezvous = B2's handshake**: AstraSim's
  eager sender completes at injection = a posted store accepted by the
  switch (design §6.2).
- **D8 — equal-wires fairness** with the disclosed orthogonal-dims gap
  (Loom's shared XPU edge port is not contended in the analytical tier —
  favors Loom; congestion-tier item).
- **D9 — no hand-authored applications**: shipped ETs, STG published
  shapes, or captured traces only.
- **D10 — asymmetric remote traversals** *(user-identified)*: destination-
  side remote work = the local-route delivery pipeline (`t_pipe_local`),
  not a second full `t_pipe`; RoCE streaming share at both ends. Charging
  a full pipeline at the destination was inconsistent with pricing the
  identical table work at 50 ns on the local route.

## 5. Open items for inspection

1. `roce_stream = 150 ns` is the newest and least-anchored placeholder —
   the Coyote RoCE floor measurement replaces it; if Coyote's FPGA stack is
   much slower, the FPGA-vs-ASIC argument must carry the difference.
2. `rdma_init_B1 = 2400 ns` assumes the published ≈3 µs end-to-end put is
   wire + initiation only; if it amortizes batching, B1 is being flattered.
3. `t_pipe_local = 50 ns` presumes lookups pipeline behind stock
   arbitration; T3 will say whether the FPGA adder is 10× that.
4. Coalescing is deliberately absent (favors baselines) until T2's curve
   exists — the small-message regime where Loom should shine is therefore
   *understated* in all current results.
5. Loom's dim1 advantage (1900 vs 3000 ns) now exceeds its dim0 penalty —
   verify the matrix cells that flipped sign track this and not an artifact.
