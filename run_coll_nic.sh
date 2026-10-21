#!/usr/bin/env bash
# Collectives at scale on the NIC model: all-reduce and all-gather (NCCL ring, system_nccl.json), all-to-all
# (direct), 1 KiB .. 64 MiB per GPU, 16 and 64 GPUs (clusters as run_moe.sh: 8 GPUs per server on NVLink,
# one 400G NIC / Loom per GPU, MTU 4096, ~300 ns per switch); variants rdma (validated NIC model) and loom
# (ideal Loom). One put per message, then the signal (frontend nic_send); GPU posting costs nothing.
# Every rank prints when it finished (loom_rank lines); tools/collect_coll_nic.py summarises.
#   run_coll_nic.sh [parallel runs]      (run it in tmux)  -> e8/coll/jobs.txt, e8/coll/coll.tsv
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; D=$E/e8/coll; mkdir -p $D/wl
GPUS=${GPUS:-16 64}; SIZES=${SIZES:-1024 16384 262144 4194304 67108864}
OPS=${OPS:-ALL_REDUCE ALL_GATHER ALL_TO_ALL}; VARS=${VARS:-rdma loom}
: > $D/jobs.txt
for n in $GPUS; do
    C=$E/e8/clusters/n$n; [ -f $C/topo.txt ] || python3 -I $E/tools/gen_cluster.py n$n $n --host-ns 155 --fabric-ns 305 > /dev/null
    for op in $OPS; do for s in $SIZES; do
        wl=$D/wl/${op}_n${n}_s$s
        [ -f $wl/coll.0.et ] || python3 -I $E/tools/gen_coll.py $wl $n $op $s > /dev/null
        for v in $VARS; do
            echo "coll__${op}__n${n}__s${s}__$v $wl/coll $E/e8/cfg/system_nccl.json $C/$v.txt $C/logical.json" >> $D/jobs.txt
        done
    done; done
done
echo "$(grep -c . $D/jobs.txt) jobs"
$E/tools/run_jobs.sh $D/jobs.txt ${1:-30}
python3 -I $E/tools/collect_coll_nic.py $D/jobs.txt
