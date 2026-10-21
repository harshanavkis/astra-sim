#!/usr/bin/env bash
# Build ASTRA-sim's ns-3 backend (AstraSimNetwork) in the fresh clone on clara,
# inside the E8 nix shell (shell.nix: -include stdint.h, protobuf 29, MPI,
# python3 for ns-3's ./ns3 wrapper). Long: run in tmux.
#
#   /scratch/harshanavkis/loom-proj/e8-astrasim/build_ns3.sh
set -euo pipefail
REPO=${ASTRA:-/scratch/harshanavkis/loom-proj/astra-sim-fresh}
mkdir -p "$REPO/logs"
cd "$REPO"
nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "bash ./build/astra_ns3/build.sh" \
    2>&1 | tee "$REPO/logs/build_ns3.log" | grep -E 'error|Error|Built target AstraSimNetwork|Finished executing' | tail -5
ls -la "$REPO/extern/network_backend/ns-3/build/scratch/" 2>/dev/null | grep -i astra
