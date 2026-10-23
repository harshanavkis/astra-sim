#!/usr/bin/env bash
# Every 2 min: copy amy/rose an_declp_* logs into clara's runs_an; remote_<host>.state = session, MemAvailable GB, sims.
E=/scratch/harshanavkis/loom-proj/e8-astrasim
while true; do
    for h in amy rose; do
        H=$h.dos.cit.tum.de
        rsync -a --include='an_declp_*.log' --exclude='*' $H:$E/runs_an/ $E/runs_an/ 2>/dev/null
        rsync -a $H:$E/remote_declp.out $E/e8_an/decode_loop/remote_$h.out 2>/dev/null
        st=$(ssh -o BatchMode=yes -o ConnectTimeout=10 $H "tmux has-session -t declp 2>/dev/null && echo alive || echo gone; awk '/MemAvailable/{print int(\$2/1048576)}' /proc/meminfo; pgrep -c -x AstraSim_Analyt" 2>/dev/null | tr '\n' ' ')
        echo "$(date -u +%H:%M) ${st:-ssh-failed}" > $E/e8_an/decode_loop/remote_$h.state
    done
    sleep 120
done
