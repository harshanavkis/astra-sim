# CHECKPOINT — Loom project state

> **Last updated: 2026-08-03, late II (6.2a BUNDLED TWO-HOST BINARY CODE
> DONE: Coyote `examples/loom/sw-bundled/` - loomd<->loomd TCP peering
> (staging-VA hello, cross-host handle resolution, DONE barrier), QP
> setup via cThread::initRDMA, BundledOrchestrator programs remote
> imports as rdma windows (pid = local QP owner, base = exporter VA);
> FPGA-free peering test 17x PASS; execution needs the two-host testbed.
> Earlier same evening: T3 STAGE CYCLE COUNTERS IMPLEMENTED,
> owner move-up: prototype phase 5.3b adds RO CSR words 48-63 — cycle
> counter, order-FIFO residency accumulator (t-queue), per-stage cycle
> sums + op counts (t-lookup/t-forward/t-encap + dma/read/fence) — all
> sims green (block TBs incl. exact-cycle checks, C++ integration 19x
> PASS, Python exact counts); T3 now needs only hardware runs. The
> FPGA-owned table intro in README.md and the implementation-plan banner
> reflect this. Earlier same day, TESTBED WORK STARTED: the Coyote vFPGA
> prototype now exists in the Coyote repo, `examples/loom/` — RTL
> (ctrl/table/engine/rx/arbiter), 5 block TBs, integration sim via the
> real cThread API, Python RDMA TX test, role-split sw, ALL GREEN in XSIM;
> hardware phases 5.2+ pending testbed time. `implementation-plan.md`
> here is now the AUTHORITATIVE plan, updated with an implementation-
> status banner and the eval-review descopes applied inline: Phase 4
> victim/failure DEAD, reads PLANNED scoped to T6 read-RTT calibration
> (correcting an earlier same-day edit that briefly marked them
> optional), Phase 6 tier-1 built; testbed deliverables = the FPGA-owned
> constants (T3 stage latencies, T2 coalescing curve, T6 read RTT,
> floors, B2 rdma-init). Reads moved UP in the prototype roadmap (owner
> direction 2026-08-03): local read path is the next phase, before the
> loomd software split. Prior update 2026-08-02:
> evaluation-review session closed out: `HANDOFF-EVAL-REVIEW.md` added —
> full session record, verdicts, integrity findings, decisions, phased
> implementation plan A–D, reviewer defenses. Prior updates 07-27/28:
> experiment catalog §5b, §5 reconciled to CSVs, descoping + sweep-policy
> + positioning decisions, MoX additions).** LIVING DOCUMENT — overwritten in place with
> every change (user mandate), alongside `CODE-MAP.md`. Written for session
> restart on a possibly different server: read this first; it contains
> everything needed to resume. Lives in the astra-sim repo (branch
> `loom-sim`, next to `examples/loom/README.md` with the run instructions);
> companion design docs live in `loom-paper/design-docs/`.

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
(Local submodule push remotes stay ssh; do not run `git submodule sync`
or it overwrites them with the https URLs.)

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

- Smoke (`smoke.csv`, 4-NPU 1 MB all-to-all): b3_ideal_rdma 10195 < loom 14723 < b1_gpu_rdma 20105 < b2_cpu_proxy 36744. Loom vs B1 **+26.77%**.
- Read credits (`sweep_credits.csv`, caps 1-1048576): exact linear 1/N scaling from 325568 cycles. Uncapped row present and equal to the 64-credit row.
- Break-even t_pipe (`sweep_tpipe.csv`): **3596 ns** (linear, 480 cycles/ns).
- Regime map (`regime_map.csv`): **13.9%** at 12% exposed comm -> **3.3%** at 91%. No negative point.
- Matrix (`matrix.csv`, 48 Loom-vs-B1 cells): +1.6...+39.5% @1 MB, -1.1...+22.8% @16 MB, -0.3...+6.1% @64 MB.
  5 negative cells (1x all_gather, 4x all_reduce); worst **-1.11%** (ring_tor all_reduce 16 MB).
  vs B2: Loom wins all 48 cells (+0.1...+72.7%).
  vs B3: +0.2...+104.7% off B3 across all 48 cells.
- Apps (`apps.csv`): gpt3_dense 32 ranks **+5.25%**; gpt3_dense 64 ranks **+4.97%**; mixtral_moe 16 ranks **+7.47%**; mixtral_moe 64 ranks **+15.01%** vs B1.

- Matrix F2 (direct algorithms) (`matrix_direct.csv`, 48 Loom-vs-B1 cells): +2.8...+42.4% @1 MB, +0.1...+30.6% @16 MB, -0.3...+7.7% @64 MB.
  3 negative cells (1x all_gather, 2x all_reduce); worst **-0.31%** (rack8x8 all_reduce 64 MB).
  vs B2: Loom wins all 48 cells (+0.2...+74.3%).
  vs B3: +0.2...+129.5% off B3 across all 48 cells.
- Apps F2 (direct algorithms) (`apps_direct.csv`): gpt3_dense 32 ranks **+5.25%**; gpt3_dense 64 ranks **+4.97%**; mixtral_moe 16 ranks **+7.47%**; mixtral_moe 64 ranks **+15.01%** vs B1.
<!-- END GENERATED RESULTS -->

## 5a. Phase-A findings (2026-08-04) — read before interpreting section 5

**F2 is settled, and the ring-artifact story was half wrong.**

1. F2 as previously specified (flip only `all-to-all-implementation` to
   `direct`) could never have answered the question: **all five negative
   cells were all_reduce (4) and all_gather (1); none was all_to_all.**
   The `*_direct.json` variants therefore switch all four collectives, for
   all four systems together (`SUFFIX=_direct`, `run_f2.sh`).
2. **Confirmed for the worst cell only.** `ring_tor all_reduce 16 MB` goes
   −1.11% → **+30.64%** under direct, and `ring_tor all_reduce 64 MB`
   −0.31% → +2.78%. Those were a ring-algorithm-on-Ring-dim1-topology
   artifact and must no longer be described as a Loom deficiency.
3. **Retracted for the rest.** Three cells are bit-identical under both
   algorithms (`rack4x4`/`rack8x8` all_reduce 64 MB, `thin_uplinks`
   all_gather 64 MB). Their cause is now measured, not guessed: it is
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

**Audit findings against the catalog (2026-08-04), still open:**

5. **The regime map (A4) is not comparable to apps/matrix.**
   `run_regime_map.sh` passes `--pipe-ns 500`, which overrides the
   per-stage source sum of 200 ns, so its Loom dim1 is 1925 ns while every
   other experiment uses 1625 ns. Pessimistic for Loom, so the gains are
   if anything understated — but it is undisclosed in the constants table.
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
