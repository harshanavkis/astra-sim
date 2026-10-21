#!/usr/bin/env bash
# Program order for a trace (2026-10-20): run it once on ASTRA-sim's congestion-unaware analytical backend (symmetric,
# no contention), log the order in which every rank issued its nodes (ASTRA_ISSUE_LOG), then chain each rank's
# communication ops (collectives and sends) in that order (tools/order_coll.py ORDER_LOG TOTAL=1). ASTRA-sim runs one
# communication op per GPU at a time and matches a group's messages by issue order, so under timing that differs
# between peers (contention) they could otherwise issue crossing groups' collectives in different orders and wait for
# each other (deadlock). The order is feasible by construction: the symmetric run completed with it.
#   tools/order_traces.sh <trace dir with workload.*.et + workload.json> <out dir> <GPUs> [GPUs per server, default 8]
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; A=/scratch/harshanavkis/loom-proj/astra-sim-fresh
IN=$1 OUT=$2 N=$3 G=${4:-8}
SYS=${SYS:-$E/e8/cfg/system_nccl_roofline.json}
mkdir -p $OUT
cp $IN/workload.json $OUT/
printf 'topology: [ Switch, Switch ]\nnpus_count: [ %d, %d ]\nbandwidth: [ 400.0, 50.0 ]\nlatency: [ 936.0, 1000.0 ]\n' $G $((N / G)) > $OUT/symmetric.yml
ASTRA_ISSUE_LOG=$OUT/issue_order.log \
    $A/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware --workload-configuration=$IN/workload \
    --system-configuration=$SYS --remote-memory-configuration=$A/examples/remote_memory/analytical/no_memory_expansion.json \
    --network-configuration=$OUT/symmetric.yml --comm-group-configuration=$IN/workload.json > $OUT/symmetric.log 2>&1 || true
echo "symmetric run: $(grep -c 'finished,' $OUT/symmetric.log) of $N ranks finished"
ORDER_LOG=$OUT/issue_order.log TOTAL=1 ALL=1 python3 -I $E/tools/order_coll.py $IN/workload $OUT/workload $N
