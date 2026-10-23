#!/usr/bin/env bash
# The 18 MoE training reruns (RDMA only, staging copy; e8_an/loop/train_jobs.txt sw_moe*) on rose (2 TB; owner 2026-10-22: use
# rose), while clara runs the dense ones (clara holds before its MoE jobs: e8_an/loop/PAUSE). Same as run_train.sh: run_an.sh,
# no ASTRA env; binary c20d3f62 copied to bin/ (rose's build is d069a629); rose's nix store lacks protobuf/abseil ->
# bin/declp-libs. At most P (default 6) at a time, a start only with >= 300 GB available. Log: e8_an/loop/run_train_moe_rose.out
set -uo pipefail
E=/scratch/harshanavkis/loom-proj/e8-astrasim; D=$E/e8_an/loop
export E8_SHELL=1 LD_LIBRARY_PATH=$E/bin/declp-libs AN_BIN=$E/bin/AstraSim_Analytical_Loom.c20d3f62
[ "$(md5sum < $AN_BIN | cut -c1-8)" = c20d3f62 ] || { echo "WRONG BINARY"; exit 1; }
gate() { while [ "$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)" -lt 300 ]; do sleep 30; done; }
export -f gate
grep '^sw_moe' $D/train_jobs.txt | awk '{print $1, $2, $3, $4, $6}' | xargs -P "${1:-6}" -L 1 bash -c 'gate; sleep 20; echo "START $1 $(date -u +%H:%M)"; '"$E"'/run_an.sh "$@" > /dev/null 2>&1 && echo "OK $1 $(date -u +%H:%M)" || echo "FAILED $1 $(date -u +%H:%M)"' _
echo "RUN_DONE $(date -u +%H:%M)"
