#!/bin/bash
# Sim-V1: victim-flow isolation at the ToR (twin of testbed T5).
# Victim 0->4 (8 x 256KB) vs 3 aggressors 1,2,3->5 (8 x 4MB), one switch.
# CSV on stdout: case,victim_fct_cycles
set -e
cd "$(dirname "$0")/../.."
BIN=build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Aware
RM=examples/remote_memory/analytical/no_memory_expansion.json

printf "topology: [ Switch ]\nnpus_count: [ 8 ]\nbandwidth: [ 64.0 ]\nlatency: [ 1000.0 ]\n" > /tmp/voq.yml
cp /tmp/voq.yml /tmp/hol.yml && echo "switch_egress: shared_fifo" >> /tmp/hol.yml
python3 examples/loom/workload/gen_p2p_patterns.py --pattern victim --racks 2 --xpus-per-rack 4 \
  --size-kb 256 --aggressor-size-kb 4096 --iters 8 --aggressors 3 --out /tmp/vic >/dev/null
python3 examples/loom/workload/gen_p2p_patterns.py --pattern victim --racks 2 --xpus-per-rack 4 \
  --size-kb 256 --iters 8 --aggressors 0 --out /tmp/solo >/dev/null

echo "case,victim_fct_cycles"
for CASE in "solo /tmp/solo /tmp/voq.yml" "voq /tmp/vic /tmp/voq.yml" "shared_fifo /tmp/vic /tmp/hol.yml"; do
  set -- $CASE
  FCT=$($BIN --workload-configuration=$2/p2p \
    --system-configuration=examples/loom/system/loom_1d.json \
    --network-configuration=$3 \
    --remote-memory-configuration=$RM 2>&1 \
    | grep -m1 "sys\[4\] finished" | grep -o "finished, [0-9]*" | grep -o "[0-9]*")
  echo "$1,$FCT"
done
