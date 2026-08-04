# Loom simulation package (ASTRA-sim)

Simulates Loom — a top-of-rack switch that routes peer-memory transactions
over the rack's scale-up fabric or encapsulates them onto per-binding RoCE RC
connections — against endpoint-RDMA baselines. Companion to the paper repo's
`design-docs/simulation-eval-plan.md`.

## Modeling approach: reuse over new code

The Loom switch is modeled as **constants folded into existing ASTRA-sim
knobs** — the same technique the in-repo `HGX-H100-validated.yml` uses (its
936.25 ns dimension latency *includes* NVSwitch traversal):

| Loom / baseline feature | ASTRA-sim mechanism (existing) |
|---|---|
| Switch pipeline latency (per-stage: lookup/queue/encap/roce/translate/forward, one param per hw-controller block) | folded into per-dimension `latency` (network YAML) |
| Encapsulation goodput (3-field header + coalescing efficiency at the run's message-size mix) | folded into per-dimension `bandwidth` |
| Posted-write source-local completion | eager mode (default; sender completes at injection) |
| Baseline RDMA large-message handshake | `--rendezvous-protocol true` (existing CLI flag) |
| Per-message endpoint cost (GPU doorbell/QP kernel, CPU proxy post+poll) | `endpoint-delay` (system JSON) |
| Baseline SM reservation for communication | COMP durations scaled at trace-generation time (`--sm-total/--sm-comm` in the workload generator) |
| Loom zero-XPU-compute communication | unscaled COMP durations + `endpoint-delay = 0` |

New code in this package is therefore **config generation only**; the
simulator is unmodified. (Congestion-tier VOQ modeling — phase S4 — will be
the first real backend change, in `congestion_aware/Device`.)

## Files and folders (what each is)

```
examples/loom/
├── README.md                  this file: run guide, constants, VOQ explainer
├── CHECKPOINT.md              LIVING: the single state doc. Sec 5 results are
│                              GENERATED; 5a Phase-A findings; 5b catalog;
│                              6 next steps; 8 code->real-system map;
│                              9 review verdicts + reviewer defenses
├── ANALYTICAL-MODEL.md        LIVING: equations, constants + decisions ledgers
├── summarize_results.py       regenerates CHECKPOINT sec 5 from results/*.csv
│
├── gen_network_config.py      network-YAML generator (loom/baseline/ideal);
│                              per-stage pipeline params, one per hw block
│                              (no network/ dir: every script generates its
│                              configs at run time. The committed samples
│                              rotted to a dead model and were deleted.)
├── system/                    endpoint models (system JSONs):
│   ├── loom.json                Loom: endpoint-delay 10ns, 2-dim collectives
│   ├── loom_1d.json             1-dim variant (congestion-aware runs)
│   ├── loom_roofline.json       + roofline peak-perf 989 (STG workloads)
│   ├── baseline_gpu_rdma.json   B1 (its rdma-init lives in the net YAML)
│   ├── baseline_gpu_rdma_roofline.json  B1 + peak-perf 839 (20/132 SM tax)
│   ├── baseline_cpu_proxy.json  B2 (run with --rendezvous-protocol=true)
│   └── ideal_rdma.json          B3 upper bound
├── remote_memory/
│   └── loom_peer_reads.json   LOOM_PEER_READS read-credit config
│                              (finite cap; >= outstanding loads = infinite)
│
├── fetch_stg.sh               pins STG (workload generator) into extern/
├── gen_stg_workloads.sh       moe/dense presets w/ published model dims
├── workload/
│   ├── gen_p2p_patterns.py    single/incast/victim flow stimulus (iperf-
│   │                          category microbenchmarks, NOT applications)
│   └── gen_read_pattern.py    independent MEM_LOADs (credit experiments)
│
├── run_smoke.sh               endpoint models on shipped all-to-all ETs
├── run_victim.sh              OPTIONAL standalone demo (not in run_all;
│                              paper claims no congestion isolation)
├── run_sweep_credits.sh       S-5: read-credit cap sweep (1..64 + infinite)
├── run_sweep_tpipe.sh         STANDALONE (not in run_all): break-even
├── run_regime_map.sh          STANDALONE (not in run_all): gain vs
│                              comm-boundedness. Superseded for most uses
│                              by the apps decomposition in CHECKPOINT 5
├── run_matrix.sh              collectives x sizes x topologies x systems
├── run_apps.sh                Mixtral MoE + GPT-3 dense at two scales
├── run_f2.sh                  F2 control: matrix+apps under direct algorithms
│                              (SUFFIX=_direct selects system/*_direct.json)
├── run_all.sh                 whole suite -> results/*.csv (in Docker)
├── run_all_docker.sh          one-command host entry (build image, run, plot)
├── plot_results.py            results/*.csv -> results/*.pdf
├── results/                   CSVs + PDFs (gitignored; root-owned by Docker)
└── figures/                   drawio sources: sim setup stack, topology,
                               per-route latency breakdown
```

Code living OUTSIDE this folder (the simulator extensions):

- `extern/network_backend/analytical` (fork, branch `loom-sim`) — switch
  egress policy: `EgressPolicy {PerDestination = VOQ (stock), SharedFifo =
  HoL strawman}`; `switch_egress:` YAML key (Link/Device/Topology/
  NetworkParser/Helper).
- `extern/remote_memory_backend/analytical` (fork, branch `loom-sim`) —
  `LOOM_PEER_READS` memory type: per-NPU read-credit cap.
- `astra-sim/workload/HardwareResource.cc` (this repo) — MEM_LOAD/STORE
  hold no GPU issue slot (fabric credits, not issue serialization, are the
  limit).
- `/CLAUDE.md` (repo root) — standing working rules.

See CHECKPOINT.md section 8 for what each piece models in the real system.

## Workload provenance

Three tiers, all Chakra ET format (the simulator sees no difference):

1. **Microbenchmark stimulus only** (`workload/gen_*.py`): victim/incast/
   single-flow and read patterns for mechanism experiments (isolation,
   credits) - the same category as the repo's shipped generator_scripts.
   Application workloads are NEVER hand-authored here: MoE and dense LLM
   traces come exclusively from tiers 2 and 3.
2. **STG-generated realistic workloads** (`fetch_stg.sh` +
   `gen_stg_workloads.sh`): astra-sim's own generator (STAGE) derives the
   full compute+comm graph from model dimensions and a parallelization
   (DP/TP/PP/SP/EP incl. `--model_type moe`); shapes set from published
   configs (DeepSeek-V3, Mixtral, GPT-3). Use roofline system configs
   (`system/*_roofline.json`) - STG compute nodes carry num_ops, and the
   SM-reservation baseline is expressed by scaling `peak-perf` (989 vs 839
   TFLOPS = 20/132 SMs reserved).
3. **Captured PyTorch ETs** (upgrade path, needs GPUs): chakra_trace_link +
   chakra_converter on a real DeepEP/NCCL run - the gold standard for the
   camera-ready; same file format, drop-in.

## Topology fairness (what is and is not modeled)

- Baseline shape = rail-optimized cluster (GPU i of each rack on rail switch
  i, one NIC per GPU); Loom shape = rack fabric through the ToR + ToR
  uplinks. Identical physical rates on both (equal-wires framing; Loom also
  deletes M NICs per rack, so equal-cost would favor Loom - stated in prose,
  not modeled).
- Loom ToR uplink aggregate = the baseline's M NICs (`--uplink-oversub
  1.0`, equal wires). This is the modelled default and is NOT swept
  (decision 2026-08-04). Rationale: 400 GB/s of uplink for a rack of 8 is
  a small fraction of a modern ToR ASIC's capacity, so non-blocking is an
  engineering choice rather than a stretch; thinning only Loom's uplinks
  while the baseline keeps a dedicated NIC per GPU would compare unequal
  wires; and under equal COST the argument runs the other way, because
  Loom deletes M NICs per rack. If challenged, the answer is that sentence
  plus `--uplink-oversub`, not a figure.
- **Oversubscription is not the same as the dim0/dim1 taper.** Per XPU,
  scale-up is 64 GB/s and scale-out 50 GB/s — PCIe5/NVLink-class vs
  400GbE-class wire rates, paid by BOTH systems and not a provisioning
  choice. Oversubscription is specifically the ToR's downlink:uplink
  ratio, which exists only for Loom because only Loom routes cross-rack
  traffic through a shared switch.
- KNOWN GAP, generous to Loom: a Loom XPU's single fabric port carries both
  intra- and cross-rack traffic, but AstraSim's orthogonal dims let dim1
  traffic bypass dim0 capacity (which matches the baseline's separate NIC,
  not Loom). Shared-edge contention belongs to the congestion tier; until
  then, bound it by charging cross-rack traffic to both dims in a worst-case
  variant.

## Constants: who owns each number

### ⚑ FPGA-owned (MUST be measured on the Coyote/U280 testbed)

One parameter per hw-controller pipeline block; each is read from a
per-stage cycle counter (or ILA) in the vFPGA, then frequency-scaled for
the ASIC argument. Placeholders below hold until then. The stage cycle
counters are IMPLEMENTED and sim-tested in the prototype (Coyote
examples/loom phase 5.3b, 2026-08-03: RO CSR words 48-63 — cycle
counter, FIFO-residency accumulator for t-queue, per-stage cycle sums +
op counts for t-lookup/t-forward/t-encap and the dma/read/fence
classes); only the hardware runs remain to fill this table.

| Config param | hw-controller block | Placeholder | Measured by |
|---|---|---|---|
| `--t-lookup` | Source Validation + Route Selector (range match → binding) | 25 ns | T3, stage counter |
| `--t-queue` | Per-Destination Transmit Queues + Scheduler (uncontended) | 75 ns | T3, stage counter |
| `--t-encap` | TX Encapsulator | 100 ns | T3, stage counter |
| `--roce-stack-ns` | QP Router + RoCEv2 engine per side (RX incl. RX Decapsulator) | 150 ns | Coyote RoCE RC ping-pong floor |
| `--t-translate` | Transaction Generator (Bounds Checker + Address Translation) | 15 ns | T3, stage counter |
| `--t-forward` | Local Forward Engine egress | 10 ns | T3, stage counter |
| Loom goodput vs message size (coalescing curve) | TX Encapsulator coalescer | 0.947 flat (header math only; coalescing benefit deliberately unmodeled) | T2 curve, coalescer on/off |
| read RTT + credit behavior | Read Credit Tracker | remote-mem-latency 5000 ns | T6 |
| B2 rdma-init | (baseline, same hosts) | 2800 ns | testbed CPU-verbs post+poll run |
| substrate floors (fabric store latency, DMA BW, RoCE ping-pong) | — | fabric 500 ns etc. | Phase 0 floors; every Loom number reported as overhead over these |

Derived sums (coarse sweep overrides `--pipe-ns`/`--pipe-local-ns`):
local adder = lookup+translate+forward = 50; source remote pipeline =
lookup+queue+encap = 200; destination = translate+forward = 25 (no range
lookup — the connection identifies the binding).

### Published / validated (no FPGA needed)

| Constant | Value | Named source |
|---|---|---|
| endpoint-delay (ALL systems) | 10 ns | in-repo `examples/system/native_collectives/HGX-H100-validated.json`, validated against real HGX-H100 runs in ASTRA-sim 2.0 (Won et al., ISPASS 2023); ideal B3 keeps 1 ns (event queue rejects 0) |
| scale-up hop (alt. preset) | 936.25 ns / 400 GB/s | in-repo `HGX-H100-validated.yml`, same validation (Won et al., ISPASS 2023) |
| fabric hop (default dim0) | 500 ns / 64 GB/s | PCIe5 x16 switch-class estimate; cross-check: Li, Ammar et al., "Evaluating Modern GPU Interconnect", IEEE TPDS 2020 (PCIe/NVLink microbenchmarks) — [verify exact figure] |
| inter-ToR wire+switch | 600 ns | Broadcom Tomahawk/Trident-class cut-through latency (300–800 ns, vendor datasheets/briefs) + propagation — [verify exact figure] |
| B1 rdma-init (dim1 only) | 2400 ns | from ≈3 µs end-to-end GPU-initiated put: NVIDIA Developer Blog on IBGDA/GPUDirect Async (2022) + NVSHMEM performance docs; swept |
| B2 rdma-init components | 2800 ns | ib_write_lat ≈1.6–2 µs: NVIDIA/Mellanox `perftest` suite (ConnectX-6/7 class); WQE/doorbell costs: Kalia, Kaminsky, Andersen, "Design Guidelines for High Performance RDMA Systems", USENIX ATC 2016; proxy handoff: NCCL net-proxy path |
| RoCE goodput | 0.95 | computed: Eth+IP+UDP+BTH ≈78 B headers on 4 KB MTU (RoCEv2 framing, InfiniBand spec Annex A17) |
| Loom goodput | 0.947 | computed: RoCE goodput × 4096/4108 (12 B ⟨offset·op·len⟩ header, paper design §6.2) |
| B1 SM reservation | 20 of 132 SMs | DeepSeek-AI, "DeepSeek-V3 Technical Report", arXiv:2412.19437; swept {8, 20, 32} |
| workload shapes | Mixtral 8x7B / GPT-3 175B | Jiang et al., arXiv:2401.04088 / Brown et al., "Language Models are Few-Shot Learners", NeurIPS 2020 |
| `--uplink-oversub` | 1.0 (equal wires) | fairness choice (ours); swept |

Entries marked **[verify exact figure]** have a solid source *class* but the
specific value should be pinned to a page/table before the paper cites it.

## Suite inventory (what runs, what it produces)

`run_all.sh` = 4 experiments, **116 simulator invocations**, ~6–9 min in
Docker (matrix dominates). Each experiment writes one CSV to `results/`;
`plot_results.py` renders one PDF per CSV (skips missing ones).

| Experiment | Sim runs | CSV (columns) | Plot | Shows |
|---|---|---|---|---|
| smoke | 4 (Loom,B1,B2,B3) | `smoke.csv` (system, wall_cycles, exposed_comm_cycles) | `smoke.pdf` bars | endpoint-model sanity on shipped ETs (comm-only) |
| sweep_credits | 8 (credits 1…64, 2^20=∞) | `sweep_credits.csv` (read_credits, wall_cycles) | `credits.pdf` log-log line | exact linear concurrency scaling; ∞ = uncapped design |
| sweep_tpipe | 7 (6 t_pipe × Loom + B1) | `sweep_tpipe.csv` (system, t_pipe_ns, wall_cycles) | `tpipe.pdf` curve + B1 line | source-pipeline break-even |
| regime_map | 12 (6 compute-speeds × 2) | `regime_map.csv` (compute_speedup, loom, b1, gain_pct, exposed_comm_pct) | `regime.pdf` gain curve + SM ceiling | where Loom wins: gain vs comm-boundedness |
| matrix | 96 (2 scales × 4 coll × 3 sizes × 4 sys; all `[Switch, Switch]`) | `matrix.csv` (topology, collective, size_mb, system, wall, exposed) | `matrix.pdf` gain grid, one row per size | scale × collective × size coverage (16 and 64 XPUs) |
| apps | 8 (4 configs × Loom/B1) | `apps.csv` (app, ranks, system, wall, exposed) | `apps.pdf` gain bars | Mixtral MoE + GPT-3 at two scales (published shapes) |
| *(F2, answered)* run_f2.sh | 104 (matrix+apps under `direct`) | `matrix_direct.csv`, `apps_direct.csv` | — | ring-vs-direct control; on the deployed topology the two agree to 0.02%, so the question is moot |
| *(optional)* victim | 3 (solo/voq/shared_fifo) | `victim.csv` (case, victim_fct_cycles) | `victim.pdf` bars | standalone demo only; not in run_all |

> **No result numbers in this file.** They live in CHECKPOINT.md section 5,
> which `summarize_results.py` generates from `results/*.csv`. This README
> used to quote results and drifted from the data every time the suite was
> rerun.

### Why each experiment exists

- **smoke** — the cheapest end-to-end correctness check that all four
  endpoint models run and order sensibly on workloads we did not author
  (the repo's shipped ETs). It is the canary: if a model change breaks
  semantics, smoke shifts first — and it did: until 2026-08-04 this was
  the only script reading static configs, which had rotted to a model
  where Loom was slower than the baseline, and the README read that
  backwards as an honest loss. It now generates its configs like every
  other script, and the ordering (B3 < Loom < B1 < B2) is the check.
- **sweep_credits** — demonstrates the read-credit mechanism (paper §6.3)
  is implemented faithfully: the exact 1x/2x/…/64x scaling and the ∞ point
  collapsing onto 64 are arithmetic predictions; matching them exactly is
  the verification. Reads carry no performance claim, so this is a
  mechanism proof, not a benchmark.
- **sweep_tpipe** — the design-headroom question ("how much switch latency
  can Loom afford?") and the FPGA→ASIC bridge: the FPGA will measure one
  point in the slowest plausible technology; the curve is what makes the
  claim robust to realization, and it is the frame the measured dot gets
  placed on (paper fig: break-even). Also the anti-cherry-picking
  guarantee for the t_pipe placeholder (fairness rule F3: swept or
  measured).
- **regime_map** — locates WHERE Loom wins and sets the paper's claim
  structure: gains approach the SM-reclamation ceiling when compute-bound
  and fall to parity when comm-bound. It exists to prevent overclaiming —
  it is the experiment that told us this is a reclamation-plus-parity
  paper, not a bulk-speedup paper.
- **matrix** — the generalization check reviewers ask for ("does it only
  win on one workload/topology?"): 4 traffic patterns × 3 sizes × 4
  topologies × 4 systems. Its job is coverage and finding the negative
  cells, not producing a headline.
- **apps** — the headline: end-to-end iteration time on published model
  shapes (Mixtral 8x7B, GPT-3 175B) at two scales, Loom vs the strongest
  baseline. This is the number the abstract will cite.
- **victim** *(optional)* — insurance, not evidence: the paper claims no
  congestion isolation (moved to Discussion); this demo exists so a
  Discussion challenge ("do known egress disciplines actually handle your
  hazard?") can be answered with a same-day run instead of a rebuild.

## Running everything

**One command (host side)** — builds the Docker image if missing, runs the
full suite, renders plots:

```bash
examples/loom/run_all_docker.sh
# CSVs + PDFs -> examples/loom/results/   (root-owned; chown if needed)
```

**Manual steps** (all sim commands run inside the official image):

```bash
# 1. image (once; official Dockerfile at repo root)
docker build -t astra-sim:loom .

# 2. shell inside the image with the repo mounted
docker run --rm -it -v $PWD:/app/astra-sim astra-sim:loom bash

# 3. build backends (once per source change)
./build/astra_analytical/build.sh -t all       # or congestion_unaware / congestion_aware

# 4. individual experiments (each prints CSV to stdout)
examples/loom/run_smoke.sh          # endpoint models, shipped all-to-all ETs
examples/loom/run_victim.sh         # Sim-V1 VOQ vs shared-FIFO (congestion_aware)
examples/loom/run_sweep_credits.sh  # S-5 read-credit cap
examples/loom/run_sweep_tpipe.sh    # S-1 break-even (STG Mixtral MoE)
examples/loom/run_regime_map.sh     # gain vs comm-boundedness
examples/loom/run_matrix.sh         # patterns x sizes x topologies x systems
examples/loom/run_apps.sh           # Mixtral MoE + GPT-3 dense at 2 scales
examples/loom/run_all.sh            # all of the above -> results/*.csv

# 5. plots (matplotlib; pip3 install -q matplotlib inside the image)
python3 examples/loom/plot_results.py   # results/*.csv -> results/*.pdf
```

**Workloads** (regenerate at other scales):

```bash
examples/loom/fetch_stg.sh                                 # pin STG once
examples/loom/gen_stg_workloads.sh moe   /tmp/moe64 --dp 2 --tp 4 --ep 8
examples/loom/gen_stg_workloads.sh dense /tmp/gpt64 --dp 4 --tp 4 --pp 4
python3 examples/loom/workload/gen_p2p_patterns.py --pattern incast --out /tmp/i
```

**Network/system configs**: `gen_network_config.py --mode {loom,baseline,ideal}`.
Knobs: per-stage pipeline params (`--t-lookup --t-queue --t-encap
--t-translate --t-forward --roce-stack-ns`, one per hw-controller block;
coarse overrides `--pipe-ns`/`--pipe-local-ns` for sweeps), `--loom-goodput
--uplink-oversub --dim1-topology --switch-egress`. System JSONs in
`system/` (roofline variants for STG workloads).

## VOQ vs shared-FIFO egress (what it is, where it applies, how to toggle)

**What a VOQ is.** With a single shared output queue, the packet at the
head blocks everything behind it whenever *its* destination is busy — one
congested destination stalls traffic to every healthy one (head-of-line
blocking). Virtual Output Queuing (VOQ), the standard switch-design remedy,
gives each destination its own egress queue, so a congested destination
grows only its own backlog. In Loom this is the **per-destination transmit
queues**, now presented in the paper as standard deep-buffer switch
engineering (§6.2 transport); the congestion-isolation *claim* was
deliberately moved out of the design into the paper's Discussion section
(2026-07-08): the hazard is the PCIe instance of the documented PFC
congestion-spreading pathology, a body of switch-design work exists for it
(VOQ classics, Jericho-class deep buffers, IEEE 802.1Qcz, BFC), and the
paper claims nothing quantitative about it. The victim experiment below is
therefore a *discussion-supporting demo*, not a headline result.

**Not to be confused with read credits** (paper §6.3, simulated by
`LOOM_PEER_READS`): both defend the fabric's finite credit/tag space, but
against different traffic. VOQ protects **posted writes** — without it, a
congested destination fills switch buffers until link-level credit
withholding stalls the source XPU's whole link (PCIe backpressure can only
say "stop everything"). Read credits protect against **non-posted reads** —
each outstanding read holds a completion tag/credit for the full
(cross-rack) round trip, so an uncapped stream of remote reads would
exhaust the fabric's tag space; the budget makes further reads wait
instead.

**Where it is used in the simulation.** Only in the **congestion-aware**
binary (`AstraSim_Analytical_Congestion_Aware`) — the tier that actually
models queues. It backs the isolation experiments (`run_victim.sh`, Sim-V1;
incast patterns from `gen_p2p_patterns.py`). The congestion-unaware tier
(all sweeps/matrix/apps) has no queues at all, so the setting is
meaningless there. Constraint: the congestion-aware backend is 1-dim only,
so these runs model the ToR as a flat switch.

**When it is enabled.** VOQ is the **default and the backend's stock
behavior** (each egress link already has a private queue) — nothing to
enable. The strawman is what gets switched on: network-YAML key
`switch_egress: shared_fifo` (added in the `astra-network-analytical`
fork) forces one shared egress FIFO with head-of-line blocking. Emit it
via `gen_network_config.py --switch-egress shared_fifo` or write the key
by hand; omit it (or `per_destination`) for VOQ. Verified contrast: victim
FCT is bit-identical to solo under VOQ, 3.2x inflated under shared_fifo.

Notes: STG needs `tqdm` (fetch_stg.sh installs it); results/ is gitignored;
sweeps accept env overrides (e.g. `KS="1 10" run_regime_map.sh`,
`SIZES="16" COLLS="all_to_all" run_matrix.sh`).
