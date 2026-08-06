#!/bin/bash
# Collective-benchmark matrix: traffic pattern x size x topology x system.
# Workloads come from the repo's OWN microbenchmark generators
# (examples/workload/microbenchmarks/generator_scripts).
# CSV on stdout: cluster,collective,size_mb,system,wall_cycles,exposed_comm
set -e
cd "$(dirname "$0")/../.."
ROOT=$PWD
BIN=$ROOT/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware
RM=$ROOT/examples/remote_memory/analytical/no_memory_expansion.json
GEN=$ROOT/examples/loom/gen_network_config.py

COLLS=${COLLS:-all_to_all all_reduce all_gather reduce_scatter}
SIZES=${SIZES:-1 16 64}
# SUFFIX picks the system-JSON variant: "" = the default ring algorithms,
# "_direct" = the direct variants (F2, see run_f2.sh). All four systems
# switch together so the comparison isolates the algorithm.
SUFFIX=${SUFFIX:-}
# name racks xpus extra-args
#
# The grid is CLUSTER SIZE x COLLECTIVE x SIZE. There is exactly ONE
# physical topology, [Switch, Switch], because that is what is deployed:
# scale-up is a switch (NVSwitch/NVLink), scale-out is a switched
# Clos/rail-optimized fabric.
#
# XPUs per rack is FIXED AT 8 - that is the deployed scale-up domain
# (DGX/HGX; NVIDIA EOS is 576 nodes x 8), and GB200 NVL72 goes the other
# way to 72. Never thin the rack to make Loom look better: a 4-GPU rack
# models a machine nobody builds. The axis is RACK COUNT, because a
# hierarchical collective puts more work on dim1 as the cluster widens,
# and dim1 is the only dimension Loom changes.
#
# Scale matters enormously and used to be invisible (2026-08-04). At 64
# GPUs, all_reduce 64 MB is a byte-identical tie (Loom = B1 = 909,088)
# because ~99% of the bytes stay on dim0; at 256 GPUs the same cell is
# +25.2%. Comparable work evaluates far larger still - NCCL EP on EOS is
# 4,608 GPUs, DeepEP targets 64+ EP degree - so 64 GPUs sat in exactly the
# regime where the scale-up/scale-out divide costs least.
#
# Removed on 2026-08-04:
#  - `ring_tor` (--dim1-topology Ring): nobody deploys a ring of ToRs, and
#    it was the sole source of the "negative cells" confusion. A ring
#    ALGORITHM on a ring TOPOLOGY made that collective ~5x slower for BOTH
#    systems, diluting Loom's per-op advantage until only its 50 ns in-rack
#    lookup showed (-1.11%). Without it, ring and direct agree to within
#    0.02%, so the F2 question is moot by construction.
#  - `thin_uplinks` (--net-bw 12.5): misnamed, and it answered the wrong
#    question. --net-bw thins the fabric for BOTH systems, so it modelled a
#    slower network for everyone, not thin LOOM uplinks. The Loom-specific
#    knob is --uplink-oversub, deliberately left at 1.0 = equal wires (ToR
#    uplink aggregate = the M NICs Loom deletes). That is buildable (400
#    GB/s of uplink is a small fraction of a modern ToR ASIC), and
#    handicapping only Loom would break the equal-wires fairness framing -
#    under equal COST the argument runs the other way, since Loom removes M
#    NICs per rack. NOTE: the intrinsic dim0/dim1 taper (64 vs 50 GB/s per
#    XPU) is NOT oversubscription - those are the wire rates, and both
#    systems pay them.
CLUSTERS=("64gpu_8racks 8 8" "256gpu_32racks 32 8")

echo "cluster,collective,size_mb,system,wall_cycles,exposed_comm"
for T in "${CLUSTERS[@]}"; do
  set -- $T; TNAME=$1; RACKS=$2; XPUS=$3; shift 3; EXTRA="$@"
  NPUS=$((RACKS * XPUS))
  python3 $GEN --mode loom     --racks $RACKS --xpus-per-rack $XPUS $EXTRA -o /tmp/net_loom.yml
  python3 $GEN --mode baseline --racks $RACKS --xpus-per-rack $XPUS $EXTRA -o /tmp/net_base.yml
  for C in $COLLS; do
    for S in $SIZES; do
      WLDIR=/tmp/microbench && mkdir -p $WLDIR && ( cd $WLDIR && \
        python3 $ROOT/examples/workload/microbenchmarks/generator_scripts/$C.py \
          --npus-count $NPUS --coll-size $S >/dev/null )
      WL=$WLDIR/$C/${NPUS}npus_${S}MB/$C
      for SYS in "loom loom${SUFFIX}.json /tmp/net_loom.yml" \
                 "b1_gpu_rdma baseline_gpu_rdma${SUFFIX}.json /tmp/net_base.yml" \
                 "b2_cpu_proxy baseline_cpu_proxy${SUFFIX}.json /tmp/net_base.yml --rendezvous-protocol=true"; do
        set -- $SYS; NAME=$1; SYSJ=$2; NET=$3; shift 3
        OUT=$($BIN --workload-configuration=$WL \
          --system-configuration=$ROOT/examples/loom/system/$SYSJ \
          --network-configuration=$NET \
          --remote-memory-configuration=$RM "$@" 2>&1 | grep -m1 "sys\[0\] finished")
        W=$(echo "$OUT" | grep -o "finished, [0-9]*" | grep -o "[0-9]*")
        E=$(echo "$OUT" | grep -o "communication [0-9]*" | grep -o "[0-9]*")
        echo "$TNAME,$C,$S,$NAME,$W,$E"
      done
    done
  done
done
