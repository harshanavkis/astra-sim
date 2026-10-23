#!/usr/bin/env bash
# The four EP256 64 / 128-token decode points with the send loops on rose (2 TB; owner 2026-10-22: use rose). Memory =
# ASTRA-sim's in-memory traces, ~46x the .et bytes (t128 6.1 GB -> ~280 GB, t64 4.9 GB -> ~225 GB), filled while the
# traces load (~13 min), then flat. A start only with >= 350 GB available. Binary = the decode binary d069a629 (rose's
# build, same md5); rose's nix store lacks protobuf/abseil -> bin/declp-libs. Log: remote_declp.out, rss: remote_rss.tsv.
set -uo pipefail
E=/scratch/harshanavkis/loom-proj/e8-astrasim; T=$E/traces/decode_loop; D=$E/e8_an/decode_loop
export E8_SHELL=1 LD_LIBRARY_PATH=$E/bin/declp-libs ASTRA_CONCURRENT_SENDS=1
export AN_BIN=/scratch/harshanavkis/loom-proj/astra-sim-fresh/build/astra_analytical/build/bin/AstraSim_Analytical_Loom
[ "$(md5sum < $AN_BIN | cut -c1-8)" = d069a629 ] || { echo "WRONG BINARY"; exit 1; }
for t in 128 64; do for v in rdma loom; do
    echo "declp_ep256_t${t}_l4096_mb1__$v $T/ep256_t${t}_l4096_mb1_$v/decode $E/e8/cfg/system_decode.json $D/cfg/${v}_ep256_t$t.txt"
done; done > $D/jobs_rose.txt
( while :; do echo "$(date -u +%H:%M) avail_GB $(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo) rss_GB" \
      "$(ps -C AstraSim_Analytical_Loom -o rss= | awk '{printf "%.0f ", $1/1048576}')" >> $E/remote_rss.tsv; sleep 60; done ) &
gate() { while [ "$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)" -lt 350 ]; do sleep 30; done; }
export -f gate
xargs -P 4 -L 1 bash -c 'gate; sleep 60; echo "START $1 $(date -u +%H:%M)"; '"$E"'/run_an.sh "$@" > /dev/null 2>&1 && echo "OK $1 $(date -u +%H:%M)" || echo "FAILED $1 $(date -u +%H:%M)"' _ < $D/jobs_rose.txt
echo "RUN_DONE $(date -u +%H:%M)"
kill %1
