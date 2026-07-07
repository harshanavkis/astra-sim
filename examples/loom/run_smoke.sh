#!/bin/bash
# Endpoint-model comparison on the repo's shipped all-to-all microbenchmark
# ETs (4 NPUs, 1MB) over 2 racks x 2 XPUs. CSV on stdout:
# system,wall_cycles,exposed_comm_cycles
set -e
cd "$(dirname "$0")/../.."
BIN=build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware
WL=examples/workload/microbenchmarks/all_to_all/4npus_1MB/all_to_all
RM=examples/remote_memory/analytical/no_memory_expansion.json

echo "system,wall_cycles,exposed_comm_cycles"
run() {  # $1 label, $2 network yml, $3 system json, extra args...
    local label=$1 net=$2 sysj=$3; shift 3
    local out=$("$BIN" --workload-configuration=$WL \
        --system-configuration="examples/loom/system/$sysj" \
        --network-configuration="examples/loom/network/$net" \
        --remote-memory-configuration=$RM "$@" 2>&1 | grep -m1 "sys\[0\] finished")
    local wall=$(echo "$out" | grep -o "finished, [0-9]*" | grep -o "[0-9]*")
    local exp=$(echo "$out" | grep -o "communication [0-9]*" | grep -o "[0-9]*")
    echo "$label,$wall,$exp"
}
run loom            loom_2racks_2xpus.yml     loom.json
run b1_gpu_rdma     baseline_2racks_2xpus.yml baseline_gpu_rdma.json
run b2_cpu_proxy    baseline_2racks_2xpus.yml baseline_cpu_proxy.json --rendezvous-protocol=true
run b3_ideal_rdma   ideal_2racks_2xpus.yml    ideal_rdma.json
