#!/usr/bin/env bash
# Congestion-control sensitivity: the MoE and collective runs (e8/moe/jobs.txt, e8/coll/jobs.txt) again with DCQCN
# for both systems (CC_MODE 1 instead of 12 = no congestion control; every other key unchanged, HPCC ns-3's DCQCN
# defaults from the cluster configs: RATE_AI 50 Mb/s, RATE_HAI 100 Mb/s, MIN_RATE 100 Mb/s, RP_TIMER 900, ECN
# KMIN/KMAX/PMAX maps). Results next to the jobs files: e8/moe_dcqcn/moe.tsv, e8/coll_dcqcn/coll.tsv.
#   run_dcqcn.sh [parallel runs]      (run it in tmux)      JOBS="moe coll" to choose
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim
for k in ${JOBS:-moe coll}; do
    D=$E/e8/${k}_dcqcn; mkdir -p $D/cfg; : > $D/jobs.txt
    while read -r name wl sys cfg topo rest; do
        [ -n "$name" ] || continue
        new=$D/cfg/$(basename $(dirname $cfg))_$(basename $cfg)
        sed -e 's/^CC_MODE .*/CC_MODE 1/' $cfg > $new
        grep -q '^CC_MODE 1$' $new || { echo "no CC_MODE in $cfg"; exit 1; }
        echo "${name/#${k}__/${k}dc__} $wl $sys $new $topo${rest:+ $rest}" >> $D/jobs.txt   # no trailing blank: xargs -L would join lines
    done < $E/e8/$k/jobs.txt
    echo "$k: $(grep -c . $D/jobs.txt) jobs"
done
[ "${PREP_ONLY:-0}" = 1 ] && exit 0
for k in ${JOBS:-moe coll}; do
    [ $k = moe ] && export ASTRA_CONCURRENT_SENDS=1 || unset ASTRA_CONCURRENT_SENDS
    $E/tools/run_jobs.sh $E/e8/${k}_dcqcn/jobs.txt ${1:-20}
done
python3 -I $E/tools/collect_moe.py $E/e8/moe_dcqcn/jobs.txt || true
python3 -I $E/tools/collect_coll_nic.py $E/e8/coll_dcqcn/jobs.txt || true
