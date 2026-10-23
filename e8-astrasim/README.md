# E8: ASTRA-sim + ns-3 with a GPU host interface (pull = RDMA NIC, push = Loom)

Model record (what is modelled, why, validation, change log): MODEL.md.

Clone: /scratch/harshanavkis/loom-proj/astra-sim-fresh (astra-sim 4ce9ecfe,
analytical backend v2.2.1). Our changes are on local branch `loom` in the
clone and in its ns-3 submodule (extern/network_backend/ns-3); never pushed.
(The old /scratch/harshanavkis/loom-proj/astra-sim is the old Loom branch: ignore.)

Everything runs through the nix shell in this directory (`shell.nix`, GC root
`.gcroots/shell`): the scripts re-exec through it, and the ns-3 binary only
finds protobuf/abseil/MPI there.

    build_ns3.sh                     # ns-3 backend (AstraSimNetwork), a few min
    run_ns3.sh example               # bundled 16-NPU 1 MiB ring all-gather: 1850320 ns
    run_ns3.sh <name> <workload prefix> <system.json> <ns3 config.txt> <logical topology.json> [comm groups.json]
    build.sh / run.sh                # analytical backend (bundled examples: ring_rs_4 22240,
                                     #   ring_ag_16 323560, hgx_h100_ar_8 57426, custom_ar_8 90174 ns)

ns-3 runs log to runs/ns3_<name>_<time>.log, with a per-run copy of the ns-3
config and its outputs in runs/ns3_<name>_<time>/. `NS3_TIMEOUT=<s>` kills a
run that takes longer.

## NIC model (HOST_IF_MODE nic, 2026-10-10): the RDMA baseline, validated on dispatch/combine

Replaces the per-message `pull` model below (its QP-per-message flows and lumped delays were wrong;
the 2026-10-09 transport validation ran at RoCE MTU 1024 because steve's CX-7 netdevs were at 1500
until 2026-10-09 22:16: invalid). The ASTRA-sim frontend does not drive it yet (next step).

