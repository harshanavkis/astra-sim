#!/usr/bin/env bash
# Refuses an ns-3 binary that was not built from the current model sources (2026-10-20: a pilot ran astra-sim-opt's
# 10-10 binary, which lacks the 10-11 push-path fix fc5126a64, and Loom came out 0.5-3.6% slower).
# Reference = astra-sim-fresh (the model's source of truth). Checks:
#  - the binary's tree has the SAME model sources as the reference (src/point-to-point, scratch, ASTRA-sim frontend);
#  - the point-to-point library the binary loads is newer than every src/point-to-point source (the model);
#  - the binary is newer than what is compiled into it (scratch/*, the ASTRA-sim frontend; for a binary outside an
#    ASTRA-sim tree, e.g. val_model's proto-replay: the scratch headers and its own ../src).
#   check_ns3_build.sh <binary>      -> prints "ns3 build OK ..." or "ns3 build STALE: ..." and exits 1
set -uo pipefail
B=$(readlink -f "$1")
REF=/scratch/harshanavkis/loom-proj/astra-sim-fresh; RN=$REF/extern/network_backend/ns-3
[ -x "$B" ] || { echo "ns3 build STALE: $B missing or not executable"; exit 1; }
lib=$(ldd "$B" 2>/dev/null | awk '/point-to-point/ {print $3}')
if [[ "$B" == */extern/network_backend/ns-3/* ]]; then
    T=${B%%/extern/network_backend/ns-3/*}; own=("$T/astra-sim")
elif [ -n "$lib" ]; then
    T=${lib%%/extern/network_backend/ns-3/*}; own=("$(dirname "$(dirname "$B")")/src")
else
    echo "ns3 build STALE: $B: not in an ASTRA-sim tree and no point-to-point library"; exit 1
fi
N=$T/extern/network_backend/ns-3
newest() { find "$@" \( -name '*.cc' -o -name '*.h' -o -name '*.hh' -o -name '*.cpp' \) -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1; }
bad=""
for d in src/point-to-point/model src/point-to-point/helper scratch; do
    diff -rq --exclude='output' --exclude='*.txt' "$RN/$d" "$N/$d" >/dev/null 2>&1 || bad="$bad $d differs from $REF;"
done
[ "$T" = "$REF" ] || diff -rq "$REF/astra-sim" "$T/astra-sim" >/dev/null 2>&1 || bad="$bad astra-sim frontend differs from $REF;"
m=$(newest "$N/src/point-to-point"); mt=${m%%.*}
c=$(newest "$N/scratch" "${own[@]}"); ct=${c%%.*}
if [ -n "$lib" ]; then
    [ "$(stat -c %Y "$lib")" -ge "$mt" ] || bad="$bad library $lib older than ${m#* };"
    [ "$(stat -c %Y "$B")" -ge "$ct" ] || bad="$bad binary older than ${c#* };"
else
    [ "$(stat -c %Y "$B")" -ge "$mt" ] && [ "$(stat -c %Y "$B")" -ge "$ct" ] || bad="$bad static binary older than its sources;"
fi
if [ -n "$bad" ]; then echo "ns3 build STALE: $B:$bad"; exit 1; fi
echo "ns3 build OK: $B (md5 $(md5sum < "$B" | cut -c1-8), p2p lib ${lib:-static}, model sources = $REF ns-3 $(git -C "$RN" rev-parse --short HEAD)$(git -C "$RN" diff --quiet || echo '+uncommitted'))"
