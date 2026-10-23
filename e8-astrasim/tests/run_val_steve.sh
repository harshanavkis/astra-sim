#!/usr/bin/env bash
# Validation V3: the pull model vs the paper's §2 measurements on steve (H200 + CX-7,
# port0<->port1 loopback, same socket; run_paper.sh session 2026-10-08 12:46-12:50).
# Inputs (configs e8/cfg/steve/*): nic_post (payload read from GPU 1.34 us; CPU inline
# BlueFlame put 2.02 us -> fits the loopback hop, 340 ns), deepep_post_lat (post 2.53 us),
# 200G link. Checks: (1) the fit, (2) DeepEP single put, (3) prediction: dispatch/combine
# (dispatch_bd t3: 6/90/683 messages of 7168/14336 B, ordered and flush), compared with
# the measured remote time minus the local path's (the kernel work both paths share).
# Writes tests/val_steve_<time>.tsv.
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
export NS3_TIMEOUT=${NS3_TIMEOUT:-1800}
E=/scratch/harshanavkis/loom-proj/e8-astrasim; A=/scratch/harshanavkis/loom-proj/astra-sim-fresh
SYS=$A/examples/system/native_collectives/HGX-H100-validated.json; TOPO=$E/e8/cfg/logical_2.json; C=$E/e8/cfg/steve
OUT=$E/tests/out_val_steve_$(date -u +%Y%m%d_%H%M%S); mkdir -p "$OUT"
TSV=$E/tests/val_steve_$(date -u +%Y%m%d_%H%M%S).tsv
fin() { grep -o "sys\[$2\] finished, [0-9]*" "$1" < /dev/null | awk '{printf "%.2f", $3 / 1000}'; }
run() { local R; R=$($E/run_ns3.sh "$1" "$2" "$SYS" "$3" "$TOPO" || true); echo "${R%%$'\n'*}"; }
printf "check\tmeasured_us\tmodel_us\n" | tee "$TSV"
python -I $E/tools/gen_p2p.py "$OUT/p8" 8 > /dev/null
python -I $E/tools/gen_p2p.py "$OUT/p7168" 7168 > /dev/null
printf "fit: CPU inline BlueFlame put -> CQE\t2.02\t%s\n" "$(fin "$(run steve_cpu_inline "$OUT/p8/p2p" $C/cpu_inline.txt)" 0)" | tee -a "$TSV"
printf "DeepEP put 8 B, post -> completion\t7.97\t%s\n" "$(fin "$(run steve_deepep_8 "$OUT/p8/p2p" $C/deepep_put.txt)" 0)" | tee -a "$TSV"
printf "DeepEP put 7168 B, post -> completion\t8.42\t%s\n" "$(fin "$(run steve_deepep_7168 "$OUT/p7168/p2p" $C/deepep_put.txt)" 0)" | tee -a "$TSV"
# measured remote seen - local seen (dispatch_bd t3 medians, us)
declare -A M=([dispatch_ordered_6]=13.3 [dispatch_ordered_90]=36.2 [dispatch_ordered_683]=211.8
              [dispatch_flush_6]=24.8 [dispatch_flush_90]=43.0 [dispatch_flush_683]=218.9
              [combine_ordered_6]=15.1 [combine_ordered_90]=62.0 [combine_ordered_683]=413.0
              [combine_flush_6]=26.1 [combine_flush_90]=72.0 [combine_flush_683]=434.6)
for op in dispatch:7168 combine:14336; do
    name=${op%%:*} H=${op#*:}
    for n in 6 90 683; do
        python -I $E/tools/gen_dispatch_loop.py "$OUT/${name}_$n" $n $H > /dev/null
        for p in ordered flush; do
            t=$(fin "$(run steve_${name}_${p}_$n "$OUT/${name}_$n/d" $C/${p}_$H.txt)" 1)
            printf "%s %s %s msgs (%s B)\t%s\t%s\n" "$name" "$p" "$n" "$H" "${M[${name}_${p}_$n]}" "${t:-FAIL}" | tee -a "$TSV"
        done
    done
done
echo "tsv: $TSV"
