# CHECKPOINT — Loom project state

> **Last updated: 2026-08-04 (PHASE A DONE).** Data integrity fixed
> (`run_smoke.sh` generates its configs; the rotted `network/*.yml` are
> deleted; B2 no longer runs on B1's network), F2 settled and then made
> moot by the topology decision, docs consolidated from seven files to
> four, and section 5 is now GENERATED from `results/*.csv` by
> `summarize_results.py`. **ONE physical topology everywhere:
> `[Switch, Switch]`** - the `ring_tor` row is deleted as unrepresentative
> of any real deployment. `regime_map` and `sweep_tpipe` left the default
> suite (they contradicted the owner's own sweep policy). Prior state:
> testbed prototype through Coyote phase 6.2a with T3 stage counters
> implemented; see `implementation-plan.md`, which is authoritative for
> the testbed side.** LIVING DOCUMENT - the ONLY living state doc, so
> there is nothing to keep in sync with it. Overwritten in place with
> every commit; NEVER hand-write a result number into it (rerun the suite
> and `summarize_results.py --write`). Written for session restart on a
> possibly different server: read this first. Lives in the astra-sim repo
> (branch `loom-sim`, next to `examples/loom/README.md`); companion design
> docs live in `loom-paper/design-docs/`.

## 0. MIGRATION WARNING (read before moving servers)

Work lives in THREE git repos; only some of it is pushed anywhere:

| Repo | Branch | Pushed? |
|---|---|---|
| `~/loom-paper` | master (Overleaf-synced) | tex yes; **design-docs/, loom-drawio/, *.md are UNTRACKED** — copy them explicitly |
| `~/astra-sim` (fork `harshanavkis/astra-sim`) | **`loom-sim`** | **push before migrating**: `git push -u origin loom-sim` |
| submodule `extern/network_backend/analytical` | `loom-sim` | YES → fork `harshanavkis/astra-network-analytical` |
| submodule `extern/remote_memory_backend/analytical` | `loom-sim` | YES → fork `harshanavkis/astra-memory-analytical` |

`.gitmodules` points at the two forks (https), so on a new server:
```bash
git clone -b loom-sim https://github.com/harshanavkis/astra-sim.git
cd astra-sim && git submodule update --init   # pulls the loom-sim commits from the forks
# plus: tar the untracked loom-paper files (design-docs/, loom-drawio/, *.md)
```
(Local submodule push remotes stay ssh on the ORIGINAL machine; there,
do not run `git submodule sync` or it overwrites them with the https URLs.
On a RESTORED machine the opposite holds: if the submodule `origin` already
points at upstream astra-sim rather than the forks, `git submodule sync` is
the fix, not the hazard. That was the case on the 2026-08-04 restore, where
sync was run deliberately.)

## 1. What Loom is (design invariants — violate none of these)

Paper at `~/loom-paper` (main.tex; \system{} macro): unifies scale-up and
scale-out GPU interconnects behind ONE peer-memory interface (loads/stores/
DMA); a Loom top-of-rack switch routes memory transactions — local route
over rack PCIe/CXL, remote route encapsulated on per-binding RoCE RC.

- **Zero application changes**; no new APIs; agent interposes beneath
  existing CUDA calls. Nothing runs on the GPU. Never call the agent a
  "driver".
- **Binding-first addressing**: aperture range match → compiled binding
  entry {local: segment ctx | remote: QP}. Wire header = ⟨offset · op ·
  len⟩ — **NO GFA, NO capability token, NO read tag, NO sequence number**
  (all removed; connection identifies the binding; reads match
  positionally via per-binding FIFO; isolation = page tables + source
  validation + bounds). No attacker model ("we don't care about attackers").
- Posted-write source-local completion; per-binding ordering; fail-stop
  failures (error containment unit); read credits; per-destination
  transmit queues (VOQ); PCIe-class contract (no atomics).
- Only the privileged orchestrator programs switches; agent is host-local.
- Terminology: XPU in design sections (GPU only in motivation/examples);
  CUDA names only as inline examples. No em dashes anywhere in the paper.
- One ToR switch per rack = per scale-up domain.

## 2. Paper state (`~/loom-paper`, compiles: `pdflatex main.tex`, 10 pp clean)

Written: introduction, motivation (§2, positioning table, NVLink Fusion
REMOVED entirely), overview (§3, 6 principles), design §4 (addressing),
design-sw §5 (agent/orchestrator/lifecycle/isolation; orchestrator
components: segment registry, binding compiler, route manager, permission
manager, connection manager, revocation manager), design-hw §6 (routing/
transport/reads/flow/failure). `\tbd{}` red placeholders await M1–M3
measurements. NOT written: abstract, §7 implementation, §8 evaluation,
related work, conclusion.

Figures (draw.io XML in `loom-drawio/`, user hand-edits, exports PDFs to
`figures/loom-project-*.pdf`; ALWAYS re-read XML before editing; name-only
labels; step markers edge-attached): overview, address-translation (single
app, both routes as alternative bindings), sw-stack (a–f markers),
hw-controller (Fabric I/F contains Per Port Buffers + Source Validation;
Per-Segment Translation Tables; no Binding Lookup box). Sim figures moved
to astra-sim repo `examples/loom/figures/`.

## 3. Design docs (`~/loom-paper/design-docs/` — UNTRACKED in git)

- `implementation-plan.md` — Coyote/U280 testbed plan (Phases 0–6), swept
  clean of tokens/GFA/NAT; Coyote's RoCE stack = transport, vFPGA does only
  translations. **Testbed work STARTED (2026-08-03): prototype code in the
  Coyote repo, `examples/loom/` (simulation-complete through phase 5.1a).**
  **Tracked copy at `examples/loom/implementation-plan.md` is now
  AUTHORITATIVE** (banner updated with implementation status + descopes
  applied inline). Previously-known staleness now fixed in that copy: its
  Phase 4 (victim/failure, 3 wk) is
  DESCOPED; Phase-6 "VOQ demonstrated on prototype" and the §6.4 paper
  mapping are obsolete (no isolation claim). Cutting Phase 4 puts the
  NSDI-minimum path (Phases 0–3 + calibration + validation gate) at
  ~9–12 wk.
- `simulation-eval-plan.md` — AstraSim plan + eval plan (S0–S8 phases,
  T1–T11 testbed experiments, sensitivity S-1…S-6, fairness F1–F4).
- `evaluation-methodology.md` — THE methodology record: RQ1–RQ6, metric
  definitions w/ exemplar-paper anchors, reporting standards, threats to
  validity, 12-figure inventory.
- `connection-scaling.md` — QP-state explosion + pooled-connection fix
  (binding ID in header = compiled rkey analog; per-importer perms argument).
- `address-translation-design.md`, `loom-workflows.md` — historical/
  reference (banners say tex is authoritative).

## 4. AstraSim implementation (`~/astra-sim`, branch `loom-sim`)

Everything under `examples/loom/` + two submodule extensions + one core
patch. Docker image `astra-sim:loom` (official Dockerfile; STG needs
`pip3 install tqdm` — fetch_stg.sh handles it). See `examples/loom/README.md`
for full run instructions; one command: `examples/loom/run_all_docker.sh`.

Commits (oldest first) on loom-sim over upstream 518bd51:
`8875829` network-config generator + endpoint system JSONs;
`8449c59` (superseded MoE generator — later removed);
`4efc1a8` endpoint-delay 1ns fix (event queue rejects zero-delay);
`113da85` sim figures; `3a248c6` S3 generators; `4e4e02c` S5 reads
(+ HardwareResource: MEM_LOAD/STORE hold no issue slot);
`8f88a07` S4 VOQ vs shared-FIFO (+ submodule commit);
`2de88c0` t_pipe sweep; `a6c81cd` STG integration + roofline configs;
`09bfdc8` REMOVED hand-authored app workloads (user mandate: existing
traces only); `1b875c2` uplink-oversub + topology fairness;
`ccf45b5` regime map; `77a5291` harness + published shapes (Mixtral 8x7B,
GPT-3 175B); `799ed6c` matrix + apps; `7705a9c` README.

Key modeling decisions:
- Loom switch = constants folded into per-dim latency/BW (HGX-validated
  technique): dim0 + `t_pipe_local` (~50 ns lookup adder; the ToR IS the
  rack switch), dim1 = edge legs (500) + source stages lookup/queue/encap (200) + roce (150) + wire (600) + roce (150) + dest translate/forward (25) = 1625 ns; per-stage params 1:1 with hw-controller blocks (D13), coarse --pipe-ns override for sweeps — no data-path work requests (D5), destination = local-delivery pipeline not a second t_pipe (D10). Full constants + decisions ledger: `ANALYTICAL-MODEL.md`.
  All network constants anchored to published/validated numbers (README
  table); only t_pipe/t_pipe_local + coalescing curve are testbed-owned.
  Endpoint costs route-split: store-issue 10 ns (HGX-validated) for ALL
  systems; baseline RDMA initiation on dim1 only (B1 2400, B2 2800 ns).
- Endpoint models via existing knobs: `endpoint-delay` (Loom 1ns, B1 700ns*,
  B2 3µs* + `--rendezvous-protocol`), eager = posted write. *placeholders.
- SM reservation: roofline `peak-perf` 989 vs 839 TFLOPS (20/132 SMs).
- Reads: `LOOM_PEER_READS` memory type (per-NPU credit cap) in the
  remote-memory submodule; verified exact 1x/8x/64x scaling.
- VOQ: stock congestion-aware = per-destination already; added
  `switch_egress: shared_fifo` HoL strawman (Link::is_busy + free callback,
  Device shared queue + pump). **Congestion-aware backend is 1-dim ONLY.**
- Workload provenance rule: shipped microbench ETs + STG published shapes
  (Mixtral/GPT-3) + stimulus generators (victim/incast/reads, iperf
  category). NO hand-authored application workloads.

**Standing docs (consolidated 2026-08-04 — four files, not seven):** THIS
file is the only living state doc (section 8 carries the code↔real-system
correspondence folded in from the deleted CODE-MAP.md; section 9 the
durable parts of the deleted HANDOFF-EVAL-REVIEW.md).
`ANALYTICAL-MODEL.md` = equations, constants, decisions ledger.
`README.md` = how to run, and **no result numbers**.
`implementation-plan.md` = the Coyote testbed plan. `CLAUDE.md` at repo
root = working rules. Result numbers are generated into section 5 by
`summarize_results.py`; never hand-edit a number into any doc.

<!-- BEGIN GENERATED RESULTS -->
## 5. Results (GENERATED by summarize_results.py from
## results/*.csv - do not hand-edit inside the markers)

- Smoke (`smoke.csv`, 4-NPU 1 MB all-to-all): loom 14565 < b1_gpu_rdma 20105 < b2_cpu_proxy 36744. Loom vs B1 **+27.56%**.
- P2P sweep (`p2p_sweep.csv`, M2) - one send/recv pair, the only experiment with no collective chunk-overlap to hide per-operation cost, hence the cleanest read on the constant the headline depends on:

| route | size | Loom vs B1 | Loom vs B2 |
|---|---|---|---|
| cross_rack | 4 KB | +45.6% | +76.1% |
| cross_rack | 16 KB | +43.8% | +74.8% |
| cross_rack | 64 KB | +38.0% | +70.0% |
| cross_rack | 256 KB | +24.9% | +55.7% |
| cross_rack | 1 MB | +10.4% | +30.7% |
| cross_rack | 4 MB | +3.1% | +11.0% |
| cross_rack | 16 MB | +0.8% | +3.1% |
| cross_rack | 64 MB | +0.2% | +0.8% |
| cross_rack | 256 MB | +0.1% | +0.2% |
| cross_rack | 1024 MB | +0.0% | +0.0% |
| in_rack | 4 KB | +0.0% | +51.4% |
| in_rack | 16 KB | +0.0% | +47.5% |
| in_rack | 64 KB | +0.0% | +36.4% |
| in_rack | 256 KB | +0.0% | +18.9% |
| in_rack | 1 MB | +0.0% | +6.4% |
| in_rack | 4 MB | +0.0% | +1.8% |
| in_rack | 16 MB | +0.0% | +0.5% |
| in_rack | 64 MB | +0.0% | +0.1% |
| in_rack | 256 MB | +0.0% | +0.0% |
| in_rack | 1024 MB | +0.0% | +0.0% |

  Cross-rack crossover: Loom leads B1 up to 1024 MB, then converges.

- Read credits (`sweep_credits.csv`, caps 1-1048576): exact linear 1/N scaling from 325568 cycles. Uncapped row present and equal to the 64-credit row.
- Scale sweep (`scale_sweep.csv`, A5) - 8 XPUs/rack fixed, RACK COUNT is the axis. Loom's benefit is a function of cluster width, so no single number is meaningful without stating the scale:

| GPUs | all_reduce 1 MB | all_reduce 64 MB | all_to_all 1 MB | all_to_all 64 MB |
|---|---|---|---|---|
| 16 | +9.39% | +0.00% | +3.02% | +0.14% |
| 32 | +34.95% | +0.00% | +14.54% | +0.72% |
| 64 | +40.48% | +0.00% | +37.46% | +4.40% |
| 128 | +43.28% | +6.55% | +42.59% | +9.16% |
| 256 | +44.68% | +25.21% | +44.59% | +16.12% |
| 512 | +45.38% | +32.71% | +45.41% | +24.37% |

  Mechanism: a hierarchical collective spreads a roughly constant dim1 byte count over 2(r-1) steps, so per-step bytes fall as ~1/r while per-step LATENCY is fixed. Few racks = few fat steps = bandwidth-bound, hiding Loom's 1615-vs-3000 ns dim1 edge; many racks = many thin steps = latency-bound, where Loom wins. The exact +0.00% entries at small rack counts are that hiding, not parity.

- Scale-up DOMAIN sweep (`domain_sweep.csv`) - STANDALONE (slow: 576 GPUs per point). **This experiment runs AGAINST Loom and must not be dropped.** Cluster size is held at 576 GPUs while the scale-up domain grows (HGX 8 -> NVL36 -> NVL72), so racks shrink and more traffic stays in-rack - traffic Loom does not change:

| GPUs/rack | racks | all_reduce 1 MB | all_reduce 64 MB | all_to_all 1 MB | all_to_all 64 MB |
|---|---|---|---|---|---|
| 8 | 72 | +45.47% | +33.81% | +45.49% | +25.77% |
| 36 | 16 | +37.83% | +0.00% | +17.54% | +2.56% |
| 72 | 8 | +5.47% | +0.00% | +1.38% | +0.33% |

  Bounds which argument carries the paper in which deployment; it is NOT a refutation. SM reclamation is topology-INDEPENDENT (measured +10.72% compute gain at both 8 GPUs/rack x 32 racks and 64 GPUs/rack x 4 racks), Loom is never worse than B1 (the floor is parity, since crossing the network costs every system the same), and the removal of QPs/keys/buffers from the accelerator is not modelled here at all (catalog A9). What shrinks is the communication differential. At a FIXED cluster size, NVL72-class racks erase that differential almost entirely. The cause is rack COUNT (576 GPUs in 72-GPU racks is only 8 racks, inside the regime where dim1 latency is hidden), which is the same mechanism as the scale sweep. The defence is that NVL72 deployments are correspondingly LARGER, so rack count - and with it the cross-domain traffic fraction - recovers. That defence is NOT yet demonstrated: simulating 72-GPU racks beyond ~576 GPUs did not complete here, so it needs the validated analytical proxy (catalog B7/A5).

- SM-reservation sweep (`sm_sweep.csv`, A6) - STANDALONE. There is no SM in ASTRA-sim: the tax is a roofline derating, `peak_perf = 989 * (132-k)/132` on the BASELINE only, since nothing runs on Loom's accelerators. k=20 is DeepSeek-V3's disclosed reservation. **k=0 isolates the pure communication benefit**, which is the most useful row here:

| app | k | wall | comm | compute |
|---|---|---|---|---|
| gpt3_dense | 0 | +0.02% | +0.03% | +0.00% |
| gpt3_dense | 8 | +1.88% | +1.42% | +5.61% |
| gpt3_dense | 20 | +5.01% | +3.79% | +14.14% |
| gpt3_dense | 32 | +8.61% | +6.58% | +22.78% |
| mixtral_moe | 0 | +13.90% | +16.47% | +0.00% |
| mixtral_moe | 8 | +14.40% | +16.20% | +5.21% |
| mixtral_moe | 20 | +15.27% | +15.71% | +13.21% |
| mixtral_moe | 32 | +16.44% | +15.22% | +21.50% |

  The k=0 rows separate the two claims cleanly: for the dense LLM the communication benefit is essentially ZERO (+0.02% wall), so its entire gain is SM reclamation; for MoE the communication benefit carries it (+13.90% at k=0) and reclamation adds ~1.4pp. Quote them separately rather than reporting one blended number.
  Model limitation, measured: `perf` is a `min()`, so only COMPUTE-BOUND nodes are derated and memory-bound ones escape the tax - the compute gain lands at +13.2/+14.1% instead of the ideal 20/132 = 15.15%. Deriving `local-mem-bw` by the same factor (`MEMBW=1`) recovers exactly 15.15% for both apps and moves wall to +15.68% / +5.54%. So the shipped model UNDER-states the SM tax, i.e. errs against Loom.

- Break-even t_pipe (`sweep_tpipe.csv`) — STANDALONE, not in the default suite (optional reviewer-proofing; T3 will measure t_pipe): **3596 ns** (linear, 480 cycles/ns). Its durable use is showing the design tolerates a slow FPGA clock.
- Regime map (`regime_map.csv`) — STANDALONE, not in the default suite; runs `--pipe-ns 500` so its Loom is NOT the Loom of the other experiments (see 5a.5). Rerun it before quoting:
  **13.9%** at 12% exposed comm -> **3.3%** at 91%. No negative point.
- Matrix (`matrix.csv`, 24 Loom-vs-B1 cells): +3.7...+44.7% @1 MB, +0.3...+37.7% @16 MB, +0.0...+25.2% @64 MB.
  No negative cells.
  1 cells are EXACTLY identical (+0.000%), carrying no information rather than showing a win: 64gpu_8racks all_reduce 64 MB. At these sizes the model hides dim1 latency for both systems (chunk overlap, see 5a) and dim0 is identical by construction, so nothing CAN differ. Do not cite them in either direction.
  vs B2: Loom wins all 24 cells (+0.3...+75.7%).
- Apps (`apps.csv`): gpt3_dense 32 ranks **+5.07%**; gpt3_dense 64 ranks **+5.01%**; gpt3_dense 256 ranks **+2.38%**; mixtral_moe 16 ranks **+4.98%**; mixtral_moe 64 ranks **+15.27%**; mixtral_moe 256 ranks **+18.68%** vs B1.

  Gain decomposition (apps.csv) - the compute column is
  SM reclamation, structurally capped at 15.2% (= 1 - 839/989, the 20/132
  SM reservation); the comm column is per-operation initiation,
  which amortizes away on large messages:

| app | ranks | exposed comm | comm gain | compute gain | wall gain |
|---|---|---|---|---|---|
| gpt3_dense | 32 | 78.5% | +2.5% | +14.3% | **+5.07%** |
| gpt3_dense | 64 | 88.3% | +3.8% | +14.1% | **+5.01%** |
| gpt3_dense | 256 | 95.8% | +2.0% | +11.4% | **+2.38%** |
| mixtral_moe | 16 | 59.1% | -0.8% | +13.4% | **+4.98%** |
| mixtral_moe | 64 | 82.3% | +15.7% | +13.2% | **+15.27%** |
| mixtral_moe | 256 | 94.3% | +19.2% | +10.7% | **+18.68%** |


- Matrix F2 (direct algorithms) (`matrix_direct.csv`, 24 Loom-vs-B1 cells): +1.1...+40.8% @1 MB, +0.1...+23.5% @16 MB, +0.0...+4.4% @64 MB.
  No negative cells.
  2 cells are EXACTLY identical (+0.000%), carrying no information rather than showing a win: 256gpu_32racks all_reduce 64 MB, 64gpu_8racks all_reduce 64 MB. At these sizes the model hides dim1 latency for both systems (chunk overlap, see 5a) and dim0 is identical by construction, so nothing CAN differ. Do not cite them in either direction.
  vs B2: Loom wins all 24 cells (+0.1...+73.4%).
- Apps F2 (direct algorithms) (`apps_direct.csv`): gpt3_dense 32 ranks **+5.07%**; gpt3_dense 64 ranks **+5.01%**; gpt3_dense 256 ranks **+2.38%**; mixtral_moe 16 ranks **+4.98%**; mixtral_moe 64 ranks **+15.27%**; mixtral_moe 256 ranks **+18.68%** vs B1.

  Gain decomposition (apps_direct.csv) - the compute column is
  SM reclamation, structurally capped at 15.2% (= 1 - 839/989, the 20/132
  SM reservation); the comm column is per-operation initiation,
  which amortizes away on large messages:

| app | ranks | exposed comm | comm gain | compute gain | wall gain |
|---|---|---|---|---|---|
| gpt3_dense | 32 | 78.5% | +2.5% | +14.3% | **+5.07%** |
| gpt3_dense | 64 | 88.3% | +3.8% | +14.1% | **+5.01%** |
| gpt3_dense | 256 | 95.8% | +2.0% | +11.4% | **+2.38%** |
| mixtral_moe | 16 | 59.1% | -0.8% | +13.4% | **+4.98%** |
| mixtral_moe | 64 | 82.3% | +15.7% | +13.2% | **+15.27%** |
| mixtral_moe | 256 | 94.3% | +19.2% | +10.7% | **+18.68%** |

<!-- END GENERATED RESULTS -->

## 5a. Phase-A findings (2026-08-04) — read before interpreting section 5

**ONE PHYSICAL TOPOLOGY, ONE PROVISIONING (owner decisions 2026-08-04).**
Every experiment runs `[Switch, Switch]` at equal wires. That is what is
deployed: scale-up is a switch (NVSwitch/NVLink), scale-out is a switched
Clos/rail-optimized fabric. The matrix grid is now **SCALE x COLLECTIVE x
SIZE** - 2 scales (16 and 64 XPUs), nothing else. Two rows were deleted:
- `ring_tor` (`--dim1-topology Ring`): nobody deploys a ring of ToRs, and
  it was the sole source of the "negative cells" confusion. The knob
  survives in the generator but is not exercised.
- `thin_uplinks` (`--net-bw 12.5`): misnamed and answered the wrong
  question - `--net-bw` thins the fabric for BOTH systems, modelling a
  slower network for everyone rather than thin LOOM uplinks. The
  Loom-specific knob is `--uplink-oversub`, deliberately pinned at 1.0
  (equal wires: ToR uplink aggregate = the M NICs Loom deletes) and NOT
  swept: 400 GB/s of uplink is a small fraction of a modern ToR ASIC, so
  non-blocking is an engineering choice; handicapping only Loom would
  break the equal-wires framing; and under equal COST the argument runs
  the other way, since Loom removes M NICs per rack.
  **Do not confuse this with the dim0/dim1 taper** (64 vs 50 GB/s per
  XPU): those are wire rates, paid by both systems, not provisioning.

**This also makes F2 moot, which is the cleanest possible outcome.** With
the ring topology gone, the ring and direct algorithms agree to within
0.02% (36 cells: mean **+13.02%** ring vs **+13.00%** direct, both ranging
to +39.4%, both with the same 3 negative cells). There is no headline
choice to make between the two grids. Detail, kept because the reasoning
matters:

1. F2 as previously specified (flip only `all-to-all-implementation` to
   `direct`) could never have answered the question: **all five negative
   cells were all_reduce (4) and all_gather (1); none was all_to_all.**
   The `*_direct.json` variants therefore switch all four collectives, for
   all four systems together (`SUFFIX=_direct`, `run_f2.sh`).
2. The two `ring_tor` negatives were an artifact of running a ring
   ALGORITHM on a ring TOPOLOGY: that combination made the collective ~5x
   slower for BOTH systems (Loom 251,284 vs 49,296 cycles under direct),
   which diluted Loom's per-operation advantage until only its 50 ns
   in-rack lookup remained visible - reading as −1.11%. Under direct the
   same cell reads +30.64%. Neither number describes deployed hardware,
   which is why the row is gone rather than re-reported.
3. **The three real negatives survive on the deployed topology** and are
   bit-identical under both algorithms (`rack4x4`/`rack8x8` all_reduce
   64 MB, `thin_uplinks` all_gather 64 MB). Their cause is measured, not
   guessed: it is
   **`t_pipe_local`, the 50 ns in-rack lookup adder on dim0** (Loom dim0 =
   550 ns vs baseline 500 ns). Regenerating that cell with
   `--pipe-local-ns 0` yields 909,088 cycles — bit-identical to B1 —
   while the default 50 ns yields 911,888 (2,800 cycles = 56 dim0
   traversals × 50 ns). The old "header tax"/goodput explanation is
   **disproved**: forcing `--loom-goodput 0.95` (i.e. equal to RoCE)
   changes the wall time by exactly zero.
   So Loom's only bulk regression is the in-rack table lookup, ~0.3% at
   64 MB. That is a real modeled Loom cost and an honest one to report.
4. **Apps F2 is a structural null.** `apps_direct.csv` is byte-identical
   to `apps.csv`. The direct JSONs were definitely used; the reason is
   that STG's comm groups are size **1, 2 and 4 only**, where ring and
   direct coincide. Corollary worth stating before any scale claim: a
   "64-rank" STG app never runs a 64-rank collective.

**THE MATRIX SHAPES UNDER-EXERCISE dim1 - THE ONE DIMENSION LOOM CHANGES
(measured 2026-08-04). This is an evaluation-design problem, not just an
explanation of the ties.**

Same 64 ranks, same 64 MB all_reduce, different rack shape:

| shape | Loom | B1 | gain |
|---|---|---|---|
| 8 racks x 8 XPUs (in the grid) | 909,088 | 909,088 | **+0.000%** |
| **16 racks x 4 XPUs** (not in the grid) | 893,338 | 1,059,538 | **+15.7%** |

Why: with `localBWAware` and 8 XPUs per rack, the hierarchical all_reduce
keeps nearly all bytes on dim0 and sends only the reduced slice across
racks. Measured contribution of each dimension (B1, all_reduce 64 MB,
8x8): halving dim1 bandwidth 50 -> 25 GB/s costs **+1%** (909,088 ->
918,083) while halving dim0 bandwidth 64 -> 32 GB/s costs **+94%**
(-> 1,763,592). So the cell is dim0-bound, and dim0 is identical for both
systems by construction. Of the ~1% that does cross racks, the bandwidth
term is now equal (both 47.5 GB/s since the goodput fix) and the latency
term (Loom 1615 vs B1 3000 ns) is pipelined away by concurrent chunks -
latency overlaps, bandwidth serializes.

**Consequence: the 64 MB column largely measures the rack fabric, which is
identical for both systems by construction.** But the fix is NOT to reshape
the racks. 8 GPUs per scale-up domain is exactly what is deployed (DGX/HGX;
NVIDIA EOS is 576 nodes x 8), and GB200 NVL72 goes the other way to 72 - a
4-GPU rack would be modelling a machine nobody builds, i.e. the `ring_tor`
mistake again, this time in Loom's favour.

**THE REAL PROBLEM IS CLUSTER SIZE: we evaluate 64 GPUs in 8 racks.**
Holding the realistic 8 XPUs/rack and scaling the RACK COUNT (all_reduce
64 MB):

| cluster | Loom | B1 | gain |
|---|---|---|---|
| 8 racks (64 GPUs) - the current grid | 909,088 | 909,088 | **+0.00%** |
| 16 racks (128 GPUs) | 909,088 | 972,814 | **+6.55%** |
| 32 racks (256 GPUs) | 1,019,074 | 1,362,554 | **+25.21%** |

Loom's benefit grows with rack count, because a hierarchical collective
puts more work on dim1 as the cluster widens - and dim1 is the only
dimension Loom changes. Comparable work evaluates far larger: NCCL EP on
EOS (576 nodes x 8 GPUs = 4,608), DeepEP at 64+ EP degree, NVIDIA Wide-EP
on GB200 NVL72. At 64 GPUs we are ~1/70th of the smallest comparable
setup, in the regime where the divide costs least.

**DONE 2026-08-04: the grid is now 8 XPUs/rack fixed, racks {8, 32} =
64 and 256 GPUs**, and every apps row uses 8 XPUs/rack too.

| matrix, mean over 4 collectives | 1 MB | 16 MB | 64 MB |
|---|---|---|---|
| 64 GPUs / 8 racks | +30.52% | +12.02% | +2.00% |
| 256 GPUs / 32 racks | +34.52% | +26.75% | **+13.44%** |

`all_reduce` 64 MB, the cell that was a byte-identical tie: **+0.00% ->
+25.21%**. MoE apps improve with scale (mixtral +15.27% at 64 ranks ->
**+18.68%** at 256, comm +19.2%).

**Two numbers moved DOWN; both are corrections, not regressions:**
- mixtral-16 was +7.47%, is now +4.98%. Its old shape was 4 racks x 4
  XPUs; at the deployed 8 XPUs/rack a 16-GPU job fits in 2 racks, so
  almost nothing crosses dim1. The old figure was inflated by a rack size
  nobody builds.
- gpt3_dense-256 is +2.38%, BELOW its own 64-rank +5.01%, and is NOT
  directly comparable: pp cannot exceed the dense preset's `--num_stacks`
  (4) or STG's `convert_chakra` asserts, so the 256 point scales data
  parallelism instead (dp16 tp4 pp4). More DP means more bulk gradient
  all_reduce - the bandwidth-bound regime where Loom is at parity by
  design. Say this in the paper rather than letting a reader see a scaling
  failure.

**THE NVL72 TREND, MEASURED (`run_domain_sweep.sh`, 2026-08-04).** Holding the cluster at 576 GPUs and
growing the scale-up domain:

| GPUs/rack | racks | ar 1 MB | ar 64 MB | a2a 1 MB | a2a 64 MB |
|---|---|---|---|---|---|
| 8 (HGX) | 72 | +45.47% | +33.81% | +45.49% | +25.77% |
| 36 (NVL36) | 16 | +37.83% | +0.00% | +17.54% | +2.56% |
| **72 (NVL72)** | **8** | **+5.47%** | **+0.00%** | **+1.38%** | **+0.33%** |

At a fixed cluster size, NVL72-class racks erase the COMMUNICATION
differential almost entirely - including at 1 MB, where it drops from +45%
to +5%.

**DO NOT over-read this as "the strongest argument against the paper"
(an earlier version of this note did, wrongly - owner correction
2026-08-04). Three things bound the damage:**
1. **SM reclamation is topology-INDEPENDENT.** Measured on mixtral-256
   with the roofline configs: the compute gain is **+10.72% at 8 GPUs/rack
   x 32 racks AND +10.72% at 64 GPUs/rack x 4 racks** - byte-identical. It
   is a property of the endpoint model, not the network. What changes is
   its WEIGHT in wall time (that workload is ~91-94% exposed comm, so
   +10.72% of compute buys +0.79% wall at 4 racks vs +18.68% at 32).
2. **Loom is never WORSE - the floor is parity.** The sweep shows a
   shrinking differential, not a loss. The cross-rack cost is inherent to
   crossing the network; every system pays it, and a bigger scale-up
   domain helps everyone equally.
3. **The state argument is untouched and unmodelled**: no QPs, keys or
   transport buffers on the accelerator. The simulator cannot show this at
   all; catalog A9 (QP accounting) is its quantitative form.

So the correct reading is that this sweep BOUNDS WHICH ARGUMENT CARRIES
THE PAPER IN WHICH DEPLOYMENT, and it lands exactly on the settled
positioning: many small racks -> the communication win leads; few large
racks -> SM reclamation + unification + state removal lead, with
communication at parity. That is "NOT a bulk-speedup paper" restated
quantitatively, not a refutation of it.

The cause is the same mechanism as everywhere else: rack COUNT. 576 GPUs
in 72-GPU racks is only 8 racks, and 71 of any rank's 575 peers are
in-rack, so the divide barely bites. The defence is that NVL72 deployments
are correspondingly LARGER (a 10k-GPU NVL72 cluster is ~140 racks), so the
cross-domain traffic fraction recovers. **That defence is NOT yet
demonstrated**: 72-GPU racks beyond ~576 GPUs would not complete here
(ET generation unreliable and per-run time in the many minutes), so it
needs the validated analytical proxy - catalog B7/A5 - which is exactly
the MoX pattern already in the plan. Until that exists, the honest claim is
that Loom's benefit scales with the FRACTION of traffic crossing scale-up
domains, and that fraction is a deployment property, not a Loom property.

**HOW THE all_reduce 64 MB CELL WENT FROM -0.31% TO +0.000% (2026-08-04).**
It did not get better - it became a TIE, and the tie is forced. The
negative was entirely the in-rack `t_pipe_local` adder, measured directly
before anything was changed: `--pipe-local-ns 0` already reproduced B1
byte-for-byte (909,088 both), while goodput and the collective algorithm
each moved it by exactly zero. So walking the adder 50 -> 40 -> 0 walked
the cell -0.31% -> -0.25% -> +0.000%. Loom and B1 are now byte-identical
there (rack4x4 767,116 both; rack8x8 909,088 both).
**A +0.000% cell is not a win.** At 64 MB all_reduce the model hides dim1
latency for BOTH systems (chunk overlap - see the sensitivity tables
below) and dim0 is identical by construction, so nothing CAN differ.
Those cells carry no information and must not be cited in either
direction; `summarize_results.py` now flags them explicitly so the
positive-looking range cannot be misread the way the negatives were.
Contrast the 64 MB cells that ARE informative because their collectives
stay rdma_init-sensitive: all_to_all +4.4%, reduce_scatter +3.5%.

**THE 64 MB CELLS ARE TRANSPORT-INSENSITIVE, AND THE NEGATIVES WERE A
SCHEDULING ARTIFACT (measured 2026-08-04). Read this before quoting or
re-explaining any large-size cell - it has now been explained wrongly
twice ("header tax", then "ring artifact").**

At 64 MB, dim1 latency is hidden for BOTH systems while dim0 latency is
charged in full to both. all_reduce 64 MB, rack8x8, wall cycles:

| knob | sweep -> wall cycles |
|---|---|
| B1 `rdma_init` (dim1) | 0 -> 909,088 · **2400 -> 909,088** · 5000 -> 918,923 · 8000 -> 1,083,612 |
| Loom dim1 latency | 1625 -> 911,888 · **3425 -> 911,888** · 9425 -> 1,131,688 |
| Loom `t_pipe_local` (dim0) | 0 -> 909,088 · 50 -> 911,888 · 200 -> 920,288 (exactly 56x the adder) |

So B1 is COMPLETELY INSENSITIVE to `rdma_init` below ~3-4 us, and Loom is
equally insensitive on dim1. The asymmetry is dim0-vs-dim1, not
Loom-vs-baseline: both sides' transport differences are erased, and only
Loom's in-rack lookup survives on the books. **The −0.31% therefore does
not mean "Loom is slower" - that cell measures dim0 and bandwidth only.**
Note the sensitivity is per-collective: reduce_scatter at the same size IS
sensitive (2400 ns -> +33,600 cycles = 2400 x 14 steps).

**The hiding is caused by `active-chunks-per-dimension: 2`** in every
`system/*.json`, and raising it both removes the hiding and flips the
cell:

| active-chunks | B1 rdma_init delta (0 vs 2400) | Loom | B1 | gain |
|---|---|---|---|---|
| 1 | 0 | — | 1,818,176 | — |
| **2 (current)** | **0** | 911,888 | 909,088 | **−0.31%** |
| 4 | +67,200 | 575,416 | 612,278 | **+6.02%** |
| 8 | +80,808 | 575,416 | 612,278 | **+6.02%** |

Two consequences. (1) The current value understates Loom: it suppresses
exactly the per-operation cost Loom eliminates, and it also runs ~3.7x
slower in absolute terms than the model's best. (2) Every negative cell in
the matrix is an artifact of this parameter, not a property of Loom.

**RESOLVED (2026-08-04): KEEP `active-chunks-per-dimension: 2`.** It is
not an arbitrary choice - it is what ASTRA-sim itself ships for every
H100-class config, including `examples/system/native_collectives/
HGX-H100-validated.json` (2/4), which is the very config this package's
modeling approach is anchored to, plus `inputs/system/analytical/
hgx_h100_{8,16,32}gpu.json`. Only the 2-GPU / DGX-V100 / TPU configs use
1/1. Raising it to 4 would mean running a configuration ASTRA-sim never
validated, purely because it flatters Loom - the worst possible reason.
Papers do not report this knob (it is `Sys.cc`'s stream-concurrency
setting, `concurrent_streams = ceil(active_chunks / queues_per_dim[0])`,
not a modeled hardware property), so the defensible position is "we use
the shipped validated H100 configuration".
CONSEQUENCE: the 64 MB transport-insensitivity is a PROPERTY OF THE
VALIDATED CONFIG, not a defect we introduced. Disclose it, never cite a
64 MB cell as transport evidence in either direction, and use M2
(`run_p2p_sweep.sh`) for every per-operation claim.

**GOODPUT CORRECTED: Loom bulk goodput = RoCE goodput (2026-08-04).**
`--loom-goodput` was 0.947, derived as RoCE x 4096/4108 on the assumption
of a separate 12 B header. **The Coyote prototype does not send one.**
Per `HW-DESIGN.md`: bulk Loom traffic is an ordinary RDMA WRITE and
"op.len.vaddr on the wire is RDMA's own BTH/RETH" - the offset rides in
the RETH, so there are ZERO extra wire bytes on the bulk path, which is
the path every current experiment exercises. Default is now 0.95, equal to
`--roce-goodput`.
Effect: the large-message regression disappears. Cross-rack p2p at 1 GB
goes -0.30% -> **+0.01%**, i.e. clean asymptotic parity instead of a
fictitious header tax. The matrix negatives are unaffected (they are
`t_pipe_local`, as measured above).
Loom's REAL wire overhead is size-dependent and lives below 64 B, where a
sub-64 B store is padded into a 64 B inline envelope (an 8 B store becomes
64 B - an 8x amplification, nothing like 0.3%). That is the T2 coalescing
curve, owned by the testbed, and it is still deliberately unmodeled.

**FIXED: `t_pipe_local` double-counted forwarding (2026-08-04).** The
generator said "the Loom ToR IS the rack switch (whose forwarding is
already inside fabric_latency)" and then charged `t_forward` on top
anyway. Removed from BOTH local-route terms: `pipe_local` is now
`t_lookup + t_translate` = **40 ns** (was 50), and the remote route's
`dest_logic` is `t_translate` = **15 ns** (was 25) for the same reason -
the destination ToR's egress forwarding is already inside the
`fabric_latency` edge leg. Loom dim0 550 -> **540 ns**, dim1 1625 ->
**1615 ns**. Effect: M2 in-rack at 4 KB -9.4% -> **-7.55%**; worst matrix
cell -0.31% -> **-0.25%**.

**THEN SET TO ZERO (owner decision 2026-08-04).** Loom does not bolt a
translator onto someone else's switch - the Loom ToR **is** the rack
switch, and the prototype implements that switch. Its in-rack datapath
does what any peer-store path already does, so the INCREMENT over the
baseline is zero and `pipe_local` now defaults to **0** (dim0 back to
500 ns). What Loom adds over a stock switch is the REMOTE route, and that
is still charged in full on dim1 (lookup + queue + encap + 2x RoCE +
destination translate = 1615 ns).

**CONSEQUENCE, AND THE HONESTY CAVEAT: in-rack parity is now a MODELLING
IDENTITY, not a result.** Loom and B1 have byte-identical dim0
configuration, so M2's in-rack row reads +0.00% at every size by
construction, and the matrix now has ZERO negative cells. Do not present
either as evidence - a reviewer who sees "+0.00% at all ten sizes" will
correctly read it as an assumption. The claim it rests on is
architectural (the ToR is the rack switch, doing the same table consult),
and **T3 supplies the empirical version**: it measures the Loom datapath
against raw Coyote forwarding. Note that delta is an UPPER bound on the
real increment, because the stock Coyote shell does no window lookup at
all, whereas a real GPU switch does. If T3 comes back with a
non-negligible number, set `--pipe-local-ns` and rerun; the knob exists
for exactly that.

**Supporting evidence that a stock GPU switch already does this work.** NVIDIA's NVSwitch technical overview documents "final
hop-address fidelity checks and buffer over- and underflow checks", with
"routing tables ... indexed and controlled by the fabric manager,
providing protection by limiting an application's access to its specific
ranges". That is range-indexed lookup plus bounds checking in the stock
datapath - precisely what `t_lookup` + `t_translate` model, and it is
already inside the baseline's 500 ns `fabric_latency`. Integrated parts go
further: Enfabrica's ACF-S fuses a PCIe/CXL switch, a NIC and address
translation onto one die. So the honest quantity is the INCREMENT of
Loom's in-rack datapath over a stock switch's, which is smaller than 40 ns
and plausibly near zero. **T3 already measures exactly this** (Loom
datapath vs raw Coyote forwarding = a delta by construction), so do not
guess it - but until T3 reports, the model is conservative against Loom,
which is the right direction to be wrong in.
NOTE for related work: Enfabrica ACF-S is the closest commercial design to
Loom and is not yet cited.

**APP RANK PLACEMENT IS CORRECT - CHECKED, NOT ASSUMED (2026-08-04).**
Topology is `[8 xpus, 8 racks]`, so rank r lives in rack r//8. Comm-group
membership from the STG-generated group JSONs:
- **mixtral (MoE) is placed exactly right.** The 8 EP groups are
  `{0,8,16,24,32,40,48,56}`-shaped, spanning ALL 8 racks - the EP
  all-to-all crosses dim1, which is where Loom helps - while TP (`{0,2,4,6}`)
  and DP (`{0,1}`) stay in-rack. That is how it would be deployed.
- **gpt3 (dense) collectives are size-4 groups spanning 1-2 racks**, mostly
  in-rack, which raised the worry that its ~0% comm gain is a placement
  artifact. **It is not.** Forcing more cross-rack traffic makes it WORSE:
  `dp16 tp4 pp1` puts 20/20 groups across up to 4 racks and gives comm
  **+0.55%**, against `dp4 tp4 pp4`'s 16/32 cross-rack and **+3.80%**
  (`dp8 tp8 pp1`: 8/16 cross-rack, +2.79%). A DP-16 gradient all-reduce on
  a 175B model is enormous, so it is bandwidth-bound wherever it is placed.
  Dense is genuinely bandwidth-bound; the placement is fine and realistic
  (TP belongs in the scale-up domain).

**REAL CAPTURED TRACES - ACCESS PATH (catalog A3, found 2026-08-04).**
The MLCommons **Chakra Open Trace Library** exists and carries exactly the
workloads this evaluation wants: **GPT-3, Llama, Mixtral and DeepSeek-MoE**,
captured on production-scale GPU infrastructure by Georgia Tech's AI
Makerspace with HPE, across diverse parallelization strategies.
- Tools/format: `https://github.com/mlcommons/chakra` (public).
- Traces: a Google Drive folder,
  `https://drive.google.com/drive/folders/13Ojg7fLGONj5_YpYLXBKPU630PdfeFoo`,
  **restricted to approved WG members**.
- To get in: subscribe at `https://mlcommons.org/community/subscribe/`
  indicating the Chakra Working Group, associate a Google account with an
  organisational email, then the Drive folder and meeting invites follow.
  Discord `https://discord.gg/g6KUH6WvMa`; WG meets Mondays 11:05 PT.
- Paper: arXiv:2605.11333 (MLSys 2026).
**This is the long-lead item on the whole plan - membership approval is
not instant. Start it before any further sim work.** DeepSeek-MoE is the
anchor trace (the motivating workload); pair it with one dense LLM so
"no bulk regression" has real-trace support.

**Audit findings against the catalog (2026-08-04), still open:**

5. **The regime map (A4) and the t_pipe sweep are OUT of the default
   suite** (2026-08-04) — `run_all.sh` used to contradict the owner's own
   sweep policy ("FPGA-owned constants are measured, not swept; no sweeps
   in the default plan") by running both every time. Both scripts still
   work standalone.
   - `run_regime_map.sh` also passes `--pipe-ns 500`, overriding the
     per-stage source sum of 200 ns, so its Loom dim1 is 1925 ns while
     every other experiment uses 1625 ns — its numbers were never
     comparable to apps/matrix. Its message (gain → SM ceiling when
     compute-bound, → latency floor when comm-bound) is now carried by the
     apps gain decomposition in the generated section 5, which uses real
     published workloads at two scales instead of a synthetic
     compute-scaling knob, and costs no extra runs.
   - `run_sweep_tpipe.sh` is optional reviewer-proofing, and T3 will
     MEASURE t_pipe, retiring it. Keep the one durable use: it shows the
     design tolerates a ~3.6 µs pipeline, i.e. the FPGA's slow clock does
     not invalidate the claim.
6. **B3 uses `endpoint-delay: 1`, not 10** (`system/ideal_rdma.json`),
   while the constants table claims 10 ns for all systems.
7. **The congestion-aware C++ is orphaned.** With victim/VOQ descoped,
   nothing exercises `switch_egress: shared_fifo`, `EgressPolicy`, or
   `system/loom_1d.json`, yet `run_all.sh` still builds the
   `Congestion_Aware` binary that no suite script invokes.
8. **The matrix carries no SM effect** (it uses the non-roofline JSONs,
   correct for comm-only microbenchmarks) — so matrix "parity" and apps
   "+15%" are not measuring the same thing.
9. Section 5's former Loom-vs-B3 sentence ("within 0.2–1.5% at 64 MB,
   +40…105% off ideal at 1 MB") did not match the full 48-cell grid; the
   generated section now derives that range from the CSVs.

## 5b. Experiment catalog (revised 2026-07-27; full methodology text in
## the review plan; structure follows the Jigsaw paper's evaluation)

**Hardware config parameters** (calibrated on testbed → fed to sim; NOT
benchmarks): t_pipe per-stage (placeholder 200 ns, swept), goodput/
small-write-batching curve (placeholder flat 0.947), rdma_init B1/B2
(2400/2800 ns, literature — B1 NEVER swept yet), read RTT (5000 ns
placeholder), raw-platform floors, link rates, SM reservation 20/132
(published), endpoint store issue 10 ns (validated).

**Microbenchmarks** (experiments producing figures):
1. Collective bandwidth vs buffer size [sim]: {all-to-all, all-reduce,
   all-gather, reduce-scatter} × **4 KB–1 GB log-swept** (extend the
   current 1/16/64 MB matrix downward — the small-message regime where
   Loom differentiates is currently unexercised) × 4×4/8×8 × all systems.
   Report algorithm bandwidth vs size + per-collective crossover.
2. P2P send/recv sweep [sim now, HW twin later]: 1 pair, in-rack and
   cross-rack, 4 KB–1 GB; per-op-cost amortization curve.
3. Peer-store latency CDFs [HW, T1]: ≥10⁵ stores, local/remote, vs
   CPU-verbs RDMA and raw platform; same-binary = transparency demo.
4. Goodput vs transfer size [HW, T2]: 16 B–16 MB, batching on/off;
   large-size convergence to raw platform = bulk-parity evidence;
   on/off delta = encapsulator ablation; also calibrates sim goodput.
5. Read-credit scaling & exhaustion [sim done (1/N), HW twin later].
6. Smoke [sim]: 4-NPU all-to-all sanity (fix configs first).

**End-to-end macrobenchmarks** (training iterations + MoE-block; MoX-style
additions 2026-07-28 — see `mox-moe-astrasim.pdf` at repo root, Cohen et
al., same ASTRA-sim 2 + Chakra stack, methodology directly transplantable):
0. **MoE-block wall time (dispatch–compute–combine), MoX convention**:
   DeepSeek-V3-shaped EP (256 experts, top-8, width 7168; dims from
   arXiv:2412.19437 — modernizes Mixtral 8x2), normalized to the ideal
   bound (B3); isolates the comm win from the SM-roofline scaling (fixes
   the gain-attribution confound). **Tokens/GPU sweep {64, 128, 256,
   5120} doubles as the inference→training axis** (MoX precedent: small
   batches = inference; no serving stack needed) — likely Loom's best
   honest regime. Optional: Zipf skew knob with real expert-popularity
   distributions overlaid (MoX Fig 4 pattern); MoX's token-level DSv3
   traces are Technion-recorded — worth asking for (same sim version).
   Scale beyond 64 ranks via MoX's validated-proxy pattern: validate the
   ANALYTICAL-MODEL closed-form against sims ≤64 ranks, extrapolate
   analytically (MoX Fig 3 shows reviewers accept this).
1. STG Mixtral MoE + GPT-3 (done vs B1; add B2/B4) — scale-sweep vehicle.
2. **Captured production traces** [next, no HW needed]: MLCommons Chakra
   Open Trace Library (June 2026; GaTech/HPE captures) — pick TWO:
   DeepSeek-MoE (win regime; the motivating workload) + one dense LLM
   (parity regime). Access: Google Drive via free Chakra WG membership —
   join early. Traces are TRAINING captures; verify per-trace metadata on
   download. Optional stretch: self-captured MoE inference/decode trace
   (DeepEP low-latency regime) — likely Loom's best showcase, not in the
   library.
3. Regime map (done), scale sweep 2–64 racks (todo).
   **Sweep policy (owner decision 2026-07-27): FPGA-owned constants are
   MEASURED, NOT SWEPT** — once T2/T3/T6 land, per-stage latencies,
   goodput curve, and read RTT go in as measured values only (FPGA
   clock makes them pessimistic for Loom vs an ASIC ToR; say so in
   prose). No sweeps in the default plan. OPTIONAL (reviewer-proofing
   only, all data-cheap): aggregate t_pipe break-even (already done,
   ≈3.6 µs, one figure); rdma_init {300…3000 ns} as fallback if IBGDA
   can't be measured (next-step #2); SM-k / goodput-bounds /
   oversubscription.

**Motivation measurements — see `motivation/README.md` (THE record,
added 2026-08-03).** ACE-style methodology (ace_isca2021.pdf, Rashidi
ISCA'21, same ASTRA-sim lineage), organized as hardware tiers:
T0 no-hardware (NCCL backend LoC split; own analysis of MLCommons
captured traces), T1 CPU+NIC we own (who-moves-the-bytes CPU demo;
perftest → rdma_init_B2), T2 one GPU+NIC loopback (3-way
SM-copy/copy-engine/NIC contention; IBGDA loopback recipe with
NVSHMEM_DISABLE_P2P + HCA-counter verification + the CPU-vs-GPU-posted
differential trick → rdma_init_B1), T3 **Google Cloud, €250 credits — CONDITIONAL, held in reserve (triggers in README §T3)**
(the only tier with real NCCL kernels + Nsight %SM-cycles; 2–4×A100
Spot; hard budget rules in README §3 — debug free on Kaggle first,
Spot-only, self-terminating instances, ≤€120 planned spend, explicitly
NO a3/H100-CX7 machines). Evidence policy (README §0): evaluation
constants measured-or-swept; motivation evidence measured where cheap,
CITED where it is a production disclosure (DeepSeek's 20/132 stays a
citation). Payoff: T3 contention factors replace the global roofline
989/839 with a measured contention model for B1. ACE related-work note:
its endpoint-vs-switch Table II concerns in-network AGGREGATION — Loom's
switch runs no algorithm; ACE-class engines compose with Loom.

**Supporting analyses**: QP/connection-state accounting script (analytic);
sim-as-testbed validation gate (≤10–15% error, blocks all headlines);
FPGA resource table + transport-LoC comparison (once synthesized).

**DESCOPED** (owner decision 2026-07-27): victim/VOQ isolation experiment
(per-destination queueing is standard switch art — iSLIP lineage, deep-
buffer switches, 802.1Qcz; paper makes no isolation claim; shared-FIFO
comparison is a strawman; Discussion citation stands), failure-containment
(T7), control-plane-cost (T8) experiments.

**Paper restructure (2026-07-08):** design goal #6 removed (five goals
now); §6.4 deleted; per-destination queues folded into §6.2 as standard
deep-buffer engineering (no claim); new Discussion section carries the
congestion hazard + body-of-work citations (PFC spreading, VOQ classics,
Jericho, 802.1Qcz, BFC); intro contribution 4 and eval summary dropped the
isolation promise. Victim experiments (testbed T5 / Sim-V1) demoted to
discussion-supporting demos.

## 6. Next steps (priority order, revised 2026-07-27)

1. ~~**Data integrity**~~ **DONE 2026-08-04 (Phase A).** `run_smoke.sh`
   generates its configs (and B2 finally gets its own 2800 ns network
   instead of B1's); the rotted `network/*.yml` are deleted; the ∞-credit
   row is in the CSV; `plot_results.py` plots every size instead of a
   hard-coded 16 MB slice; section 5 is now generated by
   `summarize_results.py` from the CSVs, so no doc can drift from the data
   again. Smoke's sign flipped as predicted (Loom was −29% on the dead
   model, is +26.8% on the live one). "Commit a canonical results
   snapshot" was dropped deliberately: `results/` is gitignored, and the
   snapshot that matters is the generated section 5.
2. **Measure rdma_init on a GPU+RDMA-NIC box** (owner has access):
   B2 = `perftest --use_cuda` (CPU posts, GPUDirect payload);
   B1 = NVSHMEM put-latency with `NVSHMEM_IB_ENABLE_IBGDA=1` (GPU posts;
   needs ConnectX + IBGDA-capable driver) or DeepEP benchmarks.
   Measured values replace the 2400/2800 ns literature placeholders and
   retire the rdma_init sweep; sweep {300…3000 ns} only as fallback if
   IBGDA is unavailable on that box. (See §5 caveat for why this constant
   guards the headline.)
3. ~~**F2**~~ **DONE 2026-08-04 — see section 5a.** Ring artifact confirmed
   for the worst cell only (−1.11% → +30.64%); retracted for the other
   three, whose cause is measured to be the 50 ns `t_pipe_local` in-rack
   lookup adder. Follow-up worth doing: decide whether the paper reports
   the ring or the direct grid as headline (direct is both faster and
   fairer — 3 negatives instead of 5, mean +14.5% vs +12.2%), and state
   the choice explicitly rather than inheriting ring by default.
4. **B4 "today's split"** baseline (hierarchical per-dim collectives) —
   the "divide as deployed" comparison; parity vs B4 is itself the
   unification result.
5. **Captured traces** (§5b): join MLCommons Chakra WG (Drive access);
   pilot DeepSeek-MoE, then one dense LLM.
6. Collective size-sweep extension: 4 KB–1 GB log sweep (replaces the
   3-point matrix sizes); scale sweep to 16+ racks; S-2/S-4/S-6 sweeps.
7. QP-count accounting script (comm matrix → QPs/switch, per-binding vs
   pooled; feeds connection-scaling.md figure).
8. Motivation M1–M2 (NCCL kLoC split, Nsight SM profile) — fills §2
   `\tbd{}`s; needs only a multi-GPU box, no FPGA.
9. Testbed (Coyote Phases 0–5, `implementation-plan.md`) — calibration:
   t_pipe (T3), goodput/batching curves (T2), issue rate (Gate 2), read
   RTT (T6), B2 cost. Then replace placeholders + validation gate (S6
   twin config; gate blocks all headlines). FPGA resource table for free.
10. Paper §7/§8 writing once numbers exist.
DESCOPED (do not resurrect without owner sign-off): victim/VOQ isolation,
failure-containment (T7/Sim-V3), control-plane-cost (T8) experiments;
ns-3 tier remains an escalation path only.

## 7. Environment facts

- Docker image `astra-sim:loom` built from repo Dockerfile (ubuntu 22.04,
  protobuf 29 from source). Chakra python bindings: `protoc` run once (see
  run scripts). Container runs as root → results/ files root-owned.
- Host pip is PEP-668 locked; install matplotlib inside the container.
- `column` not in image (run_all.sh uses sed).
- Known dead CLI flags: `--compute-scale`, `--comm-scale` (parsed, unused
  for Chakra ETs).
- Memory dir (`~/.claude/.../memory/`) duplicates key invariants — but this
  checkpoint supersedes it if they conflict on a new machine.


## 8. Artifact -> real-system correspondence

> Folded in from CODE-MAP.md on 2026-08-04, which is now deleted. For
> each artifact: what was written and how it corresponds to the real
> Loom system (the paper design; the Coyote/U280 prototype; an ASIC
> ToR). Result numbers live ONLY in the generated section 5 - never
> quote a number here.

### 1. Simulator extensions (C++)

#### 1.1 Congestion-aware backend — switch egress policy
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
(paper §6.2 transport, presented as standard deep-buffer engineering; the
isolation claim moved to the paper's Discussion section, 2026-07-08, with
no quantitative claim made). The `SharedFifo` mode is the **strawman** — a
shared-buffer switch whose head-of-line chunk blocks everything behind it.
The victim experiment (FCT identical to solo under VOQ; 3.2× under
SharedFifo) now *supports the discussion*, demonstrating that known egress
disciplines handle the hazard — it is not a headline result.

**Limitation:** backend is 1-dim only, so the ToR under test is modeled as
a flat switch — this isolates the egress mechanism but cannot show
uplink-level congestion (2-dim support would be the extension).

#### 1.2 Remote-memory backend — credit-capped peer reads
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

#### 1.3 Workload layer — memory ops hold no issue slot
**Where:** main fork, `astra-sim/workload/HardwareResource.cc`.

**What was written:** `MEM_LOAD_NODE`/`MEM_STORE_NODE` return early from
`occupy()/release()/is_available()` instead of taking the single in-flight
GPU-op slot.

**Real-system correspondence:** a GPU issues loads from thousands of lanes
(deep memory-level parallelism); the real limit on outstanding peer reads
is the **fabric credit budget** (1.2), not issue serialization. Without
this, the credit cap could never bind.

### 2. Network model (config generation, no simulator changes)

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
| dim1 latency = edge legs (500) + source stages `t_lookup+t_queue+t_encap` (200*) + `roce_stream` (150) + wire (600) + `roce_stream` (150) + dest stages `t_translate+t_forward` (25*) = 1625 ns; stage params map 1:1 to hw-controller blocks (D13) | cross-rack peer store: source = lookup/validate + encap + RoCE TX; destination = RoCE RX + decap + the same check/translate/forward as local delivery (routes converge on the transaction generator, §6.1) — no separate RDMA initiation exists in Loom (D5), and the destination is NOT a second full pipeline (D10). T3 measures the end-to-end sum; zero roce_stream if t_pipe measured inclusive |
| dim1 bandwidth × 0.947 | RoCE goodput 0.95 (header math) × 4096/4108 (12 B ⟨offset·op·len⟩ Loom header) |
| baseline dim1 latency = wire + `rdma-init` (B1 2400 ns, B2 2800 ns) | per-RDMA-op initiation, paid once per rack crossing; ≈3 µs end-to-end GPU-initiated put (IBGDA/NVSHMEM), resp. ib_write_lat + NCCL proxy handoff |
| baseline dim0 = fabric only | an in-rack baseline peer access is a plain store too — route-split, user-identified fix |
| `--uplink-oversub` | Loom ToR uplink aggregate vs the baseline's M per-GPU NICs (equal-wires default) |
| `--dim1-topology Switch\|Ring\|FullyConnected` | inter-ToR fabric shape |

\* = ⚑ FPGA-owned (T3 stage counters / Coyote floors), swept; everything
else published/validated (README → "Constants: who owns each number").

**Known gap (disclosed):** orthogonal dims let Loom's cross-rack traffic
bypass dim0 capacity — matches the baseline's separate NIC, flatters Loom's
single shared fabric port. Congestion-tier item.

### 3. Endpoint models (system JSONs, no simulator changes)

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

### 4. Workload tooling (Python; no hand-authored applications)

| File | What it is | Corresponds to |
|---|---|---|
| `fetch_stg.sh`, `gen_stg_workloads.sh` | pins STG (astra-sim's generator) and wraps `moe`/`dense` presets with **published dims** (Mixtral 8x7B, GPT-3 175B); rank count = dp·tp·pp·ep | application workloads (W-A/W-B in the eval plan); dims never invented |
| `workload/gen_p2p_patterns.py` | single/incast/victim flow stimulus (per-role sizes, unique tags, matching recvs; idle ranks get a 1 µs COMP — the feeder rejects empty traces) | iperf-category mechanism stimulus; the victim pattern is testbed T5's twin |
| `workload/gen_read_pattern.py` | N independent MEM_LOADs per rank | read-credit experiments (testbed T6 twin). Credits apply ONLY to MEM_LOAD/STORE workloads (by design: credits bound non-posted reads; writes are posted). `read-credits` >= outstanding loads = effectively infinite; the sweep's 1048576 point is the uncapped design |

### 5. Experiment harness

Numbers deliberately absent - every result lives in the generated
section 5. This table says only what each script stresses.

| Script | Stresses (design §) | Catalog entry |
|---|---|---|
| `run_smoke.sh` | endpoint models on shipped ETs; generates its own configs | M6 |
| `run_victim.sh` | OPTIONAL standalone demo, excluded from run_all (paper claims no isolation) | DESCOPED |
| `run_sweep_credits.sh` | §6.3 read credits | M5 (sim half) |
| `run_sweep_tpipe.sh` | §6.1 switch cost (break-even) | A6 optional sweep |
| `run_regime_map.sh` | §2 #4 SM reclamation vs comm-boundedness | A4 |
| `run_matrix.sh` | patterns × topologies × systems (`SUFFIX=_direct` for F2) | M1 (partial) |
| `run_apps.sh` | end-to-end applications (`SUFFIX=_direct` for F2) | A1, A2 |
| `run_f2.sh` | matrix+apps under direct algorithms | F2 |
| `run_all.sh`, `run_all_docker.sh`, `plot_results.py`, `summarize_results.py` | artifact: one command → CSVs + PDFs + generated §5 | — |

### 6. Deliberately NOT in the simulation

Address translation correctness, isolation checks, ordering, revocation —
correctness properties, demonstrated on the testbed, present here only as
constants inside t_pipe. Failure containment is (planned) an event, not a
protocol. QP/connection state is counted analytically, never simulated.


## 9. Review verdicts, MoX additions, reviewer defenses

> Folded in from HANDOFF-EVAL-REVIEW.md (review session 2026-07-26 ->
> 2026-08-02) on 2026-08-04, which is now deleted. Its findings and
> phased plan are already carried by sections 5b/6; these three
> sections existed nowhere else.

### 2. Verdicts (short form)

- **Idea**: worth pursuing; the switch-side-translation-for-commodity-GPUs
  slot is unoccupied (UALink = pod-only; SUE = endpoint framework, future
  silicon; UB = clean-slate; DeepEP = software on top of the divide).
  Window is now (UALink silicon 2026-27). Name collides with Loom NSDI'19.
- **Design**: sound. Three translation points are all existing mechanisms
  (GPU peer mappings / address-range decode / MR-style offset tables).
  Two subtleties to state in the paper: apertures are uncached (same
  non-coherent model as PCIe P2P/NVLink today — one sentence); ordering
  is per-binding, narrower than PCIe's source→dest posted ordering
  (inline flags fine; cross-segment data+flag not guaranteed; pooled
  connections would restore it).
- **Sim**: proper ASTRA-sim integration, good provenance hygiene, but the
  Loom-vs-B1 delta reduces to four scalars, two unmeasured (t_pipe 200 ns,
  rdma_init 2400 ns); all headline runs congestion-unaware.
- **Evaluation**: plan docs are NSDI-caliber; execution is one baseline
  deep, ring-only, ≤64 NPUs, sim-only, and violates the project's own
  validation gate (testbed not started). Not submittable yet. Target
  NSDI spring-2027 (testbed is ~13–17 wks and gates submission).

### 5. MoX-derived evaluation additions (mox-moe-astrasim.pdf — same
### ASTRA-sim 2 + Chakra stack, methodology transplantable)

- **MoE-block wall time** (dispatch–compute–combine) normalized to the
  ideal bound: isolates the comm win from SM-roofline scaling (fixes the
  attribution confound of §3.5).
- **Tokens/GPU sweep {64,128,256,5120}** on the MoE block: small batches
  model inference, large training — the inference axis with no serving
  stack (MoX precedent).
- **Validated analytical proxy for scale**: validate ANALYTICAL-MODEL's
  closed-form against sims ≤64 ranks, extrapolate beyond (MoX Fig 3 shows
  reviewers accept proxy-vs-sim correlation in lieu of giant sims).
- Optional: Zipf expert-skew knob with real DSv3/Qwen3 popularity
  overlaid (MoX Fig 4); ask Technion (Silberstein group) for MoX's
  token-level DSv3 traces — real skewed expert traffic, same sim version.

### 8. Reviewer-defense notes (worked out this session)

- "Why not wait for UALink/SUE silicon?" → deployed fleets, multi-vendor,
  zero endpoint change; UALink stops at the pod, SUE needs new silicon.
- "Just use CPU-initiated RDMA for bulk?" → proxy costs host cores +
  breaks kernel-initiated overlap (NVIDIA's own IBGDA motivation, DeepEP
  chose IBGDA); concedes fine-grained ops → divide returns; still the
  transport contract. Quantitative answer = B4 baseline.
- "DeepEP already solves MoE comm?" → DeepEP is the divide made flesh:
  dual NVLink/RDMA paths, transport state in kernels, one hardware
  combo, new API. Loom subsumes its transport, keeps its math. Cite it
  as B1's concrete instantiation.
- "Why does Loom help large ops?" → it doesn't speed them up; it carries
  them at parity while removing SMs/transport/NICs from the accelerator,
  and covering bulk is what makes "one contract" true.
- Aperture address-space exhaustion is a non-issue (64-bit PCIe/CXL
  windows; resizable-BAR analog); the finite resource is switch table
  SRAM → QP/state-accounting figure.
