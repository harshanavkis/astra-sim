# CHECKPOINT — Loom project state

> **Last updated: 2026-08-02 (evaluation-review session closed out:
> `HANDOFF-EVAL-REVIEW.md` added — full session record, verdicts,
> integrity findings, decisions, phased implementation plan A–D, reviewer
> defenses. Prior updates 07-27/28: experiment catalog §5b, §5 reconciled
> to CSVs, descoping + sweep-policy + positioning decisions, MoX
> additions).** LIVING DOCUMENT — overwritten in place with
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
  translations. **Testbed work NOT started.**
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

**Standing docs:** `examples/loom/CODE-MAP.md` = running summary of all
code and its real-system correspondence; `CLAUDE.md` at repo root = working
rules. BOTH this checkpoint and CODE-MAP are overwritten in place on every
change.

## 5. Results so far (reconciled to `results/*.csv` on 2026-07-27 — the
## CSVs are ground truth; earlier checkpoint numbers were stale)

- Apps (`apps.csv`): mixtral_moe **+7.47% (16 ranks) / +15.01% (64)**;
  gpt3_dense **+5.25% (32) / +4.97% (64)** vs B1. CAVEAT (gain
  attribution): mixtral-64 is 82% exposed-comm and ~84% of its gain is
  comm-time reduction — i.e. it rides the unmeasured `rdma_init_B1 =
  2400 ns` placeholder, NOT the SM-reclamation story. Decompose honestly
  before quoting; rdma_init sweep (next-steps #2) is the guard.
- Regime map (`regime_map.csv`): **+13.9%** compute-bound (12% exposed
  comm; SM ceiling 15.2%) → **+3.3%** fully comm-bound (91% exposed).
  NO negative/parity point in current data (older "−3%" was pre-D10/D13).
- Matrix (`matrix.csv`, 48 Loom-vs-B1 cells): +1.6…+39.5% at 1 MB,
  −1.1…+22.8% at 16 MB, −0.3…+6.1% at 64 MB; only 5 small negative
  cells (worst −1.11%, ring_tor all_reduce 16 MB). vs B2 wins everywhere;
  vs B3 within 0.2–1.5% at 64 MB but +40…105% off ideal at 1 MB.
- Break-even t_pipe (`sweep_tpipe.csv`): **≈3.6 µs** on Mixtral-MoE
  (linear, 480 cycles/ns). Earlier "950 ns"/"~2 µs" claims were stale.
- Read credits (`sweep_credits.csv`): exact linear 1/N concurrency
  scaling, caps 1…64. A closed-form mechanism proof (reads bypass the
  network model; no bandwidth sharing). The ∞-credit row is MISSING from
  the CSV despite the README counting it — rerun.
- Smoke (`smoke.csv`): **INVALID** — `run_smoke.sh` is the only script
  reading the committed `network/*.yml`, which encode the pre-D10 model
  (Loom dim1 3000 vs baseline 2000, the inverse of the current model).
  The "Loom loses with no compute to reclaim" framing in the README is
  wrong; regenerate configs like the other scripts and rerun.
- Victim (`victim.csv`): solo 77,024 = VOQ 77,024 vs shared-FIFO 249,954
  (3.2×) — but the 1-dim flat-switch topology gives victim and aggressors
  NO shared link, so VOQ==solo is guaranteed by construction and the
  shared-FIFO comparison is a strawman. Already excluded from run_all and
  demoted to a discussion demo; now formally DESCOPED (see §5b).
- STRATEGIC READ: claim = SM reclamation (≤15%) + bulk parity + latency +
  unification (isolation claim withdrawn). NOT a bulk-speedup paper.
  Parity vs the split baseline IS a result: same performance with one
  contract, zero comm SMs, no transport state on the accelerator, no
  per-GPU NIC. Outright wins live where per-op costs concentrate:
  fine-grained cross-rack transfers and EP all-to-all. Negative matrix
  cells still attributed to the ring algorithm until F2 is run.

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

**Motivation measurements** (fill §2 \tbd{}s; any GPU box): NCCL
scale-up/scale-out backend LoC split; Nsight %SM-cycles during all-to-all.

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

1. **Data integrity (days)**: make `run_smoke.sh` generate configs like the
   other scripts (or regenerate+commit `network/*.yml`); rerun the full
   suite; add the missing ∞-credit run; reconcile README/CODE-MAP against
   the fresh CSVs (this checkpoint is reconciled as of 2026-07-27); commit
   a canonical results snapshot.
2. **Measure rdma_init on a GPU+RDMA-NIC box** (owner has access):
   B2 = `perftest --use_cuda` (CPU posts, GPUDirect payload);
   B1 = NVSHMEM put-latency with `NVSHMEM_IB_ENABLE_IBGDA=1` (GPU posts;
   needs ConnectX + IBGDA-capable driver) or DeepEP benchmarks.
   Measured values replace the 2400/2800 ns literature placeholders and
   retire the rdma_init sweep; sweep {300…3000 ns} only as fallback if
   IBGDA is unavailable on that box. (See §5 caveat for why this constant
   guards the headline.)
3. **F2**: rerun matrix/apps/sweeps with `direct` all-to-all
   (`all-to-all-implementation: ["direct","direct"]`) — verifies or
   retracts the ring-artifact explanation of the negative cells.
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
