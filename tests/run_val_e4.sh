#!/usr/bin/env bash
# Loom side of the NIC model vs the E4 prototype (amy V80 -> both U280 Loom switches -> rose V80 HBM,
# ce_dispatch, ~/loom-experiments/e4/<run>): every E4 point replayed on LoomReplay with
# e8/cfg/testbed_e4/push.txt. One fitted parameter: the link delay, so that the 0-token flag's one-way
# time equals the measured one (0-token round trip / 2); everything else comes from E1 and the RTL.
#   tests/run_val_e4.sh [e4 run dir]     -> val_e4/<e4 run name>/{runs,model,compare.tsv}
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim
BIN=/scratch/harshanavkis/loom-proj/astra-sim-fresh/extern/network_backend/ns-3/build/scratch/ns3.42-LoomReplay-default
/scratch/harshanavkis/loom-proj/e8-astrasim/tools/check_ns3_build.sh "$BIN" || exit 1   # refuse a stale build (2026-10-20)
E4=$(readlink -f ${1:-$HOME/loom-experiments/e4/20261010_1144_dispatch_v80})
O=$E/val_e4/$(basename $E4); mkdir -p $O/model
CFG=$E/e8/cfg/testbed_e4/push.txt; TOPO=$E/e8/cfg/testbed_e4/topo.txt
python3 -I $E/tools/val_e4.py runs $E4 $O
topo() { printf "3 1 2\n2\n0 2 100Gbps %sms 0\n1 2 100Gbps %sms 0\n" $1 $1 > $TOPO; }
seen() { $BIN $CFG $O/runs/dispatch_t0.run $O/model/dispatch_t0.out > $O/model/dispatch_t0.log 2>&1; awk '/^sum/{print $6}' $O/model/dispatch_t0.out; }
# fit: one-way flag time is linear in the two link delays
topo 0; s0=$(seen)
want=$(awk '/^dispatch 0 tokens/{for(i=1;i<=NF;i++) if($i=="back"){print $(i+1)*1000/2; exit}}' $E4/dispatch_t0.client.log)
d=$(awk -v w=$want -v s=$s0 'BEGIN{printf "%.6f", (w - s) / 2 / 1e6}')   # ns -> ms
topo $d; s1=$(seen)
echo "fit: flag one-way measured $want ns, model with 0 delay $s0 ns -> link delay $d ms each -> $s1 ns"
for r in $O/runs/*.run; do b=$(basename $r .run); [ $b = dispatch_t0 ] && continue
  $BIN $CFG $r $O/model/$b.out > $O/model/$b.log 2>&1 || echo "FAIL $b"; done
python3 -I $E/tools/val_e4.py compare $E4 $O
