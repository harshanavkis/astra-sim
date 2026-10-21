#!/usr/bin/env bash
# Build the LoomNet analytical model: AstraSim_Analytical_Loom (astra-sim-fresh analytical build dir) + bin/an_replay
set -euo pipefail
cd /scratch/harshanavkis/loom-proj/astra-sim-fresh/build/astra_analytical/build
nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "cmake .. -DBUILDTARGET=all > /dev/null && cmake --build . --target AstraSim_Analytical_Loom -j 16" 2>&1 | grep -E 'error|Built target AstraSim_Analytical_Loom'
/scratch/harshanavkis/loom-proj/e8-astrasim/tools/build_an_replay.sh
