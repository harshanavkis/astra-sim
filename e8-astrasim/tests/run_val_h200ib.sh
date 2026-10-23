#!/usr/bin/env bash
# Validation A: pull mode vs Baydamirli et al. (arXiv 2610.01380, Table 3, P-IB:
# H200 + CX-7, 200G IB, mini-gda, one 8 B put). Two hosts on one 200G switch,
# 500 ns links: the one fitted parameter (network one-way, from the inline
# put+completion). Predictions: non-inline put+completion, round trip.
# Writes tests/val_h200ib_<time>.tsv (metric, paper_ns, model_ns).
#   tests/run_val_h200ib.sh
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
export NS3_TIMEOUT=${NS3_TIMEOUT:-300}
E=/scratch/harshanavkis/loom-proj/e8-astrasim; A=/scratch/harshanavkis/loom-proj/astra-sim-fresh
SYS=$A/examples/system/native_collectives/HGX-H100-validated.json; TOPO=$E/e8/cfg/logical_2.json
OUT=$E/tests/out_val_h200ib_$(date -u +%Y%m%d_%H%M%S); mkdir -p "$OUT"
python -I $E/tools/gen_p2p.py "$OUT/put" 8 > /dev/null
python -I $E/tools/gen_p2p.py "$OUT/pp" 8 10 --pingpong > /dev/null
fin() { grep -o "sys\[$2\] finished, [0-9]*" "$1" < /dev/null | awk '{print $3}'; }
run() { local R; R=$($E/run_ns3.sh "$1" "$2" "$SYS" "$3" "$TOPO" || true); echo "${R%%$'\n'*}"; }
inl=$(fin "$(run val_put_inline "$OUT/put/p2p" $E/e8/cfg/val_h200ib_inline.txt)" 0)
non=$(fin "$(run val_put_noinline "$OUT/put/p2p" $E/e8/cfg/val_h200ib_noinline.txt)" 0)
pp=$(fin "$(run val_pingpong_inline "$OUT/pp/p2p" $E/e8/cfg/val_h200ib_inline.txt)" 0)
TSV=$E/tests/val_h200ib_$(date -u +%Y%m%d_%H%M%S).tsv
{ printf "metric\tpaper_ns\tmodel_ns\n"
  printf "put+completion inline (fitted)\t4030\t%s\n" "$inl"
  printf "put+completion non-inline\t4640\t%s\n" "$non"
  printf "non-inline - inline\t610\t%s\n" "$((non - inl))"
  printf "round trip inline\t6850\t%s\n" "$((pp / 10))"; } | tee "$TSV"
echo "tsv: $TSV"
