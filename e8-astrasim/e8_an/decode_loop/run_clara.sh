#!/usr/bin/env bash
# Decode step with the GPU's measured send loops (owner 2026-10-22: charge the GPU-side work; e8_an/loop/params.tsv,
# MEASURED on steve): traces with LOOP=<dispatch ns>,<combine ns> per system and token count (tools/gen_decode.py), network
# configs = the decode configs + POST_LOOP_NS / POST_LOOP_HIGH_NS (loop, first, last post) + DOORBELL_BATCH 1.
# EP64 / EP256 x 1 4 16 64 128 tokens x rdma / loom, one micro-batch. Runs: runs_an/an_declp_*.  Log: run_clara.out.
set -uo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; T=$E/traces/decode_loop; D=$E/e8_an/decode_loop; P=$E/e8_an/loop/params.tsv
mkdir -p $T $D/cfg
p() { awk -F'\t' -v o=$1 -v s=$2 -v t=$3 '$1==o && $2==s && $3==t {print $4, $5, $6}' $P; }
for v in rdma loom; do for t in 1 4 16 64 128; do
    read -r Ld fd ld <<< "$(p dispatch $v $t)"; read -r Lc fc lc <<< "$(p combine $v $t)"
    for ep in 64 256; do
        { cat $D/../decode/cfg/${v}_ep$ep.txt; echo; echo "# send loops (e8_an/loop/params.tsv, measured): loop ns, first, last post"
          echo "POST_LOOP_NS $Ld $fd $ld"; echo "POST_LOOP_HIGH_NS $Lc $fc $lc"; echo "DOORBELL_BATCH 1"; } > $D/cfg/${v}_ep${ep}_t$t.txt
        d=$T/ep${ep}_t${t}_l4096_mb1_$v
        [ -f $d/.done ] || echo "LOOP=$Ld,$Lc python3 -I $E/tools/gen_decode.py $d $ep $t 4096 1 && touch $d/.done"
    done
done; done | xargs -d '\n' -P 8 -I{} bash -c '{}'
echo "GEN_DONE $(date -u +%H:%M)"
for ep in 256 64; do for t in 128 64 16 4 1; do for v in rdma loom; do
    echo "declp_ep${ep}_t${t}_l4096_mb1__$v $T/ep${ep}_t${t}_l4096_mb1_$v/decode $E/e8/cfg/system_decode.json $D/cfg/${v}_ep${ep}_t$t.txt x"
done; done; done > $D/jobs.txt
ASTRA_CONCURRENT_SENDS=1 $E/tools/run_an_jobs.sh $D/jobs.txt 10
echo "RUN_DONE $(date -u +%H:%M)"
