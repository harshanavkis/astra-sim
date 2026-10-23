#!/usr/bin/env bash
# E8 campaign: every workload run, launched through run_e8.sh (tmux per run).
# Re-running skips sessions that are still running. Collect with
#   nix-shell shell.nix --run "python -I tools/collect_e8.py"
#   campaign.sh [workload...]   (default: all)
set -euo pipefail
E=/scratch/harshanavkis/loom-proj/e8-astrasim; F=/scratch/harshanavkis/loom-proj/chakra-traces/fixed
NCCL=$E/e8/cfg/system_nccl.json
VARIANTS="none pull pull_deepep pull_nvshmem push"
want() { [ $# -eq 0 ] || [[ " $* " == *" $W "* ]]; }
W=mixtral8x22b; want "$@" && $E/run_e8.sh $W $F/mixtral-8x22b-32/chakra_trace $F/mixtral-8x22b-32/comm_groups.json c32 $NCCL $VARIANTS
W=llama3_70b; want "$@" && $E/run_e8.sh $W $F/llama3-70b-16tp/chakra_trace $F/llama3-70b-16tp/comm_groups.json c16 $NCCL $VARIANTS
true
