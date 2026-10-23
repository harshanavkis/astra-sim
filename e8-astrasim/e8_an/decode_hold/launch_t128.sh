#!/usr/bin/env bash
# EP256 128-token decode with HOLD=1 (owner 2026-10-21: the general path, the sender waits for its completions, everywhere):
# copy the trace to amy (rdma) and rose (loom) at the same path, start remote_jobs.sh in tmux swhold there.
E=/scratch/harshanavkis/loom-proj/e8-astrasim; T=$E/traces/decode_hold; D=$E/e8_an/decode_hold; n=ep256_t128_l4096_mb1
for hv in amy:rdma rose:loom; do
    h=${hv%%:*}; v=${hv##*:}; H=$h.dos.cit.tum.de
    rsync -a $T/$n $H:$T/ || { echo "RSYNC FAILED $h"; continue; }
    ssh -o BatchMode=yes $H "mkdir -p $D && echo 'dechold_${n}__$v $T/$n/decode $E/e8/cfg/system_decode.json $E/e8_an/decode/cfg/${v}_ep256.txt' > $D/jobs_$h.txt && tmux new-session -d -s swhold 'ASTRA_CONCURRENT_SENDS=1 bash $E/remote_jobs.sh $D/jobs_$h.txt 1 > $D/remote_$h.out 2>&1; echo RUN_DONE >> $D/remote_$h.out'" \
        && echo "STARTED $h $v $(date -u +%H:%M)" || echo "START FAILED $h"
done
