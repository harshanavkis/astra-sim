#!/usr/bin/env bash
# NIC model (HOST_IF_MODE nic) vs the single-message measurements its PCIe/NIC latencies come from
# (consistency: these must come out) and the 7168 B DeepEP put (a prediction). steve, MTU 4096.
#   nic_post (CPU posts, dst GPU memory): post -> CQE, payload inline / host / GPU, BlueFlame on / off
#   perftest T1 8 B host write: one-way (post -> receiver sees it)
#   DeepEP single put (GPU posts, IBGDA): post call end -> CQE seen, 8 B and 7168 B
# Writes tests/val_nic_micro_<time>.tsv.
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim
BIN=/scratch/harshanavkis/loom-proj/astra-sim-fresh/extern/network_backend/ns-3/build/scratch/ns3.42-LoomReplay-default
/scratch/harshanavkis/loom-proj/e8-astrasim/tools/check_ns3_build.sh "$BIN" || exit 1   # refuse a stale build (2026-10-20)
BASE=${BASE:-$E/e8/cfg/steve_nic/base.txt}
O=$E/tests/out_val_nic_micro_$(date -u +%Y%m%d_%H%M%S); mkdir -p $O
TSV=$E/tests/val_nic_micro_$(date -u +%Y%m%d_%H%M%S).tsv
printf "check\tmeasured_us\tmodel_us\terr_pct\n" | tee $TSV
# name | config lines | bytes | quantity (cqe | seen) | measured us
CASES=(
  "nic_post inline BF|NIC_POSTER host,NIC_SQ_MEM host,NIC_CQ_MEM host,NIC_BF 1,INLINE_MAX 64|8|cqe|2.02"
  "nic_post host BF|NIC_POSTER host,NIC_SQ_MEM host,NIC_CQ_MEM host,NIC_BF 1,NIC_BUF_MEM host|8|cqe|2.68"
  "nic_post gpu BF|NIC_POSTER host,NIC_SQ_MEM host,NIC_CQ_MEM host,NIC_BF 1|8|cqe|3.37"
  "nic_post inline doorbell|NIC_POSTER host,NIC_SQ_MEM host,NIC_CQ_MEM host,INLINE_MAX 64|8|cqe|2.71"
  "nic_post host doorbell|NIC_POSTER host,NIC_SQ_MEM host,NIC_CQ_MEM host,NIC_BUF_MEM host|8|cqe|3.39"
  "nic_post gpu doorbell|NIC_POSTER host,NIC_SQ_MEM host,NIC_CQ_MEM host|8|cqe|4.05"
  "perftest 8 B host write one-way|NIC_POSTER host,NIC_SQ_MEM host,NIC_CQ_MEM host,NIC_BF 1,INLINE_MAX 64,NIC_BUF_MEM host,NIC_RX_MEM host|8|seen|1.42"
  "DeepEP put 8 B -> CQE|-|8|cqe|5.45"
  "DeepEP put 7168 B -> CQE (prediction)|-|7168|cqe|6.13"
)
for c in "${CASES[@]}"; do
  IFS='|' read -r name keys bytes what meas <<< "$c"
  f=$O/$(echo "$name" | tr -c 'a-zA-Z0-9\n' '_')
  cp $BASE $f.cfg
  [ "$keys" = "-" ] || tr ',' '\n' <<< "$keys" >> $f.cfg
  printf "path ordered\nnodes 0 1\nnqp 1\nreap 0\nsignal 0\nmsg 0 1000 0 %s 1\n" $bytes > $f.run
  $BIN $f.cfg $f.run $f.out > $f.log 2>&1
  read -r _ _ seen cqe < <(grep '^msg' $f.out)
  t=$([ "$what" = cqe ] && echo $cqe || echo $seen)
  python3 -c "m=$meas; x=($t-1000)/1000; print(f'$name\t{m:.2f}\t{x:.2f}\t{(x-m)/m*100:+.1f}')" | tee -a $TSV
done
echo "tsv: $TSV"
