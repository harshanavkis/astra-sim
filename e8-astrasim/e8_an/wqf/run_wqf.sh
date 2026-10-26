#!/usr/bin/env bash
# WQE_FETCH_MAX sensitivity (owner 2026-10-26): the paper's Fig 10 (b) MoE jobs (e8_an/loop/moe_jobs.txt) and (c)
# collective jobs (e8_an/loop/coll/jobs.txt) with the RDMA work-request fetch limit at 1, 8, 16, 64, 256 and no limit
# (1e9). Config copies under k<k>/cfg (named <cluster dir>_<file>: every cluster's file is rdma.txt / loom.txt), logs
# runs_an/an_wqf<k>__*; collected with the paper's collectors into k<k>/moe.tsv and k<k>/coll.tsv. Run from e8-astrasim:
#   e8_an/wqf/run_wqf.sh     (~4 min on clara; the 2026-10-26 run used a scratch copy, results identical in layout)
set -uo pipefail
E=/scratch/harshanavkis/loom-proj/e8-astrasim; S=$E/e8_an/wqf
for k in 1 8 16 64 256 1000000000; do
  for grp in moe coll; do
    src=$E/e8_an/loop/$([ $grp = moe ] && echo moe_jobs.txt || echo coll/jobs.txt)
    D=$S/k$k/$grp; mkdir -p $D/cfg; J=$D/jobs.txt; : > $J; : > $D/jobs_orig.txt
    grep -v '^#' $src | grep . | while read -r name wl sys net topo rest; do
      c=$D/cfg/$(basename $(dirname $net))_$(basename $net)
      [ -f $c ] || sed "s/^WQE_FETCH_MAX .*/WQE_FETCH_MAX $k/" $net > $c
      echo "wqf${k}${grp}__$name $wl $sys $c $topo $rest" >> $J
      echo "$name $wl $sys $c $topo $rest" >> $D/jobs_orig.txt
    done
    if [ $grp = moe ]; then ASTRA_CONCURRENT_SENDS=1 $E/tools/run_an_jobs.sh $J 24; else $E/tools/run_an_jobs.sh $J 24; fi
    if [ $grp = moe ]; then LOGS=runs_an/an_wqf${k}${grp}__ python3 -I $E/tools/collect_moe.py $D/jobs_orig.txt > /dev/null && mv $D/moe.tsv $S/k$k/moe.tsv
    else LOGS=runs_an/an_wqf${k}${grp}__ python3 -I $E/tools/collect_coll_nic.py $D/jobs_orig.txt > /dev/null && mv $D/coll.tsv $S/k$k/coll.tsv; fi
    rm -rf $D
  done
done
echo "WQF DONE $(date -u +%T)"
