#!/bin/bash
# Scale-up DOMAIN-SIZE sweep: the NVL72 threat-to-validity experiment.
#
# The industry is enlarging the scale-up domain - HGX/DGX puts 8 GPUs in
# one NVLink domain, GB200 NVL36 puts 36, GB200/GB300 NVL72 puts 72. A
# bigger domain means MORE traffic stays in-rack, which is precisely the
# traffic Loom does not change. So this sweep runs AGAINST Loom by
# construction, and is here because a reviewer will ask it. Do not quietly
# drop it if the numbers are unflattering - they are (see below).
#
# Total GPU count is held CONSTANT while the domain size varies, so racks =
# TOTAL / domain. 576 is used because it divides by 8, 36 and 72.
#
# Measured 2026-08-04 at 576 GPUs, all_reduce 64 MB:
#     8 GPUs/rack (HGX)   x 72 racks -> +33.81%
#    36 GPUs/rack (NVL36) x 16 racks ->  +0.00%
#    72 GPUs/rack (NVL72) x  8 racks ->  +0.00%
# i.e. at a fixed cluster size, NVL72-class racks erase the large-collective
# benefit entirely. The reason is rack COUNT, consistent with
# run_scale_sweep.sh: 576 GPUs in 72-GPU racks is only 8 racks, which is
# inside the regime where dim1 latency is fully hidden by chunk overlap.
# MECHANISM, measured 2026-08-04. Cross-rack steps = 2(racks-1), so at a
# fixed 576 GPUs:
#     8 GPUs/rack -> 72 racks -> 142 dim1 steps (568 exposed with splits)
#    72 GPUs/rack ->  8 racks ->  14 dim1 steps
# Two effects compound. There are 10x fewer cross-rack operations for Loom
# to improve, AND those few steps sit under a 142-step IN-RACK phase that
# carries most of the data, so they overlap away entirely: B1's wall is
# byte-identical at rdma_init 0 and 6900 ns (1,279,034 both), and exposure
# only begins between 6900 and 25,000 ns.
#
# So this is not an architectural defeat. Loom remains the device that
# connects racks; NVL72 just makes racks bigger, so fewer operations cross
# them. At real NVL72 deployment scale (10k GPUs is ~140 racks) the step
# count returns, which is what run_scale_sweep.sh demonstrates. Small-buffer
# gains do NOT vanish this way either - check the 1 MB rows before drawing
# conclusions.
#
# CSV on stdout: xpus_per_rack,racks,gpus,collective,size_mb,system,wall_cycles,exposed_comm
set -e
cd "$(dirname "$0")/../.."
ROOT=$PWD
BIN=$ROOT/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware
RM=$ROOT/examples/remote_memory/analytical/no_memory_expansion.json
GEN=$ROOT/examples/loom/gen_network_config.py

TOTAL=${TOTAL:-576}                  # divisible by 8, 36 and 72
DOMAINS=${DOMAINS:-8 36 72}          # HGX, NVL36, NVL72 - all shipping.
# NOTE (checked 2026-08-04): what NVIDIA cancelled is NVL36x2, the DUAL-rack
# 72-GPU configuration. Single-rack GB200 NVL36 keeps its original
# development and shipment plans, so 36 is a real product and belongs here.
# But NVL72 is the primary platform for frontier training by 2026, so the
# 72 row is the one that carries the argument.
COLLS=${COLLS:-all_reduce all_to_all}
SIZES=${SIZES:-1 64}

echo "xpus_per_rack,racks,gpus,collective,size_mb,system,wall_cycles,exposed_comm"
for M in $DOMAINS; do
  R=$((TOTAL / M))
  python3 $GEN --mode loom     --racks $R --xpus-per-rack $M -o /tmp/net_dom_loom.yml
  python3 $GEN --mode baseline --racks $R --xpus-per-rack $M -o /tmp/net_dom_b1.yml
  python3 $GEN --mode baseline --racks $R --xpus-per-rack $M --rdma-init-ns 2800 \
      -o /tmp/net_dom_b2.yml
  for C in $COLLS; do
    for S in $SIZES; do
      WLDIR=/tmp/dombench && mkdir -p $WLDIR && ( cd $WLDIR && \
        python3 $ROOT/examples/workload/microbenchmarks/generator_scripts/$C.py \
          --npus-count $TOTAL --coll-size $S >/dev/null )
      WL=$WLDIR/$C/${TOTAL}npus_${S}MB/$C
      for SYS in "loom loom.json /tmp/net_dom_loom.yml" \
                 "b1_gpu_rdma baseline_gpu_rdma.json /tmp/net_dom_b1.yml" \
                 "b2_cpu_proxy baseline_cpu_proxy.json /tmp/net_dom_b2.yml --rendezvous-protocol=true"; do
        set -- $SYS; NAME=$1; SYSJ=$2; NET=$3; shift 3
        OUT=$($BIN --workload-configuration=$WL \
          --system-configuration=$ROOT/examples/loom/system/$SYSJ \
          --network-configuration=$NET \
          --remote-memory-configuration=$RM "$@" 2>&1 | grep -m1 "sys\[0\] finished")
        W=$(echo "$OUT" | grep -o "finished, [0-9]*" | grep -o "[0-9]*")
        E=$(echo "$OUT" | grep -o "communication [0-9]*" | grep -o "[0-9]*")
        echo "$M,$R,$TOTAL,$C,$S,$NAME,$W,$E"
      done
    done
  done
done
