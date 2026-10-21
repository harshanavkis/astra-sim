#!/usr/bin/env bash
# RDMA vs ideal Loom, both modelled, zero GPU-side cost (tools/gen_zero_gpu.py): steve's validated NIC
# config for RDMA, push_1000mhz for Loom. Prints, per operation and token count (us): sender busy until
# the arrival signal is issued, ordered's completions collected, and when the receiver sees every signal.
#   tests/run_model_compare.sh      -> val_dispatch/zero_gpu/compare.tsv
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; D=$E/val_dispatch/zero_gpu
BIN=/scratch/harshanavkis/loom-proj/astra-sim-fresh/extern/network_backend/ns-3/build/scratch/ns3.42-LoomReplay-default
/scratch/harshanavkis/loom-proj/e8-astrasim/tools/check_ns3_build.sh "$BIN" || exit 1   # refuse a stale build (2026-10-20)
python3 -I $E/tools/gen_zero_gpu.py $D/runs > /dev/null
mkdir -p $D/out
for f in $D/runs/*.run; do
  b=$(basename $f .run); c=$E/e8/cfg/steve_nic/base.txt
  [[ $b == *_push_* ]] && c=$E/e8/cfg/steve_nic/push_1000mhz.txt
  $BIN $c $f $D/out/$b.out > $D/out/$b.log 2>&1 &
done
wait
python3 -I - $D <<'PY'
import sys, os
d = sys.argv[1]
def s(n):  # arr_first arr_last drain signal seen reaped sender_out (ns)
    for line in open(os.path.join(d, "out", n + ".out")):
        if line.startswith("sum"):
            return [int(x) / 1e3 for x in line.split()[1:]]
with open(os.path.join(d, "compare.tsv"), "w") as f:
    f.write("op\ttokens\tordered_signal\tordered_reaped\tflush_signal\tloom_signal\tordered_seen\tflush_seen\tloom_seen\n")
    print(f"{'':9}{'':4}  {'---- sender: signal issued ----':>44}   {'-- receiver sees every signal --':>34}")
    print(f"{'op':9}{'tok':>4}  {'ord':>8}{'ord+reap':>10}{'flush':>9}{'Loom':>9}     {'ord':>8}{'flush':>9}{'Loom':>9}")
    for op in ["dispatch", "combine"]:
        for T in [1, 16, 128]:
            o, fl, p = s(f"{op}_ordered_t{T}"), s(f"{op}_flush_t{T}"), s(f"{op}_push_t{T}")
            row = [0.0, o[5], fl[3], p[6], o[4], fl[4], p[4]]
            f.write(f"{op}\t{T}\t" + "\t".join(f"{x:.2f}" for x in row) + "\n")
            print(f"{op:9}{T:4d}  {row[0]:8.2f}{row[1]:10.2f}{row[2]:9.2f}{row[3]:9.2f}     {row[4]:8.2f}{row[5]:9.2f}{row[6]:9.2f}")
PY
