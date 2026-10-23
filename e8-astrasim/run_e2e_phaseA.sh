#!/usr/bin/env bash
# Fig 14 (At Scale "Training"), Phase A (owner 2026-10-20, review in 12 h): one bar group per parallelism, the traffic
# of the parallelism under test crossing servers (TP inside a server), on Opus's (SIGCOMM) applications (owner 2026-10-20:
# their applications only, not their emulation setups); RDMA and
# Loom each, ns-3 model, 400 G cluster. Layers cut for ns-3 run time, the vocabulary scaled by the same factor
# (dvocal x layers / full layers) so the vocabulary layers keep a full model's share; results are reported as ratios.
# Opus's MoE (rows moe_*): pilot traces (traces/pilot/opus_*), run here too. Clusters n64nm/n128nm = queue monitor off
# (cycle-identical, verified). 2026-10-20 16:00: rerun on the bandwidth-only in-server model (opt2 e59e7ee3).
#   run_e2e_phaseA.sh gen      generate + check every trace (STAGE, remap_ranks.py; et_summary per trace)
#   run_e2e_phaseA.sh run      launch every RDMA/Loom pair (run_e8.sh -> run_ns3.sh, build-checked binary)
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; S=/scratch/harshanavkis/loom-proj/stage-ref/stage; P=$E/traces/e2e
export NS3_BIN=/scratch/harshanavkis/loom-proj/astra-sim-opt2/extern/network_backend/ns-3/build/scratch/ns3.42-AstraSimNetwork-optimized
V=128256                                                     # Llama-3 vocabulary
L8="--model_type dense --dmodel 4096 --dff 14336 --head 32 --kvhead 8"      # Llama-3 8B, 32 layers
L70="--model_type dense --dmodel 8192 --dff 28672 --head 64 --kvhead 8"     # Llama-3 70B, 80 layers
L80="--model_type dense --dmodel 8192 --dff 28672 --head 64 --kvhead 8"     # Opus's Llama-80B, 96 layers
voc() { echo $(( V * $1 / $2 )); }                            # vocabulary scaled to <layers> of <full layers>
# name | model args | layers | full layers | parallelism | batch | micro-batch | seq | extra | cluster | GPUs per server
CFG=(
  "dp|$L8|4|32|dp=8 tp=8 pp=1|256|256|4096||n64nm|8"
  "fsdp|$L8|4|32|dp=8 tp=8 pp=1|256|256|4096|--weight_sharded true|n64nm|8"
  "pp|$L70|8|80|dp=1 tp=8 pp=8|64|8|4096||n64nm|8"
  "cp|$L8|4|32|dp=1 tp=8 sp=8 pp=1|8|8|32768||n64nm|8"
  "hybrid|$L70|8|80|dp=2 tp=8 pp=4|64|8|4096||n64nm|8"
  "depth16|$L8|16|32|dp=8 tp=8 pp=1|256|256|4096||n64nm|8"
  "l80|$L80|8|96|dp=4 tp=8 pp=4|256|256|4096||n128nm|8")
mkcl() {   # cluster with 4 GPUs per server (Opus's Perlmutter nodes): same topology, NVLink domain of 4
    local src=$1 dst=$E/e8/clusters/$2
    [ -d $dst ] && return; mkdir -p $dst
    cp $E/e8/clusters/$src/logical.json $dst/
    for v in rdma loom; do sed 's/^GPUS_PER_SERVER 8$/GPUS_PER_SERVER 4/' $E/e8/clusters/$src/$v.txt > $dst/$v.txt; done
    grep -q "GPUS_PER_SERVER 4" $dst/loom.txt
}
case ${1:-} in
gen)
    mkdir -p $P
    for c in "${CFG[@]}"; do
        IFS='|' read -r n model l lf par b mb seq extra cl gps <<< "$c"
        [ -f $P/$n/workload.json ] && { echo "$n: exists"; continue; }
        args=""; for kv in $par; do args="$args --${kv%%=*} ${kv#*=}"; done
        (cd $S && python3 main.py --output_dir $P/${n}_raw --output_name workload $model --dvocal $(voc $l $lf) $args \
            --num_stacks $l --batch $b --micro_batch $mb --seq $seq --mixed_precision true $extra > $P/$n.gen.log 2>&1) \
            || { echo "GEN FAILED $n"; tail -5 $P/$n.gen.log; exit 1; }
        python3 -I $E/tools/remap_ranks.py $P/${n}_raw workload $P/$n ${par//sp=/cp=} --gpus-per-server $gps | sed "s/^/$n: /"
        python3 -I $E/tools/et_summary.py $P/$n/workload.0.et | sed "s/^/   /"
    done ;;
run)
    for c in "${CFG[@]}"; do
        IFS='|' read -r n model l lf par b mb seq extra cl gps <<< "$c"
        $E/run_e8.sh e2e_$n $P/$n/workload $P/$n/workload.json $cl $E/e8/cfg/system_nccl_roofline.json rdma loom
    done
    # Opus's DeepSeek-V3-style MoE (tools/gen_opus_moe.py traces from the pilot; fixed durations -> no roofline)
    for t in opus_mixed_ep64 opus_scaleout_ep8; do
        $E/run_e8.sh pilotfix_$t $E/traces/pilot/$t/workload/workload $E/traces/pilot/$t/comm_group.json n64nm \
            $E/e8/cfg/system_nccl.json rdma loom
    done ;;
*) sed -n '2,9p' "$0"; exit 2 ;;
esac
