#!/usr/bin/env bash
# R2: collective latency vs size, RDMA vs Loom: all-reduce and all-gather (NCCL ring),
# all-to-all (direct), 1 KiB .. 64 MiB, 16 and 64 GPUs (2 and 8 servers, NVLink inside).
# Variants (e8/cfg/variants): gdaki (NCCL device API, 2610.01380: post 1.60 us,
# completion +1.09 us), deepep_ordered, loom; one message per peer and step.
# Writes e8/r2/jobs.txt, runs it, collects e8/r2/jobs.txt.tsv. Run it in tmux.
#   run_r2.sh [parallel runs]
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; D=$E/e8/r2; mkdir -p $D/wl $D/cfg
GPUS=${GPUS:-16 64}; SIZES=${SIZES:-1024 16384 262144 4194304 67108864}
OPS=${OPS:-ALL_REDUCE ALL_GATHER ALL_TO_ALL}; VARS=${VARS:-gdaki deepep_ordered loom}
: > $D/jobs.txt
for n in $GPUS; do
    C=$E/e8/clusters/c$n; [ -f $C/topo.txt ] || python -I $E/tools/gen_cluster.py c$n $n > /dev/null
    for v in $VARS; do
        cfg=$D/cfg/${v}_c$n.txt
        { cat $C/none.txt; cat $E/e8/cfg/variants/$v.txt; } > $cfg
    done
    for op in $OPS; do for s in $SIZES; do
        wl=$D/wl/${op}_n${n}_s$s
        [ -f $wl/coll.0.et ] || python -I $E/tools/gen_coll.py $wl $n $op $s > /dev/null
        for v in $VARS; do
            echo "r2__${op}__n${n}__s${s}__$v $wl/coll $E/e8/cfg/system_nccl.json $D/cfg/${v}_c$n.txt $C/logical.json" >> $D/jobs.txt
        done
    done; done
done
echo "$(grep -c . $D/jobs.txt) jobs"
$E/tools/run_jobs.sh $D/jobs.txt ${1:-24}
python -I $E/tools/collect_jobs.py $D/jobs.txt
