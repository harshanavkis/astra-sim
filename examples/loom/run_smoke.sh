#!/bin/bash
# Endpoint-model comparison on the repo's shipped all-to-all microbenchmark
# ETs (4 NPUs, 1MB) over 2 racks x 2 XPUs. CSV on stdout:
# system,wall_cycles,exposed_comm_cycles
#
# Configs are GENERATED at run time from gen_network_config.py, like every
# other script in the suite. Until 2026-08-04 this was the only script
# reading the committed network/*.yml, which had rotted to the pre-D10
# model (Loom dim1 3000 vs baseline 2000 - the inverse of the current
# model), so smoke.csv measured a dead model. Do not reintroduce a static
# config here.
set -e
cd "$(dirname "$0")/../.."
BIN=build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware
GEN=examples/loom/gen_network_config.py
WL=examples/workload/microbenchmarks/all_to_all/4npus_1MB/all_to_all
RM=examples/remote_memory/analytical/no_memory_expansion.json

# B2 carries its own rdma-init (2800 ns, CPU-posted) exactly as in
# run_matrix.sh; the old static config handed it B1's network by mistake.
python3 $GEN --mode loom     --racks 2 --xpus-per-rack 2 -o /tmp/net_smoke_loom.yml
python3 $GEN --mode baseline --racks 2 --xpus-per-rack 2 -o /tmp/net_smoke_b1.yml

echo "system,wall_cycles,exposed_comm_cycles"
run() {  # $1 label, $2 network yml, $3 system json, extra args...
    local label=$1 net=$2 sysj=$3; shift 3
    local out=$("$BIN" --workload-configuration=$WL \
        --system-configuration="examples/loom/system/$sysj" \
        --network-configuration="$net" \
        --remote-memory-configuration=$RM "$@" 2>&1 | grep -m1 "sys\[0\] finished")
    local wall=$(echo "$out" | grep -o "finished, [0-9]*" | grep -o "[0-9]*")
    local exp=$(echo "$out" | grep -o "communication [0-9]*" | grep -o "[0-9]*")
    echo "$label,$wall,$exp"
}
run loom            /tmp/net_smoke_loom.yml  loom.json
run b1_gpu_rdma     /tmp/net_smoke_b1.yml    baseline_gpu_rdma.json
run b2_cpu_proxy    /tmp/net_smoke_b2.yml    baseline_cpu_proxy.json --rendezvous-protocol=true
