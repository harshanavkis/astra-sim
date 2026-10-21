#!/usr/bin/env bash
# Build ASTRA-sim's analytical backend (congestion aware + unaware) in the
# fresh clone on clara, with what NixOS needs:
#   - no /bin/bash: the repo's scripts are run with `bash`
#   - gcc 15: the bundled cxxopts.hpp lacks <cstdint>; stdint.h is force-
#     included through the nix compiler wrapper (CXXFLAGS is overridden by
#     the repo's CMakeLists)
#   - protobuf 29 + abseil from nix, found through protobuf's own CMake
#     package (PROTOBUF_FROM_SOURCE=True, the repo's Docker setting)
# yaml-cpp is downloaded by CMake at configure time (network needed).
#
#   /scratch/harshanavkis/loom-proj/e8-astrasim/build.sh [--clean]
set -euo pipefail
REPO=${ASTRA:-/scratch/harshanavkis/loom-proj/astra-sim-fresh}
CLEAN=""; [ "${1:-}" = --clean ] && CLEAN="bash ./build/astra_analytical/build.sh -l &&"
mkdir -p "$REPO/logs"
cd "$REPO"
nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run \
    "$CLEAN bash ./build/astra_analytical/build.sh" \
    2>&1 | tee "$REPO/logs/build_analytical.log" | grep -E 'error|Error|Built target|\[100%\]' | tail -5
ls -la "$REPO/build/astra_analytical/build/bin/"
