#!/bin/bash
# Generate realistic Chakra workloads via STG (run fetch_stg.sh first).
# Usage: gen_stg_workloads.sh moe|dense <outdir> [extra STG args...]
# Presets are DeepSeek/Mixtral-shaped for moe, GPT-3-shaped for dense; rank
# count = dp*tp*pp*ep. Pass the emitted <outdir>/<name>.json to the simulator
# as --comm-group-configuration, and use a roofline-enabled system config
# (system/loom_roofline.json etc.): STG compute nodes carry num_ops, not
# durations.
set -e
KIND=$1; OUT=$2; shift 2
STG="$(dirname "$0")/../../extern/graph_frontend/stage"
case $KIND in
  moe)   set -- --model_type moe --dp 2 --tp 2 --pp 1 --ep 4 \
             --experts 8 --kexperts 2 --num_stacks 4 --batch 16 --seq 2048 "$@" ;;
  dense) set -- --model_type dense --dp 4 --tp 4 --pp 2 \
             --num_stacks 8 --batch 32 --seq 2048 "$@" ;;
  *) echo "usage: $0 moe|dense <outdir> [stg args]"; exit 1 ;;
esac
(cd "$STG" && python3 main.py --output_dir "$OUT" --output_name "$KIND.%d.et" "$@")
echo "workload: $OUT/$KIND   comm groups: $OUT/$KIND.json"
