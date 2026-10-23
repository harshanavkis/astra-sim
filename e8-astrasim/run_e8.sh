#!/usr/bin/env bash
# Launch E8 workload runs, one tmux session per host-interface variant
# (session e8_<workload>_<cluster>_<variant>; the run is
# runs/ns3_e8__<workload>__<cluster>__<variant>_<time>.log, which
# (NS3_BIN=<binary>: e.g. the optimized build, build_ns3_opt.sh)
# tools/collect_e8.py reads).
#   run_e8.sh <workload> <trace prefix> <comm groups json|empty> <cluster> <system json> <variant>...
#   e.g. run_e8.sh mixtral8x22b /scratch/harshanavkis/loom-proj/chakra-traces/fixed/mixtral-8x22b-32/chakra_trace \
#          /scratch/harshanavkis/loom-proj/chakra-traces/fixed/mixtral-8x22b-32/comm_groups.json c32 \
#          /scratch/harshanavkis/loom-proj/astra-sim-fresh/examples/system/native_collectives/HGX-H100-validated.json none pull push
set -euo pipefail
E=/scratch/harshanavkis/loom-proj/e8-astrasim
[ $# -ge 6 ] || { sed -n '2,10p' "$0"; exit 2; }
WL=$1 TRACE=$2 CG=$3 CL=$4 SYS=$5; shift 5
C=$E/e8/clusters/$CL
[ -f "$C/topo.txt" ] || { echo "no cluster $C (tools/gen_cluster.py)"; exit 1; }
for v in "$@"; do
    [ -f "$C/$v.txt" ] || { echo "no variant $C/$v.txt"; exit 1; }
    s="e8_${WL}_${CL}_$v"
    tmux has-session -t "=$s" 2>/dev/null && { echo "running already: $s"; continue; }
    tmux new-session -d -s "$s" "${NS3_BIN:+NS3_BIN=$NS3_BIN }$E/run_ns3.sh e8__${WL}__${CL}__$v $TRACE $SYS $C/$v.txt $C/logical.json $CG"
    echo "started tmux $s"
done
