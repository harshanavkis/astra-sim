#!/usr/bin/env bash
# Builds the ns-3 backend binaries: LoomReplay (NIC-model replay of measured dispatch/combine runs)
# and AstraSimNetwork. Usage: bash build_replay.sh   (log: astra-sim-fresh/logs/build_replay.log)
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
REPO=/scratch/harshanavkis/loom-proj/astra-sim-fresh
cd $REPO/extern/network_backend/ns-3
./ns3 build LoomReplay AstraSimNetwork -j $(nproc) 2>&1 | tee $REPO/logs/build_replay.log | grep -E 'error|Error|warning: unused|Finished executing|Built target (LoomReplay|AstraSimNetwork)' | tail -30
ls -la build/scratch/ | grep -E 'LoomReplay|AstraSim'
