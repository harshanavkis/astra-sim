# E8 simulation model: running record

What the at-scale simulation models, why, how it was validated, and how it changed. Use it for the
paper's methodology and validation text. How to run things (scripts, config keys) is in README.md.

Maintenance: every change to the model (mechanism, parameters, cluster, workloads, bugs that change
results) gets a dated entry in the change log (section 6), and sections 1-5 are updated to match.
Every number says whether it is **measured** (hardware), **model** (simulator output) or
**computed** (arithmetic on either).

## 1. Current model (2026-10-11)

### 1.1 Stack
- ASTRA-sim 2.x (fresh clone `astra-sim-fresh`, upstream 4ce9ecfe, local branch `loom`, HEAD a69e163)
  with its ns-3 backend (ns-3.42, HPCC-lineage `RdmaHw` RoCE model; submodule branch `loom`, HEAD
  fc5126a64). Local commits only, never pushed.
- Workloads: Chakra execution traces. Training = MLCommons Chakra WG traces with measured H200
  compute durations (Llama-3 70B on 16 GPUs, TP16 over 2 servers; Mixtral 8x22B on 32 GPUs,
  TP4 x EP8). MoE dispatch/combine and collectives = generated traces (tools/gen_moe.py,
  tools/gen_coll.py). End-to-end training also on STAGE-generated traces (github.com/astra-sim/stage, arXiv
  2511.10480; run_stage.sh): Llama-3 8B / 70B (TP8 in a server, DP and PP across) and Mixtral 8x7B / 8x22B
  (TP4 x EP8, PP4 at 128 GPUs) at 32 and 128 GPUs, layers cut to 4 (n32) / 8 (n128) for ns-3 run time, seq
  4096, bf16, compute from an H200 roofline (989 TFLOPS, 4.8 TB/s; e8/cfg/system_nccl_roofline.json);
  tools/remap_ranks.py puts TP innermost so TP stays inside a server.
