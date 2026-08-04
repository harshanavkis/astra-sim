#!/bin/bash
# SM-reservation sweep (catalog A6): how much of the app-level gain is SM
# reclamation, and how sensitive is it to the number of reserved SMs?
#
# HOW THE SM TAX IS MODELLED. There is no notion of an SM in ASTRA-sim.
# Every COMP node's duration comes from the roofline (Workload.cc):
#     operational_intensity = num_ops / tensor_size
#     perf     = min(local_mem_bw * operational_intensity, peak_perf)
#     duration = num_ops / perf
# so reserving k of 132 SMs for communication is expressed by giving the
# BASELINE a derated endpoint: peak_perf = 989 * (132-k)/132, while Loom
# keeps the full 989 because nothing runs on its accelerators. k=20 is
# DeepSeek-V3's disclosed reservation and gives the shipped 839.
#
# TWO KNOWN LIMITATIONS, both making this an UNDER-estimate:
#  1. `perf` is a min(), so only COMPUTE-BOUND nodes are derated. Anything
#     memory-bound (mem_bw * OI < peak_perf) is untouched, and both systems
#     use the same local-mem-bw. Reserving SMs also costs achievable memory
#     bandwidth in reality, since fewer SMs issue loads. Set MEMBW=1 to
#     derate local-mem-bw by the same factor and bound that effect.
#  2. 989 is H100 peak while the 20/132 reservation is DeepSeek's H800 -
#     a provenance mix, flagged in the README constants table.
#
# The reclamation gain is topology-INDEPENDENT (measured: +10.72% compute
# gain at both 8 GPUs/rack x 32 racks and 64 GPUs/rack x 4 racks) but its
# WEIGHT in wall time is set by the workload's compute fraction, which is
# what this sweep exposes.
#
# CSV on stdout: app,ranks,reserved_sms,membw_derated,system,wall_cycles,exposed_comm
set -e
cd "$(dirname "$0")/../.."
ROOT=$PWD
BIN=$ROOT/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware
RM=$ROOT/examples/remote_memory/analytical/no_memory_expansion.json
examples/loom/fetch_stg.sh >/dev/null 2>&1

PEAK=${PEAK:-989}          # full-GPU peak TFLOPS (Loom always gets this)
SMS=${SMS:-132}            # total SMs
KS=${KS:-0 8 20 32}        # reserved-SM counts to sweep
MEMBW=${MEMBW:-0}          # 1 = also derate local-mem-bw by (SMS-k)/SMS
# app kind ranks racks xpus stg-overrides...
CFGS=${CFGS:-}
[ -n "$CFGS" ] || CFGS_DEFAULT=1
CFG_LIST=("mixtral_moe moe 64 8 8 --dp 2 --tp 4 --ep 8"
          "gpt3_dense dense 64 8 8 --dp 4 --tp 4 --pp 4")

echo "app,ranks,reserved_sms,membw_derated,system,wall_cycles,exposed_comm"
for CFG in "${CFG_LIST[@]}"; do
  set -- $CFG; APP=$1; KIND=$2; RANKS=$3; RACKS=$4; XPUS=$5; shift 5
  WL=/tmp/stg_sm_${APP}_${RANKS}
  [ -f $WL/$KIND.json ] || examples/loom/gen_stg_workloads.sh $KIND $WL "$@" >/dev/null 2>&1
  python3 examples/loom/gen_network_config.py --mode loom --racks $RACKS \
      --xpus-per-rack $XPUS -o /tmp/net_sm_loom.yml
  python3 examples/loom/gen_network_config.py --mode baseline --racks $RACKS \
      --xpus-per-rack $XPUS -o /tmp/net_sm_b1.yml
  for K in $KS; do
    # Loom: full GPU. Baseline: k SMs reserved for communication.
    python3 - "$K" "$PEAK" "$SMS" "$MEMBW" << 'PY'
import collections, json, sys
k, peak, sms, membw = int(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
base = "examples/loom/system/"
frac = (sms - k) / sms
for src, dst, pk in ((f"{base}loom_roofline.json", "/tmp/sys_sm_loom.json", peak),
                     (f"{base}baseline_gpu_rdma_roofline.json", "/tmp/sys_sm_b1.json",
                      peak * frac)):
    d = json.load(open(src), object_pairs_hook=collections.OrderedDict)
    d["peak-perf"] = round(pk, 2)
    if membw and dst.endswith("b1.json"):
        d["local-mem-bw"] = round(d["local-mem-bw"] * frac, 2)
    open(dst, "w").write(json.dumps(d, indent=4))
PY
    for SYS in "loom /tmp/sys_sm_loom.json /tmp/net_sm_loom.yml" \
               "b1_gpu_rdma /tmp/sys_sm_b1.json /tmp/net_sm_b1.yml"; do
      set -- $SYS; NAME=$1; SYSJ=$2; NET=$3
      OUT=$($BIN --workload-configuration=$WL/$KIND \
        --system-configuration=$SYSJ --network-configuration=$NET \
        --remote-memory-configuration=$RM \
        --comm-group-configuration=$WL/$KIND.json 2>&1 | grep -m1 "sys\[0\] finished")
      W=$(echo "$OUT" | grep -o "finished, [0-9]*" | grep -o "[0-9]*")
      E=$(echo "$OUT" | grep -o "communication [0-9]*" | grep -o "[0-9]*")
      echo "$APP,$RANKS,$K,$MEMBW,$NAME,$W,$E"
    done
  done
done
