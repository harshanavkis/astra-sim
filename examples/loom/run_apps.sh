#!/bin/bash
# Application-level comparison (published model shapes via STG):
#   mixtral_moe (Mixtral 8x7B, EP all-to-all heavy)
#   gpt3_dense  (GPT-3 175B, TP/PP/DP)
# at 16 and 64 ranks, Loom vs B1 (roofline configs carry the SM tax).
# CSV on stdout: app,ranks,system,wall_cycles,exposed_comm
set -e
cd "$(dirname "$0")/../.."
ROOT=$PWD
BIN=$ROOT/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware
RM=$ROOT/examples/remote_memory/analytical/no_memory_expansion.json
examples/loom/fetch_stg.sh >/dev/null 2>&1
# SUFFIX: "" = default ring algorithms, "_direct" = direct variants (F2).
SUFFIX=${SUFFIX:-}

# app kind ranks racks xpus stg-overrides...
#
# XPUs per rack is FIXED AT 8 - the deployed scale-up domain (DGX/HGX;
# NVIDIA EOS is 576 nodes x 8). The 16- and 32-rank rows used to be 4x4 and
# 8x4, i.e. 4-GPU racks, which no one builds and which under-exercised dim1
# (the only dimension Loom changes). Scale is now carried by RACK COUNT.
# The 256-GPU rows matter most: at 64 GPUs a hierarchical collective keeps
# ~99% of its bytes on dim0, so the divide barely shows (2026-08-04).
# Rank count must equal dp*tp*pp*ep. NOTE: pp cannot exceed the preset's
# --num_stacks (4), or STG's convert_chakra asserts - dense 256 therefore
# scales dp (dp16 tp4 pp4), not pp.
CFGS=("mixtral_moe moe 16 2 8"
      "mixtral_moe moe 64 8 8 --dp 2 --tp 4 --ep 8"
      "mixtral_moe moe 256 32 8 --dp 8 --tp 4 --ep 8"
      "gpt3_dense dense 32 4 8"
      "gpt3_dense dense 64 8 8 --dp 4 --tp 4 --pp 4"
      "gpt3_dense dense 256 32 8 --dp 16 --tp 4 --pp 4")

echo "app,ranks,system,wall_cycles,exposed_comm"
for CFG in "${CFGS[@]}"; do
  set -- $CFG; APP=$1; KIND=$2; RANKS=$3; RACKS=$4; XPUS=$5; shift 5
  WL=/tmp/stg_${APP}_${RANKS}
  [ -f $WL/$KIND.json ] || examples/loom/gen_stg_workloads.sh $KIND $WL "$@" >/dev/null 2>&1
  python3 examples/loom/gen_network_config.py --mode loom --racks $RACKS --xpus-per-rack $XPUS -o /tmp/net_loom.yml
  python3 examples/loom/gen_network_config.py --mode baseline --racks $RACKS --xpus-per-rack $XPUS -o /tmp/net_base.yml
  for SYS in "loom loom_roofline${SUFFIX}.json /tmp/net_loom.yml" \
             "b1_gpu_rdma baseline_gpu_rdma_roofline${SUFFIX}.json /tmp/net_base.yml"; do
    set -- $SYS
    OUT=$($BIN --workload-configuration=$WL/$KIND \
      --system-configuration=$ROOT/examples/loom/system/$2 \
      --network-configuration=$3 \
      --remote-memory-configuration=$RM \
      --comm-group-configuration=$WL/$KIND.json 2>&1 | grep -m1 "sys\[0\] finished")
    W=$(echo "$OUT" | grep -o "finished, [0-9]*" | grep -o "[0-9]*")
    E=$(echo "$OUT" | grep -o "communication [0-9]*" | grep -o "[0-9]*")
    echo "$APP,$RANKS,$1,$W,$E"
  done
done
