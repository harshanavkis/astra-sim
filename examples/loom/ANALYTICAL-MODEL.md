# The analytical model, number by number (inspection document)

> **Last updated: 2026-08-04 — REWRITTEN for consistency.** Living document
> (CLAUDE.md rule 1). Every constant and modelling decision in the
> simulation, with its value, decomposition, what it includes/excludes per
> system, provenance, and the reasoning — so each can be inspected and
> vetoed individually.
>
> This rewrite was needed because a run of model corrections (in-rack
> increment → 0, goodput → equal, `t_forward` double-count removed, B3
> deleted, and above all `rdma_init` moved out of dim1 latency into
> endpoint occupancy) left the previous text describing a model that no
> longer existed. Where a number changed, the old value and the reason are
> recorded in §4 rather than silently overwritten.

## 0. The four cases at a glance (one peer write)

| Case | Steps | Total |
|---|---|---|
| **Loom in-rack** | fabric traversal incl. stock switching (500) | **500 ns** |
| **Loom cross-rack** | edge fabric legs XPU↔ToR both ends (500) + source ToR `t_lookup+t_queue+t_encap` (200) + RoCE TX stream (150) + wire (600) + RoCE RX stream (150) + dest `t_translate` (15) | **1615 ns** |
| **Baseline in-rack** | fabric traversal (500) — a plain peer store, no RDMA machinery on this route | **500 ns** |
| **Baseline cross-rack** | wire (600) **as latency**, plus `rdma_init` (2400 B1 / 2800 B2) **as endpoint occupancy** — see §6 | **600 ns latency + 2400/2800 ns occupancy** |

**In-rack is identical for every system (500 ns).** Loom does not bolt a
translator onto someone else's switch — the Loom ToR *is* the rack switch,
and its in-rack datapath does what any peer-store path already does
(range-indexed table consult + bounds check). NVIDIA documents the same
class of work inside NVSwitch. See D15.

Cross-rack, Loom never pays WQE creation, doorbell, QP fetch or payload
DMA: those happen once, at binding time, on the control path. That
asymmetry is the paper's claim rendered as arithmetic.

## 1. The latency equations

(Visualized in `figures/loom-latency-breakdown.drawio.xml`.)

```
              dim0 (in-rack)             dim1 (cross-rack)
Loom      :  fabric        = 500 ns   fabric legs (both ends)              =  500
                                      + (t_lookup+t_queue+t_encap) + roce  =  350   [src]
                                      + wire                               =  600
                                      + roce + t_translate                 =  165   [dest]
                                                                     total = 1615 ns
B1 (GPU)  :  fabric        = 500 ns   wire = 600 ns   + issue overhead 2400 ns (§6)
B2 (proxy):  fabric        = 500 ns   wire = 600 ns   + issue overhead 2800 ns (§6)
                                                      + --rendezvous-protocol

bandwidth : dim0 = 64 GB/s (all)      dim1 = 50 GB/s x goodput 0.95 = 47.5 (all)
```

Stage params, one per hw-controller block — what the FPGA measures per
pipeline stage: `t_lookup` 25 (Source Validation + Route Selector) ·
`t_queue` 75 (Per-Destination Queues + Scheduler, uncontended) · `t_encap`
100 (TX Encapsulator) · `roce_stream` 150/side (QP Router + RoCEv2; RX
includes the RX Decapsulator) · `t_translate` 15 (Transaction Generator:
bounds + offset→PA) · `t_forward` 10 (Local Forward Engine).

Derived route costs: **local adder 0** (D15) · source pipeline
`lookup+queue+encap` = 200 · destination `translate` = 15 (D17).
Coarse overrides `--pipe-ns`/`--pipe-local-ns` serve the sweeps.

**`t_forward` appears in no route term** (D17): the ToR's forwarding is
already inside `fabric_latency`, and the destination's egress is inside
the `fabric_latency` edge leg that dim1 already counts. Charging it again
counted it twice.

### How the simulator composes dimensions (why the legs are in dim1)

AstraSim's dimensions are **alternatives, not layers**:
`MultiDimTopology::send()` selects the single dimension a hop travels in
and prices it with that dimension's latency/BW alone — dim0 is never added
underneath a dim1 hop. So each dimension's latency must describe the
COMPLETE physical path of one hop of its type:

- a dim0 hop = the full in-rack trip, XPU→ToR→XPU (500, all systems);
- a dim1 hop = the full cross-rack trip, XPU→ToR→wire→ToR→XPU (1615 Loom,
  legs included per D11; 600 baseline, its endpoint cost now charged
  separately as occupancy rather than buried in this term — D14).

