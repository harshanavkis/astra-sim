# HANDOFF — Loom evaluation review session (2026-07-26 → 2026-08-02)

> Session record of a full review of the Loom paper, simulation, and
> evaluation, plus the resulting implementation plan. Written for resuming
> this work on another machine. Read alongside `CHECKPOINT.md` (living
> project state — supersedes this doc where they conflict) and
> `CODE-MAP.md`. The paper draft lives in `~/loom-paper` (tex is design
> ground truth); the MoX paper referenced below is `mox-moe-astrasim.pdf`
> at the repo root (untracked — arXiv:2607.20220, "MoX: Efficient MoE
> Routing on Direct-Connect Topologies", Cohen et al.).

## 1. What this session did

Reviewed: the full paper draft (all tex), the design docs
(`~/loom-paper/design-docs/`), the sim implementation (this folder + both
submodule forks), the shipped `results/*.csv`, the evaluation plan
(`evaluation-methodology.md`, `simulation-eval-plan.md`), the Jigsaw
paper's evaluation structure (methodology template), and the MoX paper
(MoE eval methodology on the same ASTRA-sim 2 + Chakra stack). Surveyed
the external landscape (UALink 1.0, Broadcom SUE, UB-Mesh/UnifiedBus,
NCCL 2.28 Device API LSA/GIN split, ThymesisFlow, CXL-over-Ethernet,
DeepEP, MLCommons Chakra Open Trace Library).

Updated during the session: `CHECKPOINT.md` §5 (results reconciled to
CSVs — several numbers were stale, see §3 below), new §5b (experiment
catalog), §6 (reprioritized next steps + sweep policy).

## 2. Verdicts (short form)

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

## 3. Data-integrity findings (fix before quoting any number)

1. `run_smoke.sh` is the only script reading committed `network/*.yml`,
   which encode the PRE-D10 model (Loom dim1 3000 vs baseline 2000 — the
   inverse of the current 1625 vs 3000). `smoke.csv` measures a dead
   model; the README's "Loom honestly loses" framing of it is wrong.
2. Stale doc numbers (now fixed in CHECKPOINT §5, still wrong in
   README/CODE-MAP): mixtral-64 is **+15.0%** (CHECKPOINT said −9.1%);
   break-even is **≈3.6 µs** (docs said 0.95/1.6/2 µs); regime map is
   **+13.9%→+3.3%**, no negative point (docs said −3%); matrix worst cell
   is **−1.11%** (docs said −11.7%).
3. `sweep_credits.csv` is missing the ∞-credit row the README counts.
4. Victim experiment is structurally vacuous (1-dim flat switch: victim
   and aggressors share no link, so VOQ==solo by construction).
5. **Gain-attribution caveat**: mixtral-64's +15% is 82% exposed-comm and
   ~84% of the gain is comm-time reduction — it rides the unmeasured
   `rdma_init_B1 = 2400 ns` placeholder, NOT SM reclamation. Decompose
   before quoting; measuring rdma_init is the guard.

## 4. Decisions made (owner, this session)

1. **Descoped permanently**: victim/VOQ isolation experiment (standard
   switch art — iSLIP/deep-buffer/802.1Qcz; paper makes no isolation
   claim; shared-FIFO comparison is a strawman), failure-containment
   (T7), control-plane-costs (T8).
2. **Sweep policy**: FPGA-owned constants are MEASURED, NOT SWEPT (FPGA
   clock makes them pessimistic for Loom vs an ASIC — say so in prose).
   No sweeps in the default plan. Optional only: t_pipe break-even
   (already done, ≈3.6 µs), rdma_init {0.3–3 µs} as fallback if IBGDA
   can't be measured, SM-k/goodput/oversub.
3. **rdma_init gets MEASURED on the owner's GPU+NIC box**: B1 via NVSHMEM
   put latency with `NVSHMEM_IB_ENABLE_IBGDA=1` (or DeepEP bench); B2 via
   `perftest --use_cuda`. (perftest --use_cuda alone = CPU-posted = B2,
   not B1 — the distinction matters.)
4. **Positioning**: general unified peer fabric, MoE as flagship — NOT an
   MoE paper. Wins concentrate in fine-grained EP all-to-all; dense =
   parity regime, and parity vs today's split IS the unification result
   (one contract, zero comm SMs, no transport state on the GPU, no
   per-GPU NIC). Scope the SM-reclamation claim to the training/
   normal-kernel regime (DeepEP's low-latency hook mode avoids SM
   occupation during decode transfers).
5. **E2E workloads**: all training (STG + captured); two captured traces —
   DeepSeek-MoE (win regime, the motivating workload) + one dense LLM
   (parity regime). Optional stretch: self-captured MoE inference/decode
   trace. Mixtral is dated as the MoE example — add a DeepSeek-V3-shaped
   EP workload (256 experts top-8, width 7168, arXiv:2412.19437).

## 5. MoX-derived evaluation additions (mox-moe-astrasim.pdf — same
## ASTRA-sim 2 + Chakra stack, methodology transplantable)

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

## 6. Implementation plan (what exists vs what to build)

**Exists, no work**: config generator (`gen_network_config.py`), four
endpoint models (`system/*.json`), credit-capped reads (remote-memory
fork), STG Mixtral/GPT-3, stimulus generators, suite harness + plots,
five experiments of data, reconciled CHECKPOINT.

**Phase A — integrity (~1 day, config/doc only)**
1. `run_smoke.sh` generates configs like every other script; regenerate
   or delete committed `network/*.yml`; rerun full suite.
2. Rerun credit sweep incl. ∞ point; fix `plot_results.py` hard-coded
   16 MB matrix slice.
3. Reconcile README + CODE-MAP to fresh CSVs; commit canonical results
   snapshot.
4. F2: `all-to-all-implementation: ["direct","direct"]`, rerun
   matrix/apps (verifies/retracts ring-artifact explanation of the
   negative cells).

**Phase B — new sim experiments (~1–2 wks, no hardware)**
1. **B4 "today's split" baseline** (biggest gap): native contract on
   dim0, B1 costs on dim1, hierarchical per-dim collectives (ASTRA-sim
   per-dim algorithm arrays). Parity vs B4 = the unification result and
   the answer to "just use CPU RDMA / best-of-both".
2. **MoE-block benchmark** (§5): DSv3-shaped EP block + tokens/GPU sweep;
   prefer an STG preset with DSv3 dims, else ALL_TO_ALL+COMP+ALL_TO_ALL
   generator labeled published-shape block (provenance rule 2 respected).
   New `run_moe_block.sh`.
3. **Collective size sweep**: matrix sizes extended to 4 KB–1 GB log
   sweep (small-message regime, where Loom differentiates, is currently
   unexercised), direct algorithm.
4. **P2P sweep script**: `gen_p2p_patterns.py --pattern single` across
   sizes, in-rack + cross-rack, all systems.
5. **Captured traces**: join MLCommons Chakra WG NOW (Drive access has
   lead time; traces are training captures — verify metadata on
   download); pilot DeepSeek-MoE, then one dense LLM; `run_traces.sh`.
   Fallbacks: MICRO'24 tutorial Megatron-LM 43B (32 ranks PP4·TP4·DP2);
   self-captured `chakra_trace_link` DeepEP run.
6. **QP-accounting script**: comm matrix → QPs/switch, per-binding vs
   pooled (`connection-scaling.md` fix), vs cluster size/tenancy.
7. **Analytical-proxy validation** script + extrapolation plot (§5).
8. Optional: Zipf skew knob; SM-model form fix (scale only
   comm-overlapping compute instead of global roofline; don't mix H100
   peak TFLOPS with H800 SM counts).

**Phase C — GPU-box session (one reservation)**
Measure rdma_init B1 + B2 (§4.3), Nsight %SM-cycles profile (motivation
M2), NCCL scale-up/scale-out backend LoC split (M1, any machine — fills
the paper's §2 `\tbd{}`s). Substitute measured constants into
`system/*.json` + ANALYTICAL-MODEL, rerun apps/matrix/MoE-block.

**Phase D — FPGA testbed (long pole, ~13–17 wks; gates NSDI)**
Coyote Phases 0–3 minimum → measured t_pipe/goodput/floors → store-CDF
and goodput figures (T1/T2) → validation gate (sim-as-2×2-testbed,
≤10–15% error — blocks every headline) → FPGA resource table + transport
LoC comparison (Jigsaw §7.6/7.7 analogs).

**Paper tasks (parallel)**: positioning sentence (§4.4); uncached-aperture
and per-binding-ordering sentences (§2 verdicts); related work (DeepEP,
MoX, ThymesisFlow, CXL-over-Ethernet, UALink/SUE/UB, disaggregation);
evaluation/implementation sections as numbers land.

## 7. Verification

Phase A: `run_all_docker.sh` → smoke sign should flip vs current
`smoke.csv`; CSVs match all three docs. Phase B: B4 in every comparison;
MoE-block win grows as tokens/GPU shrinks; proxy-vs-sim correlation shown
before any extrapolated claim. Phase C: headline survives the measured
rdma_init — if not, shift the claim onto the regime-map / MoE-block
framing (parity + reclamation + unification still stands).

## 8. Reviewer-defense notes (worked out this session)

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
