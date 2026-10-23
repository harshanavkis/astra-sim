#!/usr/bin/env bash
# MoE decode sweep on the LoomNet model (owner 2026-10-21: end-to-end DeepSeek-V3 decode step, roofline compute as the
# training traces): tools/gen_decode.py traces, RDMA vs Loom on Fig 11's configs (e8/moe/cfg, + the combine split).
#   tools/sweep_decode.sh gen [parallel, default 6]     traces/decode/ep<EP>_t<T>_l<L>_mb<MB> (skips existing)
#   tools/sweep_decode.sh run [parallel, default 8]     runs_an/an_dec_<trace>__<v>_*.log
# Points: EP 64 / 256 x tokens per GPU 1 4 16 64 128 x 1 or 2 micro-batches (2 needs >= 2 tokens), context 4096.
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; T=$E/traces/decode; L=4096
points() { for ep in 64 256; do for t in 1 4 16 64 128; do for mb in 1 2; do
    [ $t -ge $mb ] && echo "$ep $t $mb"; done; done; done; }
case ${1:-} in
gen)
    mkdir -p $T
    points | while read -r ep t mb; do
        d=$T/ep${ep}_t${t}_l${L}_mb$mb
        [ -f $d/.done ] || echo "python3 -I $E/tools/gen_decode.py $d $ep $t $L $mb && touch $d/.done"
    done | xargs -d '\n' -P "${2:-6}" -I{} bash -c '{}' ;;
run)
    J=$(mktemp); trap 'rm -f $J' EXIT
    points | while read -r ep t mb; do n=ep${ep}_t${t}_l${L}_mb$mb
        for v in rdma loom; do
            echo "dec_${n}__$v $T/$n/decode $E/e8/cfg/system_decode.json $E/e8_an/decode/cfg/${v}_ep$ep.txt x"
        done
    done > $J
    ASTRA_CONCURRENT_SENDS=1 $E/tools/run_an_jobs.sh $J "${2:-8}" ;;
*) sed -n '2,6p' "$0"; exit 2 ;;
esac