**Lumping note:** the analytical hop is one scalar — `latency + size/BW` —
and the simulator has no notion of where along the path time is spent. The
remote ToR's share is "paid at the source" only in the sense that all terms
are summed; for delivery time this is provably equivalent (addition
commutes), and both systems are lumped identically, so no comparison bias
enters. Location starts to matter only where queues form — the congestion
tier and ns-3.

**Why the number of exposed traversals matters more than any single
constant.** Because Loom and the baseline now differ in exactly two places
— dim1 latency (1615 vs 600) and endpoint occupancy (0 vs 2400/2800) —
every collective result reduces to how many cross-rack operations a
workload performs, and how many of them are exposed rather than overlapped.
Measured: exposed traversals = `2(racks-1) x preferred-dataset-splits`
when exposed at all. Hence gains grow with rack count, and a dense LLM
iteration (≈12 exposed cross-rack ops) benefits far less than an MoE one
(≈2128).

## 2. The core asymmetry (why Loom's cross-rack cost ≠ the baseline's)

**The baseline creates and submits a work request for every transfer.**

| Component | Where | Approx. share |
|---|---|---|
| WQE creation + doorbell ring | GPU kernel (B1) / CPU proxy after GPU handoff (B2) | 100s ns (B1) / µs-class incl. handoff (B2) |
| Doorbell processing + WQE fetch over PCIe | NIC | ~400–800 ns (PCIe round trip) |
| QP-context fetch/update | NIC | ~100s ns (cache-dependent) |
| Payload DMA from device memory over PCIe | NIC | ~400–800 ns first bytes |
| Packet build / ICRC / congestion state | NIC pipeline | ~100–200 ns |

**Loom performs none of this on the data path.** Connections are
established once, at binding time, by the orchestrator's connection manager;
QP context is resident in the switch; the payload is not DMA-fetched — it
streams from the fabric port through the encapsulator into the RoCE engine.
What remains per traversal is the routing pipeline (200 ns source, 15 ns
destination) and the RoCE streaming share (150 ns per side).

The two ToR traversals are **asymmetric** (D10): the source runs the full
remote pipeline; the destination runs RoCE RX + decap + the same bounds/
translate that local delivery uses — both routes converge on the
transaction generator (design §6.1).

**Accounting rule:** never add `roce_stream` on top of a `t_pipe` measured
inclusive of the stack — set it to 0 then.

## 3. Constants ledger

