#!/usr/bin/env bash
# Decode (Fig 10a) RDMA reruns with no limit on work requests per fetch (owner 2026-10-26: WQE_FETCH_MAX 1e9 in every
# config; "do all simulations that are affected"). Loom has no work requests: its 10-22 runs stand. Current binary (run_an.sh
# refuses binaries older than the model header; d069a629 differs only in staging-copy code, unused here). Largest first,
# at most P at a time (default 3), a start only with >= GATE GB available (default 150). Log: run_nolimit_rdma.out.
set -uo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; T=$E/traces/decode_loop; D=$E/e8_an/decode_loop
{ for ep in 256 64; do for t in 128 64 16 4 1; do
    echo "declp_ep${ep}_t${t}_l4096_mb1__rdma $T/ep${ep}_t${t}_l4096_mb1_rdma/decode $E/e8/cfg/system_decode.json $D/cfg/rdma_ep${ep}_t$t.txt"
  done; done; } > $D/jobs_nolimit_rdma.txt
gate() { while [ "$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)" -lt ${GATE:-150} ]; do sleep 30; done; }
export -f gate
export ASTRA_CONCURRENT_SENDS=1
echo "RUN_START $(date -u +%H:%M)"
xargs -P "${1:-3}" -L 1 bash -c 'gate; sleep 30; echo "start $1 $(date -u +%H:%M)"; '"$E"'/run_an.sh "$@" > /dev/null 2>&1 && echo "done $1 $(date -u +%H:%M)" || echo "FAILED $1"' _ < $D/jobs_nolimit_rdma.txt
echo "RUN_DONE $(date -u +%H:%M)"
