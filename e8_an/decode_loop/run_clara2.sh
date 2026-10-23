#!/usr/bin/env bash
# Rerun after the 10:37 out-of-memory kill (10 parallel decode runs filled clara's 377 GB): the 14 small points here, at
# most 4 at a time and each start only with >= 100 GB available; the EP256 16 / 64 / 128-token points run on amy (rdma)
# and rose (loom), e8_an/decode_loop/jobs_<host>.txt, logs synced by logsync.sh. Log: run_clara2.out.
set -uo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; T=$E/traces/decode_loop; D=$E/e8_an/decode_loop
{ for t in 1 4; do for v in rdma loom; do echo "declp_ep256_t${t}_l4096_mb1__$v $T/ep256_t${t}_l4096_mb1_$v/decode $E/e8/cfg/system_decode.json $D/cfg/${v}_ep256_t$t.txt"; done; done
  for t in 128 64 16 4 1; do for v in rdma loom; do echo "declp_ep64_t${t}_l4096_mb1__$v $T/ep64_t${t}_l4096_mb1_$v/decode $E/e8/cfg/system_decode.json $D/cfg/${v}_ep64_t$t.txt"; done; done; } > $D/jobs_clara2.txt
gate() { while [ "$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)" -lt 100 ]; do sleep 30; done; }
export -f gate
export ASTRA_CONCURRENT_SENDS=1
xargs -P 4 -L 1 bash -c 'gate; sleep 20; '"$E"'/run_an.sh "$@" > /dev/null 2>&1 || echo "FAILED $1"' _ < $D/jobs_clara2.txt
echo "RUN_DONE $(date -u +%H:%M)"
