#!/usr/bin/env bash
# EP256 128-token issue-time decode runs on amy (rdma) and rose (loom): wait for the trace (.done), copy it to the host's
# mirror (same path), start remote_jobs.sh in tmux swissue there. Rose: stop its old-model t128 run first (superseded).
E=/scratch/harshanavkis/loom-proj/e8-astrasim; T=$E/traces/decode_issue; D=$E/e8_an/decode_issue
for hv in amy:rdma rose:loom; do
    h=${hv%%:*}; v=${hv##*:}; H=$h.dos.cit.tum.de; n=ep256_t128_l4096_mb1
    until [ -f $T/${n}_$v/.done ]; do sleep 30; done
    rsync -a $T/${n}_$v $H:$T/ || { echo "RSYNC FAILED $h"; continue; }
    [ $h = rose ] && ssh -o BatchMode=yes $H 'tmux kill-session -t swdecode2 2>/dev/null; tmux kill-session -t swdecode 2>/dev/null; sleep 3'
    ssh -o BatchMode=yes $H "mkdir -p $D && echo 'decissue_${n}__$v $T/${n}_$v/decode $E/e8/cfg/system_decode.json $E/e8_an/decode/cfg/${v}_ep256.txt' > $D/jobs_$h.txt && tmux new-session -d -s swissue 'ASTRA_CONCURRENT_SENDS=1 bash $E/remote_jobs.sh $D/jobs_$h.txt 1 > $D/remote_$h.out 2>&1; echo RUN_DONE >> $D/remote_$h.out'" \
        && echo "STARTED $h $v $(date -u +%H:%M)" || echo "START FAILED $h"
done
