#!/usr/bin/env bash
# Every 2 min: copy amy/rose decode logs into clara's runs_an and their runner output to e8_an/decode/remote_<host>.out;
# remote_<host>.state = session alive / gone, MemAvailable, simulations.
E=/scratch/harshanavkis/loom-proj/e8-astrasim
while true; do
    fin=0
    for h in amy rose; do
        H=$h.dos.cit.tum.de
        rsync -a --include='an_dec_*.log' --exclude='*' $H:$E/runs_an/ $E/runs_an/ 2>/dev/null
        rsync -a $H:$E/remote_decode.out $E/e8_an/decode/remote_$h.out 2>/dev/null
        [ $h = rose ] && rsync -a $H:$E/remote_decode2.out $E/e8_an/decode/remote_rose2.out 2>/dev/null
        st=$(ssh -o BatchMode=yes -o ConnectTimeout=10 $H "tmux has-session -t swdecode 2>/dev/null && echo alive || echo gone; awk '/MemAvailable/{print int(\$2/1048576)}' /proc/meminfo; pgrep -c -x AstraSim_Analyt" 2>/dev/null | tr '\n' ' ')
        echo "$(date -u +%H:%M) ${st:-ssh-failed}" > $E/e8_an/decode/remote_$h.state
    done
    grep -q RUN_DONE $E/e8_an/decode/remote_amy.out 2>/dev/null && fin=$((fin + 1))
    grep -q RUN_DONE $E/e8_an/decode/remote_rose2.out 2>/dev/null && fin=$((fin + 1))
    [ $fin = 2 ] && { echo "SYNC_DONE $(date -u +%H:%M)"; exit 0; }
    sleep 120
done