Mechanism (ns-3 rdma-hw.cc "nic mode", pcie-fabric.{h,cc}): persistent QPs (RdmaHw::NicQp); the
poster writes WQEs into the send queue (NicPost) and rings doorbells (NicRing, an 8 B MMIO write
over PCIe); the NIC fetches the WQEs it was rung for (one read per QP at a time, up to
`WQE_FETCH_MAX`), reads each payload (`PCIE_MRRS` per read), sends a packet once its bytes are in
(`NIC_TX_NS` later; packets never cross a WQE's end); the responder writes data into memory
(`NIC_RX_NS` after the packet, then the PCIe write) and runs an RDMA atomic as read + write (the
H200 is no PCIe AtomicOp completer; the CX-7 reports ATOMIC_HCA), ACKing after the read; the
requester writes a CQE per WQE (`NIC_RX_NS` after the ACK). PCIe: each transaction takes a measured
latency plus its bytes on the source's outgoing and the destination's incoming link (one FIFO per
direction, `PCIE_LINK_GBPS`); links only add delay when busy (on steve they never bind).

| key | default | meaning |
|---|---|---|
| `HOST_IF_MODE nic` | | this model |
| `NIC_TX_NS`, `NIC_RX_NS` | 0, 0 | NIC pipelines: bytes in -> packet may leave; packet/ACK in -> its action |
| `WQE_BYTES`, `WQE_FETCH_MAX` | 64, 64 | WQE size, WQEs per fetch |
| `ATOMIC_WIRE` | 20 | atomic request bytes on the wire besides an 8 B data packet |
| `NIC_POSTER`, `NIC_SQ_MEM`, `NIC_BUF_MEM`, `NIC_CQ_MEM`, `NIC_RX_MEM` | gpu | who rings (gpu/host); where the SQ, send buffers, CQ, receive buffers live |
| `NIC_BF` | 0 | BlueFlame: the WQE goes with the doorbell (no fetch) |
| `INLINE_MAX` | 0 | payloads up to this ride in the WQE |
| `PCIE_LINK_GBPS` | 57.6 | payload rate per link direction (Gen5 x16 x 256/280) |
| `PCIE_RD_GPU_NS`, `PCIE_RD_HOST_NS` | 1350, 680 | NIC read of GPU / host memory: issue -> data |
| `PCIE_WR_GPU_NS`, `PCIE_WR_HOST_NS` | 700, 340 | NIC write -> visible to the GPU's SMs / the CPU |
| `PCIE_DB_GPU_NS`, `PCIE_DB_HOST_NS` | 700, 340 | GPU / CPU store (doorbell) -> at the NIC |
| `NODE_HOST <node> <host>` | node | the node's NIC sits on that host's PCIe (steve: both ports on one) |
| `RX_POLL_NS`, `CQE_POLL_NS`, `WIRE_BYTES_PER_PACKET`, `PCIE_MRRS` | | as below |

steve config: e8/cfg/steve_nic/base.txt (topology e8/topo/steve_cable.txt: port0 -> port1 cable,
no switch, 200G, MTU 4096, 82 B per packet). Every latency comes from single-message measurements
(sources in the file): NIC reads host 670 / GPU 1350 ns (nic_post, MTU 4096), NIC_RX_NS 590
(nic_post inline post->CQE 2.02 - perftest 8 B one-way 1.42), NIC_TX_NS 260, host one-way 280,
GPU doorbell + write visible to a polling SM 1290 split 645/645 (DeepEP single put 5.45 us).

    build_replay.sh                         # ns-3 LoomReplay + AstraSimNetwork
    build_ns3_opt.sh                        # the same, ns-3 "optimized" profile, in a copy (astra-sim-opt):
                                            #   identical results, ~15% faster; use with NS3_BIN=<binary>
    tests/run_val_nic_micro.sh              # the single-message inputs + the 7168 B DeepEP put
    # steve: sudo bash ~/loom-experiments/gpu-posted/run_bd_trace.sh   (dispatch_bd_ring: Section 2
    #   dispatch/combine runs, BD_DEBUG per-message trace + every doorbell rung -> bd_trace_ring/)
    python3 -I tools/bd_trace_to_replay.py ~/loom-experiments/gpu-posted/bd_trace_ring val_dispatch/<name>
    tests/run_val_dispatch.sh val_dispatch/<name> [config]   # LoomReplay per run -> tools/val_dispatch.py table

LoomReplay (ns-3 scratch/loom-replay.cc) replays one measured run: the GPU side (posts, measured
doorbells, signals) as stamped by the benchmark, the NIC/PCIe/wire simulated; out: per message when
the receiver sees it and its CQE, plus first/last arrival, drain, signal seen, reap.

Results 2026-10-10 (val_dispatch/20261010_ring, 20 runs per point, medians; model vs measured):
- single messages (tests/val_nic_micro_*.tsv): the 8 inputs within 1%; DeepEP 7168 B put -> CQE
  5.68 vs 6.13 us (-7.3%, prediction).
- receiver sees every signal (Fig 3's end point), dispatch and combine, ordered (DeepEP V1, 3 QPs per
  destination) and flush (V2.5, QPs per warp), 1/16/128 tokens: +0.9..-7.8%; 16 and 128 tokens
  within +-1.4%. Last arrival -0.2..-8.7% (16/128 tokens within -2.9%); reap -0.5..-7.7%.
- 1 token is the weakest (-6..-12% on the last arrival): measured arrivals spread ~2 us over the QPs
  with tight doorbells, the model 0.6 us. Flush drain at 1 token (-12/-30%) includes CTAs still
  waiting on DeepEP's post lock after the completions are in (GPU side).
- every error is on the RDMA-favourable side (model faster than measured).
- with rule-based doorbells (no ring log, val_dispatch/20261010) flush at 1 token was -18..-41%: the
  flush CTAs' doorbells wait 2-10 us on DeepEP's per-QP post lock (20 CTAs ring all 24 QPs), so
  the GPU-side doorbell times must be measured inputs.

Loom push what-if (tests/run_push_whatif.sh -> tools/push_whatif.py, val_dispatch/20261010_ring/
push_whatif.tsv): the local runs' GPU side (TMA store issue times and signal time; Loom uses the
scale-up stores) through e8/cfg/steve_nic/push_{250,1000}mhz.txt (stores = posted writes into Loom,
21/7 Loom cycles, same wire and receive-side writes; signals plain writes behind the data; Loom
buffers without limit, so the sender-side back-pressure at large sizes is not in it). Receiver sees
every signal, us (local measured / RDMA ordered measured / flush measured / push model 1 GHz):
dispatch 1 tok 4.9 / 18.2 / 30.2 / 6.0, 16 tok 5.4 / 38.5 / 47.4 / 29.3, 128 tok 12.5 / 213 / 221 / 203;
combine 1 tok 3.6 / 19.2 / 30.2 / 6.2, 16 tok 6.1 / 65.3 / 74.9 / 55.4, 128 tok 27.7 / 416 / 450 / 403.
Loom's clock (250 MHz vs 1 GHz) changes these by < 0.1 us. From 16 tokens on, both are bound by
the 200G link (dispatch: 26 us at 16 tokens, 200 us at 128).

