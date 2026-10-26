#!/usr/bin/env bash
# Fig 10a decode, the three large EP256 RDMA points with no WQE fetch limit (owner 2026-10-26: "do all simulations that are
# affected"; "you can do them on rose/amy"): too big for clara next to two FPGA builds (t128 ~280 GB, t64 ~225 GB). Binary
# 0b714281 (clara's current build, copied); amy's nix store lacks protobuf/abseil -> bin/declp-libs-0b714281. A start only
# with >= 350 GB available. Logs runs_an/an_declp_*, synced back to clara by hand. Output: run_amy_nolimit.out.
set -uo pipefail
E=/scratch/harshanavkis/loom-proj/e8-astrasim; T=$E/traces/decode_loop; D=$E/e8_an/decode_loop
export E8_SHELL=1 LD_LIBRARY_PATH=$E/bin/declp-libs-0b714281 ASTRA_CONCURRENT_SENDS=1
export AN_BIN=/scratch/harshanavkis/loom-proj/astra-sim-fresh/build/astra_analytical/build/bin/AstraSim_Analytical_Loom
[ "$(md5sum < $AN_BIN | cut -c1-8)" = 0b714281 ] || { echo "WRONG BINARY"; exit 1; }
for t in 128 64 16; do
    echo "declp_ep256_t${t}_l4096_mb1__rdma $T/ep256_t${t}_l4096_mb1_rdma/decode $E/e8/cfg/system_decode.json $D/cfg/rdma_ep256_t$t.txt"
done > $D/jobs_amy_nolimit.txt
gate() { while [ "$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)" -lt 350 ]; do sleep 30; done; }
export -f gate
echo "RUN_START $(date -u +%H:%M)"
xargs -P 3 -L 1 bash -c 'gate; sleep 60; echo "start $1 $(date -u +%H:%M)"; '"$E"'/run_an.sh "$@" > /dev/null 2>&1 && echo "done $1 $(date -u +%H:%M)" || echo "FAILED $1 $(date -u +%H:%M)"' _ < $D/jobs_amy_nolimit.txt
echo "RUN_DONE $(date -u +%H:%M)"
