#!/bin/bash
# M2: point-to-point send/recv sweep - the pipeline-parallel traffic class,
# and the ONLY clean measurement of per-operation cost in the suite.
#
# Why this exists (2026-08-04). Every other experiment is a collective, and
# collectives hide the quantity the headline depends on: at 64 MB the model
# is COMPLETELY insensitive to rdma_init (0 ns and 2400 ns give identical
# wall times) because chunk scheduling overlaps dim1 latency away. A single
# send/recv pair has no chunk-overlap machinery, so the fixed per-operation
# cost that Loom eliminates is directly visible, and the crossover where it
# stops mattering is measured rather than asserted.
#
# One pair, in-rack (0->1) and cross-rack (0->4), swept 4 KB - 1 GB against
# all four systems.
#
# READ BEFORE USING THE IN-RACK ROWS: no baseline comparison is meaningful
# in-rack. B1 and B3 are identical to Loom BY CONSTRUCTION (the model's own
# invariant - in-rack peer access is a plain store for every system - and
# the ToR IS the rack switch, so dim0 config is byte-identical: all three
# give 8472 cycles at 4 KB). B2 differs ONLY because --rendezvous-protocol
# is a GLOBAL simulator flag, so it charges a large-message handshake to
# that same plain store; without the flag B2 is 8472 too. The in-rack rows
# are therefore a reference FLOOR (same binary, same store, routed locally
# instead of across racks = the location-transparency result) and the sim
# twin of hardware T1/M3 - never a win over a baseline. 2 racks x 8 XPUs (the deployed scale-up domain): ranks 0-7 = rack 0,
# 8-15 = rack 1.
# CSV on stdout: route,size_kb,system,wall_cycles
set -e
cd "$(dirname "$0")/../.."
ROOT=$PWD
BIN=$ROOT/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware
RM=$ROOT/examples/remote_memory/analytical/no_memory_expansion.json
GEN=$ROOT/examples/loom/gen_network_config.py
PAT=$ROOT/examples/loom/workload/gen_p2p_patterns.py

# 4 KB ... 1 GB, log2 sweep (KB units; the p2p generator is KB-granular, so
# unlike the upstream collective generators it is NOT floored at 1 MB).
SIZES=${SIZES:-4 16 64 256 1024 4096 16384 65536 262144 1048576}
ITERS=${ITERS:-8}

python3 $GEN --mode loom     --racks 2 --xpus-per-rack 8 -o /tmp/net_p2p_loom.yml
python3 $GEN --mode baseline --racks 2 --xpus-per-rack 8 -o /tmp/net_p2p_b1.yml

echo "route,size_kb,system,wall_cycles"
for ROUTE in in_rack cross_rack; do
  # in-rack stays inside rack 0 (dim0 only); cross-rack crosses to rack 1
  [ "$ROUTE" = "in_rack" ] && DST=1 || DST=8
  for S in $SIZES; do
    WL=/tmp/p2p_${ROUTE}_${S}
    python3 $PAT --pattern single --racks 2 --xpus-per-rack 8 \
        --src 0 --dst $DST --size-kb $S --iters $ITERS --out $WL >/dev/null
    for SYS in "loom loom.json /tmp/net_p2p_loom.yml" \
               "b1_gpu_rdma baseline_gpu_rdma.json /tmp/net_p2p_b1.yml" \
               "b2_cpu_proxy baseline_cpu_proxy.json /tmp/net_p2p_b1.yml --rendezvous-protocol=true"; do
      set -- $SYS; NAME=$1; SYSJ=$2; NET=$3; shift 3
      # MAX over all ranks, not sys[0]: in eager mode the sender completes
      # at injection (posted-write source-local completion), and the six
      # uninvolved ranks finish on their 1 us idle node. Grabbing the first
      # "finished" line reports 1000 cycles for every configuration.
      W=$($BIN --workload-configuration=$WL/p2p \
        --system-configuration=$ROOT/examples/loom/system/$SYSJ \
        --network-configuration=$NET \
        --remote-memory-configuration=$RM "$@" 2>&1 \
        | grep -o "finished, [0-9]*" | grep -o "[0-9]*" | sort -n | tail -1)
      echo "$ROUTE,$S,$NAME,$W"
    done
  done
done