- Traffic inside a server (NVLink) bypasses ns-3 and is modelled by its BANDWIDTH ONLY (since 2026-10-20): a
  message takes size / 400 GB/s and arrives 936.25 ns later (ASTRA-sim's HGX-H100-validated values), independent of
  other messages: no port, no queue (as ASTRA-sim's congestion-unaware analytical backend). Identical for RDMA and Loom;
  only traffic between servers goes through ns-3 and the host-interface model. (Before: a per-GPU NVLink port
  reserved message by message in issue order, a loom-branch addition; see section 6, 2026-10-20.)

### 1.2 Cluster (owner-approved 2026-10-10)
- 8 GPUs per server; one 400G NIC (RDMA) or one Loom per GPU, on PCIe Gen5 x16.
- One switch up to 32 GPUs (n16, n32); above that leaf-spine with full bisection, 32 GPUs per leaf
  (n64: 34 switches, n128: 36, n256: 40).
- Link delays carry cable + switch: host links 155 ns, fabric links 305 ns (~300 ns per switch).
- RoCEv2, MTU 4096, 82 B per packet on the wire (preamble/IFG 20, Ethernet+FCS 18, IP 20, UDP 8,
  BTH 12, ICRC 4) -> 4178 B frames.
- Lossless: PFC with dynamic thresholds, 32 MB switch buffer, headroom per port =
  rate x link delay x 3 + 2 frames (section 6, 2026-10-10 17:00). No congestion control
  (`CC_MODE 12`); go-back-N on loss; an ACK per packet.

### 1.3 RDMA baseline: GPU-initiated RDMA NIC (`HOST_IF_MODE nic`)
Mechanism (ns-3 rdma-hw.cc "nic mode", pcie-fabric.{h,cc}):
- Persistent QPs, one per GPU pair. The GPU writes WQEs into the send queue and rings a doorbell
  per put (8 B MMIO write over PCIe).
- The NIC fetches the WQEs it was rung for (one fetch per QP at a time, all rung WQEs per read: no limit since
  2026-10-26, WQE_FETCH_MAX 1e9 in every config; was 64, an unsourced default; e8_an/wqf/RESULTS.txt: identical from 16 up),
  then reads each payload from GPU memory in MRRS pieces, round robin over its QPs, with a bounded
  number of read bytes outstanding. A packet leaves once its bytes are in the NIC and never crosses
  a WQE's end.
- The receiving NIC writes the data into GPU memory over PCIe. An RDMA atomic is a read + write
  (the H200 is no PCIe AtomicOp completer; the CX-7 reports ATOMIC_HCA).
- A CQE per WQE is written back over PCIe once the WQE is acknowledged.
- PCIe: every transaction takes a measured latency plus its bytes on the source's outgoing and the
  destination's incoming link (one FIFO per direction, 57.6 GB/s payload rate). Not TLP-level.

### 1.4 Loom: ideal push (`NIC_PUSH 1`)
- The GPU's stores carry the data: posted PCIe writes into Loom's window. No WQE, doorbell,
  payload read or CQE. The stores cross PCIe in HIF_CHUNK (4 KiB) pieces and Loom has each piece as it
  lands (it forwards per packet, E3); before 2026-10-11 09:15 a whole message crossed as one transaction
  (store-and-forward, an artifact; section 6).
- Loom adds its pipeline: 21 cycles on the send side, 7 on the receive side (RTL), at 1 GHz
  (ASIC) or 250 MHz (FPGA bound).
- Same network, transport, switches and receive-side writes as RDMA.
- Ideal: Loom accepts every store at once; there is no window and no back-pressure on the GPU.
  At large sizes the Loom sender is therefore bound by its PCIe link (57.6 GB/s), not the wire.

### 1.5 Library semantics and metrics (owner decisions 2026-10-10)
- A message between servers = ordered puts (`MSG_SPLIT_BYTES` each; MoE: one put per token) on the
  pair's QP, a doorbell per put, then an 8 B signal write behind the data.
- The receiver has the message when it sees the signal.
- The sender is released when it may reuse its buffer: RDMA at the signal's CQE, Loom when its
  stores have left the GPU.
- Metrics, always labelled: **sender busy** (until the arrival signal is issued; Section 2/Fig 3's
  metric) and **delivered** (receiver sees the signal); training traces: iteration time and exposed
  communication per rank.
- ASTRA-sim keeps one communication op in flight per GPU (HardwareResource.cc), so a sender's
  release gates its next op. MoE runs set `ASTRA_CONCURRENT_SENDS=1` (a GPU's sends to different
  peers go out together, interleaved put by put); training traces leave it unset.

### 1.6 Parameters and sources
All from single-message **measurements** on steve (H200 + CX-7, MTU 4096), file
e8/cfg/steve_nic/base.txt; none is fitted to the dispatch/combine runs used for validation.

| parameter | value | source |
|---|---|---|
| NIC read of GPU / host memory (issue -> data) | 1350 / 670 ns | nic_post, measured |
| NIC receive pipeline (`NIC_RX_NS`) | 590 ns | nic_post inline post->CQE 2.02 us minus perftest 8 B one-way 1.42 us (computed) |
| NIC transmit pipeline (`NIC_TX_NS`) | 260 ns | steve single-message measurements |
| host one-way (doorbell / write) | 280 ns | measured |
| GPU doorbell + NIC write visible to a polling SM | 645 + 645 ns | split of 1290 ns; DeepEP single put 5.45 us, measured |
| PCIe payload rate per direction | 57.6 GB/s | Gen5 x16 x 256/280 (computed) |
| WQE size, WQEs per fetch, PCIe max read request | 64 B, no limit (was 64 until 2026-10-26), 4096 B | model settings |
| RDMA staging copy (`STAGE_COPY <GB/s> <chunk>`) | bytes at 2400 GB/s, 512 KiB pieces, no fixed latency (350 ns until 2026-10-26: a 7 KiB token's measured copy, charged as fixed on top of the bytes) | H200 HBM spec 4.8 TB/s / 2 |
| Loom pipeline | 21 / 7 cycles | Loom RTL |
| switch + cable per hop | ~300 ns | owner-approved cluster |

### 1.7 Deliberately not modelled (owner decisions; say so in the paper)
- GPU-side posting cost: zero for both systems ("why model it, we can't do it correctly"). The
  post-chain SM cost stays a Section 2 measurement.
- PCIe at TLP level ("do we really need this?"): per-transaction measured latency + FIFOs instead.
- Congestion control (DCQCN for both: later sensitivity).
- Loom's window / back-pressure (cannot be measured at scale on hardware; later).
- Switch-delay sweep (later).

## 2. Validation (what the paper can claim)

| check | comparison | result |
|---|---|---|
| single-message inputs (8) | model vs measured, steve | within 1% |
| DeepEP 7168 B put -> CQE | model vs measured (prediction) | 5.68 vs 6.13 us (-7.3%) |
| Section 2 dispatch/combine, receiver sees every signal | LoomReplay of measured runs (GPU side = measured posts and doorbells) vs measured; ordered and flush, 1/16/128 tokens, 20 runs per point, medians | +0.9..-7.8%; 16 and 128 tokens within +-1.4% |
| same, last arrival / reap | as above | -0.2..-8.7% / -0.5..-7.7% |
| error direction | | every error is RDMA-favourable (model faster than measured) |
| ASTRA-sim frontend vs replay tool | model vs model, 8 B..4.9 MB, RDMA and Loom | identical to the ns |
| Loom side vs E4 prototype, sender busy | model vs measured (tests/run_val_e4.sh, val_e4/20261010_1144_dispatch_v80; fixed push path, 2026-10-11 09:36) | -0.2..+1.9% (dispatch 1/128 tok), +0.8..+5.5% (combine 1/128); +9.1/+14.3% at 16 tok (the prototype's buffers absorb the burst) |
| Loom side vs E4 prototype, delivered | same | -1.0..-0.3% at 16/128 tok; **-51% (dispatch) / -60% (combine) at 1 token** (prototype 10-20 us slower, ~1 us per 4 KiB touched at the receiver; open). Before the push-path fix: -0.6..+0.1% and -50/-57% |

E4 replay inputs (e8/cfg/testbed_e4/push.txt): PCIe/store rate 10.7 GB/s = E1 Loom program puts (2026-10-07), one fixed
latency fitted to the 0-token flag (5.10 us one way, put into the two 100G link delays: 2.486 us each), Loom 21/7 cycles at
250 MHz, WQE_BYTES 0, everything posted at time 0. Figure: ~/loom-paper/plots/eval-validation.pdf.

Weakest point: 1 token (-6..-12% on last arrival): measured arrivals spread ~2 us over the QPs, the
model 0.6 us. Doorbell times must be measured inputs: DeepEP's flush CTAs wait 2-10 us on its
per-QP post lock (rule-based doorbells gave -18..-41% at 1 token).

## 3. Results under the current model

| result | file | status |
|---|---|---|
| zero-GPU-cost dispatch/combine, RDMA vs ideal Loom | val_dispatch/zero_gpu/compare.tsv | valid |
| MoE dispatch/combine at scale (EP16-256, 1/16/128 tokens) | e8/moe/moe.tsv (rerun on the push-path fix, 2026-10-11 09:22) | valid; no drops; Loom moves < 1 us (7 KiB messages); RDMA within 0.2 us of the 10-10 10:59 table, a change from the 10-10 17:00 PFC-headroom fix (that regression covered EP32/64 only), not from the push fix (push-only code). PFC pauses, combine EP256 128 tok: Loom 10,057 vs RDMA 2,206 (4.6x; were 9,952 / 2,019 before the headroom fix) |
| collectives at scale (AR/AG/A2A/RS, 16/64 GPUs) | e8/coll/coll.tsv (rerun on the push-path fix, 2026-10-11 09:33; previous 3-op table e8/coll/coll_20261010_3ops.tsv) | valid; RDMA identical in all 30 common rows, Loom -0.2..-2.3% at >= 256 KiB |
| STAGE end-to-end training, n32 (Llama-3 8B, Mixtral 8x7B) | runs/ns3_e8__stage_<cfg>__n32__{rdma,loom}_2026101*.log (Loom: 09:23 runs on the fixed build) | done: iteration Loom/RDMA -0.07% (Llama-3 8B, 51.78 ms) and -0.17% (Mixtral 8x7B, 40.71 ms) (model); before the fix dense Loom was +5.4-5.7% |
| STAGE n32 Llama-3 70B / Mixtral 8x22B, all n128 | same | **running** (Loom started 09:23 on the fixed build; RDMA runs from 08:55-09:01, unaffected by the fix) |
| training trace Mixtral 8x22B n32 | runs/ns3_e8__mixtral8x22b__n32__{rdma,loom}_2026101*.log | RDMA done (10-10 run, 0 gaps/drops: iteration 14.2850-14.3989 s, exposed comm 12.50-12.64 s); **Loom rerunning** on the fixed build (started 2026-10-11 09:18, ~4.3 h). The 10-10 Loom result (+0.010..+0.030% per GPU) predates the fix |
| training trace Llama-3 70B n16 | runs/ns3_e8__llama3_70b__n16__{rdma,loom}_2026101*.log | **running**: RDMA since 10-10 17:37 (~4 days estimated); Loom restarted on the fixed build 2026-10-11 09:18 |
| E4 prototype dispatch/combine | ~/loom-experiments/e4/ | measured (prototype, not simulator) |

Headline readings (model, RDMA / ideal Loom, slowest GPU, EP16-256; 2026-10-11 reruns): sender busy, dispatch
8.3-12.7x at 1 token, 2.2-2.5x at 16, 1.4-1.5x at 128; combine 2.7-5.2x, 1.5-1.8x, 1.2-1.3x. Delivered, dispatch
1.6-2.4x at 1 token, 1.1-1.5x at 16, 1.0-1.2x at 128; combine 1.4-2.1x, 0.94-1.34x, 0.92-1.04x (wire-bound).
Collectives: small AR/AG/RS 1.5-1.6x, small A2A 2.8-3.9x; large ~1.0x (A2A 64 MiB 0.86x at 16 GPUs, 0.99x at 64).
Where ideal Loom delivers later (combine EP128/256 >= 16 tokens 0.9x; A2A 64 MiB at 16 GPUs): more PFC pauses,
because ideal Loom injects at line rate at once while RDMA is paced by its payload reads and nothing models
congestion control. End to end (STAGE n32 so far): Loom within 0.2% of RDMA (bandwidth-bound training traffic).

## 4. Open decisions and planned changes
1. **Fast model for the training traces: NOT built (owner, 2026-10-10 18:00).** The training traces run
   in ns-3 only (Mixtral n32 ~3.5 h; Llama n16 ~4 days, estimate) - one simulator, one validation
   story. Training traffic is bandwidth-bound (RDMA ~ Loom), so a few ns-3 points suffice. Revisit only
   if the paper needs training results beyond 32 GPUs (then option B, ATLAHS traces, is the better
   route). Kept for reference: ns-3 is too slow for sweeps (one Llama iteration is ~167 s simulated;
   ns-3 managed ~5 s simulated in 3 h). Model type if built: a message-level endpoint
   model, the class of ATLAHS's LogGOPSim backend (section 5): per-message costs, then the message
   occupies the endpoint resources (sender PCIe, NIC TX, NIC RX, receiver PCIe); with one switch
   (n16, n32) these are the only contention points. Open: who implements it:
   A. a new ASTRA-sim network backend of that type (not an extension of the congestion-aware
      backend: 1-D only, store-and-forward per hop). Same Chakra traces as the ns-3 runs -> end-to-end
      validation on identical inputs; keeps explicit PCIe/NIC links and the RDMA/Loom release rules,
      parameters from the same steve measurements;
   B. ATLAHS's LogGOPSim itself + ATLAHS traces (real NCCL, 64-256 GPUs), RDMA and Loom as two
      LogGOPS parameter sets derived from the ns-3 model; one global parameter set per run, no shared
      trace format with our ns-3 runs (per-op validation only, unless Chakra -> GOAL).
   In both, ns-3 stays the reference: MoE dispatch/combine, collectives, and end-to-end at 16/32 GPUs.
2. Loom-side validation against E4: DONE 2026-10-11 (section 2); open: the prototype's 1-token receiver start-up.
   DCQCN sensitivity: runner run_dcqcn.sh (CC_MODE 1, else unchanged; e8/{moe,coll}_dcqcn). NOT run: with the
   HPCC defaults inherited by the configs (RATE_AI 50 Mb/s, RATE_HAI 100 Mb/s, MIN_RATE 100 Mb/s, RP_TIMER 900,
   tuned for 100G) the congested A2A 64 MiB n16 ran > 10 min vs 23 s without CC -> needs 400G parameters (owner).
   That run (model, runs/ns3_colldcsmoke__*): RDMA 711 -> 1709 us, Loom 843 -> 1845 us (PFC pause lines 3820 ->
   2181 for Loom, 0 for RDMA either way): DCQCN acts in nic mode, but these parameters over-throttle both ~2.2-2.4x.
3. Same-testbed RDMA baseline for E4 (perf_rdma CPU-posted dispatch).
4. Later: switch-delay sweep, DCQCN for both, Loom window/back-pressure, decode workloads.

## 5. Methodology context from related work
- **ASTRA-sim 2.0** ([arXiv 2303.14006](https://arxiv.org/html/2303.14006v1)): analytical backend,
  5% mean error vs real NCCL all-reduce 64 MB-1.5 GB; valid only for bandwidth-bound collectives
  without congestion ("congestion modelling is future work").
- **ATLAHS** (SC'25, [arXiv 2505.08936](https://arxiv.org/html/2505.08936v1),
  [code, MIT](https://github.com/spcl/atlahs), [traces](https://spcl.inf.ethz.ch/Research/Scalable_Networking/ATLAHS/)):
  nsys traces -> GOAL -> LogGOPSim (message-level) or htsim (packet-level); ns-3 backend "in
  progress". <5% vs real on Alps. Message-level within 1% of packet-level on a fully provisioned
  network, >120% off at 4:1 oversubscription. Reports ASTRA-sim's congestion-aware backend as 1-D
  only (true in our checkout) and its ns-3 backend segfaulting for their traces. Traces: Alps GH200
  (4 per node), Llama 7B/70B, MoE 8x7B/8x13B/8x70B at 64-256 GPUs. No NIC/host-interface model.
- **Wormhole** (NSDI'26, [arXiv 2602.10615](https://arxiv.org/html/2602.10615)): ns-3 (HPCC
  ns-3.17 lineage) with steady-state fast-forwarding and memoization, 135-745x faster, <1% FCT
  error; ASTRA-sim + ns-3 3.01% vs a real GPT-18B/256-GPU trace. Claims flow-level ~20% and m3
  10-15% error on LLM workloads. No code released (checked 2026-10-10).
- **SimAI** (NSDI'25, [paper](https://www.usenix.org/conference/nsdi25/presentation/wang-xizheng-simai)):
  analytical mode (user-supplied bus bandwidth) + multithreaded ns-3 mode; 98.1% alignment with
  real runs. Used and retired here (2026-10-08).
- **m3** (SIGCOMM'24): flow-level + ML, aggregate tail statistics, <10% error, 1000x faster than ns-3.
- **Hardware papers' at-scale methodology** (survey 2026-10-09): SCIN (BookSim2 cycle-level, 8 GPUs,
  validated vs FPGA), ACE (ASTRA-sim + Garnet), MixNet (htsim, 1024 GPUs), Canary/REPS/Swing
  (htsim/SST). Pattern: prototype microbenchmarks + packet-level simulation at scale; the host
  interface is usually a constant (our explicit PCIe/NIC stage differs).

## 6. Change log

**2026-10-07.** E8 starts. The old Loom ASTRA-sim branch and its model are rejected by the owner
(never use). SimAI is set up as a first vehicle.

**2026-10-08.** Base switched to a fresh ASTRA-sim 2.x + ns-3 + Chakra traces (owner): SimAI's
workloads carry no compute and it had five upstream bugs. SimAI's lumped model (a per-message start
delay) rejected by the owner as "half fake numbers"; its results are cross-checks only.
First host-interface model ("per-message", `HOST_IF_MODE pull/push`): one ns-3 NIC model with two
host-interface modes, a QP per message, lumped PCIe delays from literature, GPU post cost
0.7/3.07/7.33 us (mini-gda/DeepEP/NVSHMEM). Traffic inside a server moved off ns-3 onto an NVLink
path (owner). Validated against arXiv 2610.01380 Table 3 (one fitted link latency) and testbed E2 (fitted link
latency and Loom's CPU store rate). **Superseded 2026-10-10; not paper numbers.**

**2026-10-09.** Mixtral 8x22B (32 GPUs) on the per-message model: iteration 14.44 s for every
variant, <= 0.015% apart (model): MB-scale training traffic is bandwidth-bound. Method survey ->
plan: ns-3 is the calibrated reference, analytical only a supplement. Transport validation against
perftest/NVSHMEM on steve, later found **invalid**: steve's CX-7 netdevs were at MTU 1500 (RoCE MTU
1024) until 22:16. `WIRE_BYTES_PER_PACKET 82` added. Finding: ASTRA-sim keeps one comm op in flight
per GPU.

**2026-10-10 (morning).** Owner: the host-interface model was wrong. Replaced by the NIC model
(`HOST_IF_MODE nic`, section 1.3): persistent QPs, doorbells, WQE fetch, payload reads, CQEs,
PCIe as measured latency + FIFOs. Parameters re-measured at MTU 4096. Owner decisions recorded in
1.5/1.7 (zero GPU posting cost, no TLP-level PCIe, ideal Loom first, sender-busy metric, cluster).
Validation target switched to the Section 2 dispatch/combine runs (section 2). Loom added as
`NIC_PUSH`. ASTRA-sim frontend ported onto the NIC model.

**2026-10-10 (MoE and collectives at scale).** Two model artifacts found and fixed, both made one
destination's data arrive in a block: the frontend posted a GPU's concurrent sends destination by
destination (now interleaved put by put), and the NIC issued payload reads destination by
destination (now round robin over QPs). Steve validation unchanged.

**2026-10-10 15:00-17:35 (two bugs, fixed; ns-3 87418ff57, 69822186f; astra-sim c874237).**
1. Sequence wrap: the persistent QPs' stream offsets are 64-bit, but the wire sequence number,
   the receiver's expected sequence and the ACK were 32-bit. Past 4 GiB on one GPU pair the
   receiver looked up the wrong WQE and the sender ignored wrapped ACKs (silent stall or go-back-N
   loop). Both training traces crossed 4 GiB on cross-server ring pairs (Llama at 249 ms simulated,
   Mixtral at 13.28 s): those runs were invalid and were killed. Fix: unwrap the 32-bit value near
   the receiver's expected / the sender's oldest unacked offset, as NICs do with PSNs. Check (model):
   3x1400 MiB and 3x2 GiB on one pair now run at 48.75 GB/s; 3x1300 MiB identical to before.
2. PFC headroom: rate x delay x 3 left no room for the two 4178 B frames in flight when a pause is
   sent (23.25 KB on 155 ns 400G host links, ~24 KB needed): switches dropped packets. Fix: + 2
   frames (31.6 KB host, 54 KB fabric). Only one current result had drops (A2A 64 MiB n16 Loom,
   843.12 -> 842.93 us); the MoE table had none.
Regression after both fixes (model): all 480 dispatch-validation replays byte-identical; frontend
test identical; MoE combine EP32/64 at 128 tokens identical per GPU.

**2026-10-10 17:37.** Training traces restarted in ns-3 on the fixed build (reference for the fast
model). Literature check on moving the training traces to a fast model (section 5); ATLAHS
considered (section 4, option B).
Decision (owner, 18:00): no fast model; wait for the ns-3 training runs (section 4).

**2026-10-10 21:57.** Mixtral 8x22B (32 GPUs) done on the fixed build in 4h20m wall: RDMA and Loom
within 0.03% per GPU (Loom marginally slower; model), iteration ~14.4 s, exposed comm ~12.6 s -
bandwidth-bound training traffic, as expected. Llama still running.

**2026-10-11 (overnight).** Loom side validated against the E4 prototype (section 2; tests/run_val_e4.sh,
tools/val_e4.py, e8/cfg/testbed_e4/). Paper figures from tools/plot_eval.py (eval-validation, eval-moe, eval-coll,
eval-micro -> ~/loom-paper/plots). DCQCN sensitivity prepared but not run (section 4). Smoke check: DCQCN leaves
uncongested MoE runs (EP16 t16, EP64 combine t128: no PFC) unchanged to the ns.

**2026-10-11 09:15 (Loom push path: whole-message store-and-forward over PCIe, FIXED; ns-3 rdma-hw.cc NicRing /
NicWqesIn, UNCOMMITTED).** In push mode NicRing sent all rung messages with their inline payload as ONE PCIe write and
Loom saw the data only when all of it had landed, so a multi-MB message waited size / 57.6 GB/s before its first
packet. Now each message's stores go in HIF_CHUNK pieces and each piece is handed to Loom as it lands (RDMA paths
untouched). Check (model, d2, one 16 MiB message): Loom delivered 637.1 -> 345.9 us, sender released 291 us
(PCIe-bound) both; RDMA 349.4 us before and after. Found because STAGE dense training showed Loom +5.4-5.7% with
equal PFC counts. EVERY Loom simulation result before this is affected (most for MB-sized messages): MoE, collectives,
STAGE, both library traces, the E4 replay (val_e4), push what-if / zero-GPU compare. Reruns started 09:18 on the fixed
build (astra-sim-opt2; default build in astra-sim-fresh rebuilt 09:16); RDMA runs are unaffected and kept.

**2026-10-11 09:30-09:50 (push-path fix committed; reruns).** Committed as ns-3 fc5126a64, astra-sim-fresh a69e163
(the optimized copy astra-sim-opt2 runs the identical rdma-hw.cc). Reruns on it (model): MoE (Loom < 1 us, 7 KiB messages;
RDMA within 0.2 us, from the 10-10 headroom fix), collectives now with reduce-scatter (RDMA identical in all 30 common rows; Loom -0.2..-2.3%
at >= 256 KiB, e.g. A2A 64 MiB n16 843.1 -> 824.7 us), E4 replay (delivered at 16/128 tokens -0.6..+0.1% ->
-1.0..-0.3%; sender unchanged), STAGE n32 Llama-3 8B and Mixtral 8x7B (Loom -0.07% / -0.17% vs RDMA; was +5.4-5.7%
for dense). Still running: STAGE n32 Llama-3 70B / Mixtral 8x22B, STAGE n128, both library traces (Loom).

**2026-10-20 (in-server NVLink = bandwidth only; owner).** Fig 14 Phase A (run_e2e_phaseA.sh) showed PP8 (Llama-3 70B,
TP8 x PP8, 64 GPUs) at Loom +13.1% (322.8 vs 285.4 ms). Cause: astra-sim-fresh entry.h local_send (a loom-branch
addition of 2026-10-08, not upstream ASTRA-sim) reserved each GPU's NVLink port for a whole message in issue order;
Loom's earlier send release lets later TP collectives take the port first, the critical ones wait. Checks (model): FIFO vs
LIFO scheduling identical; MSG_SPLIT 1 MiB identical; 1 active chunk -> level (387.7/387.3); NVLINK_GBPS 400000 -> level
(191.86/191.87). Owner: "don't build your own NVLink model, we only use its bandwidth" -> local_send now takes
size/bandwidth + latency per message with no port/queue (congestion-unaware, as ASTRA-sim's analytical backend). Built:
astra-sim-fresh default 63b98faf, astra-sim-opt2 e59e7ee3 (tools/check_ns3_build.sh OK). Every result with in-server
traffic is rerun on it: Fig 11 (run_moe.sh), Fig 12 (run_coll_nic.sh, 4 ops), Fig 13b (all-to-all of the link sweep),
Fig 14 (Phase A). Backups: entry.h.pre_nvlbw_20261020, moe.tsv / coll.tsv .pre_nvlbw_20261020. Also: the ns-3 queue
monitor (common.h monitor_buffer, every 100 ns, never stops) dominated compute-heavy runs; e8/clusters/n64nm, n128nm start it
after the run (QLEN_MON_START 1e14); verified cycle-identical on DP (both systems).

**2026-10-20 ~19:30 (workload trace, not the network model: cross-server collectives in program order).** Phase A hybrid
(Llama-3 70B TP8 x PP4 x DP2, STAGE, 64 GPUs) DEADLOCKED on ns-3 in BOTH systems (15:50 runs): no rank finished; after
3.5 h both processes spun in monitor_buffer, which with QLEN_MON_START 1e14 only runs once the event queue is otherwise
empty (perf). Cause: the STAGE trace leaves a DP group's gradient collectives of different layers unordered in each rank's
DAG (e.g. transformer.0 / transformer.1 _sharded_grad); ASTRA-sim numbers a group's streams in issue order
(Sys.cc communicator_group->num_streams++), so two DP partners on different servers that issue them in different orders
cross-match streams. The analytical backend (symmetric timing) runs the same trace to the end (valgrind: 64 finished,
161.0 ms model; its only error is a double free in ~CommunicatorGroup at teardown = the exit-134 abort, after the run).
Fix (trace post-processing, network model unchanged): tools/order_coll.py chains every CROSS-SERVER group's collectives
in a deterministic topological order (Kahn, ties by node id; = one program order, identical on every member; checked:
members get the same (type, size) sequence), as frameworks issue a process group's collectives in program order. Hybrid:
32 DP groups, 992 ctrl deps; analytical 162.0 vs 161.0 ms (+0.6%). Chaining ALL groups (incl. in-server TP) is wrong:
it forced one global schedule (418 ms). Trace traces/e2e/hybrid_ord; ns-3 pair started 19:32 (e59e7ee3). PP, DP, FSDP,
CP, Llama-80B and the Opus MoE traces finished without it (unchanged).
CORRECTION (19:38): the ordered trace (hybrid_ord) ALSO deadlocks on ns-3 in both systems (monitor_buffer hot after ~5 min,
no rank finished; stopped). The cross-server ordering is not the (whole) cause; still open. collect_e2e.py hybrid row points at
hybrid_ord (no valid run yet).

**2026-10-20 ~20:00 - 2026-10-21 (owner: ns-3 DROPPED; analytical model LoomNet).** All ns-3 runs stopped. New model =
ANALYTICAL.md (read it first): per-put closed-form stages (Loom posted writes; RDMA doorbell, WQE fetch, payload read,
CQE), busy-until PCIe and network links, ns-3's exact ECMP hash, NVLink bandwidth only; same cluster config files as the
ns-3 runs. Validation vs the prototype equals the ns-3 model's within 1-2%; Phase A iterations within -0.6..+2.6% of
ns-3; collectives median 0.5%; MoE median 5.8% (RDMA at EP >= 128 open). Training traces need the program-order rule
(tools/order_traces.sh) because ASTRA-sim's one-comm-op-per-GPU + issue-order matching deadlocks under asymmetric
timing (also the cause of the ns-3 hybrid hang). Sections 1-5 above describe the retired ns-3 model.
2026-10-21 ~00:00 (LoomNet): round-robin store/read engines with MTU turns (ANALYTICAL.md section 2): fixes RDMA EP 256
combine (+13-18% -> +-4% of ns-3) and the 16-GPU 64 MiB all-to-all (840 -> 712 us = ns-3); removes ns-3's asymmetry
(RDMA reads interleaved per 4 KiB, Loom stores per whole put): Loom MoE delivery at 16 tokens EP >= 64 10-22% sooner than
ns-3 had it. Owner decision needed before any paper number moves.
2026-10-21 (owner): no interleaving - whole puts, first come first served on every resource (as Opus); round-robin
engines removed. NIC reads payloads in posting order (WQE-fetch order made RDMA MoE 43-73% slow via incast bursts).
2026-10-27 (owner: every experiment on the ASTRA-sim layer, no hand-written replayer): the prototype validation runs in
ASTRA-sim (val_model/run_val_astra.py: Chakra traces of the tools' steps, gen_p2p/gen_proto_coll/gen_bcast), the
sensitivity sweep too (val_model/run_sweep_astra.py; one message = gen_p2p.py --pre <GPU work> + the frontend's staging
copy; all 190 values within 2 ns of an_replay), and alpha_beta.py / stage_breakdown.py / sweep_p2p.py (tools/astra_p2p.py:
one message on any cluster config, gen_p2p.py --npus/--src/--dst). run_an_all.sh calls these; run_val_an.py /
run_sweep_an.py / run_sweep.py refuse to run without ALLOW_REPLAYER=1; the an_loomreplay H200 dispatch check is retired.
At scale RDMA's collectives never wait for a completion (ASTRA-sim's own collectives): its best case; NCCL 2.28 refills each
of 8 slots per connection only after the slot's send completed, which a 64-GPU ring would hit with 1-2 channels (not with
>= 4; computed from the model's traces). Decode's DeepEP double buffering never delays a step (gen_decode.py NOREUSE=1,
identical at EP64 1-128 / EP256 1-16 tokens).
