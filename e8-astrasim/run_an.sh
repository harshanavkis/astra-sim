#!/usr/bin/env bash
# One ASTRA-sim run on the LoomNet analytical model (AstraSim_Analytical_Loom; ANALYTICAL.md).
#   run_an.sh <name> <workload prefix> <system.json> <network config (cluster rdma.txt / loom.txt)> [comm groups json]
# Log: runs_an/an_<name>_<time>.log; line 1 = binary md5 + model header md5 (which model produced the numbers).
# ASTRA_CONCURRENT_SENDS and the other ASTRA-sim env settings pass through.
set -uo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim
A=/scratch/harshanavkis/loom-proj/astra-sim-fresh
BIN=${AN_BIN:-$A/build/astra_analytical/build/bin/AstraSim_Analytical_Loom}
HDR=$A/astra-sim/network_frontend/analytical/include/loom/LoomNet.hh
MEM=$A/examples/remote_memory/analytical/no_memory_expansion.json
[ $# -ge 4 ] || { sed -n '2,5p' "$0"; exit 2; }
NAME=$1 WL=$2 SYS=$3 NET=$4 CG=${5:-}
[ "$BIN" -nt "$HDR" ] || { echo "REFUSE: $BIN is older than $HDR (rebuild: tools/build_an.sh)"; exit 1; }
mkdir -p $E/runs_an
LOG=$E/runs_an/an_${NAME}_$(date -u +%Y%m%d_%H%M%S).log
echo "loomnet bin $(md5sum < $BIN | cut -c1-8) model $(md5sum < $HDR | cut -c1-8) net $NET" > $LOG
ARGS="--workload-configuration=$WL --system-configuration=$SYS --remote-memory-configuration=$MEM --network-configuration=$NET"
[ -n "$CG" ] && ARGS="$ARGS --comm-group-configuration=$CG"
s=$(date +%s.%N)
$BIN $ARGS >> $LOG 2>&1
rc=$?
echo "an_exit $rc wall_s $(awk -v a=$s -v b=$(date +%s.%N) 'BEGIN{printf "%.1f", b-a}')" >> $LOG
exit $rc
