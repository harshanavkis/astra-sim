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
- `workload/gen_moe_alltoall.py` — MoE expert-parallel iteration
  (dispatch all-to-all → expert compute → combine all-to-all), with the
  SM-reservation scaling flag for baseline traces.
- `run_smoke.sh` — end-to-end smoke run (Loom vs baselines, small config).

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

## Running (Docker)

```bash
docker build -t astra-sim:loom /path/to/astra-sim   # official Dockerfile
docker run --rm -v /path/to/astra-sim:/app/astra-sim astra-sim:loom \
    bash -c "./build/astra_analytical/build.sh && examples/loom/run_smoke.sh"
```
