#!/usr/bin/env bash
# Run analytical-model jobs in parallel (jobs file format as tools/run_jobs.sh: <name> <workload prefix> <system.json>
# <network config> <logical topology.json, ignored> [comm groups]). Logs: runs_an/an_<name>_<time>.log.
#   tools/run_an_jobs.sh <jobs file> [parallel runs, default 32]
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim
grep -v '^#' "$1" | awk '{print $1, $2, $3, $4 ($6 != "" ? " " $6 : "")}' | xargs -P "${2:-32}" -L 1 bash -c "$E/run_an.sh \"\$@\" > /dev/null 2>&1 || echo \"FAILED \$1\"" _
echo "done: $1"
