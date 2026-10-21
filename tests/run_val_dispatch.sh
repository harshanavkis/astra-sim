#!/usr/bin/env bash
# NIC model vs the Section 2 dispatch/combine runs on steve (MTU 4096): each traced run (posts,
# doorbells, CTA ends, signal times as measured) replayed on LoomReplay; tools/val_dispatch.py
# compares arrivals, drain, signal seen and reap times. Traces: steve run_bd_trace.sh ->
# ~/loom-experiments/gpu-posted/bd_trace; tools/bd_trace_to_replay.py -> <dir>/runs.
#   tests/run_val_dispatch.sh <dir> [config]      (config default: e8/cfg/steve_nic/base.txt)
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim
BIN=/scratch/harshanavkis/loom-proj/astra-sim-fresh/extern/network_backend/ns-3/build/scratch/ns3.42-LoomReplay-default
/scratch/harshanavkis/loom-proj/e8-astrasim/tools/check_ns3_build.sh "$BIN" || exit 1   # refuse a stale build (2026-10-20)
D=$(readlink -f $1); CFG=$(readlink -f ${2:-$E/e8/cfg/steve_nic/base.txt})
O=$D/model_$(basename $CFG .txt); mkdir -p $O
ls $D/runs/*.run | xargs -P $(nproc) -I{} sh -c 'f={}; b=$(basename $f .run); '"$BIN $CFG"' $f '"$O"'/$b.out > '"$O"'/$b.log 2>&1 || echo "FAIL $b"'
python3 -I $E/tools/val_dispatch.py $D $O
