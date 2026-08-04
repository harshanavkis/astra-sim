#!/bin/bash
# A5: cluster-scale sweep. XPUs per rack FIXED at 8 (the deployed scale-up
# domain - DGX/HGX, NVIDIA EOS is 576 nodes x 8); RACK COUNT is the axis.
#
# Why this is the headline sensitivity (measured 2026-08-04): at 64 GPUs in
# 8 racks, all_reduce 64 MB is a byte-identical tie between Loom and B1,
# and at 256 GPUs in 32 racks the same cell is +25.2%. The mechanism is the
# STRUCTURE of the dim1 phase, not its size. A hierarchical collective does
# reduce-scatter on dim0 -> exchange on dim1 -> all-gather on dim0. The
# dim1 phase moves roughly constant total bytes (~2S/m) but spreads them
# over 2(r-1) steps, so per-step bytes fall as ~1/r while per-step LATENCY
# is constant. Few racks = few fat steps = bandwidth-bound, and Loom's
# 1615-vs-3000 ns dim1 edge is hidden. Many racks = many thin steps =
# latency-bound, which is exactly where Loom wins.
#
# Consequence for the paper: Loom's benefit is a function of cluster width,
# so quoting a single number is meaningless without stating the scale. Real
# deployments are far wider than anything simulated here (NCCL EP evaluates
# on EOS at 4,608 GPUs), i.e. the regime this sweep walks TOWARDS.
#
# CSV on stdout: racks,gpus,collective,size_mb,system,wall_cycles,exposed_comm
set -e
cd "$(dirname "$0")/../.."
ROOT=$PWD
BIN=$ROOT/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware
RM=$ROOT/examples/remote_memory/analytical/no_memory_expansion.json
GEN=$ROOT/examples/loom/gen_network_config.py

XPUS=${XPUS:-8}                       # deployed scale-up domain; do not thin
RACKS=${RACKS:-2 4 8 16 32 64}        # 16 .. 512 GPUs
COLLS=${COLLS:-all_reduce all_to_all}
SIZES=${SIZES:-1 64}

echo "racks,gpus,collective,size_mb,system,wall_cycles,exposed_comm"
for R in $RACKS; do
  N=$((R * XPUS))
  python3 $GEN --mode loom     --racks $R --xpus-per-rack $XPUS -o /tmp/net_sc_loom.yml
  python3 $GEN --mode baseline --racks $R --xpus-per-rack $XPUS -o /tmp/net_sc_b1.yml
  python3 $GEN --mode baseline --racks $R --xpus-per-rack $XPUS --rdma-init-ns 2800 \
      -o /tmp/net_sc_b2.yml
  for C in $COLLS; do
    for S in $SIZES; do
      WLDIR=/tmp/scalebench && mkdir -p $WLDIR && ( cd $WLDIR && \
        python3 $ROOT/examples/workload/microbenchmarks/generator_scripts/$C.py \
          --npus-count $N --coll-size $S >/dev/null )
      WL=$WLDIR/$C/${N}npus_${S}MB/$C
      for SYS in "loom loom.json /tmp/net_sc_loom.yml" \
                 "b1_gpu_rdma baseline_gpu_rdma.json /tmp/net_sc_b1.yml" \
                 "b2_cpu_proxy baseline_cpu_proxy.json /tmp/net_sc_b2.yml --rendezvous-protocol=true"; do
        set -- $SYS; NAME=$1; SYSJ=$2; NET=$3; shift 3
        OUT=$($BIN --workload-configuration=$WL \
          --system-configuration=$ROOT/examples/loom/system/$SYSJ \
          --network-configuration=$NET \
          --remote-memory-configuration=$RM "$@" 2>&1 | grep -m1 "sys\[0\] finished")
        W=$(echo "$OUT" | grep -o "finished, [0-9]*" | grep -o "[0-9]*")
        E=$(echo "$OUT" | grep -o "communication [0-9]*" | grep -o "[0-9]*")
        echo "$R,$N,$C,$S,$NAME,$W,$E"
      done
    done
  done
done
