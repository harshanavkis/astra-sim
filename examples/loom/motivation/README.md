# Loom motivation experiments — the record

> Purpose: fill every red `\tbd{}` in the paper's §1–§2 with defensible
> evidence, and (same sessions) measure the two endpoint constants the
> evaluation needs. Written to be picked up cold: each experiment states
> claim → method → hardware → deliverable. Methodology model:
> ACE (Rashidi et al., ISCA'21, `~/loom-paper/ace_isca2021.pdf`) — real
> contention measurements + simulation, same ASTRA-sim lineage.

## 0. Evidence policy (decided 2026-08-03)

- **Evaluation constants** (anything that drives a result figure, e.g.
  `rdma_init`): measured, or literature-derived AND swept. Never bare.
- **Motivation evidence**: measured where we can measure cheaply; *cited*
  where the source is a production system's own disclosure (citing
  DeepSeek-V3's 20-SM reservation is stronger than any microbenchmark we
  could run — it is their engineering decision, not our estimate).
- Analyzing raw public data ourselves (MLCommons traces) counts as our
  own measurement, not a citation.

## 1. Claims to substantiate (the `\tbd{}` map)

| # | Claim (paper location) | Evidence source (tier) |
|---|---|---|
| C1 | Scale-up vs scale-out backends: X/Y kLoC, Z% shared (§1, §2#2) | T0-a LoC analysis |
| C2 | Accelerator-side path manages X transport-state objects in Y kLoC (§2#3) | T0-a (device-code half) |
| C3 | Communication occupies X% SM cycles, Y% memory BW (§1, §2#4) | T3-d Nsight (real GPU); interim: T0-b trace analysis |
| C4 | Who-moves-the-bytes: processor-driven data movement steals compute; offloaded transport doesn't (§2#4 narrative) | T1-a CPU demo; T3-a/b GPU version (headline) |
| C5 | 20-of-132 SMs reserved for comm; call for unified adapter (§1, §2#4) | **cited**: DeepSeek-V3 report (policy §0) |
| K1 | `rdma_init_B2` (CPU-proxy per-op cost) — evaluation constant | T1-b / T2-c perftest |
| K2 | `rdma_init_B1` (GPU-initiated per-op cost) — evaluation constant | T2-d IBGDA loopback if NIC exists; else literature + sweep (sanctioned fallback) |

## 2. Experiment tiers (pick by available hardware)

### T0 — no hardware (do first, this week)

**T0-a. NCCL backend LoC split (C1, C2).**
Clone NCCL (pin the version). Classify `src/transport/*` into
scale-up (p2p, shm) vs scale-out (net_ib, net_socket, proxy) vs shared;
`cloc` per class; count distinct transport-state object types touched by
device code (queue pairs, doorbells, keys, completion structures) for C2.
Repeat coarsely for NVSHMEM/DeepEP device paths. Deliverable: one table,
replaces four `\tbd{}`s. Jigsaw §7.7 is the presentation template.

**T0-b. MLCommons trace analysis (interim C3).**
From the Chakra Open Trace Library captures (join the WG for Drive
access — lead time, start now): parse per-kernel timings; report the
fraction of GPU time in `ncclDevKernel*` and the comm/compute overlap
structure, per model (DeepSeek-MoE, dense). Our own analysis of raw
data. Superseded by T3-d if the GCP session runs.

### T1 — CPU + NIC we already own (testbed hosts)

**T1-a. Who-moves-the-bytes, CPU edition (C4 principle).**
dgemm across N cores, concurrent with the same byte stream moved
(a) by CPU threads (memcpy/TCP) vs (b) by NIC RDMA offload.
Compute-throughput loss in (a) but not (b) = the architectural claim on
hardware we own. Coherent with the prototype's CPU-thread-as-XPU
fidelity argument; doubles as a testbed substrate baseline.

**T1-b. `rdma_init_B2` (K1).** `perftest` (ib_write_lat/bw) host-memory
loopback on our NIC; small-message ops/sec → per-op post+doorbell+poll
cost. The posting overhead is host-side by definition; GPU memory not
required.

### T2 — one GPU + one RDMA NIC, loopback (if/when that box exists)

**T2-a. Three-way who-moves-the-bytes (C4 headline without a cluster).**
Same GEMM loop concurrent with the same byte stream moved by:
(a) custom SM copy kernel (NCCL-class data path; label it exactly that,
never "NCCL" — NCCL needs ≥2 devices), (b) copy-engine
`cudaMemcpyAsync` (zero SMs), (c) NIC loopback RDMA via GPUDirect
(zero SMs, real network path). GEMM slowdown across a/b/c measures the
SM tax and its removal; the b/c residual isolates the memory-BW
component.

**T2-b. CTAs-vs-bandwidth curve.** Sweep the SM copy kernel's CTA count
vs achieved bandwidth: SMs needed to move bytes at X GB/s on our
silicon (grounds the SM-reservation parameter).

**T2-c. K1 with GPU memory**: `perftest --use_cuda` loopback.

**T2-d. K2, IBGDA loopback (best-effort).** NVSHMEM 2 PEs on 1 GPU
under MPS, `NVSHMEM_IB_ENABLE_IBGDA=1` + **`NVSHMEM_DISABLE_P2P=1`**
(without it NVSHMEM short-circuits same-GPU puts to an on-GPU copy and
never touches the NIC). **Verify with HCA counters** (`port_xmit_data`
must grow with puts) before trusting any number. Differential trick:
CPU-posted (T2-c) and GPU-posted (T2-d) share the identical loopback
path, so their latency delta isolates the B1-vs-B2 initiation
difference. Loopback doubles PCIe traffic on the GPU link — fine for
small-message latency (all K2 needs), never for bandwidth curves.
Fallbacks: hand-rolled loopback RC QP with kernel-built WQE + doorbell
(~200 LoC ibverbs); DOCA GPUNetIO samples (CX-6 Dx+). If all fail:
literature + sweep.

### T3 — Google Cloud session (€250 credits — **CONDITIONAL, decided 2026-08-03: hold in reserve**)

T0-b covers the motivation: % of GPU **execution time** in comm kernels
(word the claim as time, not "SM cycles" — traces hold durations, not
counters), from real production captures, paired with the cited DeepSeek
reservation. What traces can't give is **causality** (no control
condition in a recording: comm kernels ran X ms, but what did they cost
the overlapped compute?). T3 exists for exactly that. **Run T3 only if
one of these triggers fires:** (a) the trace library lacks a usable MoE
capture; (b) drafting/reviewing exposes the missing-causality gap as
load-bearing; (c) we decide the copy-engine-vs-NCCL contrast is worth
having as the motivation's centerpiece figure. Otherwise the credits
stay unspent. Note the sim needs no T3 either: B1's SM model mimics a
static reservation — a documented production POLICY (cited + swept is
the faithful treatment), not a physical constant.

If triggered: machine = one **a2-highgpu-2g or -4g (2–4×A100, NVLink),
Spot**. Explicitly NOT: a3/H100-with-CX7 instances (≈€80+/h — the budget
dies in 3 hours; K2 is not worth it, the loopback/fallback path covers
it).

- **T3-a. NCCL contention matrix (C4).** Async NCCL all-to-all +
  all-reduce (1–256 MB) overlapped with GEMM at MoE shapes; solo vs
  overlapped, both directions, CUDA events. (ACE Fig 4a analog.)
- **T3-b. Copy-engine vs NCCL contrast (C4 headline).** Same bytes via
  NCCL kernels vs `cudaMemcpyPeerAsync`; GEMM-slowdown delta = directly
  measured SM reclamation on real hardware.
- **T3-c. SMs-to-drive-fabric (grounds SM-reservation k).** nccl-tests
  busbw × `NCCL_MAX_NCHANNELS` ∈ {1,2,4,8,16}; confirm grid sizes with
  Nsight. (ACE Fig 6 analog.)
- **T3-d. Overlap toggle + profile (C3).** Small MoE fwd+bwd loop
  (Mixtral-class layer in plain PyTorch), natural overlap vs
  forced-sequential; Nsight Systems on the overlapped run → % GPU time
  in `ncclDevKernel*`, occupancy, memory BW. (ACE Fig 4b analog.)

Payoff beyond motivation: T3-a/b slowdown factors replace the global
roofline (989 vs 839) with a measured while-comm-in-flight contention
model for the B1 endpoint in the simulator.

## 3. GCP budget discipline (hard rules — the credits drain in hours if ignored)

1. **Zero interactive debugging on A100s.** Scripts are developed and
   fully green on Kaggle's free 2×T4 (or the cheapest 2×L4/2×T4 Spot VM,
   ≤€10 total) first. The A100 machine only ever runs a finished,
   unattended pipeline.
2. **Spot instances only**; the pipeline checkpoints per-experiment CSVs
   to a GCS bucket as it goes, so preemption costs a rerun of one
   experiment, not the session.
3. **Self-terminating**: the startup script runs everything, copies
   results out, then `poweroff`; create with
   `--instance-termination-action=DELETE`. Never an idle instance.
4. **Billing budget alerts** at €50/€125/€200 before the first launch.
5. Cost envelope (verify current prices; A100 Spot ≈ €1–1.5/GPU/h):
   debug tier ≤€10; one 2×A100 Spot measurement session ≈ 5 h ≈ €15;
   one 4×A100 repeat ≈ €30; two full repetitions for repeatability +
   on-demand fallback buffer — total plan ≤€120, leaving ≥€130 reserve.
6. Everything (scripts, images, exact commands, prices observed) gets
   committed here so the session is reproducible.

## 4. Citations the motivation will carry (policy §0 — evidence, not constants)

| Citation | Role |
|---|---|
| DeepSeek-V3 tech report (arXiv:2412.19437) | 20/132 SMs reserved; the "unified adapter" call (C5) |
| DeepEP (repo/report) | dual NVLink/RDMA paths + IBGDA state in kernels — the divide as engineering practice; B1's concrete instantiation |
| NCCL 2.28 Device API docs | LSA vs GIN split — the divide institutionalized in the API surface |
| UALink 1.0, Broadcom SUE (OCP), UB-Mesh (arXiv:2503.20377) | landscape: pod-boundary / endpoint-framework / clean-slate |
| ACE (ISCA'21) | contention-measurement methodology precedent; endpoint-offload ancestor (distinguish: Table II's endpoint-vs-switch dichotomy is about in-network *aggregation*; Loom's switch runs no algorithm) |
| IBGDA/NVSHMEM microbench publications; Kalia et al. (ATC'16) | provenance of `rdma_init` constants when the measured path fails (always swept then) |
| Mixtral (arXiv:2401.04088), GPT-3 (NeurIPS'20) | workload dims provenance |

## 5. Deliverables → where they land

- C1/C2 table → §1 + §2#2/#3 `\tbd{}`s (T0-a).
- C3 percentages → §1 + §2#4 (T3-d; interim T0-b).
- C4 figure (who-moves-the-bytes bars) → §2#4, arguably the motivation's
  money figure (T3-b, else T2-a, else T1-a).
- K1/K2 → `system/*.json` + `ANALYTICAL-MODEL.md` constants table;
  rerun apps/matrix/MoE-block after substitution.
- SMs-vs-bandwidth curve → grounds/sweeps the SM-reservation parameter.
