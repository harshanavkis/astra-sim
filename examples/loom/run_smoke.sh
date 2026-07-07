#!/bin/bash
# Smoke run: endpoint models (Loom vs baselines) on the repo's OWN shipped
# all-to-all microbenchmark ETs (examples/workload/microbenchmarks, 4 NPUs,
# 1 MB) over 2 racks x 2 XPUs. No generated workloads.
set -e
cd "$(dirname "$0")/../.."
BIN=build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware
WL=examples/workload/microbenchmarks/all_to_all/4npus_1MB/all_to_all
RM=examples/remote_memory/analytical/no_memory_expansion.json

run() {  # $1 label, $2 network yml, $3 system json, extra args...
    local label=$1 net=$2 sysj=$3; shift 3
    echo "=== $label ==="
    "$BIN" \
        --workload-configuration=$WL \
        --system-configuration="examples/loom/system/$sysj" \
        --network-configuration="examples/loom/network/$net" \
        --remote-memory-configuration=$RM "$@" 2>&1 | grep -m2 -E "finished"
}

run "Loom"            loom_2racks_2xpus.yml     loom.json
run "B1 (GPU RDMA)"   baseline_2racks_2xpus.yml baseline_gpu_rdma.json
run "B2 (CPU proxy)"  baseline_2racks_2xpus.yml baseline_cpu_proxy.json --rendezvous-protocol=true
run "B3 (ideal RDMA)" ideal_2racks_2xpus.yml    ideal_rdma.json
