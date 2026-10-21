#!/usr/bin/env bash
# GPU-initiated single put + completion on steve (deepep_post_lat, 2026-10-08): the library's
# post time is the input, the transport model predicts the rest. Transport parameters = the
# ones validated by run_val_transport.sh (hop 364 ns, MTU 1024, 82 B/packet, GPU read 1090 ns,
# posted write 330 ns); the GPU reads its CQE from host memory: 768 ns (fence_cost sys_load).
# WQE in GPU memory (fetched). Writes tests/val_gpuput_<time>.tsv.
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
export NS3_TIMEOUT=${NS3_TIMEOUT:-600}
E=/scratch/harshanavkis/loom-proj/e8-astrasim; A=/scratch/harshanavkis/loom-proj/astra-sim-fresh
SYS=$A/examples/system/native_collectives/HGX-H100-validated.json; TOPO=$E/e8/cfg/logical_2.json
OUT=$E/tests/out_val_gpuput_$(date -u +%Y%m%d_%H%M%S); mkdir -p $OUT
TSV=$E/tests/val_gpuput_$(date -u +%Y%m%d_%H%M%S).tsv
printf '3 1 2\n2\n0 2 200Gbps 0.000364ms 0\n1 2 200Gbps 0.000364ms 0\n' > $OUT/topo.txt
printf "library\tsize\tpost_us\tmeasured_total_us\tmodel_total_us\n" > $TSV
for c in deepep:8:2530:8.06 deepep:7168:2530:8.48 nvshmem:8:6690:12.90 nvshmem:7168:6750:13.73; do
  IFS=: read lib z post meas <<< "$c"
  python -I $E/tools/gen_p2p.py $OUT/p_$z $z > /dev/null
  f=$OUT/${lib}_$z.txt
  { sed "s#^TOPOLOGY_FILE .*#TOPOLOGY_FILE $OUT/topo.txt#; s/PACKET_PAYLOAD_SIZE 1000/PACKET_PAYLOAD_SIZE 1024/" $E/e8/cfg/16n_1sw.txt
    printf 'HOST_IF_MODE pull\nPCIE_GBPS 63\nPCIE_LAT_NS 330\nPCIE_RD_RTT_NS 1090\nINLINE_MAX 0\nWIRE_BYTES_PER_PACKET 82\nHIF_CHUNK 1024\nCQE_POLL_NS 768\nPOST_NS %s\n' $post; } > $f
  R=$($E/run_ns3.sh vg_${lib}_$z $OUT/p_$z/p2p $SYS $f $TOPO || true)
  t=$(grep -o "sys\[0\] finished, [0-9]*" "${R%%$'\n'*}" < /dev/null | awk '{printf "%.2f", $3 / 1000}')
  printf "%s\t%s\t%s\t%s\t%s\n" $lib $z $(awk -v p=$post 'BEGIN {printf "%.2f", p / 1000}') $meas $t | tee -a $TSV
done
