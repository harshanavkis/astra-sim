#!/usr/bin/env bash
# Host-interface single-message tests: 2 GPUs on one 400G switch (1 us links),
# rank 0 sends COUNT x SIZE to rank 1, for host-interface modes none/pull/push.
# Prints sender-done and receiver-done times (ns) per mode and size.
#   tests/run_hif_p2p.sh [count] [--serial] [sizes...]
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
export NS3_TIMEOUT=${NS3_TIMEOUT:-300}
E=/scratch/harshanavkis/loom-proj/e8-astrasim; A=/scratch/harshanavkis/loom-proj/astra-sim-fresh
COUNT=${1:-1}; shift || true
SERIAL=""; [ "${1:-}" = --serial ] && { SERIAL=--serial; shift; }
SIZES=${*:-8 4096 65536 1048576}
SYS=$A/examples/system/native_collectives/HGX-H100-validated.json
OUT=$E/tests/out_p2p_$(date -u +%Y%m%d_%H%M%S); mkdir -p "$OUT"
printf "%-6s %9s %12s %12s\n" mode size sender_ns receiver_ns
for s in $SIZES; do
    python -I $E/tools/gen_p2p.py "$OUT/wl_$s" "$s" "$COUNT" $SERIAL > /dev/null
    for m in ${MODES:-none pull push}; do
        R=$($E/run_ns3.sh p2p_${m}_$s "$OUT/wl_$s/p2p" "$SYS" "$E/e8/cfg/test_2n_$m.txt" "$E/e8/cfg/logical_2.json" || true)
        L=${R%%$'\n'*}
        t0=$(grep -o 'sys\[0\] finished, [0-9]*' "$L" | awk '{print $3}' || true)
        t1=$(grep -o 'sys\[1\] finished, [0-9]*' "$L" | awk '{print $3}' || true)
        printf "%-6s %9s %12s %12s\n" "$m" "$s" "${t0:-FAIL}" "${t1:-FAIL}"
        echo "$m $s ${t0:-FAIL} ${t1:-FAIL} $L" >> "$OUT/results.txt"
    done
done
echo "results: $OUT/results.txt"
