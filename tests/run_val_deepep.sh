#!/usr/bin/env bash
# Validation V4: DeepEP low-latency dispatch/combine vs DeepEP v1.2.1's README table
# (H800 + CX-7 400G IB; 128 tokens per rank, hidden 7168, top-8, FP8 dispatch 7408 B
# and BF16 combine 14336 B per (token, expert) put; latency = the kernel's time, every
# rank sends and receives). Model: one direct all-to-all per rank of 1024 puts
# (uniform routing over 256 experts), 8 GPUs per server (NVLink inside), pull with
# DeepEP's post path (2.53 us, steve), sender continues after posting (ordered),
# deployment PCIe (380/550 ns), clusters from tools/gen_cluster.py.
# Runs every case in parallel (one process each); writes tests/val_deepep_<time>.tsv.
#   tests/run_val_deepep.sh [EP sizes...]   (default 8 16 32 64 128 256; run it in tmux)
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
export NS3_TIMEOUT=${NS3_TIMEOUT:-21600}
E=/scratch/harshanavkis/loom-proj/e8-astrasim
EPS=${*:-8 16 32 64 128 256}
OUT=$E/tests/out_val_deepep_$(date -u +%Y%m%d_%H%M%S); mkdir -p "$OUT"
TSV=$E/tests/val_deepep_$(date -u +%Y%m%d_%H%M%S).tsv
declare -A M=([dispatch_8]=77 [dispatch_16]=118 [dispatch_32]=155 [dispatch_64]=173 [dispatch_128]=192 [dispatch_256]=194
              [combine_8]=114 [combine_16]=195 [combine_32]=273 [combine_64]=314 [combine_128]=369 [combine_256]=360)
declare -A LOGS
for ep in $EPS; do
    C=$E/e8/clusters/c$ep
    [ -f $C/topo.txt ] || python -I $E/tools/gen_cluster.py c$ep $ep > /dev/null
    for op in dispatch:7408 combine:14336; do
        name=${op%%:*} B=${op#*:}
        python -I $E/tools/gen_coll.py "$OUT/${name}_$ep" $ep ALL_TO_ALL $((1024 * B)) > /dev/null
        cfg=$OUT/${name}_$ep.txt
        { cat $C/none.txt; printf "HOST_IF_MODE pull\nPOST_NS 2530\nPOST_LANES 128\nCQE_POLL_NS 100\nSENDER_RELEASE post\nMSG_SPLIT_BYTES %s\n" $B; } > $cfg
        R=$($E/run_ns3.sh val_deepep_${name}_$ep "$OUT/${name}_$ep/coll" $E/e8/cfg/system_direct.json $cfg $C/logical.json > "$OUT/${name}_$ep.out" 2>&1; head -1 "$OUT/${name}_$ep.out") &
    done
done
wait
printf "op\tEP\tmeasured_us\tmodel_mean_us\tmodel_max_us\n" | tee "$TSV"
for ep in $EPS; do for name in dispatch combine; do
    L=$(head -1 "$OUT/${name}_$ep.out")
    t=$(grep -o "sys\[[0-9]*\] finished, [0-9]*" "$L" < /dev/null | awk '{s += $3; if ($3 > m) m = $3; n++} END {if (n) printf "%.1f\t%.1f", s / n / 1000, m / 1000; else printf "FAIL\tFAIL"}')
    printf "%s\t%s\t%s\t%s\n" $name $ep "${M[${name}_$ep]}" "$t" | tee -a "$TSV"
done; done
echo "tsv: $TSV"
