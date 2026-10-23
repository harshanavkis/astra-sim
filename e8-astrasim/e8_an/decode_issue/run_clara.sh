#!/usr/bin/env bash
# Decode with ISSUE=<system> (owner 2026-10-21: each GPU is busy for its measured issue time, as DeepEP's low-latency
# kernels, which never wait for completions; tools/gen_decode.py) on clara: traces for EP64 / EP256 x 1 16 128 tokens
# (mb1) per system -> traces/decode_issue/, then runs (decissue_*): EP64 16 / 128 + EP256 1 / 16, four at a time.
# EP256 128 tokens run on amy (rdma) and rose (loom). Log: e8_an/decode_issue/run_clara.out (RUN_DONE at the end).
set -uo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; T=$E/traces/decode_issue; D=$E/e8_an/decode_issue
export ASTRA_CONCURRENT_SENDS=1
for ep in 64 256; do for t in 1 16 128; do for v in rdma loom; do
    d=$T/ep${ep}_t${t}_l4096_mb1_$v
    [ -f $d/.done ] || echo "ISSUE=$v python3 -I $E/tools/gen_decode.py $d $ep $t 4096 1 && touch $d/.done"
done; done; done | xargs -d '\n' -P 6 -I{} bash -c '{}'
echo "GEN_DONE $(date -u +%H:%M)"
job() { echo "decissue_$1__$2 $T/$1_$2/decode $E/e8/cfg/system_decode.json $E/e8_an/decode/cfg/${2}_ep$3.txt"; }   # 4 args
gate() { while [ "$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)" -lt "$1" ]; do sleep 30; done; }
export -f gate
{ for t in 16 128; do for v in rdma loom; do job ep64_t${t}_l4096_mb1 $v 64; done; done
  for t in 1 16; do for v in rdma loom; do job ep256_t${t}_l4096_mb1 $v 256; done; done; } > $D/jobs_clara.txt
xargs -P 4 -L 1 bash -c 'gate 100; '"$E"'/run_an.sh "$@" > /dev/null 2>&1 || echo "FAILED $1"' _ < $D/jobs_clara.txt
echo "RUN_DONE $(date -u +%H:%M)"
