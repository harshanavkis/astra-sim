#!/usr/bin/env bash
# Run ns-3 jobs in parallel. Jobs file: one line per run,
#   <name> <workload prefix> <system.json> <ns3 config> <logical topology.json> [comm groups]
# Logs: runs/ns3_<name>_<time>.log (run_ns3.sh); tools/collect_jobs.py reads them.
#   tools/run_jobs.sh <jobs file> [parallel runs, default 24]   (run it in tmux)
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
export NS3_TIMEOUT=${NS3_TIMEOUT:-21600}
E=/scratch/harshanavkis/loom-proj/e8-astrasim
grep -v '^#' "$1" | xargs -P "${2:-24}" -L 1 bash -c "$E/run_ns3.sh \"\$@\" > /dev/null 2>&1 || true" _
echo "done: $1"
