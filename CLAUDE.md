# Working rules for this repo (Loom simulation, branch `loom-sim`)

Start here when resuming: `examples/loom/CHECKPOINT.md` — the single living
state doc (section 5 results are GENERATED; 5a Phase-A findings; 5b the
experiment catalog; 6 next steps; 8 code↔real-system correspondence;
9 review verdicts and reviewer defenses). Then `examples/loom/README.md`
(how to run), `ANALYTICAL-MODEL.md` (equations, constants, decisions
ledger), `implementation-plan.md` (the Coyote testbed plan).
CODE-MAP.md and HANDOFF-EVAL-REVIEW.md were folded into CHECKPOINT
sections 8 and 9 and deleted on 2026-08-04.

## Standing rules (from the project owner)

1. **With every commit that adds or changes anything, overwrite
   `examples/loom/CHECKPOINT.md` in place** (bump its Last-updated date) —
   it is the one living state doc, so there is nothing to keep in sync
   with it. **Never hand-write a result number into any doc**: rerun the
   suite and `python3 examples/loom/summarize_results.py --write`, which
   regenerates section 5 from `results/*.csv`. Hand-quoted numbers are
   exactly how README/CODE-MAP drifted from the CSVs before.
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
   messages and CHECKPOINT, never dropped. The paper claim is SM reclamation
   + bulk parity + latency/isolation/unification — not bulk speedup.
6. Commit at regular intervals on `loom-sim`; **no Co-Authored-By lines**.
7. Run experiments inside the Docker image `astra-sim:loom` (official
   Dockerfile); one-command suite: `examples/loom/run_all_docker.sh`.
8. The paper repo (`~/loom-paper`) is OFF LIMITS: never edit or commit
   anything there unless explicitly told; all work lives on this repo's
   `loom-sim` branch. (Paper prose rules, for when asked: no em dashes,
   XPU terminology, tex is design ground truth: no GFA/token/tag/seq;
   wire = offset·op·len.)
9. Paper-repo references in CHECKPOINT stay on `loom-sim` (they
   bind code to the design and enable session restart); when the repo must
   stand alone for submission, create a separate sanitized `artifact`
   branch (strip CLAUDE.md/CHECKPOINT internals, squash history)
   rather than scrubbing the working branch.
