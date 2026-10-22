#!/usr/bin/env bash
# Generic model (no hold, no flush; Loom's config never had flush): EP256 128-token Loom decode, the one generic point
# missing (its run was stopped at 22:49). Starts on clara after tmux decflush ends and >= 300 GB are free.
set -uo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; n=ep256_t128_l4096_mb1
while tmux has-session -t decflush 2>/dev/null; do sleep 60; done
while [ "$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)" -lt 300 ]; do sleep 60; done
echo "START $(date -u +%H:%M)"
ASTRA_CONCURRENT_SENDS=1 $E/run_an.sh dec_${n}__loom $E/traces/decode/$n/decode $E/e8/cfg/system_decode.json $E/e8_an/decode/cfg/loom_ep256.txt > /dev/null 2>&1 || echo "FAILED dec_${n}__loom"
echo "RUN_DONE $(date -u +%H:%M)"
