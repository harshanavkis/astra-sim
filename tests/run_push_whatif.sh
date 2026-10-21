#!/usr/bin/env bash
# Loom push what-if on the Section 2 runs: the local runs' GPU side (TMA store issue times, signal
# time; Loom uses the scale-up stores) replayed through push configs (e8/cfg/steve_nic/push_*mhz.txt:
# posted writes into Loom, Loom cycles, the same wire and receive-side writes as the validated NIC
# model), next to the measured local and RDMA runs and the NIC model.
#   tests/run_push_whatif.sh <val_dispatch dir>      (after tests/run_val_dispatch.sh on that dir)
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim
BIN=/scratch/harshanavkis/loom-proj/astra-sim-fresh/extern/network_backend/ns-3/build/scratch/ns3.42-LoomReplay-default
/scratch/harshanavkis/loom-proj/e8-astrasim/tools/check_ns3_build.sh "$BIN" || exit 1   # refuse a stale build (2026-10-20)
D=$(readlink -f $1)
for c in 250 1000; do
  O=$D/model_push_${c}mhz; mkdir -p $O
  ls $D/runs/*_local_*.run | xargs -P $(nproc) -I{} sh -c 'f={}; b=$(basename $f .run); '"$BIN $E/e8/cfg/steve_nic/push_${c}mhz.txt"' $f '"$O"'/$b.out > '"$O"'/$b.log 2>&1 || echo "FAIL $b"'
done
python3 -I $E/tools/push_whatif.py $D
