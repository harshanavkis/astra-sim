#!/usr/bin/env bash
# Transport validation of the pull model vs plain perftest on steve (H200 + CX-7, 200G
# port0 -> port1 loopback, RoCE MTU 1024; tools/parse_transport.py -> transport_measured.tsv).
# Model inputs: nic_post (2026-10-08): host read 650 ns (posted write = half, 330), GPU payload
# read 1340 ns, CPU post 25 ns (BlueFlame: WQE_FETCH 0), RoCEv2 frame overhead 82 B per packet;
# perftest: inline <= 220 B for host
# memory, none for GPU memory. Fitted: (1) the loopback hop, from host write 8 B (T1);
# (2) the GPU payload read, from GPU write 8 B minus host (inline) write 8 B (nic_post said
# 1340 ns, perftest implies ~1090: the smaller one, the RDMA-favourable choice);
# (3) the CPU's per-message cost in perftest's bandwidth loop, from 64 B (T2).
# Writes tests/val_transport_<time>.tsv (test, series, size, measured, model, unit).
#   tests/run_val_transport.sh
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
export NS3_TIMEOUT=${NS3_TIMEOUT:-1800}
E=/scratch/harshanavkis/loom-proj/e8-astrasim; A=/scratch/harshanavkis/loom-proj/astra-sim-fresh
SYS=$A/examples/system/native_collectives/HGX-H100-validated.json; TOPO=$E/e8/cfg/logical_2.json
M=$E/tests/transport_measured.tsv
OUT=$E/tests/out_val_transport_$(date -u +%Y%m%d_%H%M%S); mkdir -p $OUT/cfg
TSV=$E/tests/val_transport_$(date -u +%Y%m%d_%H%M%S).tsv
meas() { awk -F'\t' -v t=$1 -v s=$2 -v z=$3 '$1==t && $2==s && $3==z {print $4}' $M; }
base() {  # hop_ns -> ns-3 config base
  printf '3 1 2\n2\n0 2 200Gbps %sms 0\n1 2 200Gbps %sms 0\n' $(awk -v h=$1 'BEGIN {printf "%.7f %.7f", h/1e6, h/1e6}') > $OUT/cfg/topo_$1.txt
  sed "s#^TOPOLOGY_FILE .*#TOPOLOGY_FILE $OUT/cfg/topo_$1.txt#; s/PACKET_PAYLOAD_SIZE 1000/PACKET_PAYLOAD_SIZE 1024/" $E/e8/cfg/16n_1sw.txt
  printf 'HOST_IF_MODE pull\nPCIE_GBPS 63\nPOST_NS 25\nWQE_FETCH 0\nHIF_CHUNK 1024\nSENDER_RELEASE post\nWIRE_BYTES_PER_PACKET 82\n'
}
series_cfg() {  # series hop -> config path
  local f=$OUT/cfg/$1_$2.txt
  { base $2
    case $1 in
      write)              printf 'PCIE_LAT_NS 330\nPCIE_RD_RTT_NS 650\nINLINE_MAX 220\n' ;;
      write_with_imm)     printf 'PCIE_LAT_NS 330\nPCIE_RD_RTT_NS 650\nINLINE_MAX 220\n' ;;
      GPU_write_with_imm) printf 'PCIE_LAT_NS 330\nPCIE_RD_RTT_NS %s\nINLINE_MAX 0\n' $GPU_RD ;;
    esac; } > $f
  echo $f
}
RT=10
oneway() {  # series hop size -> model one-way latency (us)
  local wl=$OUT/pp_$3; [ -f $wl/p2p.0.et ] || python -I $E/tools/gen_p2p.py $wl $3 $RT --pingpong > /dev/null
  local R; R=$($E/run_ns3.sh vt_$1_$3 $wl/p2p $SYS $(series_cfg $1 $2) $TOPO || true)
  grep -o "sys\[0\] finished, [0-9]*" "${R%%$'\n'*}" < /dev/null | awk -v n=$RT '{printf "%.3f", $3 / n / 2 / 1000}'
}
# fit the hop: model(8 B, hop 0) + 2 x hop = measured host write 8 B (one way crosses 2 links)
m8=$(meas T1_latency write 8); b8=$(oneway write 0 8)
HOP=$(awk -v m=$m8 -v b=$b8 'BEGIN {printf "%.0f", (m - b) * 1000 / 2}')
echo "fit: host write 8 B measured $m8 us, model at hop 0 $b8 us -> hop $HOP ns"
GPU_RD=$(awk -v g=$(meas T1_latency GPU_write_with_imm 8) -v h=$m8 'BEGIN {printf "%.0f", (g - h) * 1000}')
echo "fit: GPU payload read $GPU_RD ns (GPU 8 B - host inline 8 B)"
printf "test\tseries\tsize\tmeasured\tmodel\tunit\n" > $TSV
for s in write write_with_imm GPU_write_with_imm; do
  for z in 8 64 128 256 512 1024 4096 16384 65536 262144 1048576 8388608; do
    printf "T1_latency\t%s\t%s\t%s\t%s\tus\n" $s $z "$(meas T1_latency $s $z)" "$(oneway $s $HOP $z)" | tee -a $TSV
  done
done
# T2: stream of N puts of size z from one QP, 128 outstanding, CPU posts one at a time
CPU=$(awk -v r=$(meas T2_bandwidth gpu_1qp 64) 'BEGIN {printf "%.0f", 64 / r}')   # ns per message at 64 B
echo "fit: perftest CPU loop $CPU ns per message (64 B)"
for z in 64 256 1024 2048 4096 8192 16384 65536 262144 1048576; do
  n=$(( z >= 65536 ? 64 : 1024 )); wl=$OUT/bw_$z
  [ -f $wl/p2p.0.et ] || python -I $E/tools/gen_p2p.py $wl $((n * z)) > /dev/null
  f=$OUT/cfg/bw_$z.txt; { cat $(series_cfg GPU_write_with_imm $HOP); printf 'POST_NS %s\nPOST_LANES 1\nSQ_DEPTH 128\nMSG_SPLIT_BYTES %s\n' $CPU $z; } > $f
  R=$($E/run_ns3.sh vt_bw_$z $wl/p2p $SYS $f $TOPO || true)
  t=$(grep -o "sys\[1\] finished, [0-9]*" "${R%%$'\n'*}" < /dev/null | awk '{print $3}')
  printf "T2_bandwidth\tgpu_1qp\t%s\t%s\t%s\tGB/s\n" $z "$(meas T2_bandwidth gpu_1qp $z)" "$(awk -v b=$((n * z)) -v t=${t:-0} 'BEGIN {if (t) printf "%.3f", b / t}')" | tee -a $TSV
done
echo "tsv: $TSV"
