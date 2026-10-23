#!/usr/bin/env bash
# MoE training sweeps on the LoomNet model (owner 2026-10-21): DeepSeek-V3-style MoE from Opus's generator
# (tools/gen_opus_moe.py; fixed compute durations -> system_nccl.json, no roofline), RDMA vs Loom. Results:
# tools/sweep_collect.py <sweep file>.
#   tools/sweep_moe_train.sh gen <sweep file> [parallel, default 8]
#   tools/sweep_moe_train.sh run <sweep file> [parallel, default 16]
# Sweep file: name|placement (mixed = EP+TP+DP, scaleout = EP+DP)|ep|GPUs|pp|micro-batches|global batch|layers per stage|seq|cluster
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; T=$E/traces/sweep_moe
gen1() {
    IFS='|' read -r n pl ep tot pp mb gbs lps seq cl <<< "$1"
    [ -f $T/$n/comm_group.json ] && [ -f $T/$n/workload/workload.$((tot - 1)).et ] && { echo "$n: exists"; return 0; }
    python3 -I $E/tools/gen_opus_moe.py $T/$n placement=$pl ep=$ep total=$tot pp=$pp mb=$mb gbs=$gbs lps=$lps seq=$seq \
        > $T/$n.gen.log 2>&1 || { echo "GEN FAILED $n"; tail -3 $T/$n.gen.log; return 1; }
    echo "$n: $(tail -1 $T/$n.gen.log | cut -c1-220)"
}
export -f gen1; export E T
lines() { grep -v '^\s*#' "$1" | grep -v '^\s*$'; }
case ${1:-} in
gen) mkdir -p $T; lines "$2" | xargs -d '\n' -P "${3:-8}" -I{} bash -c 'gen1 "$1"' _ {} ;;
run)
    J=$(mktemp); trap 'rm -f $J' EXIT
    lines "$2" | while IFS='|' read -r n pl ep tot pp mb gbs lps seq cl; do
        for v in rdma loom; do
            echo "sw_${n}__${cl}__$v $T/$n/workload/workload $E/e8/cfg/system_nccl.json $E/e8/clusters/$cl/$v.txt x $T/$n/comm_group.json"
        done
    done > $J
    $E/tools/run_an_jobs.sh $J "${3:-16}" ;;
*) sed -n '2,7p' "$0"; exit 2 ;;
esac
