#!/usr/bin/env bash
# The ASTRA-sim frontend on the NIC model (HOST_IF_MODE nic: one QP per GPU pair, puts + signal,
# zero GPU cost) against LoomReplay doing the same puts: rank 0 sends one message of S bytes to
# rank 1 in 7168 B puts (steve, e8/cfg/steve_nic). Sender release = rank 0's finish (RDMA: the
# signal's CQE seen; Loom: its stores out of the GPU), receiver = rank 1's finish (signal seen).
#   tests/run_nic_frontend.sh      -> tests/nic_frontend_<time>.tsv
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
export NS3_TIMEOUT=${NS3_TIMEOUT:-1800}
E=/scratch/harshanavkis/loom-proj/e8-astrasim; A=/scratch/harshanavkis/loom-proj/astra-sim-fresh
BIN=$A/extern/network_backend/ns-3/build/scratch/ns3.42-LoomReplay-default
/scratch/harshanavkis/loom-proj/e8-astrasim/tools/check_ns3_build.sh "$BIN" || exit 1   # refuse a stale build (2026-10-20)
SYS=$A/examples/system/native_collectives/HGX-H100-validated.json; TOPO=$E/e8/cfg/logical_2.json
O=$E/tests/out_nic_frontend_$(date -u +%Y%m%d_%H%M%S); mkdir -p $O
TSV=$E/tests/nic_frontend_$(date -u +%Y%m%d_%H%M%S).tsv
fin() { grep -o "sys\[$2\] finished, [0-9]*" "$1" < /dev/null | awk '{printf "%.2f", $3 / 1000}'; }
printf "system\tbytes\tsender_astra_us\tsender_replay_us\treceiver_astra_us\treceiver_replay_us\n" | tee $TSV
for sys in rdma loom; do
  cfg=$O/$sys.cfg
  if [ $sys = rdma ]; then cp $E/e8/cfg/steve_nic/base.txt $cfg; else cp $E/e8/cfg/steve_nic/push_1000mhz.txt $cfg; fi
  echo "MSG_SPLIT_BYTES 7168" >> $cfg
  for S in 8 7168 43008 645120 4895744; do
    python3 -I $E/tools/gen_p2p.py $O/p$S $S > /dev/null
    R=$($E/run_ns3.sh nicfe_${sys}_$S $O/p$S/p2p $SYS $cfg $TOPO || true); log=${R%%$'\n'*}
    run=$O/${sys}_$S.run
    { printf "path ordered\nnodes 0 1\nnqp 1\nsigkind write\nreap %d\nsignal 0 0\n" $([ $sys = rdma ] && echo 1 || echo 0)
      i=0; for ((off = 0; off < S; off += 7168)); do b=$((S - off < 7168 ? S - off : 7168)); echo "msg $i 0 0 $b 1"; i=$((i + 1)); done; } > $run
    $BIN $cfg $run $O/${sys}_$S.out > $O/${sys}_$S.log 2>&1
    read -r _ _ _ _ _ seen reaped out < <(grep '^sum' $O/${sys}_$S.out)
    snd=$([ $sys = rdma ] && echo $reaped || echo $out)
    printf "%s\t%s\t%s\t%s\t%s\t%s\n" $sys $S "$(fin $log 0)" "$(awk -v x=$snd 'BEGIN{printf "%.2f", x / 1000}')" \
      "$(fin $log 1)" "$(awk -v x=$seen 'BEGIN{printf "%.2f", x / 1000}')" | tee -a $TSV
  done
done
echo "tsv: $TSV"
