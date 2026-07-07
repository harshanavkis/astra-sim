#!/bin/bash
# S-1 sensitivity sweep: Loom switch pipeline latency (t_pipe) vs completion
# time, Loom against the B1 GPU-RDMA baseline, MoE all-to-all workload.
# Output: CSV on stdout (system,t_pipe_ns,wall_cycles).
set -e
cd "$(dirname "$0")/../.."
BIN=build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware
RACKS=${RACKS:-8}; XPUS=${XPUS:-8}; NPUS=$((RACKS * XPUS))
RM=examples/remote_memory/analytical/no_memory_expansion.json

python3 examples/loom/workload/gen_moe_alltoall.py --npus $NPUS --coll-size-kb 512 \
    --expert-time-us 800 --iters 4 --sm-comm 0  --out /tmp/sweep_loom >/dev/null
python3 examples/loom/workload/gen_moe_alltoall.py --npus $NPUS --coll-size-kb 512 \
    --expert-time-us 800 --iters 4 --sm-comm 20 --out /tmp/sweep_b1 >/dev/null

echo "system,t_pipe_ns,wall_cycles"
for T in 100 250 500 1000 2000 5000; do
    python3 examples/loom/gen_network_config.py --mode loom --racks $RACKS \
        --xpus-per-rack $XPUS --pipe-ns $T -o /tmp/net_loom.yml
    W=$($BIN --workload-configuration=/tmp/sweep_loom/moe \
        --system-configuration=examples/loom/system/loom.json \
        --network-configuration=/tmp/net_loom.yml \
        --remote-memory-configuration=$RM 2>&1 | grep -m1 -o 'finished, [0-9]*' | grep -o '[0-9]*')
    echo "loom,$T,$W"
done
python3 examples/loom/gen_network_config.py --mode baseline --racks $RACKS \
    --xpus-per-rack $XPUS -o /tmp/net_b1.yml
W=$($BIN --workload-configuration=/tmp/sweep_b1/moe \
    --system-configuration=examples/loom/system/baseline_gpu_rdma.json \
    --network-configuration=/tmp/net_b1.yml \
    --remote-memory-configuration=$RM 2>&1 | grep -m1 -o 'finished, [0-9]*' | grep -o '[0-9]*')
echo "b1_gpu_rdma,0,$W"
