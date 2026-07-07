#!/bin/bash
# Fetch STG/STAGE (astra-sim's symbolic workload generator) at a pinned commit.
# STG generates Chakra ETs for transformer models incl. MoE (--model_type moe,
# --ep/--experts/--kexperts) with DP/TP/PP/SP/EP parallelism.
set -e
DEST="$(dirname "$0")/../../extern/graph_frontend/stage"
PIN=71ceb42394bde658f9d4fd646168e42310c6a24d
pip3 install -q tqdm 2>/dev/null || true
[ -d "$DEST" ] || git clone https://github.com/astra-sim/symbolic_tensor_graph "$DEST"
git -C "$DEST" checkout -q $PIN
echo "STG ready at $DEST (pinned $PIN)"
