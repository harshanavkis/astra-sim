#!/usr/bin/env bash
# Prepare a Chakra WG trace set for ASTRA-sim: fix deps/metadata nodes per rank
# (fix_ctrl_deps.py), infer comm groups (infer_comm_groups.py). Collectives with
# an empty pg_name show up as pg '' in the printout: fix them with fill_pg_name.py.
#   tools/prep_trace.sh <set dir> <rank file prefix> <out name>
#   -> /scratch/harshanavkis/loom-proj/chakra-traces/fixed/<out name>/{chakra_trace.N.et,comm_groups.json,groups.txt}
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
T=/scratch/harshanavkis/loom-proj/e8-astrasim/tools
SET=$1 PFX=$2 OUT=/scratch/harshanavkis/loom-proj/chakra-traces/fixed/$3
mkdir -p "$OUT"
N=$(ls "$SET" | grep -c "^$PFX\.[0-9]*\.et$")
for r in $(seq 0 $((N - 1))); do python -I $T/fix_ctrl_deps.py "$SET/$PFX.$r.et" "$OUT/chakra_trace.$r.et" & done; wait
python -I $T/infer_comm_groups.py "$OUT/comm_groups.json" $(for r in $(seq 0 $((N - 1))); do printf '%s ' "$OUT/chakra_trace.$r.et"; done) | tee "$OUT/groups.txt"
echo "$OUT: $N ranks"
