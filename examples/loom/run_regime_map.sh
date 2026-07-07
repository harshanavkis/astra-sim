#!/bin/bash
# Regime map: where does Loom win, and by how much?
# Sweeps compute speed (scaling BOTH systems' roofline peak-perf, ratio fixed
# at 132:112) to move the STG MoE workload from compute-bound to comm-bound.
# Output CSV: compute_speedup,loom,b1_gpu_rdma,gain_pct,loom_exposed_comm_pct
#
# Reading (placeholder constants): gain -> SM-reclamation ceiling (~15%) as
# the workload becomes compute-bound; parity (+-1.5%) when fully comm-bound,
# i.e., bulk collective throughput is NOT where Loom wins - the SM tax,
# fine-grained latency (testbed T1), isolation, and unification are.
set -e
cd "$(dirname "$0")/../.."
BIN=build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware
RM=examples/remote_memory/analytical/no_memory_expansion.json

examples/loom/fetch_stg.sh >/dev/null 2>&1
[ -f /tmp/stg_moe/moe.json ] || examples/loom/gen_stg_workloads.sh moe /tmp/stg_moe >/dev/null 2>&1
python3 examples/loom/gen_network_config.py --mode loom --racks 4 --xpus-per-rack 4 --pipe-ns 500 -o /tmp/net_loom.yml
python3 examples/loom/gen_network_config.py --mode baseline --racks 4 --xpus-per-rack 4 -o /tmp/net_b1.yml

run() { $BIN --workload-configuration=/tmp/stg_moe/moe --system-configuration=$1 \
  --network-configuration=$2 --remote-memory-configuration=$RM \
  --comm-group-configuration=/tmp/stg_moe/moe.json 2>&1; }

echo "compute_speedup,loom,b1_gpu_rdma,gain_pct,loom_exposed_comm_pct"
for K in ${KS:-0.1 0.3 1 3 10 100}; do
  python3 - <<PY
import json
for src, dst, base in [("examples/loom/system/loom_roofline.json","/tmp/sys_loom.json",989),
                       ("examples/loom/system/baseline_gpu_rdma_roofline.json","/tmp/sys_b1.json",839)]:
    c = json.load(open(src)); c["peak-perf"] = base * $K
    json.dump(c, open(dst,"w"))
PY
  OUT=$(run /tmp/sys_loom.json /tmp/net_loom.yml | grep -m1 "finished")
  L=$(echo "$OUT" | grep -o "finished, [0-9]*" | grep -o "[0-9]*")
  E=$(echo "$OUT" | grep -o "communication [0-9]*" | grep -o "[0-9]*")
  B=$(run /tmp/sys_b1.json /tmp/net_b1.yml | grep -m1 -o "finished, [0-9]*" | grep -o "[0-9]*")
  python3 -c "print(f\"$K,$L,$B,{100*($B-$L)/$B:.1f},{100*$E/$L:.0f}\")"
done
