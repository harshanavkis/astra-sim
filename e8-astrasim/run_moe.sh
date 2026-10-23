#!/usr/bin/env bash
# MoE dispatch / combine at scale on the NIC model (Section 2's shape, tools/gen_moe.py): EP GPUs, T
# tokens each, top-8 of 256 experts, one put per token (7168 B dispatch, 14336 B combine), all sends at
# time 0 (GPU posting costs nothing; ASTRA_CONCURRENT_SENDS=1). Clusters (tools/gen_cluster.py): 8 GPUs
# per server on NVLink (frontend path), one 400G NIC / Loom per GPU, PCIe Gen5 x16, MTU 4096, leaf-spine
# full bisection; ~300 ns per switch in the link delays (host 155 ns, fabric 305 ns). Variants: rdma
# (the validated NIC model: one QP per GPU pair, puts + signal, sender released at the signal's CQE),
# loom (ideal Loom: stores carry the data, released once they left the GPU). Every rank prints its last
# send release and last arrival (loom_rank lines); tools/collect_moe.py summarises.
#   run_moe.sh [parallel runs]      (run it in tmux)  -> e8/moe/jobs.txt, e8/moe/moe.tsv
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
export ASTRA_CONCURRENT_SENDS=1
E=/scratch/harshanavkis/loom-proj/e8-astrasim; D=$E/e8/moe; mkdir -p $D/wl $D/cfg
EPS=${EPS:-16 32 64 128 256}; TOKENS=${TOKENS:-1 16 128}; VARS=${VARS:-rdma loom}
: > $D/jobs.txt
for ep in $EPS; do
    C=$E/e8/clusters/n$ep; [ -f $C/topo.txt ] || python3 -I $E/tools/gen_cluster.py n$ep $ep --host-ns 155 --fabric-ns 305 > /dev/null
    for op in dispatch:7168 combine:14336; do
        name=${op%%:*} H=${op#*:}
        for v in $VARS; do
            cfg=$D/cfg/${v}_ep${ep}_$name.txt
            { cat $C/$v.txt; echo "MSG_SPLIT_BYTES $H"; } > $cfg
        done
        for t in $TOKENS; do
            wl=$D/wl/${name}_ep${ep}_t$t
            [ -f $wl/moe.0.et ] || python3 -I $E/tools/gen_moe.py $wl $ep $t $name $H > /dev/null
            for v in $VARS; do
                echo "moe__${name}__ep${ep}__t${t}__$v $wl/moe $E/e8/cfg/system_direct.json $D/cfg/${v}_ep${ep}_$name.txt $C/logical.json" >> $D/jobs.txt
            done
        done
    done
done
echo "$(grep -c . $D/jobs.txt) jobs"
$E/tools/run_jobs.sh $D/jobs.txt ${1:-30}
python3 -I $E/tools/collect_moe.py $D/jobs.txt
