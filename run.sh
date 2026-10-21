#!/usr/bin/env bash
# Run ASTRA-sim's analytical backend from the fresh clone, inside the nix
# E8 nix shell (shell.nix; its binaries link nix-store libraries).
#
#   run.sh <example>        a bundled example, with the arguments of the
#                           repo's own run script (those scripts call build.sh
#                           through #!/bin/bash, which NixOS lacks):
#     ring_rs_4      congestion unaware, ring reduce-scatter, 4 NPUs, 1 MB
#     ring_ag_16     congestion aware, ring all-gather, 16 NPUs, 1 MB
#     hgx_h100_ar_8  congestion aware, all-reduce on the validated HGX-H100 model
#     custom_ar_8    congestion aware, all-reduce with a custom collective (Chakra ET)
#   run.sh aware|unaware <workload prefix> <system.json> <network.yml> [remote_memory.json] [extra args]
#
# Output: /scratch/harshanavkis/loom-proj/e8-astrasim/runs/<time>_<name>.log; the simulator's
# own log goes to <repo>/log/. Prints how many NPUs finished and their cycles. 1 cycle = 1 ns.
set -uo pipefail
REPO=${ASTRA:-/scratch/harshanavkis/loom-proj/astra-sim-fresh}
BIN=$REPO/build/astra_analytical/build/bin
EX=$REPO/examples
MEM=$EX/remote_memory/analytical/no_memory_expansion.json
case ${1:-} in
    ring_rs_4)     NAME=$1; MODE=unaware; W=$EX/workload/microbenchmarks/reduce_scatter/4npus_1MB/reduce_scatter
                   S=$EX/system/native_collectives/Ring_4chunks.json; N=$EX/network/analytical/Ring_4npus.yml; EXTRA=() ;;
    ring_ag_16)    NAME=$1; MODE=aware; W=$EX/workload/microbenchmarks/all_gather/16npus_1MB/all_gather
                   S=$EX/system/native_collectives/Ring_4chunks.json; N=$EX/network/analytical/Ring_16npus.yml; EXTRA=() ;;
    hgx_h100_ar_8) NAME=$1; MODE=aware; W=$EX/workload/microbenchmarks/all_reduce/8npus_1MB/all_reduce
                   S=$EX/system/native_collectives/HGX-H100-validated.json; N=$EX/network/analytical/HGX-H100-validated.yml; EXTRA=() ;;
    custom_ar_8)   NAME=$1; MODE=aware; W=$EX/workload/microbenchmarks/all_reduce/8npus_1MB/all_reduce
                   S=$EX/system/custom_collectives/custom_collective.json; N=$EX/network/analytical/Ring_8npus.yml; EXTRA=() ;;
    aware|unaware) [ $# -ge 4 ] || { sed -n '2,17p' "$0"; exit 2; }
                   MODE=$1; W=$2; S=$3; N=$4; MEM=${5:-$MEM}; shift $(( $# >= 5 ? 5 : 4 )); EXTRA=("$@")
                   NAME=$(basename "$W")_$(basename "$N" .yml) ;;
    *) sed -n '2,17p' "$0"; exit 2 ;;
esac
case $MODE in aware) B=$BIN/AstraSim_Analytical_Congestion_Aware ;; *) B=$BIN/AstraSim_Analytical_Congestion_Unaware ;; esac
[ -x "$B" ] || { echo "no $B: run /scratch/harshanavkis/loom-proj/e8-astrasim/build.sh"; exit 1; }
OUT=/scratch/harshanavkis/loom-proj/e8-astrasim/runs; mkdir -p "$OUT"
LOG=$OUT/$(date -u +%Y%m%d_%H%M%S)_$NAME.log
CMD="$B --workload-configuration=$W --system-configuration=$S --remote-memory-configuration=$MEM --network-configuration=$N ${EXTRA[*]:-}"
echo "$CMD" > "$LOG"
cd "$REPO"   # the simulator writes ./log/, and custom-collective configs use repo-relative paths
nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$CMD" >> "$LOG" 2>&1
rc=$?
grep -oE 'sys\[[0-9]+\] finished, [0-9]+ cycles' "$LOG" | awk '{n++; c=$3+0; if (c>mx) mx=c; if (mn==""||c<mn) mn=c}
    END { if (n) printf "%d NPUs finished; cycles (ns) min %d, max %d\n", n, mn, mx; else print "NO NPU FINISHED" }'
echo "exit $rc, log $LOG"
exit $rc
