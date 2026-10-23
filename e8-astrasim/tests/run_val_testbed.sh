#!/usr/bin/env bash
# Validation B (structure check): E2 one-way latency on the testbed (U280s,
# 100G, one switch; ping-pong / 2), RDMA = perf_rdma one WR per 64 B, SQ 32,
# one CPU poster, WQE by MMIO (Coyote); Loom = CPU stores into the window.
# Configs e8/cfg/val_testbed_{pull,push}.txt. Fitted: link latency (Loom flag),
# PUSH_GBPS 0.233 (Loom 64 KiB); the rest is predicted.
# Writes tests/val_testbed_<time>.tsv (size, mode, measured_us, model_us).
#   tests/run_val_testbed.sh [round trips]
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
export NS3_TIMEOUT=${NS3_TIMEOUT:-1800}
E=/scratch/harshanavkis/loom-proj/e8-astrasim; A=/scratch/harshanavkis/loom-proj/astra-sim-fresh
SYS=$A/examples/system/native_collectives/HGX-H100-validated.json; TOPO=$E/e8/cfg/logical_2.json
RT=${1:-5}
OUT=$E/tests/out_val_testbed_$(date -u +%Y%m%d_%H%M%S); mkdir -p "$OUT"
# E2 2026-10-07 rerun on the standard images (us): rdma_pingpong --chunk 64 --sq 32, uwin_pingpong
declare -A MEAS=([pull_8]=4.81 [pull_64]=5.30 [pull_256]=5.51 [pull_1024]=10.19 [pull_4096]=25.5 [pull_16384]=90.3 [pull_65536]=356.2
                 [push_8]=3.90 [push_64]=4.26 [push_256]=4.20 [push_1024]=4.84 [push_4096]=16.5 [push_16384]=69.6 [push_65536]=281)
TSV=$E/tests/val_testbed_$(date -u +%Y%m%d_%H%M%S).tsv
printf "size\tmode\tmeasured_us\tmodel_us\n" | tee "$TSV"
for s in 8 64 256 1024 4096 16384 65536; do
    python -I $E/tools/gen_p2p.py "$OUT/pp_$s" "$s" "$RT" --pingpong > /dev/null
    for m in pull push; do
        R=$($E/run_ns3.sh val_testbed_${m}_$s "$OUT/pp_$s/p2p" "$SYS" "$E/e8/cfg/val_testbed_$m.txt" "$TOPO" || true)
        L=${R%%$'\n'*}
        t=$(grep -o "sys\[0\] finished, [0-9]*" "$L" < /dev/null | awk '{print $3}' || true)
        us=$( [ -n "$t" ] && awk -v t="$t" -v n="$RT" 'BEGIN{printf "%.2f", t / n / 2 / 1000}' || echo FAIL)
        printf "%s\t%s\t%s\t%s\n" "$s" "$m" "${MEAS[${m}_$s]}" "$us" | tee -a "$TSV"
    done
done
echo "tsv: $TSV"
