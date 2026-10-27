#!/usr/bin/env bash
# 2026-10-27 (owner: at scale RDMA gets its best case, never waiting for a completion): does Fig 10a's buffer-reuse wait
# (a send depends on the same kind of sends two layers back, DeepEP low-latency double buffering) ever delay RDMA's decode?
# RDMA traces as run_clara.sh but NOREUSE=1 (tools/gen_decode.py), same network configs (cfg/rdma_ep*_t*.txt) and
# ASTRA_CONCURRENT_SENDS=1; compare each run's slowest GPU with the paper's run (newest runs_an/an_declp_*__rdma_*).
# Points: EP64 x 1 4 16 64 128 tokens, EP256 x 1 4 16 (EP256 at 64 / 128 tokens need 225-280 GB each: not here).
# Runs: runs_an/an_declpnr_*. Log: run_noreuse_20261027.out.
set -uo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; T=$E/traces/decode_noreuse; D=$E/e8_an/decode_loop; P=$E/e8_an/loop/params.tsv
mkdir -p $T
p() { awk -F'\t' -v o=$1 -v s=$2 -v t=$3 '$1==o && $2==s && $3==t {print $4, $5, $6}' $P; }
PTS="64:1 64:4 64:16 64:64 64:128 256:1 256:4 256:16"
for pt in $PTS; do ep=${pt%:*} t=${pt#*:}
    read -r Ld fd ld <<< "$(p dispatch rdma $t)"; read -r Lc fc lc <<< "$(p combine rdma $t)"
    d=$T/ep${ep}_t${t}_l4096_mb1_rdma
    [ -f $d/.done ] || echo "NOREUSE=1 LOOP=$Ld,$Lc python3 -I $E/tools/gen_decode.py $d $ep $t 4096 1 && touch $d/.done"
done | xargs -d '\n' -P 8 -I{} bash -c '{}'
echo "GEN_DONE $(date -u +%H:%M)"
for pt in $PTS; do ep=${pt%:*} t=${pt#*:}
    echo "declpnr_ep${ep}_t${t}_l4096_mb1__rdma $T/ep${ep}_t${t}_l4096_mb1_rdma/decode $E/e8/cfg/system_decode.json $D/cfg/rdma_ep${ep}_t$t.txt"
done > $D/jobs_noreuse_20261027.txt
gate() { while [ "$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)" -lt 120 ]; do sleep 30; done; }
export -f gate
export ASTRA_CONCURRENT_SENDS=1
xargs -P 8 -L 1 bash -c 'gate; sleep 10; echo "start $1 $(date -u +%H:%M)"; '"$E"'/run_an.sh "$@" > /dev/null 2>&1 && echo "done $1 $(date -u +%H:%M)" || echo "FAILED $1"' _ < $D/jobs_noreuse_20261027.txt
echo "RUN_DONE $(date -u +%H:%M)"
