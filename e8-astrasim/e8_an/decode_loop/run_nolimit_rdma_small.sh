#!/usr/bin/env bash
# Fig 10a decode, the seven small RDMA points (EP256 at 1 and 4 tokens, EP64 all; ~30 GB together) with no WQE fetch limit,
# on clara; the three large EP256 points (16/64/128 tokens) run on amy (run_amy_nolimit.sh there). run_nolimit_rdma.sh tried
# all ten here first and was stopped at 21:13 (EP256 t64/t128 need 225-280 GB each, next to two FPGA builds).
set -uo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; T=$E/traces/decode_loop; D=$E/e8_an/decode_loop
{ for t in 4 1; do echo "declp_ep256_t${t}_l4096_mb1__rdma $T/ep256_t${t}_l4096_mb1_rdma/decode $E/e8/cfg/system_decode.json $D/cfg/rdma_ep256_t$t.txt"; done
  for t in 128 64 16 4 1; do echo "declp_ep64_t${t}_l4096_mb1__rdma $T/ep64_t${t}_l4096_mb1_rdma/decode $E/e8/cfg/system_decode.json $D/cfg/rdma_ep64_t$t.txt"; done; } > $D/jobs_nolimit_rdma_small.txt
gate() { while [ "$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)" -lt 100 ]; do sleep 30; done; }
export -f gate
export ASTRA_CONCURRENT_SENDS=1
echo "RUN_START $(date -u +%H:%M)"
xargs -P 7 -L 1 bash -c 'gate; sleep 10; echo "start $1 $(date -u +%H:%M)"; '"$E"'/run_an.sh "$@" > /dev/null 2>&1 && echo "done $1 $(date -u +%H:%M)" || echo "FAILED $1"' _ < $D/jobs_nolimit_rdma_small.txt
echo "RUN_DONE $(date -u +%H:%M)"
