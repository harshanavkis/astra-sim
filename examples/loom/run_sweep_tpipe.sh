#!/bin/bash
# S-1 sensitivity sweep: Loom switch pipeline latency (t_pipe) vs completion
# time, Loom against the B1 GPU-RDMA baseline (SM reservation via roofline
# peak-perf). Workload: STG-generated MoE (dp2 x tp2 x ep4 = 16 ranks).
# Output: CSV on stdout (system,t_pipe_ns,wall_cycles).
set -e
cd "$(dirname "$0")/../.."
BIN=build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware
RM=examples/remote_memory/analytical/no_memory_expansion.json
RACKS=4; XPUS=4

examples/loom/fetch_stg.sh >/dev/null
[ -f /tmp/stg_moe/moe.json ] || examples/loom/gen_stg_workloads.sh moe /tmp/stg_moe \
    --num_stacks 2 --batch 8 --seq 512 >/dev/null 2>&1

run() {  # $1 sysjson, $2 netyml -> wall cycles
    $BIN --workload-configuration=/tmp/stg_moe/moe \
        --system-configuration=examples/loom/system/$1 \
        --network-configuration=$2 \
        --remote-memory-configuration=$RM \
        --comm-group-configuration=/tmp/stg_moe/moe.json 2>&1 \
        | grep -m1 -o 'finished, [0-9]*' | grep -o '[0-9]*'
}

echo "system,t_pipe_ns,wall_cycles"
for T in 100 250 500 1000 2000 5000; do
    python3 examples/loom/gen_network_config.py --mode loom --racks $RACKS \
        --xpus-per-rack $XPUS --pipe-ns $T -o /tmp/net_loom.yml
    echo "loom,$T,$(run loom_roofline.json /tmp/net_loom.yml)"
done
python3 examples/loom/gen_network_config.py --mode baseline --racks $RACKS \
    --xpus-per-rack $XPUS -o /tmp/net_b1.yml
echo "b1_gpu_rdma,0,$(run baseline_gpu_rdma_roofline.json /tmp/net_b1.yml)"
