#!/usr/bin/env bash
# Host-interface collective tests: 16 GPUs on one switch, one collective per rank,
# for the given test configs (e8/cfg/test_16n_<cfg>.txt). Prints min/max finish (ns).
#   tests/run_hif_coll.sh <ALL_TO_ALL|...> <bytes> <cfg>...
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
export NS3_TIMEOUT=${NS3_TIMEOUT:-300}
E=/scratch/harshanavkis/loom-proj/e8-astrasim; A=/scratch/harshanavkis/loom-proj/astra-sim-fresh
TYPE=$1 SIZE=$2; shift 2
OUT=$E/tests/out_coll_$(date -u +%Y%m%d_%H%M%S); mkdir -p "$OUT"
python -I $E/tools/gen_coll.py "$OUT/wl" 16 "$TYPE" "$SIZE" > /dev/null
printf "%-10s %12s %12s\n" cfg min_ns max_ns
for c in "$@"; do
    R=$($E/run_ns3.sh coll_${c}_${TYPE}_$SIZE "$OUT/wl/coll" "$E/e8/cfg/system_direct.json" "$E/e8/cfg/test_16n_$c.txt" \
        "$A/examples/network/ns3/sample_16nodes_1D.json" || true)
    L=${R%%$'\n'*}
    t=$(grep -o 'sys\[[0-9]*\] finished, [0-9]*' "$L" < /dev/null | awk '{print $3}' | sort -n || true)
    printf "%-10s %12s %12s\n" "$c" "$(echo "$t" | head -1)" "$(echo "$t" | tail -1)"
    echo "$c $TYPE $SIZE $(echo $t | tr ' ' ',') $L" >> "$OUT/results.txt"
done
