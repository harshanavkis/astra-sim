#!/bin/bash
# S-5: read-credit cap sensitivity. 4 ranks x 64 independent 4KB peer reads
# through LOOM_PEER_READS. CSV on stdout: read_credits,wall_cycles
set -e
cd "$(dirname "$0")/../.."
BIN=build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware
python3 examples/loom/workload/gen_read_pattern.py --npus 4 --loads 64 --size-kb 4 --out /tmp/reads >/dev/null
python3 examples/loom/gen_network_config.py --mode loom --racks 2 --xpus-per-rack 2 -o /tmp/net.yml
echo "read_credits,wall_cycles"
for CR in 1 2 4 8 16 32 64; do
  sed "s/\"read-credits\": 32/\"read-credits\": $CR/" examples/loom/remote_memory/loom_peer_reads.json > /tmp/rm.json
  W=$($BIN --workload-configuration=/tmp/reads/reads \
    --system-configuration=examples/loom/system/loom.json \
    --network-configuration=/tmp/net.yml \
    --remote-memory-configuration=/tmp/rm.json 2>&1 | grep -m1 -o 'finished, [0-9]*' | grep -o '[0-9]*')
  echo "$CR,$W"
done
