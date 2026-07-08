# CHECKPOINT — Loom project state

> **Last updated: 2026-07-08 (README VOQ explainer + egress toggle + knob list).** LIVING DOCUMENT — overwritten in place with
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

## 5. Results so far (constants now published/validated; t_pipe swept)

- Victim isolation: solo 77,024 = VOQ 77,024 (bit-identical) vs shared-FIFO
  249,954 cycles (3.2×). The isolation money-plot twin works.
- Read credits: exact linear concurrency scaling.
- Break-even t_pipe ≈ 950 ns on Mixtral-MoE (500 ns placeholder wins).
- Regime map (Mixtral shape): +12.8% compute-bound (13% exposed comm;
  SM ceiling 15.2%) → +2.6% balanced → −3% comm-bound.
- Matrix (16 MB): pure-comm collectives parity-to-NEGATIVE (worst −11.7%
  all_reduce 8×8) — per-hop t_pipe × many-hop ring vs per-message 700 ns.
- Apps: gpt3_dense +5.3%/+4.7% (32/64 ranks); mixtral_moe +2.6% (16) but
  **−9.1% (64, comm-bound ep8)**.
- STRATEGIC READ: claim = SM reclamation (≤15%) + bulk parity + latency/
  isolation/unification. NOT a bulk-speedup paper. Comm-bound losses are a
  ring-algorithm artifact until F2 is checked.

## 6. Next steps (priority order)

1. **F2**: rerun matrix/apps/sweeps with `direct` all-to-all (config change:
   `all-to-all-implementation: ["direct","direct"]`) — ring inflates Loom's
   per-hop tax; expected to flip several negative cells.
2. **B1 endpoint-cost sweep** {300, 700, 1500, 3000 ns} — 700 ns likely
   generous to baseline.
3. **B4 "today's split"** baseline (hierarchical per-dim collectives).
4. QP-count accounting script (comm matrix → QPs/switch, per-binding vs
   pooled; feeds connection-scaling.md figure).
5. S6 validation-twin config skeleton (awaits testbed numbers).
6. Testbed (Coyote Phases 0–5, `implementation-plan.md`) — calibration
   constants: t_pipe (T3), goodput curves (T2), issue rate (Gate 2), read
   RTT (T6), B2 cost. Then replace placeholders + validation gate.
7. Paper §7/§8 writing once numbers exist; motivation M1–M3 measurements
   (NCCL kLoC count, SM profile) fill §2 `\tbd{}`s.
8. Larger: 2-dim congestion-aware, failure injection (Sim-V3), ns-3 tier
   (check fork's config.txt CC knobs first).

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
