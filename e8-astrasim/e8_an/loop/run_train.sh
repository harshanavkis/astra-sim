#!/usr/bin/env bash
# RDMA-only reruns of the training sweeps with the staging copy (owner 2026-10-22; Loom has no copy, its runs stand):
# sweeps/train_dense.txt (tools/sweep_train.sh's jobs) then sweeps/train_moe.txt (tools/sweep_moe_train.sh's jobs), at
# most P at a time (default 2), a start only with >= GATE GB available (default 120). Log: run_train.out.
set -uo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; D=$E/e8_an/loop
lines() { grep -v '^\s*#' "$1" | grep -v '^\s*$'; }
{ lines $E/sweeps/train_dense.txt | while IFS='|' read -r n model l par b mb seq extra cl; do
      echo "sw_${n}__${cl}__rdma $E/traces/sweep/$n/workload $E/e8/cfg/system_nccl_roofline.json $E/e8/clusters/$cl/rdma.txt x $E/traces/sweep/$n/workload.json"
  done
  lines $E/sweeps/train_moe.txt | while IFS='|' read -r n pl ep tot pp mb gbs lps seq cl; do
      echo "sw_${n}__${cl}__rdma $E/traces/sweep_moe/$n/workload/workload $E/e8/cfg/system_nccl.json $E/e8/clusters/$cl/rdma.txt x $E/traces/sweep_moe/$n/comm_group.json"
  done; } > $D/train_jobs.txt
gate() { while [ "$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)" -lt "${GATE:-120}" ] || [ -e /scratch/harshanavkis/loom-proj/e8-astrasim/e8_an/loop/PAUSE ]; do sleep 30; done; }
export -f gate; export GATE=${GATE:-120}
awk '{print $1, $2, $3, $4, $6}' $D/train_jobs.txt | xargs -P "${1:-2}" -L 1 bash -c 'gate; sleep 20; '"$E"'/run_an.sh "$@" > /dev/null 2>&1 || echo "FAILED $1"' _
echo "RUN_DONE $(date -u +%H:%M)"