| Constant | Value | Includes | Excludes | Provenance | Replaced by |
|---|---|---|---|---|---|
| `endpoint-delay` | 10 ns (all) | NPU↔memory-accelerator bus cost | **anything on the network path** — it is passed to `MemBus`, NOT the network (§6.2) | AstraSim `HGX-H100-validated.json` | — |
| `endpoint-issue-overhead` | `[0,0]` Loom · `[0,2400]` B1 · `[0,2800]` B2 | per-op RDMA initiation, charged as sender-side occupancy | in-rack (dim0 = 0 for all) | §6; value bracketed 2400–6900 | **Phase C: decomposed B1 measurement** |
| `fabric_latency` | 500 ns | rack fabric hop incl. stock switch forwarding AND its table consult | — | PCIe5-switch class; alt preset HGX 936.25 validated | testbed floor |
| `t_lookup` | 25 ns* | Source Validation + Route Selector | — | ASIC-class SRAM/TCAM lookup | **⚑ T3 stage counter** |
| `t_queue` | 75 ns* | Per-Destination Queues + Scheduler, uncontended | congestion (congestion tier) | switch-design class | **⚑ T3 stage counter** |
| `t_encap` | 100 ns* | TX Encapsulator | coalescing benefit (T2 curve) | HW pipeline class | **⚑ T3 stage counter** |
| `t_translate` | 15 ns* | bounds + offset→PA | — | pipelined table read | **⚑ T3 stage counter** |
| `t_forward` | 10 ns* | Local Forward Engine egress | **charged in no route term** (D17) | HW pipeline class | **⚑ T3 stage counter** |
| `roce_stream` | 150 ns* | QP Router + RoCEv2 per side | WQE/doorbell/QP-fetch/payload-DMA | HW packet-engine class | **⚑ Coyote RoCE floor** |
| derived | local 0 · source 200 · dest 15 | sums of the above | — | D15, D17 | `--pipe-ns`/`--pipe-local-ns` |
| `wire` (`--net-latency`) | 600 ns | inter-ToR cut-through switch + propagation | endpoint anything | ToR datasheets (300–800 ns class) | — |
| goodput | **0.95, all systems** | Eth+IP+UDP+BTH ≈78 B on 4 KB MTU | sub-64 B envelope + coalescing (T2) | header arithmetic; D16 | **T2** goodput-vs-size curve |
| `peak-perf` | 989 vs 839 TFLOPS | full SMs vs 20/132 statically reserved | dynamic SM contention; memory-bound ops escape the tax (§6.6 of the SM sweep) | DeepSeek-V3 (20 of H800's 132) | swept {0,8,20,32} |
| `read-credits` | 32 | outstanding peer reads per NPU | per-binding granularity | design §6.3 | **T6** + swept |
| `--uplink-oversub` | 1.0 | ToR uplink aggregate = M NICs (equal wires) | equal-cost framing (Loom deletes M NICs — prose only) | fairness choice, D8 | not swept (D19) |

\* = ⚑ FPGA-owned: MUST be measured on the Coyote/U280 testbed, then
frequency-scaled for the ASIC argument. Everything unstarred is
published/validated. Full checklist in README → "Constants: who owns each
number".

## 4. Decisions ledger (each individually vetoable)

**Foundational**

- **D1 — folding technique**: switch behaviour as constants inside per-dim
  latency/BW, the method of AstraSim's own validated HGX config. Note the
  *technique* is validated, not our numbers: the only validated config in
  the repo is single-dimension, 8 GPUs, NVLink 400 GB/s / 936.25 ns. There
  is no validated multi-node config, and ASTRA-sim models scale-out as an
  idealized link with no endpoint cost at all.
- **D2 — route-split endpoint costs** *(user-identified)*: in-rack peer
  access is a plain store for every system; RDMA initiation exists only on
  the scale-out route. **Revised 2026-08-04**: it lives in
  `endpoint-issue-overhead[dim1]`, not in dim1 latency (D14) and not in
  `endpoint-delay`, which never reaches the network at all.
- **D3 — the ToR is the rack switch** *(user-identified)*: stock forwarding
  is already inside `fabric_latency`. **Extended by D15.**
- **D4 — composite per-traversal pipeline**: transport processing composes
  INTO the pipeline term; no separate additive NIC charge.
- **D5 — control-path vs data-path RDMA** *(user-identified)*: Loom never
  creates/submits work requests on the data path; only the streaming share
  survives per traversal.
- **D6 — SM reservation as peak-perf scaling**: production reserves SMs
  statically (DeepSeek-V3), so compute-speed scaling is faithful; applies
  to the baselines only.
- **D7 — eager = posted write; rendezvous = B2's handshake**.
- **D8 — equal-wires fairness**, with the disclosed orthogonal-dims gap
  (Loom's shared XPU edge port is not contended in this tier — favours Loom).
- **D9 — no hand-authored applications**: shipped ETs, STG published
  shapes, or captured traces only.
- **D10 — asymmetric remote traversals** *(user-identified)*: destination
  work = the delivery pipeline, not a second full `t_pipe`.
- **D11 — edge legs included** *(user-identified)*: Loom's dim1 adds one
  full fabric traversal for the XPU↔ToR legs at both ends.
- **D12 — t_pipe is source-side lookup/encap only** *(user-identified)*.
- **D13 — per-stage parameters** *(user-identified)*: one per
  hw-controller block, matching what the FPGA measures.

**Added 2026-08-04 — each changed a number, so each is recorded with what
it replaced**

- **D14 — endpoint cost is OCCUPANCY, not latency** *(user-identified)*.
  `rdma_init` moved from dim1 latency to `endpoint-issue-overhead`.
  Charged as latency it (a) pipelined away — `d(wall)/d(latency)` is
  exactly 0 for the 64 GPU/64 MB cell — and (b) was charged **twice** per
  point-to-point transfer, when an RDMA WRITE initiation is paid once, by
  the sender. Effect: 64 GPU all_reduce 1 MB went +40.48% → +8.33%.
  Full design in §6.
- **D15 — the in-rack increment is ZERO** *(user-identified)*. Was 50 ns
  (`t_lookup+t_translate+t_forward`), then 40, now 0. Loom does not add a
  translator to someone else's switch: the Loom ToR *is* the rack switch,
  and NVSwitch already performs range-indexed lookup and bounds checking
  in its datapath. **Caveat: in-rack parity is now a modelling identity,
  not a result** — do not present it as evidence; T3 supplies the
  empirical delta.
- **D16 — Loom's bulk goodput EQUALS RoCE's** *(user-identified)*. Was
  0.947 (RoCE × 4096/4108, assuming a separate 12 B header). The Coyote
  prototype sends no such header: bulk traffic is an ordinary RDMA WRITE
  and offset/op/len ride in RDMA's own BTH/RETH. Real overhead is the
  sub-64 B inline envelope, which is a size-dependent curve owned by T2.
- **D17 — `t_forward` is not double-counted** *(user-identified)*. It was
  charged in both local-route terms despite the model's own statement that
  the ToR's forwarding sits inside `fabric_latency`.
- **D18 — B3 (ideal bound) removed** *(owner decision)*. A bound, not a
  system anyone builds; "gain over an ideal bound" is negative by
  definition and made every figure harder to read. NOTE: catalog item A0
  was specified as normalized to B3 and now needs a different normalizer.
- **D19 — one physical topology, scale is the axis** *(user-identified)*.
  `[Switch, Switch]` everywhere; **8 XPUs per rack fixed** (the deployed
  scale-up domain — DGX/HGX, NVIDIA EOS is 576 nodes × 8); rack count is
  the axis. A `ring_tor` row and a `thin_uplinks` row were deleted as
  unrepresentative, and oversubscription is not swept: handicapping only
  Loom breaks equal-wires, and under equal *cost* the argument runs the
  other way since Loom deletes M NICs per rack.

## 5. Open items for inspection

1. **`endpoint-issue-overhead` value is bracketed, not measured**: 2400 ns
   (literature, isolates initiation) to ~6900 ns (upper bound — an
   end-to-end NVSHMEM put with only our assumed wire removed, so it also
   absorbs their wire and NVSHMEM library overhead). Published anchors:
   IBGDA inter-node scalar put ~7.5 µs one-way and intra-node 1.3–2.2 µs
   (arXiv:2606.05951); NVSHMEM small-message 11.5–13.8 µs
   (arXiv:2604.22126); DeepEP low-latency dispatch 77 µs @EP8 → 194 µs
   @EP256. Note even the *intra-node* figure exceeds the 1015 ns
   break-even, so the placeholder errs against Loom.
2. **Phase C must measure COMPONENTS, not one end-to-end number** —
   doorbell, WQE fetch over PCIe, NIC processing, HBM payload fetch, wire,
   remote delivery. Loom's side is a constructed sum; comparing it against
   a measured whole is apples-to-oranges, and an end-to-end put latency
   already contains the wire that the model adds separately.
3. `roce_stream = 150 ns` is the least-anchored placeholder; the Coyote
   RoCE floor replaces it.
4. Coalescing is deliberately absent (favours baselines) until T2's curve
   exists — the small-message regime where Loom should shine is
   *understated* in all current results.
5. **The SM model under-states its own tax**: `perf` is a `min()`, so only
   compute-bound nodes are derated and memory-bound ops escape. Measured
   compute gain is +13.2/+14.1% against the ideal 20/132 = 15.15%;
   derating `local-mem-bw` by the same factor recovers exactly 15.15%.
6. `fabric_latency` 500 ns / 64 GB/s models a PCIe5-class rack fabric,
   **not** the 400 GB/s NVLink of a real HGX node. Equal-wires fairness
   justifies giving both systems the same substrate, but the baseline is
   then not a real DGX cluster — and since the dim0/dim1 balance drives
   every overlap threshold, this deserves a hard look.

## 6. Endpoint issue overhead (design)

### 6.1 The problem

The baseline's per-operation RDMA initiation cost was folded into dim1
`latency`. That is the wrong *kind* of quantity, in two measurable ways.

**It is occupancy, not latency.** A doorbell write, a WQE fetch across
PCIe and NIC command processing occupy the issuing path: the next
operation cannot start until they finish. Link latency pipelines instead.
In the analytical backend `latency` is overlappable and `bandwidth` is the
serializing resource, measured directly:

| representation of the same 2400 ns | 64 GPU all_reduce 1 MB |
|---|---|
| dim1 `latency` | Loom +40.48% |
| effective-`bandwidth` derating | Loom −0.64% |

A 41-point swing from placement alone — larger than the uncertainty in the
constant. And `d(wall)/d(latency)` is exactly **0** for the 64 GPU/64 MB
cell: charged as latency, the cost can vanish entirely.

**It was charged twice per point-to-point transfer.** On p2p cross-rack
4 KB × 8 the latency representation adds `16 × 2400` over the wire-only
baseline — twice per transfer, send leg and recv leg. An RDMA WRITE
initiation is paid once, by the sender. Loom's dim1 latency was doubled
identically, so *gain percentages* survived while both systems' absolute
times were inflated ~2×.

Neither field can express a fixed per-message cost across sizes:
`latency` has the right magnitude but overlaps away; `bandwidth`
serializes but is a rate, needing recalibration per size (96% derate at
1 MB, 28% at 64 MB, for the same 2400 ns). The backend is missing a degree
of freedom, not a calibration.

### 6.2 Why not something else

- **`endpoint-delay`** looks right and is not: it maps to
  `communication_delay` and is passed to `MemBus`, the NPU↔memory-
  accelerator bus, never to the network. Proven empirically — B3 with
  `endpoint-delay: 1` and B1 with `10` gave byte-identical p2p results.
- **LogGP `L/o/g/G`** are parsed by `Sys` — `o` is literally "per-message
  overhead" — and also go to `MemBus`.
- **ns-3 backend** models the wire, not the host: `rdma-hw` exposes only
  congestion-control and link-layer knobs (`CcMode`/DCQCN, `Mtu`, PFC,
  rate control). Grepping its RDMA path for doorbell/WQE/post_send returns
  nothing; `AddQueuePair` starts sending immediately. It would also force
  the scale-up fabric to be modelled as Ethernet — it has no NVLink or
  PCIe link model — and one backend serves the whole network.
- **Garnet** is absent from this checkout (the build script references a
  missing submodule) and is an on-chip NoC model regardless.
- **SST/Ember, LogGOPSim, SimGrid** do model endpoint overhead as
  first-class LogGP `o`, but adopting one means abandoning Chakra ETs, STG
  workloads, the harness and the 512-GPU scale sweep.

### 6.3 Mechanism

`Sys::sim_send(Tick delay, ...)` already defers injection when
`delay != 0`, plumbed through every send path with every caller passing 0:

```cpp
if (delay == 0)  comm_NI->sim_send(...);                  // immediate
else             try_register_event(new SimSendCaller(...), ..., delay);
```

Deferring injection puts the cost on the **issuing stream's** critical path
while concurrent streams (`active-chunks-per-dimension`) still overlap —
*partially pipelined*, which is how GPU-initiated RDMA behaves, and which
sits between the latency and bandwidth extremes rather than at either.

### 6.4 Interface

```json
"endpoint-issue-overhead": [0, 2400]
```

Per-dimension array. dim0 is always 0 — an in-rack peer access is a plain
store for every system. Absent key == all zeros, so the hook is inert
unless configured. Consequence: baseline dim1 latency is now the **wire
only** (600 ns); `--rdma-init-ns` survives with default 0 purely so the old
representation can be reproduced for the bracket.

### 6.5 Implementation note

The dimension is derived from **src/dst coordinates**, not
`request->vnet`. The point-to-point path (`Workload.cc:405`) builds a
`sim_request` with `srcRank`/`dstRank`/`reqType` and never sets `vnet`, so
reading it there is undefined behaviour — the first version of this patch
had that bug and silently charged nothing on the p2p path.

```
for each dim d:  if (src % dims[d]) != (dst % dims[d])  crossed = d
                 src /= dims[d];  dst /= dims[d]
```

### 6.6 Validation gates

1. **Null**: key absent == `[0,0]` == prior `rdma_init=0`. PASSES (57,195
   three ways) — the hook is inert when unset.
2. **In-rack**: unaffected, dim0 charged 0. PASSES (8,472 both).
3. **Collective divergence**: representations must differ. PASSES
   (64 GPU 1 MB: 191,595 latency vs 124,395 overhead).
4. **Single-message equivalence**: deliberately NOT expected to hold — the
   latency representation double-charges p2p (§6.1). The overhead
   representation charges once, which is correct.
5. **Hiding**: at 64 GPU/64 MB the overhead is absorbed exactly as the
   latency was (909,088 at overhead 0, 2400, 4800). Same conclusion under
   both representations, so **that tie is structural — a dim0-bound cell —
   not an artifact of the representation.**

### 6.7 What this does not fix

The *value* is still unmeasured (§5.1). This change fixes **where** the
cost is charged and **how it composes**, not what it is.
