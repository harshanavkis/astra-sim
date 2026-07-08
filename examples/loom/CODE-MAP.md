# Loom simulation code map (running summary)

> **Keep this updated with every commit that adds/changes code.** For each
> artifact: what was written, and how it corresponds to the real Loom system
> (the paper's design; eventually the Coyote/U280 prototype and an ASIC ToR).
> Last updated: 2026-07-08 (D10 asymmetric remote traversals; see ANALYTICAL-MODEL.md).

## 1. Simulator extensions (C++)

### 1.1 Congestion-aware backend — switch egress policy
**Where:** fork `harshanavkis/astra-network-analytical`, branch `loom-sim`
(`Link.{h,cpp}`, `Device.{h,cpp}`, `Topology.{h,cpp}`, `Helper.cpp`,
`NetworkParser.{h,cpp}`).

**What was written:** `Link::is_busy()` + a becomes-free callback;
`Device` gained `EgressPolicy {PerDestination, SharedFifo}`, a shared
egress FIFO, and a `pump_shared_queue()` that dispatches in FIFO order but
stops at the first chunk whose egress link is busy; `Topology::
set_switch_egress_policy()` applies it to all non-NPU devices; new optional
network-YAML key `switch_egress: shared_fifo`.

**Real-system correspondence:** the stock model (each egress link has its
own private queue) *is* the Loom ToR's **per-destination transmit queues**
(design §6.4, VOQ): a congested destination grows only its own queue. The
new `SharedFifo` mode is the **strawman** — a shared-buffer switch whose
head-of-line chunk blocks everything behind it, i.e., what the rack fabric's
link-level credit backpressure would do without VOQs. The victim experiment
toggles exactly the design's claim: isolation is a property of the egress
discipline, nothing else (verified: victim FCT identical to solo under VOQ;
3.2× inflated under SharedFifo).

**Limitation:** backend is 1-dim only, so the ToR under test is modeled as
a flat switch — this isolates the egress mechanism but cannot show
uplink-level congestion (2-dim support would be the extension).

### 1.2 Remote-memory backend — credit-capped peer reads
**Where:** fork `harshanavkis/astra-memory-analytical`, branch `loom-sim`
(`AnalyticalRemoteMemory.{hh,cc}`).

**What was written:** new `LOOM_PEER_READS` memory type: per-NPU credit
budget (`read-credits` JSON field); `issue()` consumes a credit and
schedules completion after `remote-mem-latency + size/bw`, or queues the
request when credits are exhausted; the completion callback hands the freed
credit to the next queued read.

**Real-system correspondence:** the switch's **read credit tracker**
(design §6.3): a peer read is non-posted; issuing one consumes a credit and
enqueues the pending fabric transaction; the returning response releases
it; exhausted credits make further reads *wait* — the fabric never stalls.
`remote-mem-latency` plays the read RTT (rack or cross-rack + 2·t_pipe).
Granularity note: per-NPU here vs per-binding in the design — equivalent
when an NPU's reads target one binding, an approximation otherwise.
Verified arithmetically: 64 independent 4 KB loads complete in exactly
1×/8×/64× concurrency at credits 1/8/64.

### 1.3 Workload layer — memory ops hold no issue slot
**Where:** main fork, `astra-sim/workload/HardwareResource.cc`.

**What was written:** `MEM_LOAD_NODE`/`MEM_STORE_NODE` return early from
`occupy()/release()/is_available()` instead of taking the single in-flight
GPU-op slot.

**Real-system correspondence:** a GPU issues loads from thousands of lanes
(deep memory-level parallelism); the real limit on outstanding peer reads
is the **fabric credit budget** (1.2), not issue serialization. Without
this, the credit cap could never bind.

## 2. Network model (config generation, no simulator changes)

**Where:** `examples/loom/gen_network_config.py` + generated
`network/*.yml`.

**What was written:** emits 2-dim `[Switch, Switch]` YAMLs
(dim0 = rack fabric through the ToR, dim1 = inter-ToR Ethernet) for three
modes, folding constants into the per-dimension `latency`/`bandwidth`
fields — the same technique as AstraSim's validated `HGX-H100-validated.yml`
(whose 936.25 ns includes NVSwitch traversal).

**Real-system correspondence, term by term:**

| Config term | Physical thing |
|---|---|
| dim0 latency = fabric + `t_pipe_local` (50 ns*) | in-rack peer store: the Loom ToR IS the rack switch (stock forwarding is inside fabric latency); Loom adds only binding lookup + bounds check (design §6.1 "adds only table lookups") |
| dim1 latency = wire (600) + (`t_pipe` 500* + `roce_stream` 150) at the source + (`roce_stream` 150 + `t_pipe_local` 50*) at the destination = 1450 ns | cross-rack peer store: source = lookup/validate + encap + RoCE TX; destination = RoCE RX + decap + the same check/translate/forward as local delivery (routes converge on the transaction generator, §6.1) — no separate RDMA initiation exists in Loom (D5), and the destination is NOT a second full pipeline (D10). T3 measures the end-to-end sum; zero roce_stream if t_pipe measured inclusive |
| dim1 bandwidth × 0.947 | RoCE goodput 0.95 (header math) × 4096/4108 (12 B ⟨offset·op·len⟩ Loom header) |
| baseline dim1 latency = wire + `rdma-init` (B1 2400 ns, B2 2800 ns) | per-RDMA-op initiation, paid once per rack crossing; ≈3 µs end-to-end GPU-initiated put (IBGDA/NVSHMEM), resp. ib_write_lat + NCCL proxy handoff |
| baseline dim0 = fabric only | an in-rack baseline peer access is a plain store too — route-split, user-identified fix |
| `--uplink-oversub` | Loom ToR uplink aggregate vs the baseline's M per-GPU NICs (equal-wires default) |
| `--dim1-topology Switch\|Ring\|FullyConnected` | inter-ToR fabric shape |

\* = testbed-owned placeholder (T3), swept; everything else is
published/validated (provenance table in README).

**Known gap (disclosed):** orthogonal dims let Loom's cross-rack traffic
bypass dim0 capacity — matches the baseline's separate NIC, flatters Loom's
single shared fabric port. Congestion-tier item.

## 3. Endpoint models (system JSONs, no simulator changes)

**Where:** `examples/loom/system/*.json`.

**What was written:** per-system configs differing only in existing knobs:
`endpoint-delay` = 10 ns for ALL systems (the route-invariant store-issue
cost, value from AstraSim's validated HGX config); B2 additionally runs
with `--rendezvous-protocol=true`; `*_roofline.json` variants set
`roofline-enabled` + `peak-perf` 989 (Loom, full SMs) vs 839 TFLOPS
(B1: 20/132 SMs statically reserved for communication, DeepSeek-V3).

**Real-system correspondence:** eager mode = **posted-write source-local
completion** (design §6.2) — AstraSim's eager sender completes at injection,
which is exactly a posted store accepted by the switch. Rendezvous mode =
the RDMA large-message handshake (B2). The peak-perf split is the **SM
reclamation** claim: production reserves SMs statically, so scaling compute
speed (not trace durations) is the faithful model.

## 4. Workload tooling (Python; no hand-authored applications)

| File | What it is | Corresponds to |
|---|---|---|
| `fetch_stg.sh`, `gen_stg_workloads.sh` | pins STG (astra-sim's generator) and wraps `moe`/`dense` presets with **published dims** (Mixtral 8x7B, GPT-3 175B); rank count = dp·tp·pp·ep | application workloads (W-A/W-B in the eval plan); dims never invented |
| `workload/gen_p2p_patterns.py` | single/incast/victim flow stimulus (per-role sizes, unique tags, matching recvs; idle ranks get a 1 µs COMP — the feeder rejects empty traces) | iperf-category mechanism stimulus; the victim pattern is testbed T5's twin |
| `workload/gen_read_pattern.py` | N independent MEM_LOADs per rank | read-credit experiments (testbed T6 twin) |

## 5. Experiment harness

| Script | Stresses (design §) | Current result (anchored constants) |
|---|---|---|
| `run_smoke.sh` | endpoint models on shipped ETs | sanity ordering; comm-only so no SM term |
| `run_victim.sh` | §6.4 VOQ isolation | solo = VOQ (77,024 = 77,024), SharedFifo 3.2× |
| `run_sweep_credits.sh` | §6.3 read credits | exact linear concurrency scaling |
| `run_sweep_tpipe.sh` | §6.1 switch cost (break-even) | break-even ≈ 1.6 µs; 500 ns placeholder wins |
| `run_regime_map.sh` | §2 #4 SM reclamation vs comm-boundedness | gain → SM ceiling (~15%) compute-bound; parity comm-bound |
| `run_matrix.sh` | patterns × topologies × systems | nearly all Loom-positive; 6 marginal cells ≤ −1.1% (large-size, header tax) |
| `run_apps.sh` | end-to-end applications | Mixtral +6.0%/+8.5%, GPT-3 +4.9%/+5.0% vs B1 |
| `run_all.sh`, `run_all_docker.sh`, `plot_results.py` | artifact: one command → CSVs + PDFs | — |

## 6. Deliberately NOT in the simulation

Address translation correctness, isolation checks, ordering, revocation —
correctness properties, demonstrated on the testbed, present here only as
constants inside t_pipe. Failure containment is (planned) an event, not a
protocol. QP/connection state is counted analytically, never simulated.
