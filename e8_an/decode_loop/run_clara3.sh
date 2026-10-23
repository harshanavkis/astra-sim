#!/usr/bin/env bash
# The six EP256 16 / 64 / 128-token decode points on clara (owner 2026-10-22: clara only), after the 10:37 out-of-memory
# kill: at most P at a time (default 2), a start only with >= 120 GB available; the 16-token pair first (its memory sets
# how many of the larger ones run together). Log: run_clara3.out.   run_clara3.sh <tokens list> [P]
set -uo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; T=$E/traces/decode_loop; D=$E/e8_an/decode_loop
# 13:31: the EP256 128-token runs grow past 140 GB each, so the 64 invocation runs ONE at a time and first reruns the
# 128-token Loom point (stopped at 13:31 to avoid an out-of-memory kill)
{ [ "$1" = 64 ] && echo "declp_ep256_t128_l4096_mb1__loom $T/ep256_t128_l4096_mb1_loom/decode $E/e8/cfg/system_decode.json $D/cfg/loom_ep256_t128.txt"
  for t in $1; do for v in rdma loom; do
    echo "declp_ep256_t${t}_l4096_mb1__$v $T/ep256_t${t}_l4096_mb1_$v/decode $E/e8/cfg/system_decode.json $D/cfg/${v}_ep256_t$t.txt"
  done; done; } > $D/jobs_clara3_$(echo $1 | tr ' ' _).txt
gate() { while [ "$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)" -lt ${GATE:-150} ]; do sleep 30; done; }
export -f gate
export ASTRA_CONCURRENT_SENDS=1
export AN_BIN=$E/bin/AstraSim_Analytical_Loom.d069a629   # the binary of every other decode point (owner: one binary)
xargs -P "$([ "$1" = 64 ] && echo 1 || echo ${2:-2})" -L 1 bash -c 'gate; sleep 30; '"$E"'/run_an.sh "$@" > /dev/null 2>&1 || echo "FAILED $1"' _ < $D/jobs_clara3_$(echo $1 | tr ' ' _).txt
echo "RUN_DONE $1 $(date -u +%H:%M)"
