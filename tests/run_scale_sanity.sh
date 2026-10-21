#!/usr/bin/env bash
# At-scale sanity of the NIC model through ASTRA-sim: EP16 (2 servers x 8 GPUs, NVLink inside,
# one 400G NIC / Loom per GPU on a leaf, e8/clusters/n16), dispatch as one all-to-all per GPU of
# T tokens x top-8 x 7168 B in per-token puts, RDMA (rdma) vs ideal Loom (loom). Prints each
# variant's slowest and fastest GPU (us).   tests/run_scale_sanity.sh [tokens...]
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
export NS3_TIMEOUT=${NS3_TIMEOUT:-3600}
E=/scratch/harshanavkis/loom-proj/e8-astrasim; C=$E/e8/clusters/n16
[ -f $C/rdma.txt ] || python3 -I $E/tools/gen_cluster.py n16 16 --host-ns 300 --fabric-ns 300 > /dev/null
O=$E/tests/out_scale_sanity_$(date -u +%Y%m%d_%H%M%S); mkdir -p $O
for T in ${@:-1 16 128}; do
  python3 -I $E/tools/gen_coll.py $O/a2a_t$T 16 ALL_TO_ALL $((T * 8 * 7168)) > /dev/null
  for v in rdma loom; do
    cfg=$O/${v}_t$T.txt; { cat $C/$v.txt; echo "MSG_SPLIT_BYTES 7168"; } > $cfg
    R=$($E/run_ns3.sh scale_${v}_t$T $O/a2a_t$T/coll $E/e8/cfg/system_direct.json $cfg $C/logical.json || true)
    log=${R%%$'\n'*}
    grep -o 'sys\[[0-9]*\] finished, [0-9]*' $log < /dev/null | awk -v v=$v -v T=$T '{x = $3 / 1000; if (x > mx) mx = x; if (mn == "" || x < mn) mn = x; n++}
      END {printf "%-5s %4d tokens: %2d GPUs finished, slowest %8.2f us, fastest %8.2f us\n", v, T, n, mx, mn}'
  done
done
