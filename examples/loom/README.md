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
| Switch pipeline latency (`t_loom_pipe`: source validation + range match + bounds + translation) | folded into per-dimension `latency` (network YAML) |
| Encapsulation goodput (3-field header + coalescing efficiency at the run's message-size mix) | folded into per-dimension `bandwidth` |
| Posted-write source-local completion | eager mode (default; sender completes at injection) |
| Baseline RDMA large-message handshake | `--rendezvous-protocol true` (existing CLI flag) |
| Per-message endpoint cost (GPU doorbell/QP kernel, CPU proxy post+poll) | `endpoint-delay` (system JSON) |
| Baseline SM reservation for communication | COMP durations scaled at trace-generation time (`--sm-total/--sm-comm` in the workload generator) |
| Loom zero-XPU-compute communication | unscaled COMP durations + `endpoint-delay = 0` |

New code in this package is therefore **config generation only**; the
simulator is unmodified. (Congestion-tier VOQ modeling — phase S4 — will be
the first real backend change, in `congestion_aware/Device`.)

## Files

- `gen_network_config.py` — emits 2-dim network YAMLs (dim0 = rack scale-up
  fabric through the ToR, dim1 = inter-ToR Ethernet), folding the pipe
  latency and goodput factor per mode (`loom` / `baseline` / `ideal`).
- `network/` — generated YAMLs (committed for reproducibility; regenerate
  with the commands in each file's header comment).
- `system/` — endpoint models as system JSONs:
  - `loom.json` — endpoint-delay 0 (a store is the whole per-message cost)
  - `baseline_gpu_rdma.json` — B1, GPU-initiated RDMA (IBGDA-like)
  - `baseline_cpu_proxy.json` — B2, CPU proxy thread
  - `ideal_rdma.json` — B3, zero-overhead upper bound
- `workload/gen_p2p_patterns.py` — single-flow / incast / victim+aggressor
  stimulus; `workload/gen_read_pattern.py` — independent peer reads.
  These are *microbenchmark stimulus* in the style of the repo's own
  `examples/workload/microbenchmarks/generator_scripts/` (iperf-like flow
  patterns with no real-trace equivalent), NOT application workloads.
- `remote_memory/loom_peer_reads.json` — LOOM_PEER_READS credit-capped read
  model (submodule extension).
- `system/loom_1d.json` — 1-dim variant for single-switch (flat) runs; the
  congestion-aware backend supports 1-dim topologies only.
- `figures/` — drawio sources explaining the setup (layer stack + topology).
- `run_smoke.sh` — end-to-end smoke run (Loom vs baselines) on the repo's
  shipped all-to-all microbenchmark ETs.
- `run_victim.sh` — Sim-V1 victim-flow isolation: VOQ (default egress) vs
  `switch_egress: shared_fifo` (head-of-line strawman, congestion-aware
  submodule extension). Verified: victim FCT identical to solo under VOQ,
  3.2x inflated under shared FIFO.
- `run_sweep_tpipe.sh` — S-1 sensitivity sweep (t_pipe vs completion time,
  CSV) on an STG-generated MoE workload: the break-even point against B1
  falls out directly. Note the ring all-to-all amplifies hop count; rerun
  with `direct` per fairness rule F2.

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
- Loom ToR uplink aggregate defaults to the baseline's M NICs
  (`--uplink-oversub 1.0`); oversubscription is an explicit sweep (S-6).
- KNOWN GAP, generous to Loom: a Loom XPU's single fabric port carries both
  intra- and cross-rack traffic, but AstraSim's orthogonal dims let dim1
  traffic bypass dim0 capacity (which matches the baseline's separate NIC,
  not Loom). Shared-edge contention belongs to the congestion tier; until
  then, bound it by charging cross-rack traffic to both dims in a worst-case
  variant.

## Placeholder constants (until testbed calibration)

All Loom-favoring constants are placeholders to be replaced by measurements
from the Coyote/U280 prototype (paper repo `design-docs/implementation-plan.md`
Phases 0–5); each is swept in the sensitivity plan regardless.

| Constant | Placeholder | Source (eventually) |
|---|---|---|
| `t_loom_pipe` | 500 ns | testbed T3 (pipeline microbench); swept 100 ns–5 µs |
| Loom goodput factor (dim1) | 0.94 | testbed T2 (goodput vs size, coalescer on) |
| Baseline RoCE goodput (dim1) | 0.90 | measured Coyote RoCE RC efficiency |
| B1 endpoint-delay | 700 ns | literature (IBGDA/NVSHMEM microbenchmarks); swept |
| B2 endpoint-delay | 3000 ns | testbed CPU-verbs post+poll baseline |
| B1 SM reservation | 20 of 132 SMs (DeepSeek-V3) | swept {8, 20, 32} |

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

**Network/system configs**: `gen_network_config.py --mode {loom,baseline,ideal}`
(knobs: `--pipe-ns --loom-goodput --uplink-oversub --dim1-topology`);
system JSONs in `system/` (roofline variants for STG workloads).

Notes: STG needs `tqdm` (fetch_stg.sh installs it); results/ is gitignored;
sweeps accept env overrides (e.g. `KS="1 10" run_regime_map.sh`,
`SIZES="16" COLLS="all_to_all" run_matrix.sh`).
