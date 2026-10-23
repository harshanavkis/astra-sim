#!/usr/bin/env bash
# Run ASTRA-sim on the ns-3 backend (fresh clone on clara), one run, log in
# /scratch/harshanavkis/loom-proj/e8-astrasim/runs/ns3_<name>_<time>.log. The binary runs from
# ns-3's build/scratch (the config's relative paths start there).
#
#   run_ns3.sh <name> <workload prefix> <system.json> <ns3 config.txt> <logical topology.json> [comm group json]
#   run_ns3.sh example    # the repo's Ring_allgather_16npus example
#   NS3_TIMEOUT=<seconds> kills a run that takes longer (tests use it)
set -euo pipefail
# every run goes through the E8 nix shell (shell.nix: ns-3 runtime libraries)
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
REPO=${ASTRA:-/scratch/harshanavkis/loom-proj/astra-sim-fresh}
EX=$REPO/examples; N3=$REPO/extern/network_backend/ns-3
BIN=${NS3_BIN:-$N3/build/scratch/ns3.42-AstraSimNetwork-default}
if [ "${1:-}" = example ]; then
    set -- example $EX/workload/microbenchmarks/all_gather/16npus_1MB/all_gather $EX/system/native_collectives/Ring_4chunks.json \
        $N3/scratch/config/config_clos.txt $EX/network/ns3/sample_16nodes_1D.json
fi
[ $# -ge 5 ] || { sed -n '2,8p' "$0"; exit 2; }
# refuse a binary not built from the current model sources (tools/check_ns3_build.sh; 2026-10-20 stale-binary pilot)
CHK=$(/scratch/harshanavkis/loom-proj/e8-astrasim/tools/check_ns3_build.sh "$BIN") || { echo "$CHK" >&2; exit 1; }
NAME=$1 WL=$2 SYS=$3 NET=$4 TOPO=$5 CG=${6:-empty}
LOG=/scratch/harshanavkis/loom-proj/e8-astrasim/runs/ns3_${NAME}_$(date -u +%Y%m%d_%H%M%S).log
mkdir -p "$(dirname "$LOG")" "$N3/scratch/output"
# per-run copy of the ns-3 config: its output files go to runs/ns3_<name>_<time>/
RUN=${LOG%.log}; mkdir -p "$RUN"
sed -E "s#^((TRACE_OUTPUT|FCT_OUTPUT|PFC_OUTPUT)_FILE|QLEN_MON_FILE) .*/([^/]+)\$#\1 $RUN/\3#" "$NET" > "$RUN/net.txt"
NET=$RUN/net.txt
cd "$N3/build/scratch"
{ echo "$CHK"; echo "run_ns3: $NAME bin $(md5sum < "$BIN" | cut -c1-8) wl $WL sys $SYS net $NET topo $TOPO cg $CG"
  ${NS3_TIMEOUT:+timeout $NS3_TIMEOUT} /usr/bin/env time -v "$BIN" --workload-configuration="$WL" --system-configuration="$SYS" --network-configuration="$NET" \
      --remote-memory-configuration="$EX/remote_memory/analytical/no_memory_expansion.json" \
      --logical-topology-configuration="$TOPO" --comm-group-configuration="$CG"; } > "$LOG" 2>&1
echo "$LOG"; grep -E "finished|Elapsed|Maximum resident|error|Error" "$LOG" | tail -6
