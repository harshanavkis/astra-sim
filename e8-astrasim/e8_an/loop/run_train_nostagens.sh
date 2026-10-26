#!/usr/bin/env bash
# RDMA-only reruns of the training sweep without the staging copy's fixed latency (owner 2026-10-26: "do all simulations
# that are affected"; STAGE_COPY <GB/s> <chunk>, binary built 18:48). Jobs = train_jobs.txt reordered: Fig 10d's 8 first,
# the rest, the seven 256-GPU MoE last (never finished on 10-22). At most P at a time (default 6), a start only with
# >= GATE GB available (default 120). Log: run_train_nostagens.out. Collect: AN=1 FULL=1 tools/collect_e2e.py.
set -uo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; D=$E/e8_an/loop
gate() { while [ "$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)" -lt "${GATE:-120}" ] || [ -e $D/PAUSE ]; do sleep 30; done; }
export -f gate; export GATE=${GATE:-120} D
echo "RUN_START $(date -u +%H:%M)"
awk '{print $1, $2, $3, $4, $6}' $D/train_jobs_nostagens.txt | xargs -P "${1:-6}" -L 1 bash -c 'gate; sleep 20; echo "start $1 $(date -u +%H:%M)"; '"$E"'/run_an.sh "$@" > /dev/null 2>&1 && echo "done $1 $(date -u +%H:%M)" || echo "FAILED $1"' _
echo "RUN_DONE $(date -u +%H:%M)"
