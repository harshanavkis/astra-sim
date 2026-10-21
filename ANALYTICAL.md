# LoomNet: the analytical network model (replaces ns-3)

Status 2026-10-21 morning. One command regenerates everything: `tools/run_an_all.sh` (~2 min; report e8_an/ALL.txt;
figure previews e8_an/preview/*.png, NOT in the paper). Owner decision 2026-10-20 ~20:00: drop the ns-3 packet simulation ("causing too many
issues") and model the network analytically in ASTRA-sim, with formulas, as Opus (SIGCOMM'26) and SCALE do. Owner's
rule: no per-chunk/per-packet simulation. **Loom = posted writes; RDMA = the same transfer plus its added delays.**
Every number below is **model** unless it says measured or computed.

## 1. What other works do, and what we take from them

| work | network model in ASTRA-sim | what we take |
|---|---|---|
| Opus (SIGCOMM'26, `opus-ref/Opus/simulation/reconfig_backend`, `Link.cpp`) | message-level alpha-beta per link: arrival = `latency + size/bandwidth`, link busy `size/bw + 2*latency`, FIFO; ECMP = random among equal-cost paths; no NIC model | busy-until links per message, ECMP routes |
| SCALE (`SCALE_Tackling_Communication_Bottlenecks...pdf`, Sec. VI-F, VII-A) | NCCL's cost model `T(a,p,n) = omega(a,p) * launches(a) + epsilon(a,p) * n` (startup = launch + one link latency per hop + inter-node latency; epsilon = 1/effective bandwidth); security costs added per send/recv as `d_omega = r*omega_SW + (1-r)*omega_HW`, `d_epsilon = 1/(r*B_SW + (1-r)*B_HW)`; calibrated against NCCL (17% geomean error) | per-system alpha (startup) and beta (per byte) added to every send; a calibration step |
| ASTRA-sim congestion-aware backend | links as independent FIFO queues with buffering between them, chunks store-and-forward per link | independent busy-until links (no head-of-line blocking) |

Other analytical models (web search 2026-10-20, for context; numbers as the papers report them, not checked):
- SimAI (NSDI'25) analytical mode: one bus bandwidth (busbw) per collective, no per-message or contention terms
  ([SimAI](https://gitee.com/aliyun/SimAI)).
- Echo (arXiv 2412.12487): profiling-based; reports 7-8% error vs ~27-28% for an alpha-beta NCCL predictor
  (NCCL-Predictor) - plain alpha-beta per collective misses protocol and contention effects
  ([Echo](https://arxiv.org/pdf/2412.12487)).
- ATLAHS (arXiv 2505.08936): ASTRA-sim's congestion-aware backend supports only a 1-dimensional topology (large errors
  on multi-tier topologies), and ASTRA-sim's ns-3 backend segfaulted for them; their tool reports < 5% error
  ([ATLAHS](https://arxiv.org/pdf/2505.08936)).
- AMSP (arXiv 2311.00257): the standard ring alpha-beta formula (alpha per transmission), noting it fails for
  Tree/CollNet/in-network aggregation ([AMSP](https://arxiv.org/pdf/2311.00257)).
What LoomNet does differently: the alpha and beta are not fitted per collective but follow from each system's
host-interface mechanism per put (the quantity Loom changes), every fabric link is a resource on a multi-tier topology
(not 1-D), and the model is checked against prototype measurements and against the packet-level model (Section 5).

LoomNet does the same at the level of one **put** (one software write of a message): each system gets its own alpha and
beta from the host-interface mechanism (Section 2), and messages contend on busy-until links (Section 3).

## 2. The host interface: per-put formulas

Notation: `S` payload bytes; `B` PCIe payload rate per direction (Gen5 x16: 57.6 GB/s computed; prototype Gen3 x16 MPS
512: 15.04 GB/s computed); `N` link rate (400 G = 50 GB/s); RoCE packets carry `MTU` = 4096 B payload + `W` = 82 B
(computed: preamble/IFG 20, Eth+FCS 18, IP 20, UDP 8, BTH 12, ICRC 4); `wire(S) = S + ceil(S/MTU)*W`.
PCIe latencies (measured on steve, H200 + CX-7, `e8/cfg/steve_nic/base.txt`): store/doorbell GPU->NIC `L_db` 645 ns,
NIC read of GPU memory `L_rd` 1350 ns, NIC write visible to the GPU `L_wr` 645 ns; NIC pipelines `T_tx` 260 / `T_rx`
590 ns (measured); Loom = its pipelines, 21 / 7 cycles (RTL) at ASTRA-sim's 1 ns clock, PLUS the network stack it reuses
(RoCE transport, MAC, PHY) at the NIC's 260 / 590 ns (owner 2026-10-21; before, Loom paid only 21 / 7 ns: ~850 ns too fast
per message at scale). The prototype validation keeps 21 / 7 cycles at 250 MHz: there both systems share Coyote's stack
inside the one fitted link delay.

Each stage is a formula evaluated at the stage's own time, in time order (so a resource is never booked "into the
past"); `max(...)` with a resource's busy-until time is the only coupling between puts.

**Loom (posted writes)**
1. Stores: the GPU's stores (payload only; Loom has no work request, so no WQE bytes since 2026-10-21) cross its PCIe
   link, puts in posting order: `s0 = max(t, busy_pcie)`, `s1 = s0 + S/B`. **Sender released at `s1`** (its last store
   has left the GPU).
2. Loom has each piece as it lands and forwards per packet: first packet ready `s0 + min(S,MTU)/B + L_db + T_tx`,
   all bytes in at `s1 + L_db`.
3. Wire and network (Section 3), then Loom's receive pipeline `T_rx` and the writes into GPU memory at `B`;
   **delivered** = last write + `L_wr`. The receiving PCIe link stays busy until that last write ends (posted writes in
   order: the signal behind the data cannot land first; fix 2026-10-21, Loom +37..+69 ns, RDMA +70 ns from 1 MiB).
Sensitivity option (default off, not used by the paper's runs): `LOOM_TX_BUF_BYTES` = Loom's transmit buffer per port: the last
store of a put is accepted at `max(s1, e0 - buf/N)` (e0 = its last byte on the Loom -> switch link, which carries only this
GPU's puts, FIFO, so it is computed at store time). Without it Loom absorbs any amount of stores (upper bound).

**RDMA (the same transfer + its added delays)**
1. Doorbell: an 8 B MMIO store, lands `L_db` later (BlueFlame configs: the WQE goes with it).
2. WQE fetch: one read per queue pair at a time, up to 64 WQEs, data one `L_rd` later (WQEs whose doorbell landed
   while a fetch was in flight wait for the next fetch, as the ns-3 NIC did).
3. Payload read: the NIC reads payloads in the order the GPU posted the puts (among those whose WQE is in), at most
   `PCIE_RD_INFLIGHT x MRRS` bytes outstanding (512 KiB); a read's first data one `L_rd` after its request, then `S/B`
   on the PCIe link; a put's credit frees one `L_rd` before its data is in (the NIC requests MRRS pieces as credit
   frees, so reads stream without gaps). `T_tx` later the packets may leave. (Reading in WQE-fetch order instead - a
   fetch brings up to 64 WQEs of one queue pair - made every NIC read one destination after another, all senders in
   step, and the receivers' incast made RDMA's 128-token MoE 43-73% slower than ns-3; Loom's stores were never
   affected because the GPU posts its puts alternating across destinations.)
4. Wire and network (Section 3), the NIC's `T_rx`, the writes into GPU memory; **delivered** = last write + `L_wr`.
5. **Sender released** at the CQE: the last packet's ACK returns (`T_rx` + path back), the NIC writes a 64 B CQE, `L_wr`.

PCIe ordering decides which small transfers queue: a doorbell (a posted write) may pass read completions, so it does
not wait behind payload reads; a WQE fetch is a read whose completion comes after the completions of reads issued
before it (in flight, capped as above), and a CQE is a posted write behind the NIC's earlier writes of
received data, so both book the link in order. (A first version let all three bypass: RDMA's 4 KiB stream at 1600 G
came out 125 instead of 82 GB/s; another queued them behind all booked reads without an in-flight cap: MoE 30-55%
too slow.)

**Whole messages, first come first served (owner 2026-10-21).** Every resource carries one put at a time, in arrival
order, as Opus's and ASTRA-sim's analytical links do; no interleaving of concurrent puts below a put. Cost against the
ns-3 model (which shared links per packet): when a GPU sends large messages to many destinations at once, they leave
one after another, so receivers are busy one after another: RDMA's 64 MiB all-to-all on 16 GPUs 840 vs 711 us (+18%),
RDMA's combine at EP 128/256 +13-20%; the same rule applies to both systems (64 MiB all-to-all: RDMA 840 / Loom 836 us).

**A message** (ASTRA-sim `sim_send`) between servers = its puts (`MSG_SPLIT_BYTES` each; 0 = one put) + an 8 B signal
put on the pair's queue pair; delivered when the receiver sees the signal; released as above. Sends a GPU issues at the
same time are posted interleaved, one put of each in turn. Inside a server: NVLink by bandwidth only (`S/400 GB/s`,
arriving 936 ns later; identical for both systems, as before).

**alpha-beta per system** (model; `tools/alpha_beta.py e8/clusters/n64nm`: one message = one put + signal, GPU 0 ->
GPU 8 on the same leaf / GPU 0 -> 32 across leaves; fit over 64 KiB..64 MiB):

| 400 G cluster | alpha delivered | alpha sender released | beta |
|---|---|---|---|
| RDMA | 5.63 / 6.33 us | 5.95 / 7.26 us | 49.0 GB/s (= 50 GB/s x 4096/4178) |
| Loom | 2.70 / 3.48 us | 0.000 us | 49.0 GB/s delivered, 57.6 GB/s released (PCIe) |

(2026-10-21 12:33, binary 73656926: with the receiver write-order fix, no Loom WQE bytes and Loom's network stack.)

**Worked example** (computed by hand from the formulas; the simulator prints the same): an 8 B message GPU 0 -> GPU 8
(two 155 ns links, one switch, 400 G). Loom: stores land 645 + 8/57.6 = 645 ns; + Loom tx 260 + 21; + 2 x 155 = 310;
+ one 90 B packet on two links 2 x 1.8; + Loom rx 590 + 7; + write 8/57.6 + 645 visible = **2482 ns** (simulator 2484).
RDMA: doorbell lands 645; WQE fetch + 1350 + 64/57.6 = 1996; payload read + 1350 = 3346; NIC tx + 260; wire + path
~ +314; NIC rx + 590; write + 645 = 5155 ns data visible; the signal's doorbell landed 0.14 ns after the first fetch
started, so its WQE comes with the second fetch (1996 + 1350 = 3346), its read at 4696, visible at **6505 ns**
(simulator 6506). Sender released: RDMA at the signal's CQE 6820 ns; Loom when its stores are out, 0 ns.

Small RDMA messages (<= 16 KiB) are delivered after 6.5 us: the signal's WQE misses the first fetch and waits one more
read round trip (as in the ns-3 NIC model).

## 3. The network: busy-until links on ns-3's ECMP paths

- Topology = the clusters' ns-3 topology files (`e8/clusters/n64/topo.txt` etc.: 8 GPUs per server, one 400 G NIC or Loom
  per GPU, leaf-spine with full bisection, 32 GPUs per leaf, link delays host 155 ns / fabric 305 ns = cable + ~300 ns
  per switch).
- Every directed link is a busy-until resource, booked when the put ARRIVES at that link (one event per hop, as Opus
  forwards a chunk when it reaches a device; booking the whole path when the put entered its first link let later
  arrivals queue behind future bookings: MoE at EP >= 128 +10-20%). A put crosses its path link by link, cut-through: on link j it starts
  at `max(start on link j-1 + delay + one packet time (store-and-forward per packet), busy_j)` and ends no earlier than
  `start + wire(S)/N` and the previous link's end + delay. A busy link delays the put there, not on the links before
  (the switch's 32 MB buffer absorbs it; no head-of-line blocking of a sender's other destinations; an earlier version
  held the sender and made all-to-all 2-5x too slow).
- ECMP exactly as ns-3's switches: next hops = neighbours one BFS hop closer in ascending node id, picked by murmur3-32
  over (src IP, dst IP, sport | dport << 16) seeded with the switch id; a NIC-mode queue pair keeps sport 30000 + qp,
  dport 100. Assumption: ns-3's node map iterates in node-id order (it is keyed by pointer; nodes are allocated in id
  order). With a random hash instead, CP and the MoE mix came out 36-46% slower than ns-3 (different collisions).
- Not modelled: PFC pauses, packet-level sharing of a link between flows (FIFO per put instead), congestion control
  (both systems run PFC-only), loss.

## 4. ASTRA-sim integration and the program-order rule

- Binary `AstraSim_Analytical_Loom` (astra-sim-fresh `astra-sim/network_frontend/analytical/loom/`, model header
  `include/loom/LoomNet.hh`). `--network-configuration` = a cluster's `rdma.txt` / `loom.txt` (the same files the ns-3
  runs used; every parameter identical). One logical dimension of all GPUs (as `logical.json`).
- ASTRA-sim (upstream) runs **one communication op per GPU at a time** and matches a communicator group's messages by
  the order members issue its collectives. When GPUs' timing differs (any contention), members can issue a group's
  collectives, or crossing groups' collectives (TP in a server, DP across), in different orders and wait for each other
  forever. This hung Phase A hybrid on ns-3 and DP/FSDP/PP/hybrid on this model. Fix (trace, not network):
  `tools/order_traces.sh` runs each trace once on ASTRA-sim's congestion-unaware backend (symmetric timing), logs the
  issue order (`ASTRA_ISSUE_LOG`, new), and chains each rank's communication ops in that order (`tools/order_coll.py`
  `ORDER_LOG TOTAL=1`): the framework's program order. Feasible by construction (that run completed with it).
  Traces: `traces/e2e_ord/<name>` (with `issue_order.log`).
- Guard: if the event queue runs dry with ranks unfinished, the binary prints `LOOMNET DEADLOCK: k of N ranks finished`
  and exits 3 (`run_an_jobs.sh` reports FAILED). Checks: the diagnostic TP8xPP4xDP2 trace with 8 micro-batches stops
  with it unordered (0 of 64) and runs ordered (RDMA 42.59 / Loom 42.01 ms); DP gives the same iteration ordered or not
  (83.0376 ms): the order does not change results where it is not needed.
- Option `ASTRA_COMM_PER_GROUP=1` (one op per communicator group, NCCL-like streams) exists but is NOT used: ASTRA-sim's
  system layer (active streams per dimension, LIFO) then deadlocks the same way. Owner decision if wanted.
- Other ASTRA-sim changes: `EventQueue` = ordered map (O(log n) instead of a linear list; same order; first slot may be at
  t = 0); the frontend does not delete `Sys` at exit (ASTRA-sim's `~CommunicatorGroup` double-frees; valgrind 2026-10-20).

## 5. Validation

**(a) Against the prototype** (measured, `~/loom-experiments/val_model/run_val_an.py` = `run_val.py` with `bin/an_replay`;
same configs: 100 G, Gen3 x16 15.04 GB/s computed, host memory, Loom at 250 MHz; same ONE fitted constant: link delay
1689 ns so that Loom's 8 B one-way = E2's 4.07 us measured). Latest: `val_model/runs_an/<newest>/REPORT.txt`.
- E2 one-way: RDMA within 10% (-9.3% at 8 B, -2.5% at 64 KiB); Loom = CPU stores within 5% up to 256 B.
- E1 throughput: RDMA within 3.1% at every size; Loom within 0.5% from 16 KiB (4/8 KiB: the PTDMA's per-descriptor cost,
  0.65 us computed, not modelled: +88/+41%, as before).
- E4 dispatch/combine: RDMA (ordered and flush) delivered within 4%, completions within 2%; Loom combine within 6% from
  16 tokens, dispatch 30% sooner (PTDMA engine 8.5 GB/s computed, not modelled), as before.
- E5 ag / a2a: Loom 12-22% faster than measured, RDMA +5..+9% at <= 16 KiB and up to -30% from 256 KiB (measured RDMA's
  large-size slowness = Coyote RoCE retransmissions, hardware session), as before.
These equal the ns-3 model's validation (`val_model/runs/20261020_e5rerun/REPORT.txt`) within 1-2% everywhere (largest:
E2 64 KiB, Loom 10.01 vs 10.27 us, RDMA 10.57 vs 10.84 us): the paper's validation statements hold unchanged.

**(a2) RDMA against the H200 server** (measured, Section 2's dispatch/combine on steve, H200 + CX-7, 200 G cable; the
paper's "receiver sees every signal within +0.9 to -7.8%" check): `bin/an_loomreplay` replays each traced run (measured
posts, doorbells and atomic signals; 20 runs per point, `val_dispatch/20261010_ring/runs`) on the model with steve's
config (`e8/cfg/steve_nic/base.txt`), `tools/val_dispatch.py` compares (model dir `val_dispatch/20261010_ring/
model_an_v4`). Receiver sees every signal: -7.8 .. +0.9% (ns-3 model: -7.8 .. +0.9%, identical); last arrival -8.5 ..
+2.0% (ns-3 -8.7 .. -0.2%); reaped -10.7 .. -0.5% (ns-3 -7.7 .. -0.5%); drain as ns-3 (-29% at 1 token, both). The
median per-message one-way time on the ordered paths (1 and 16 tokens) is 11-17% below measured (ns-3 within 3-12%):
the first message arrives ~0.8 us sooner than in ns-3 (e.g. 14.22 vs 15.06 us), and the RDMA completion comes 44 ns
before the data is visible instead of 545 ns after (ns-3). A hand calculation of the stages (doorbell 645, WQE fetch
1350, payload read 1350 + bytes, NIC tx 260, wire, NIC rx 590, write 645) gives the analytical value; the extra ~0.8 us
sits inside ns-3's packet-level ACK/transmit path, not attributed further (ns-3 dropped).
Not a metric the paper uses. Needed for this: separate WQE
posting and doorbells (`post_wqe` / `ring`), RDMA atomics (responder reads, answers, writes), and the in-order byte
stream per queue pair (an atomic signal must not overtake the QP's data still being read: without it the signal was
seen 54-69% early at 128 tokens).

**(b) Against the ns-3 model on the paper's workloads** (model vs model, identical jobs and configs;
`tools/cmp_an_ns3.py`):
- Collectives (Fig 12 jobs: AG/AR/RS/A2A, 1 KiB..64 MiB, 16/64 GPUs): median |diff| 0.3%; largest: all-to-all 64 MiB
  on 16 GPUs RDMA +18% (whole messages, Section 2), ratio 1.00x (ns-3 0.86x).
- MoE dispatch/combine (Fig 11 jobs, EP 16..256, 1/16/128 tokens): median ~1%; Loom within 0-7%; RDMA within +-8% except
  combine 16 tokens at EP 128/256 (+15/+20%) and 128 tokens at EP 256 (+13%) (whole messages).
- Phase A training iterations (64/128 GPUs, `e8_an/e2e/e2e_phaseA.tsv`, RDMA): DP 83.04 vs 83.10 ms, FSDP 83.87 vs
  81.77, PP 213.2 vs 213.9, CP 78.49 vs 78.86, Llama-80B 981.0 vs 981.4, MoE EP+TP+DP 141.3 vs 142.7 (all -1.0..+2.6%);
  hybrid TP+PP+DP and MoE EP+DP (never finished on ns-3) now run: 187.8 / 985.4 ms. Loom vs RDMA: DP -0.14%, FSDP
  -0.13%, PP -0.02%, CP -0.29%, hybrid -0.49%, Llama-80B -0.01%, MoE EP+TP+DP -0.02%, MoE EP+DP -0.00% (ns-3: DP -0.14,
  FSDP -0.32, PP +0.70, CP -0.29, Llama-80B -0.01, MoE +0.19%).
- ECMP sensitivity (LOOMNET_ECMP_SALT 1-3 = other collision patterns than ns-3's hash): Phase A absolute iteration
  times move by up to 2-4% (Llama-80B 981 -> 1002 ms, CP 78.5 -> 81.3 ms), Loom vs RDMA by at most 0.3 percentage points
  (DP -0.10..-0.14%, PP -0.02..-0.30%, CP -0.16..-0.32%, hybrid -0.42..-0.49%, others ~0): the training conclusion does
  not depend on the collision pattern.
- Link-rate sweep (Fig 13b: `val_model/run_sweep_an.py` vs `run_sweep.py`, 100..1600 G, PCIe Gen5/6/7): latency,
  streams and the 16-GPU all-to-all match the ns-3 sweep within ~1% at every point (e.g. 4 KiB stream RDMA 39.25 vs
  39.28 GB/s at 400 G, 82.8 vs 82.5 at 1600 G; 1 MiB stream 190.0 vs 189.4 at 1600 G; all-to-all ratio 3.07..3.89x
  both). (Before the NIC released a put's credit one read latency early, as ns-3's per-MRRS requests do, a
  put larger than the in-flight cap left a read-latency gap: 1 MiB stream 173 GB/s at 1600 G.)
- Speed: a 64-GPU training iteration in ~1 s (ns-3: 7 min to never); 140 Fig 11/12 jobs in ~10 s; 256 GPUs (scratch
  check, not a paper point): all-reduce 64 MiB 4.9 s / 76 MB, all-to-all 64 MiB 46 s / 0.57 GB (many concurrent QPs
  interleaved per MTU). Model results there: all-reduce RDMA 3048 vs Loom 2734 us (a 256-GPU ring = 510 dependent steps
  of 64 KiB pieces, so the per-message alpha adds up), all-to-all 1424 vs 1412 us.

## 6. How to run

```
e8-astrasim/tools/build_an.sh                                   # AstraSim_Analytical_Loom + bin/an_replay
e8-astrasim/run_an.sh <name> <workload prefix> <system.json> e8/clusters/n64nm/rdma.txt [comm groups.json]
e8-astrasim/tools/run_an_jobs.sh <jobs file> [parallel]          # jobs format as tools/run_jobs.sh; logs runs_an/an_*
LOGS=runs_an/an_ python3 -I tools/collect_coll_nic.py e8_an/coll/jobs.txt     # Fig 12 data -> e8_an/coll/coll.tsv
ASTRA_CONCURRENT_SENDS=1 tools/run_an_jobs.sh e8_an/moe/jobs.txt; LOGS=runs_an/an_ python3 -I tools/collect_moe.py e8_an/moe/jobs.txt
AN=1 python3 -I tools/collect_e2e.py                             # Phase A -> e8_an/e2e/e2e_phaseA.tsv
tools/order_traces.sh <trace dir> <out dir> <GPUs>               # program order for any new training trace (required)
python3 -I ~/loom-experiments/val_model/run_val_an.py            # validation against the prototype
python3 -I tools/alpha_beta.py e8/clusters/n64nm [src dst]       # alpha / beta per system
python3 -I tools/cmp_an_ns3.py [coll|moe]                        # model vs ns-3 model
ls val_dispatch/20261010_ring/runs/*.run | grep -v _local | xargs -P 32 -I{} sh -c 'b=$(basename {} .run); bin/an_loomreplay e8/cfg/steve_nic/base.txt {} <out>/$b.out'
python3 -I tools/val_dispatch.py val_dispatch/20261010_ring <out>   # RDMA vs the H200 server (measured)
tools/run_an_all.sh                                              # EVERYTHING above in one go (~2 min), report in e8_an/ALL.txt
MODEL=an python3 -I tools/plot_eval.py e8_an/preview e8_an/preview   # figure previews from this model (not the paper)
```
Every log's first line: `loomnet bin <md5> model <md5 of LoomNet.hh>`; `run_an.sh` refuses a binary older than the model
header.

## 7. Open items (for the owner)

1. DECIDED 2026-10-21 (owner): no interleaving; whole messages first come first served, as Opus (Section 2).
2. Program-order rule (Section 4) is required for every training trace: OK to state in the paper ("collectives issued in
   program order, as frameworks do")?
3. `ASTRA_COMM_PER_GROUP` (concurrent TP/DP/PP streams) not used; upstream one-op-per-GPU kept.
4. Paper figures (11-14, model markers on 9/10) still come from ns-3; previews from this model in e8_an/preview/*.png;
   regenerating into the paper (owner OK 2026-10-21). "bandwidth-bound within 0.86-1.17x" ->
   recompute; training within 0.5% (paper 0.7%).
5. PP: Loom vs RDMA -0.02% here vs +0.70% on ns-3 (the ns-3 value came from its NVLink-port queue era / ordering).
6. FORMULA REVIEW 2026-10-21 (owner asked; a + b APPLIED 2026-10-21 10:57 on owner OK, c in the paper's simulator
   paragraph (alpha-beta form); d dropped: one PCIe payload rate for every size and both systems, so it cannot change
   the comparison - a store-rate option I added was removed again on owner's order):
   a. BUG, receiver write order: `rx()` books the receiving PCIe link for `bytes/B` from the first packet, but the last
      packet's write ends at `a1 + T_rx + last/B`; the next put's write (the 8 B signal right behind the data) may then
      land before the data's last packet. Fix (scratch: scratchpad rxorder/inc/LoomNet.hh): set the link busy until
      `i1`. Effect (model, alpha_beta n64nm 0->8): Loom delivered +37 ns at 16 KiB, +69 ns from 64 KiB; RDMA +70 ns
      from 1 MiB; alpha Loom 1.786 -> 1.855 us, RDMA 5.630 -> 5.668 us. Needs owner OK + rerun of all figures.
   b. Loom pays `WQE_BYTES 64` per put on PCIe (loom.txt); Loom has no work request: +1.1 ns per put, conservative.
   c. Paper text: T_RDMA / T_Loom are per PUT; a message adds its signal, and a small RDMA message's signal WQE waits
      for a second fetch (+L_rd: 6.5 vs 5.15 us); RDMA completion is L_path after the data is visible (6821 - 6506 =
      315 ns), not "L_path + L_wr".
   d. Assumption: B = 57.6 GB/s assumes 256 B TLPs for the GPU's stores and for the NIC's read completions (not measured).
   Fig 14 rerun on 7b733e65 (10:53): all 18 jobs identical to e8_an/e2e/e2e_phaseA.tsv.

**Proposed paper text (NOT applied; evaluation.tex "Simulator and its validation", lines 73-75, and At Scale
methodology line 304).** Replace the ns-3 sentence pair with:
> To evaluate \system{} beyond two racks, we use ASTRA-sim~\cite{} with an analytical network model, as recent studies
> of large clusters do~\cite{}. % CITE: ASTRA-sim 2.0; Opus (SIGCOMM'26); SCALE
> The model computes each transfer with formulas instead of simulating its packets.
> A transfer pays the latencies on its way and moves at the rate of its slowest link.
> Every link, including each PCIe link, is busy for the transfers it carries, so transfers that share a link queue.
> We add a model of how each system meets its endpoints.
(the RDMA / Loom / PCIe sentences that follow stay as they are), and in At Scale "modelled outside ns-3" -> "modelled by
its bandwidth only". The validation sentences stay true (Section 5a/a2: identical errors).

## 8. Proposed next steps (plan only; nothing run, needs your approval)

Same workloads as the 3.5-week plan of 2026-10-20 (owner's list), now on this model (run time is no longer the limit:
a 128-GPU iteration takes < 1 s; the largest MoE job 9 s):
1. Full-depth Phase A: Llama-3 8B (32 layers) and 70B (80), full vocabulary, the six groups + hybrid + MoE EP+DP; every
   trace through `tools/order_traces.sh`; check that the Loom/RDMA ratio at full depth equals the cut-depth one (as the
   16-layer depth check did).
2. Opus's larger setups: DeepSeek-V3-style MoE on 256 GPUs (EP 8..256 in both placements: EP inside TP / EP on the
   rails = Opus "mixed" / "scaleout", `tools/gen_opus_moe.py`), GPT-80B TP32 on 512 B200 (needs: a cluster with 32- or
   72-GPU NVLink domains (`GPUS_PER_SERVER`), a B200 roofline (spec values, computed), 800 G links + PCIe Gen6 as the
   sweep's 800 G point).
3. GPU-count sweep (weak scaling, 64 -> 512 / 1024 GPUs) for one dense and one MoE workload.
4. Then the figure: Fig 14 extended or a second panel; text with model labels.
Decisions needed: the exact points of 2-3, B200 parameters, whether the interleaving change (Section 7.1) is adopted.

## 9. Files

astra-sim-fresh (not committed): `astra-sim/network_frontend/analytical/{loom/main.cc, loom/LoomNetworkApi.cc,
include/loom/LoomNet.hh, include/loom/LoomNetworkApi.hh, CMakeLists.txt (+ .pre_loom_20261020)}`;
`astra-sim/workload/{HardwareResource.{cc,hh} (+ .pre_pergroup_20261020), Workload.cc (+ .pre_issuelog_20261020)}`;
`extern/network_backend/analytical/{common/event-queue/EventQueue.cpp, include/.../EventQueue.h} (+ .pre_map_20261020)`.
e8-astrasim: `ANALYTICAL.md`, `run_an.sh`, `tools/{an_replay.cc, an_loomreplay.cc, build_an_replay.sh, build_an.sh, run_an_jobs.sh,
run_an_all.sh, order_coll.py, order_traces.sh, alpha_beta.py, cmp_an_ns3.py}`, collectors with `LOGS=` / `AN=1`
(+ `.pre_an_20261020`), `tools/plot_eval.py` with `MODEL=an` (+ `.pre_an_20261020`; default unchanged), data `e8_an/`
(ALL.txt, preview/), logs `runs_an/`, ordered traces `traces/e2e_ord/`. val_model: `run_val_an.py`, `run_sweep_an.py`,
`runs_an/`, `sweep_an/`. Model header backups `LoomNet.hh.pre_*` (each step tonight). Nothing committed.
