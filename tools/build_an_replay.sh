#!/usr/bin/env bash
# Build tools/an_replay (LoomNet analytical model, header-only) -> e8-astrasim/bin/an_replay
set -euo pipefail
E=/scratch/harshanavkis/loom-proj/e8-astrasim
mkdir -p $E/bin
nix-shell $E/shell.nix --run "g++ -O2 -std=c++17 -Wall -I/scratch/harshanavkis/loom-proj/astra-sim-fresh/astra-sim/network_frontend/analytical/include/loom -o $E/bin/an_replay $E/tools/an_replay.cc"
nix-shell $E/shell.nix --run "g++ -O2 -std=c++17 -Wall -I/scratch/harshanavkis/loom-proj/astra-sim-fresh/astra-sim/network_frontend/analytical/include/loom -o $E/bin/an_loomreplay $E/tools/an_loomreplay.cc"
ls -la $E/bin/an_replay $E/bin/an_loomreplay
