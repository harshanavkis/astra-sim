#!/usr/bin/env bash
# Every 2 min: copy amy/rose run logs into clara's runs_an (the collector picks the newest log per run) and their runner
# output to e8_an/sweep/remote_<host>.out (+ rose's MoE queue: remote_rose_moe.out); e8_an/sweep/remote_<host>.state = session alive / gone, MemAvailable.
E=/scratch/harshanavkis/loom-proj/e8-astrasim
while true; do
    fin=0
    for h in amy rose; do
        H=$h.dos.cit.tum.de
        rsync -a --include='an_sw_*.log' --exclude='*' $H:$E/runs_an/ $E/runs_an/ 2>/dev/null
        rsync -a $H:$E/remote.out $E/e8_an/sweep/remote_$h.out 2>/dev/null
        [ $h = rose ] && rsync -a $H:$E/remote_moe.out $E/e8_an/sweep/remote_rose_moe.out 2>/dev/null
        st=$(ssh -o BatchMode=yes -o ConnectTimeout=10 $H "tmux has-session -t swremote 2>/dev/null && echo alive || echo gone; awk '/MemAvailable/{print int(\$2/1048576)}' /proc/meminfo; pgrep -c -x AstraSim_Analyt" 2>/dev/null | tr '\n' ' ')
        echo "$(date -u +%H:%M) ${st:-ssh-failed}" > $E/e8_an/sweep/remote_$h.state
        grep -q RUN_DONE $E/e8_an/sweep/remote_$h.out 2>/dev/null && fin=$((fin + 1))
    done
    grep -q RUN_DONE $E/e8_an/sweep/remote_rose_moe.out 2>/dev/null && fin=$((fin + 1))
    [ $fin = 3 ] && { echo "SYNC_DONE $(date -u +%H:%M)"; exit 0; }
    sleep 120
done
