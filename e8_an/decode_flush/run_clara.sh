#!/usr/bin/env bash
# Decode, the general path (owner 2026-10-21): HOLD traces (traces/decode_hold: the GPU waits for its own sends) on
# LoomNet with RDMA_FLUSH 1 in the RDMA configs (the signal waits for the writes' completion). Runs decflush_*: EP64
# 1-128 + EP256 1 / 4 / 16 four at a time, then EP256 64 tokens one at a time. EP256 128 tokens on amy / rose.
set -uo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; T=$E/traces/decode_hold; D=$E/e8_an/decode_flush
export ASTRA_CONCURRENT_SENDS=1
job() { echo "decflush_$1__$2 $T/$1/decode $E/e8/cfg/system_decode.json $E/e8_an/decode/cfg/${2}_ep$3.txt"; }   # 4 args
gate() { while [ "$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)" -lt "$1" ]; do sleep 30; done; }
export -f gate
{ for t in 1 4 16 64 128; do for v in rdma loom; do job ep64_t${t}_l4096_mb1 $v 64; done; done
  for t in 1 4 16; do for v in rdma loom; do job ep256_t${t}_l4096_mb1 $v 256; done; done; } > $D/jobs_small.txt
xargs -P 4 -L 1 bash -c 'gate 100; '"$E"'/run_an.sh "$@" > /dev/null 2>&1 || echo "FAILED $1"' _ < $D/jobs_small.txt
echo "SMALL_DONE $(date -u +%H:%M)"
for v in rdma loom; do job ep256_t64_l4096_mb1 $v 256; done > $D/jobs_t64.txt
xargs -P 1 -L 1 bash -c 'gate 280; '"$E"'/run_an.sh "$@" > /dev/null 2>&1 || echo "FAILED $1"' _ < $D/jobs_t64.txt
echo "RUN_DONE $(date -u +%H:%M)"
