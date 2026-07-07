#!/bin/bash
# Loom smoke run: MoE all-to-all on 2 racks x 2 XPUs, Loom vs baselines.
# Run from the astra-sim repo root (inside the official Docker image).
set -e
cd "$(dirname "$0")/../.."

BIN=build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware
[ -x "$BIN" ] || BIN=build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Aware

WL=/tmp/loom_smoke
python3 examples/loom/workload/gen_moe_alltoall.py --npus 4 --coll-size-kb 256 \
    --expert-time-us 500 --iters 2 --sm-comm 0  --out $WL/loom
python3 examples/loom/workload/gen_moe_alltoall.py --npus 4 --coll-size-kb 256 \
    --expert-time-us 500 --iters 2 --sm-comm 20 --out $WL/b1

run() {  # $1 label, $2 workload dir, $3 network yml, $4 system json, extra args...
    local label=$1 wl=$2 net=$3 sysj=$4; shift 4
    echo "=== $label ==="
    "$BIN" \
        --workload-configuration="$wl/moe" \
        --system-configuration="examples/loom/system/$sysj" \
        --network-configuration="examples/loom/network/$net" \
        --remote-memory-configuration=examples/remote_memory/analytical/no_memory_expansion.json \
        "$@" 2>&1 | grep -E "finished|Wall time|COMM time|GPU time" | head -8
}

run "Loom"            $WL/loom loom_2racks_2xpus.yml     loom.json
run "B1 (GPU RDMA)"   $WL/b1   baseline_2racks_2xpus.yml baseline_gpu_rdma.json
run "B2 (CPU proxy)"  $WL/b1   baseline_2racks_2xpus.yml baseline_cpu_proxy.json --rendezvous-protocol=true
run "B3 (ideal RDMA)" $WL/loom ideal_2racks_2xpus.yml    ideal_rdma.json
