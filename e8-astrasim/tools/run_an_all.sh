#!/usr/bin/env bash
# Regenerate every LoomNet analytical result (ANALYTICAL.md) end to end: build, prototype validation, link sweep,
# collectives (Fig 12 jobs), MoE (Fig 11 jobs), Phase A training (ordered traces), comparisons with the ns-3 model,
# alpha-beta, figure previews. Report: e8_an/ALL.txt.   tools/run_an_all.sh   (~2 min)
# 2026-10-27 (owner: every experiment on the ASTRA-sim layer): the prototype validation is val_model/run_val_astra.py (the
# paper's model: measured rates, in-place reductions; was run_val_an.py with an_replay), the sweep run_sweep_astra.py (was
# run_sweep_an.py), alpha_beta.py runs in ASTRA-sim; the H200 dispatch replay (an_loomreplay, in no paper text) is retired.
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; V=$HOME/loom-experiments/val_model
cd $E
R=$E/e8_an/ALL.txt
{
echo "# LoomNet analytical model: all results, $(date -u '+%Y-%m-%d %H:%M UTC') (model unless marked measured)"
tools/build_an.sh > /dev/null
echo "binary $(md5sum < /scratch/harshanavkis/loom-proj/astra-sim-fresh/build/astra_analytical/build/bin/AstraSim_Analytical_Loom | cut -c1-8) model $(md5sum < /scratch/harshanavkis/loom-proj/astra-sim-fresh/astra-sim/network_frontend/analytical/include/loom/LoomNet.hh | cut -c1-8)"
echo; echo "## Validation against the prototype (measured vs model)"
(cd $V && IDEAL_LINK=0 REDSHIFT=$HOME/loom-experiments/e5_ptdma/20261027_1704_redshift REDSHIFT_RATE=0 python3 -I run_val_astra.py \
    && ln -sfn $(ls -td runs_astra/2026*/ | head -1 | xargs basename) runs_astra/current) | tail -n +1
echo; echo "## Link-rate sweep"
(cd $V && python3 -I run_sweep_astra.py && ln -sfn $(ls -td sweep_astra/2026*/ | head -1 | xargs basename) sweep_astra/current)
tools/run_an_jobs.sh e8_an/coll/jobs.txt 40 > /dev/null
ASTRA_CONCURRENT_SENDS=1 tools/run_an_jobs.sh e8_an/moe/jobs.txt 40 > /dev/null
tools/run_an_jobs.sh e8_an/e2e/jobs.txt 20 > /dev/null
echo; echo "## Collectives"; LOGS=runs_an/an_ python3 -I tools/collect_coll_nic.py e8_an/coll/jobs.txt
echo; echo "## MoE"; LOGS=runs_an/an_ python3 -I tools/collect_moe.py e8_an/moe/jobs.txt
echo; echo "## Phase A training"; AN=1 python3 -I tools/collect_e2e.py
echo; echo "## vs the ns-3 model"; python3 -I tools/cmp_an_ns3.py
# retired 2026-10-27 (hand-written replayer an_loomreplay; no paper text uses it): "## RDMA vs the H200 server"
# O=$E/val_dispatch/20261010_ring/model_an_current; mkdir -p $O
# ls $E/val_dispatch/20261010_ring/runs/*.run | grep -v _local | xargs -P 32 -I{} sh -c 'b=$(basename {} .run); '"$E"'/bin/an_loomreplay '"$E"'/e8/cfg/steve_nic/base.txt {} '"$O"'/$b.out > '"$O"'/$b.log 2>&1 || echo "FAILED $b"'
# python3 -I tools/val_dispatch.py $E/val_dispatch/20261010_ring $O | grep -E " seen |reaped|arr_last"
echo; echo "## alpha-beta"; TMPDIR=$(mktemp -d) python3 -I tools/alpha_beta.py e8/clusters/n64nm 0 8; TMPDIR=$(mktemp -d) python3 -I tools/alpha_beta.py e8/clusters/n64nm 0 32 | tail -4
MODEL=an python3 -I tools/plot_eval.py e8_an/preview e8_an/preview > /dev/null
echo; echo "previews: e8_an/preview/*.png"
} > $R 2>&1
grep -E "FAILED|Traceback|error" $R && echo "CHECK $R" || echo "OK: $R"
