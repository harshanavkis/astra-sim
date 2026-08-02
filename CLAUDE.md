# Working rules for this repo (Loom simulation, branch `loom-sim`)

Start here when resuming: `examples/loom/CHECKPOINT.md` (project state),
`examples/loom/HANDOFF-EVAL-REVIEW.md` (2026-08 evaluation-review session:
verdicts, integrity findings, decisions, phased implementation plan A–D —
the current work queue), `examples/loom/CODE-MAP.md` (what every piece of
code models; its result numbers are stale until the Phase-A rerun),
`examples/loom/README.md` (how to run).

## Standing rules (from the project owner)

1. **With every commit that adds or changes anything, overwrite BOTH
   `examples/loom/CODE-MAP.md` AND `examples/loom/CHECKPOINT.md` in place**
   (bump their Last-updated dates). CODE-MAP = what was written and how it
   corresponds to the real Loom system; CHECKPOINT = full project state for
   session restart. Do not let either drift.
2. **No hand-authored application workloads.** Application traces come only
   from: the repo's shipped microbenchmark ETs, STG with published model
   dimensions (Mixtral 8x7B, GPT-3 175B — never invent dims), or captured
   PyTorch ETs. Flow-level stimulus generators (victim/incast/reads) are
   allowed but labeled as microbenchmarks, never as applications.
3. **Every constant needs provenance**: a validated AstraSim config, a
   published measurement, or the Coyote testbed. Placeholders are allowed
   only if documented in the README table AND swept. Currently only
   t_pipe/t_pipe_local and the coalescing curve are testbed-owned.
4. **Modeling invariants**: endpoint costs are route-split (in-rack peer
   access is a plain store for every system; RDMA initiation exists only on
   the scale-out route); the Loom ToR IS the rack switch (in-rack pays only
   the lookup adder t_pipe_local, full t_pipe is remote-route only);
   equal-wires topology fairness with the shared-XPU-edge gap disclosed.
5. **Honest reporting**: negative/parity results are recorded in commit
   messages and CODE-MAP, never dropped. The paper claim is SM reclamation
   + bulk parity + latency/isolation/unification — not bulk speedup.
6. Commit at regular intervals on `loom-sim`; **no Co-Authored-By lines**.
7. Run experiments inside the Docker image `astra-sim:loom` (official
   Dockerfile); one-command suite: `examples/loom/run_all_docker.sh`.
8. The paper repo (`~/loom-paper`) is OFF LIMITS: never edit or commit
   anything there unless explicitly told; all work lives on this repo's
   `loom-sim` branch. (Paper prose rules, for when asked: no em dashes,
   XPU terminology, tex is design ground truth: no GFA/token/tag/seq;
   wire = offset·op·len.)
9. Paper-repo references in CODE-MAP/CHECKPOINT stay on `loom-sim` (they
   bind code to the design and enable session restart); when the repo must
   stand alone for submission, create a separate sanitized `artifact`
   branch (strip CLAUDE.md/CHECKPOINT/CODE-MAP internals, squash history)
   rather than scrubbing the working branch.
