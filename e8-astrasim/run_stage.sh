#!/usr/bin/env bash
# End-to-end training on STAGE traces (github.com/astra-sim/stage, clone stage-ref/stage; arXiv 2511.10480): dense
# Llama-3 8B / 70B and MoE Mixtral 8x7B / 8x22B at 32 and 128 GPUs, layers reduced to 2 per pipeline stage
# (4 at PP1/PP2, 8 at PP4; our choice, for ns-3 run time), bf16, seq 4096. Every configuration sends traffic
# across servers: dense = TP8 inside a server, DP and PP across (tools/remap_ranks.py puts TP innermost);
# MoE = TP4 x EP8 (x PP4), EP groups span 4 servers. Compute: H200 roofline (e8/cfg/system_nccl_roofline.json =
# system_nccl.json + roofline-enabled, 989 TFLOPS, 4.8 TB/s). Then RDMA and Loom per configuration (run_e8.sh,
# optimized ns-3 build), workload names stage_<model>_<n>.
#   run_stage.sh [config ...]      (run it in tmux; configs below, default all)
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; S=/scratch/harshanavkis/loom-proj/stage-ref/stage
export NS3_BIN=${NS3_BIN:-/scratch/harshanavkis/loom-proj/astra-sim-opt2/extern/network_backend/ns-3/build/scratch/ns3.42-AstraSimNetwork-optimized}   # opt2 = fe4553df with the 10-11 push-path fix; opt (c183e35a) is older
LLAMA8="--model_type dense --dmodel 4096 --dff 14336 --head 32 --kvhead 8 --dvocal 128256"
LLAMA70="--model_type dense --dmodel 8192 --dff 28672 --head 64 --kvhead 8 --dvocal 128256"
MIX7="--model_type moe --dmodel 4096 --dff 14336 --head 32 --kvhead 8 --dvocal 32000 --experts 8 --kexperts 2"
MIX22="--model_type moe --dmodel 6144 --dff 16384 --head 48 --kvhead 8 --dvocal 32768 --experts 8 --kexperts 2"
declare -A CFG=(
  [llama3_8b_n32]="$LLAMA8|dp=2 tp=8 pp=2|4|16|4|n32"    [llama3_8b_n128]="$LLAMA8|dp=4 tp=8 pp=4|8|32|4|n128"
  [llama3_70b_n32]="$LLAMA70|dp=2 tp=8 pp=2|4|16|4|n32"  [llama3_70b_n128]="$LLAMA70|dp=4 tp=8 pp=4|8|32|4|n128"
  [mixtral8x7b_n32]="$MIX7|tp=4 ep=8 pp=1|4|16|4|n32"    [mixtral8x7b_n128]="$MIX7|tp=4 ep=8 pp=4|8|32|4|n128"
  [mixtral8x22b_n32]="$MIX22|tp=4 ep=8 pp=1|4|16|4|n32"  [mixtral8x22b_n128]="$MIX22|tp=4 ep=8 pp=4|8|32|4|n128")
for c in ${@:-llama3_8b_n32 llama3_8b_n128 llama3_70b_n32 llama3_70b_n128 mixtral8x7b_n32 mixtral8x7b_n128 mixtral8x22b_n32 mixtral8x22b_n128}; do
    IFS='|' read -r model par layers batch mb cl <<< "${CFG[$c]}"
    R=$E/traces/stage/${c}_raw; T=$E/traces/stage/$c
    if [ ! -f $T/workload.json ]; then
        args=""; for kv in $par; do args="$args --${kv%%=*} ${kv#*=}"; done
        (cd $S && python3 main.py --output_dir $R --output_name workload $model $args --num_stacks $layers \
            --batch $batch --micro_batch $mb --seq 4096 --mixed_precision true > $R.gen.log 2>&1)
        python3 -I $E/tools/remap_ranks.py $R workload $T $par | tee $T.remap.txt
    fi
    $E/run_e8.sh stage_$c $T/workload $T/workload.json $cl $E/e8/cfg/system_nccl_roofline.json rdma loom
done
