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
# Presets use PUBLISHED model dimensions (workload realism without GPUs):
#   moe   = Mixtral 8x7B: dmodel 4096, dff 14336, 32 heads / 8 KV heads,
#           8 experts top-2 (Jiang et al., arXiv:2401.04088)
#   dense = GPT-3 175B: dmodel 12288, dff 49152, 96 heads
#           (Brown et al., NeurIPS'20)
#   dsv3  = DeepSeek-V3: dmodel 7168, 256 routed experts top-8, per-expert
#           intermediate 2048, 128 heads, seq 4096 (DeepSeek-AI,
#           arXiv:2412.19437). Modernises the moe preset, whose Mixtral
#           8-expert/top-2 shape is dated: 32x more experts and 4x the
#           top-k means far more, far smaller all-to-all messages - the
#           regime where the divide costs most. NOTE MLA is NOT modelled
#           (STG has no latent-attention path); kvhead=head approximates
#           MHA, which OVERSTATES attention KV traffic vs real DSv3.
# num_stacks/batch/seq are workload-scale knobs (layers are homogeneous, so
# per-iteration time extrapolates linearly in stacks); override as needed.
case $KIND in
  moe)   set -- --model_type moe --dp 2 --tp 2 --pp 1 --ep 4 \
             --dmodel 4096 --dff 14336 --head 32 --kvhead 8 \
             --experts 8 --kexperts 2 --num_stacks 4 --batch 8 --seq 2048 "$@" ;;
  dense) set -- --model_type dense --dp 4 --tp 4 --pp 2 \
             --dmodel 12288 --dff 49152 --head 96 --kvhead 96 \
             --num_stacks 4 --batch 8 --seq 2048 "$@" ;;
  dsv3)  set -- --model_type moe --dp 2 --tp 4 --pp 1 --ep 8 \
             --dmodel 7168 --dff 2048 --head 128 --kvhead 128 \
             --experts 256 --kexperts 8 --num_stacks 4 --batch 8 --seq 4096 "$@" ;;
  *) echo "usage: $0 moe|dense|dsv3 <outdir> [stg args]"; exit 1 ;;
esac
(cd "$STG" && python3 main.py --output_dir "$OUT" --output_name "$KIND.%d.et" "$@")
echo "workload: $OUT/$KIND   comm groups: $OUT/$KIND.json"
