#!/bin/bash
# Collective-benchmark matrix: traffic pattern x size x topology x system.
# Workloads come from the repo's OWN microbenchmark generators
# (examples/workload/microbenchmarks/generator_scripts).
# CSV on stdout: topology,collective,size_mb,system,wall_cycles,exposed_comm
set -e
cd "$(dirname "$0")/../.."
ROOT=$PWD
BIN=$ROOT/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware
RM=$ROOT/examples/remote_memory/analytical/no_memory_expansion.json
GEN=$ROOT/examples/loom/gen_network_config.py

COLLS=${COLLS:-all_to_all all_reduce all_gather reduce_scatter}
SIZES=${SIZES:-1 16 64}
# name racks xpus extra-args
TOPOS=("rack4x4 4 4" "rack8x8 8 8" "thin_uplinks 8 8 --net-bw 12.5" "ring_tor 8 8 --dim1-topology Ring")

echo "topology,collective,size_mb,system,wall_cycles,exposed_comm"
for T in "${TOPOS[@]}"; do
  set -- $T; TNAME=$1; RACKS=$2; XPUS=$3; shift 3; EXTRA="$@"
  NPUS=$((RACKS * XPUS))
  python3 $GEN --mode loom     --racks $RACKS --xpus-per-rack $XPUS $EXTRA -o /tmp/net_loom.yml
  python3 $GEN --mode baseline --racks $RACKS --xpus-per-rack $XPUS $EXTRA -o /tmp/net_base.yml
  python3 $GEN --mode ideal    --racks $RACKS --xpus-per-rack $XPUS $EXTRA -o /tmp/net_ideal.yml
  for C in $COLLS; do
    for S in $SIZES; do
      WLDIR=/tmp/microbench && mkdir -p $WLDIR && ( cd $WLDIR && \
        python3 $ROOT/examples/workload/microbenchmarks/generator_scripts/$C.py \
          --npus-count $NPUS --coll-size $S >/dev/null )
      WL=$WLDIR/$C/${NPUS}npus_${S}MB/$C
      for SYS in "loom loom.json /tmp/net_loom.yml" \
                 "b1_gpu_rdma baseline_gpu_rdma.json /tmp/net_base.yml" \
                 "b2_cpu_proxy baseline_cpu_proxy.json /tmp/net_base.yml --rendezvous-protocol=true" \
                 "b3_ideal ideal_rdma.json /tmp/net_ideal.yml"; do
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
