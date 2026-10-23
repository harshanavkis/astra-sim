#!/usr/bin/env bash
# Decode with HOLD=1 (owner 2026-10-21: the sending GPU is busy until its sends are released; tools/gen_decode.py) on clara:
# traces for EP64 / EP256 x 1 4 16 64 128 tokens (mb1) -> traces/decode_hold/, then runs (dechold_*): EP64 all + EP256
# 1 / 4 / 16 four at a time, then EP256 64 tokens one at a time (~250 GB each). EP256 128 tokens run on amy / rose.
# Each start waits until enough memory is free (gate). Log: e8_an/decode_hold/run_clara.out (RUN_DONE at the end).
set -uo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; T=$E/traces/decode_hold; D=$E/e8_an/decode_hold
export ASTRA_CONCURRENT_SENDS=1
for ep in 64 256; do for t in 1 4 16 64 128; do
    d=$T/ep${ep}_t${t}_l4096_mb1
    [ -f $d/.done ] || echo "HOLD=1 python3 -I $E/tools/gen_decode.py $d $ep $t 4096 1 && touch $d/.done"
done; done | xargs -d '\n' -P 6 -I{} bash -c '{}'
echo "GEN_DONE $(date -u +%H:%M)"
job() { echo "dechold_$1__$2 $T/$1/decode $E/e8/cfg/system_decode.json $E/e8_an/decode/cfg/${2}_ep$3.txt"; }   # 4 args (a 5th = comm groups)
gate() { while [ "$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)" -lt "$1" ]; do sleep 30; done; }
export -f gate
# restart 22:25 (EP64 1-128 done before the stop): EP256 1 / 4 / 16 only
for t in 1 4 16; do for v in rdma loom; do job ep256_t${t}_l4096_mb1 $v 256; done; done > $D/jobs_small.txt
xargs -P 4 -L 1 bash -c 'gate 100; '"$E"'/run_an.sh "$@" > /dev/null 2>&1 || echo "FAILED $1"' _ < $D/jobs_small.txt
echo "SMALL_DONE $(date -u +%H:%M)"
for v in rdma loom; do job ep256_t64_l4096_mb1 $v 256; done > $D/jobs_t64.txt
xargs -P 1 -L 1 bash -c 'gate 280; '"$E"'/run_an.sh "$@" > /dev/null 2>&1 || echo "FAILED $1"' _ < $D/jobs_t64.txt
echo "RUN_DONE $(date -u +%H:%M)"