Sender side (Fig 3's end point: busy until the arrival signal is issued), tools/sender_side.py ->
sender_side.tsv, us, medians of the bd_trace_ring runs (local / RDMA ordered signal / ordered with
completions collected, measured & model / flush, measured & model / ideal Loom model): dispatch 1 tok
4.6 / 9.2 / 19.1 & 17.6 / 25.9 & 23.4 / 4.6, 16 tok 5.1 / 13.1 / 39.3 & 38.7 / 42.9 & 40.8 / 12.8,
128 tok 12.3 / 27.1 / 213.8 & 212.7 / 216.3 & 214.8 / 87.4; combine 128 tok 27.4 / 38.4 / 416.6 &
414.8 / 446.0 & 432.4 / 171.8. Ideal Loom = Loom takes every store at once (no window, the first
version on purpose); the signal store leaves the GPU over its PCIe link (57.6 GB/s) behind the data,
so from 16 tokens on the Loom sender is PCIe-bound (LoomReplay's sender_out). Back-pressure (Loom's
window) comes later.

ASTRA-sim on the NIC model (frontend entry.h nic_send, 2026-10-10): with HOST_IF_MODE nic every
cross-server message goes on one QP per GPU pair as puts of MSG_SPLIT_BYTES (0 = one put), each rung
as posted (GPU posting costs nothing, owner's call), then an 8 B signal write behind them; the
receiver has the message when it sees the signal; the sender is released when it may reuse its
buffer: RDMA at the signal's CQE (SENDER_RELEASE post: at once), Loom (NIC_PUSH 1, with the push
config's NIC_BF 1 + INLINE_MAX) when its stores have left the GPU (no CQEs). tests/run_nic_frontend.sh
(rank 0 -> rank 1, 8 B .. 4.9 MB in 7168 B puts) gives the same times as LoomReplay to the ns, e.g.
RDMA 4.9 MB sender 206.47 / receiver 206.34 us, Loom 86.06 / 201.62.

Zero-GPU-cost comparison of the Section 2 dispatch/combine (tools/gen_zero_gpu.py,
tests/run_model_compare.sh -> val_dispatch/zero_gpu/compare.tsv; 8 QPs, one per destination): sender
busy until the signal is issued (RDMA ordered collects completions before buffer reuse) and
receiver sees every signal, us, RDMA ordered / flush / ideal Loom: dispatch 1 tok sender 7.3 (reap) /
7.3 / 0.8, receiver 7.0 / 12.2 / 3.3; 16 tok 31.5 / 31.5 / 11.4 and 31.4 / 36.3 / 27.9; 128 tok
205.2 / 205.2 / 86.1 and 205.1 / 210.1 / 201.7.

Zero GPU-side cost (owner 2026-10-10: GPU posting is not modelled, both systems hand every message
over when the op starts): tools/gen_zero_gpu.py + tests/run_model_compare.sh -> val_dispatch/zero_gpu/
compare.tsv (one QP per destination, a doorbell per put, 8 B signal write behind the data).

ASTRA-sim frontend on the NIC model (HOST_IF_MODE nic, entry.h nic_send): a cross-server message goes
on one QP per GPU pair as puts of MSG_SPLIT_BYTES (each rung when posted) and an 8 B signal behind
them; the receiver has it when it sees the signal; the sender is released when it sees the signal's
CQE (RDMA; SENDER_RELEASE post: at once) or when its stores are out of the GPU (NIC_PUSH 1, Loom).
tests/run_nic_frontend.sh: ASTRA-sim = LoomReplay to the ns for 8 B .. 4.9 MB, RDMA and Loom.
Clusters: tools/gen_cluster.py variants rdma / loom / loom250 (steve's NIC and PCIe latencies; links
carry cable + switch only, e.g. --host-ns 300 --fabric-ns 300); tests/run_scale_sanity.sh (EP16
dispatch, 1/16/128 tokens: RDMA 7.3 / 21.6 / 136.4 us, Loom 3.2 / 18.7 / 134.3, slowest GPU).

## MoE dispatch / combine at scale (run_moe.sh, 2026-10-10)

Owner-approved cluster: 8 GPUs per server (NVLink, frontend path), one 400G NIC / Loom per GPU,
PCIe Gen5 x16 with steve's latencies, MTU 4096, leaf-spine full bisection (32 GPUs per leaf),
~300 ns per switch in the link delays (host 155, fabric 305 ns); no congestion control (CC_MODE 12,
PFC only). Workload tools/gen_moe.py: top-8 of 256 experts per token, one send per (src, dst) with
one put per token (7168 / 14336 B), all at time 0, GPU posting free, ASTRA_CONCURRENT_SENDS=1.
tools/collect_moe.py -> e8/moe/moe.tsv: over the GPUs, max last send release (sender busy) and max
last arrival (delivered). RDMA / ideal Loom, us: dispatch EP16 1 tok 8.0/0.6 and 7.1/3.1, 128 tok
84.2/55.1 and 83.8/71.6; EP256 1 tok 10.5/1.0 and 9.0/5.6, 16 tok 40.5/16.2 and 39.0/35.9, 128 tok
191.9/127.3 and 190.6/191.2; combine EP256 128 tok 351.1/266.5 and 350.2/380.2. Where Loom delivers
later (combine EP128/256, >= 16 tokens, 0.9x): ~5x more PFC pauses (EP256 t128: 9952 vs 2019) -
ideal Loom injects at line rate at once, RDMA is paced by its reads; congestion control not modelled
yet (DCQCN for both = next sensitivity).
Two model artifacts found and fixed on the way (both made one destination's data come in a block):
the frontend now posts a GPU's concurrent sends interleaved put by put (nic_flush), and the NIC
issues payload reads round robin over its QPs (NicReadPump; steve validation unchanged).

## Collectives at scale (run_coll_nic.sh, 2026-10-10)

Same clusters and variants as MoE; ASTRA-sim's NCCL ring (all-reduce, all-gather) and direct
all-to-all; sizes per GPU (all-gather: each GPU's INPUT, ASTRA-sim Ring.cc: output = size x GPUs).
tools/collect_coll_nic.py -> e8/coll/coll.tsv (last GPU's finish). RDMA / ideal Loom, us, 16 | 64 GPUs:
all-reduce 1 KiB 101.5/62.4 | 422.0/265.9 (1.6x: every ring step pays the initiation), 4 MiB
193.7/164.5 | 462.8/302.5, 64 MiB 2586/2601 | 2718/2718 (1.0x); all-gather 1 KiB 50.8/31.3 |
211.1/133.3, 4 MiB 1296/1310 | 5426/5440, 64 MiB 20649/20937 | 86711/86998 (1.0x); all-to-all 1 KiB 13.1/3.4 | 14.8/5.3 (3.9x | 2.8x),
256 KiB 14.8/6.4 | 17.6/9.6, 64 MiB 711/843 | 1235/1258 (0.84x | 0.98x: PFC with no CC, as MoE).

## Host interface (ns-3 config keys; pull/push = the OLD per-message model)

Without `HOST_IF_MODE` the simulator behaves exactly as upstream (the sender
and the receiver both learn of a message when its last ACK returns).

| key | default | meaning |
|---|---|---|
| `HOST_IF_MODE` | none | `pull` (GPU-initiated RDMA NIC) or `push` (Loom) |
| `PCIE_GBPS` | 63 | raw PCIe bandwidth per direction (Gen5 x16) |
| `PCIE_LAT_NS` | 380 | posted write, one way (doorbell, receive-side write, CQE) |
| `PCIE_RD_RTT_NS` | 550 | read request to completion (WQE fetch, payload read) |
| `PCIE_MPS`, `PCIE_TLP_OVH` | 256, 24 | payload and overhead bytes per TLP |
| `HIF_CHUNK` | 4096 | bytes per simulated PCIe transfer |
| `POST_NS` | 700 | pull: WQE build + fences + doorbell store on the GPU |
| `STAGING_GBPS` | 0 (off) | pull: copy into the pinned send buffer |
| `POST_LANES` | 0 (unbounded) | pull: GPU posts in parallel |
| `SQ_DEPTH` | 0 (unbounded) | pull: messages outstanding per NIC until their CQE |
| `PCIE_MRRS`, `PCIE_RD_INFLIGHT` | 512, 128 | pull: read size and reads in flight |
| `INLINE_MAX` | 0 | pull: payloads up to this ride in the WQE |
| `CQE_POLL_NS` | 0 | pull: GPU sees the CQE this long after it lands |
| `WQE_FETCH` | 1 | pull: 0 = the WQE arrives with the doorbell (MMIO / BlueFlame / Coyote) |
| `MSG_SPLIT_BYTES` | 0 (off) | split each cross-server message into puts of this size (one WR per 64 B, one put per token) |
| `RX_POLL_NS` | 0 | both: receiver notices the data this long after it lands |
| `WIRE_BYTES_PER_PACKET` | 0 (ns-3 headers) | per data packet on the wire besides payload; 82 = RoCEv2 over Ethernet (preamble+IFG 20, Eth+FCS 18, IP 20, UDP 8, BTH 12, ICRC 4) |
| `SENDER_RELEASE` | cqe | pull: `post` = the sender goes on once posted (DeepEP low latency); the slot still frees at the CQE |
| `LOOM_CLK_MHZ`, `LOOM_TX_CYC`, `LOOM_RX_CYC` | 250, 21, 7 | push: Loom pipeline (E3 cycles) |
| `LOOM_TX_BUF` | 0 = line rate | push: unacked bytes Loom accepts per message |
| `PUSH_GBPS` | 0 = PCIe | push: rate the source writes into the window (testbed CPU stores) |
| `GPUS_PER_SERVER` | 0 (off) | messages inside a server take NVLink in the frontend, not ns-3 |
| `NVLINK_GBPS`, `NVLINK_LAT_NS` | 400, 936.25 | NVLink path (ASTRA-sim HGX-H100-validated) |

Per cross-server message of S bytes:
- **pull:** GPU copy (S / `STAGING_GBPS`) + `POST_NS` → doorbell `PCIE_LAT_NS` →
  WQE fetch `PCIE_RD_RTT_NS` → payload reads (one round trip + S over PCIe,
  `PCIE_RD_INFLIGHT` x `PCIE_MRRS` bytes outstanding) → a packet leaves once
  its bytes are at the NIC → network (ns-3) → receiver write `PCIE_LAT_NS`:
  the receiver has it → last ACK → CQE `PCIE_LAT_NS` + `CQE_POLL_NS`: the
  sender is released and its send queue slot is freed.
- **push:** the GPU writes S into the window (posted, S over PCIe), Loom has
  each piece `PCIE_LAT_NS` + `LOOM_TX_CYC` later → network → `LOOM_RX_CYC` +
  receiver write `PCIE_LAT_NS`. The sender is released once its last write
  has left the GPU; Loom accepts writes only while its unacked bytes fit.

Both modes share one PCIe link per GPU (round robin over messages), the
network, RoCE transport, ACKs and congestion control. ASTRA-sim keeps one
communication op in flight per GPU (receives excepted, HardwareResource.cc),
so a sender's release gates its next op.

## Tests

    tests/run_hif_p2p.sh [count] [--serial] [sizes...]   # 2 GPUs, rank 0 -> rank 1 (MODES="none pull push")
    tests/run_hif_coll.sh <ALL_TO_ALL|...> <bytes> <cfg>...   # 16 GPUs, configs e8/cfg/test_16n_<cfg>.txt

Results 2026-10-08 (1 us links, 400G; ns, sender / receiver):

| size | none | pull | push |
|---|---|---|---|
| 8 B | 4004 / 4004 | 6564 / 4562 | 0 / 2874 |
| 4 KiB | 4110 / 4110 | 6741 / 4739 | 71 / 3051 |
| 64 KiB | 5399 / 5399 | 8030 / 6028 | 1136 / 4340 |
| 1 MiB | 26043 / 26043 | 28674 / 26672 | 21765 / 24984 |

8 B pull receiver = 700 + 380 + 550 + 550 + network 2002 + 380; push receiver =
380 + 84 + 2002 + 380 + 28. Both reach line rate at 1 MiB. NVLink path
(`GPUS_PER_SERVER 2`): 8 B 1 / 937, 1 MiB 2622 / 3558. 16-GPU direct all-to-all,
1 KiB per peer (500 ns links): none 2353, pull 3928, pull `SQ_DEPTH 4` 17719,
pull `POST_LANES 1` 13420, push 2240.

## Transport validation (the OLD model vs plain RDMA, 2026-10-09; INVALID: RoCE MTU was 1024)

    ssh steve 'sudo bash ~/loom-experiments/transport-val/run.sh [t1 t2 t3 t4 nvshmem]'   # perftest + NVSHMEM on steve
    nix-shell shell.nix --run "python -I tools/parse_transport.py"   # -> tests/transport_measured.tsv
    tests/run_val_transport.sh     # T1 latency vs size (host/GPU memory), T2 bandwidth vs size -> tests/val_transport_<time>.tsv
    tests/run_val_gpuput.sh        # GPU-initiated put + completion (DeepEP, NVSHMEM post paths) -> tests/val_gpuput_<time>.tsv

steve: H200 + CX-7, port0 -> port1 loopback, 200G, RoCE MTU 1024. Fits: loopback hop 364 ns (host
write 8 B), GPU payload read 1090 ns (perftest; nic_post said 1340, the RDMA-favourable one is
used), perftest CPU loop 370 ns per message (64 B). Model vs measured: host write -5..+5%, host
write+imm -7..+7%, GPU write+imm -3..+3% (8 B..8 MiB), bandwidth -3..+3% (+7% at the 8 KiB knee),
GPU-initiated put+completion DeepEP -6%, NVSHMEM -9..-11% (its quiet). No per-QP slowdown on the
CX-7 from 1 to 256 QPs (T3). Not yet compared: T4 latency under load.

## Validation (step 4)

    tests/run_val_h200ib.sh       # pull vs 2610.01380 Table 3 -> tests/val_h200ib_<time>.tsv
    tests/run_val_testbed.sh      # pull + push vs testbed E2 -> tests/val_testbed_<time>.tsv
    nix-shell shell.nix --run "python -I tools/plot_val.py"   # -> figures/val_{testbed,h200ib}.{png,pdf}

**A. H200 + CX-7, 200G IB, 8 B (2610.01380 Table 3).** Configs
e8/cfg/val_h200ib_{inline,noinline}.txt (defaults: POST_NS 700, PCIe 380/550 ns,
500 ns links = the one fitted parameter). 2026-10-08, paper / model ns:
put+completion inline 4030 / 4018 (fitted), non-inline 4640 / 4568, difference
610 / 550, round trip 6850 / 6028 (-12%: the receiving GPU's flag poll and turn
around, not modelled; `RX_POLL_NS`, same for both modes).

**B. Testbed E2 one-way latency (U280s, 100G, ping-pong / 2).** Configs
e8/cfg/val_testbed_{pull,push}.txt: PCIe Gen3 x16 15.75 GB/s, 380/550 ns;
RDMA = one WR per 64 B (MSG_SPLIT_BYTES 64), SQ 32, one CPU poster (POST_LANES 1,
POST_NS 350 measured), WQE by MMIO (WQE_FETCH 0); Loom = CPU stores. Fitted:
link latency 1500 ns (Loom flag), PUSH_GBPS 0.233 (Loom 64 KiB). Measured /
model us, RDMA: 4.81/4.67, 5.30/4.68, 5.51/5.73, 10.19/9.93, 25.5/26.73,
90.3/93.93, 356.2/362.73 (8 B..64 KiB, -12%..+5%, all predicted); Loom: 3.90/3.91,
4.26/4.16, 4.20/5.02, 4.84/8.44, 16.5/21.88, 69.6/74.64, 281/285.6 (256 B-4 KiB
too slow: a constant CPU store rate misses write-combining bursts; a testbed CPU
effect, the GPU push path is PCIe-bound).

## End-to-end runs (step 5)

    tools/prep_trace.sh <set dir> <rank prefix> <name>   # WG trace -> chakra-traces/fixed/<name> (+ comm_groups.json)
    nix-shell shell.nix --run "python -I tools/gen_cluster.py <name> <gpus>"   # -> e8/clusters/<name>/
    campaign.sh [workload...]                            # every run, one tmux session each (run_e8.sh)
    nix-shell shell.nix --run "python -I tools/collect_e8.py"   # -> results/e8.tsv (progress while running)
    nix-shell shell.nix --run "python -I tools/plot_e8.py"      # -> figures/e8_iteration.{png,pdf}

Cluster (gen_cluster.py): servers of 8 GPUs (NVLink path in the frontend), one
400G NIC/Loom per GPU on a leaf (32 GPUs per leaf, full-bisection spines above
that), host links 500 ns (the 2610.01380 fit, includes NIC pipelines), fabric
links 200 ns, MTU 4096, PCIe Gen5 x16 63 GB/s, 380/550 ns. Variants: none
(upstream), pull (POST_NS 700, mini-gda), pull_deepep (3070), pull_nvshmem
(7330), push (Loom). System config e8/cfg/system_nccl.json = ASTRA-sim's
HGX-H100-validated with direct all-to-all (NCCL sends to every peer).
Workloads (Chakra WG traces, measured H200 compute): mixtral8x22b (32 GPUs,
TP4 x EP8, c32), llama3_70b (16 GPUs, TP16 across 2 servers, c16).

## Tools

    tools/gen_p2p.py, tools/gen_coll.py      # test traces (gen_p2p --pingpong: round trips)
    tools/plot_val.py                        # validation figures
    tools/gen_cluster.py, tools/prep_trace.sh, tools/collect_e8.py, tools/plot_e8.py   # end-to-end runs
    tools/fix_ctrl_deps.py                   # real Chakra WG traces: dangling deps, metadata nodes
    tools/infer_comm_groups.py               # comm groups from pg_name use
    tools/fill_pg_name.py                    # a collective missing its pg_name
    tools/et_summary.py                      # comm/compute summary of a trace

## Paper evaluation (2026-10-11)

    tests/run_val_e4.sh [~/loom-experiments/e4/<run>]   # Loom model vs the E4 prototype (LoomReplay, e8/cfg/testbed_e4/push.txt;
                                                       #   one fitted latency = the 0-token flag) -> val_e4/<run>/compare.tsv
    nix-shell shell.nix --run "python3 -I tools/plot_eval.py ~/loom-paper/plots <png dir>"
        # paper figures (jigsaw / Fig 3 style): eval-validation (RDMA model vs Section 2 runs + Loom model vs E4),
        # eval-moe (e8/moe/moe.tsv), eval-coll (e8/coll/coll.tsv), eval-micro (E1/E2 from ~/loom-experiments);
        # prints every number the text quotes. Wrappers with provenance: ~/loom-paper/plots/eval-*.tex
    run_dcqcn.sh [parallel]      # DCQCN for both (CC_MODE 1) over the MoE + collective jobs -> e8/{moe,coll}_dcqcn/;
                                 #   NOT run yet: the inherited 100G DCQCN defaults crawl at 400G (MODEL.md section 4)
