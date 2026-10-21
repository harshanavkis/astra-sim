#!/usr/bin/env bash
# R1: MoE dispatch/combine latency, RDMA vs Loom, in DeepEP's low-latency shape: one
# put per (token, expert), FP8 dispatch 7408 B, BF16 combine 14336 B, top-8 of 256
# experts, uniform routing; 8 GPUs per server (NVLink inside).
# Variants (e8/cfg/variants): deepep_ordered (DeepEP LL: post 2.53 us, goes on after
# posting), deepep_flush (waits for completions), minimal_ordered (mini-gda post 0.70 us),
# loom; per token (MSG_SPLIT = message size) and per peer (one message per peer).
# Writes e8/r1/jobs.txt, runs it, collects e8/r1/jobs.txt.tsv. Run it in tmux.
#   run_r1.sh [parallel runs]
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; D=$E/e8/r1; mkdir -p $D/wl $D/cfg
EPS=${EPS:-16 32 64 128 256}; TOKENS=${TOKENS:-16 64 128 256}
VARS=${VARS:-deepep_ordered deepep_flush minimal_ordered loom}; PEER_VARS=${PEER_VARS:-deepep_ordered loom}
: > $D/jobs.txt
for ep in $EPS; do
    C=$E/e8/clusters/c$ep; [ -f $C/topo.txt ] || python -I $E/tools/gen_cluster.py c$ep $ep > /dev/null
    for t in $TOKENS; do for op in dispatch:7408 combine:14336; do
        name=${op%%:*} B=${op#*:} wl=$D/wl/${name}_ep${ep}_t$t
        [ -f $wl/coll.0.et ] || python -I $E/tools/gen_coll.py $wl $ep ALL_TO_ALL $((t * 8 * B)) > /dev/null
        for gran in token peer; do
            vs=$VARS; split=$B; [ $gran = peer ] && { vs=$PEER_VARS; split=0; }
            for v in $vs; do
                cfg=$D/cfg/${v}_${gran}_ep${ep}_$name.txt
                { cat $C/none.txt; cat $E/e8/cfg/variants/$v.txt; echo "MSG_SPLIT_BYTES $split"; } > $cfg
                echo "r1__${name}__ep${ep}__t${t}__${gran}__$v $wl/coll $E/e8/cfg/system_direct.json $cfg $C/logical.json" >> $D/jobs.txt
            done
        done
    done; done
done
echo "$(grep -c . $D/jobs.txt) jobs"
$E/tools/run_jobs.sh $D/jobs.txt ${1:-24}
python -I $E/tools/collect_jobs.py $D/jobs.txt
