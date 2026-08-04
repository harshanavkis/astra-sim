#!/bin/bash
# F2: rerun the matrix and the apps with the DIRECT collective algorithms
# instead of ring, to confirm or retract the "ring artifact" explanation of
# the negative matrix cells.
#
# IMPORTANT (2026-08-04): F2 was originally specified as flipping only
# `all-to-all-implementation` to direct. That cannot work - all five
# negative cells in matrix.csv are all_reduce (4) and all_gather (1), and
# NONE is all_to_all. The *_direct.json variants therefore switch all four
# collectives, and all four systems switch together so the comparison
# isolates the algorithm rather than the system.
#
# Writes results/{matrix,apps}_direct.csv next to the ring baselines.
set -e
cd "$(dirname "$0")/../.."
RES=examples/loom/results
mkdir -p $RES

echo ">>> matrix (direct)"
SUFFIX=_direct examples/loom/run_matrix.sh > $RES/matrix_direct.csv
echo ">>> apps (direct)"
SUFFIX=_direct examples/loom/run_apps.sh > $RES/apps_direct.csv
echo ">>> results in $RES/{matrix,apps}_direct.csv"
