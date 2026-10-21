#!/usr/bin/env bash
# Training sweeps on the LoomNet model (owner 2026-10-21: "run as many sweeps as you can ... where Loom is worse, better
# and equal"): STAGE dense traces (stage-ref/stage), TP inside a server (tools/remap_ranks.py), program order
# (tools/order_traces.sh), then RDMA and Loom on a cluster. Full depth and the full vocabulary unless a line cuts layers
# (then the vocabulary shrinks by the same factor, as Phase A). Results: tools/sweep_collect.py <sweep file>.
#   tools/sweep_train.sh gen <sweep file> [parallel, default 16]     generate + order every trace (skips existing)
#   tools/sweep_train.sh run <sweep file> [parallel, default 24]     RDMA + Loom per line (runs_an/an_sw_<name>__<cluster>__<v>_*)
# Sweep file: one line per point, '#' comments:  name|model|layers|parallelism|batch|micro-batch|seq|extra STAGE args|cluster
#   model = l8 (Llama-3 8B, 32 layers) | l70 (Llama-3 70B, 80) | l80 (Opus's Llama-80B, 96); layers "full" = the model's own
#   parallelism = "dp=8 tp=8 pp=1" (STAGE sp = context parallelism); cluster = e8/clusters/<name> (rdma.txt / loom.txt)
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; S=/scratch/harshanavkis/loom-proj/stage-ref/stage; T=$E/traces/sweep
SYS=$E/e8/cfg/system_nccl_roofline.json
V=128256                                                     # Llama-3 vocabulary

model_args() {   # <model> -> "<STAGE args>|<full layers>"
    case $1 in
    l8)  echo "--model_type dense --dmodel 4096 --dff 14336 --head 32 --kvhead 8|32" ;;
    l70) echo "--model_type dense --dmodel 8192 --dff 28672 --head 64 --kvhead 8|80" ;;
    l80) echo "--model_type dense --dmodel 8192 --dff 28672 --head 64 --kvhead 8|96" ;;
    *) echo "unknown model $1" >&2; return 1 ;;
    esac
}

gen1() {   # one sweep line -> traces/sweep/<name> (ordered) ; logs traces/sweep/<name>.gen.log
    IFS='|' read -r n model l par b mb seq extra cl <<< "$1"
    [ -f $T/$n/.done ] && { echo "$n: exists"; return 0; }
    local ma full args gpus=1
    ma=$(model_args $model); full=${ma#*|}; ma=${ma%|*}
    [ "$l" = full ] && l=$full
    args=""; for kv in $par; do args="$args --${kv%%=*} ${kv#*=}"; gpus=$((gpus * ${kv#*=})); done
    rm -rf $T/${n}_raw $T/${n}_map
    (cd $S && python3 main.py --output_dir $T/${n}_raw --output_name workload $ma --dvocal $((V * l / full)) $args \
        --num_stacks $l --batch $b --micro_batch $mb --seq $seq --mixed_precision true $extra) > $T/$n.gen.log 2>&1 \
        || { echo "GEN FAILED $n"; tail -3 $T/$n.gen.log; return 1; }
    python3 -I $E/tools/remap_ranks.py $T/${n}_raw workload $T/${n}_map ${par//sp=/cp=} --gpus-per-server 8 >> $T/$n.gen.log 2>&1 \
        || { echo "REMAP FAILED $n"; return 1; }
    $E/tools/order_traces.sh $T/${n}_map $T/$n $gpus >> $T/$n.gen.log 2>&1 || { echo "ORDER FAILED $n"; return 1; }
    [ -f $T/$n/issue_order.log ] || { echo "ORDER FAILED $n (no issue log)"; return 1; }
    rm -rf $T/${n}_raw $T/${n}_map
    touch $T/$n/.done                                        # complete (ordered traces written)
    echo "$n: $gpus GPUs, $l layers, ok"
}
export -f gen1 model_args; export E S T V

lines() { grep -v '^\s*#' "$1" | grep -v '^\s*$'; }

case ${1:-} in
gen)
    mkdir -p $T
    lines "$2" | awk -F'|' '!seen[$1]++' | xargs -d '\n' -P "${3:-16}" -I{} bash -c 'gen1 "$1"' _ {} ;;   # one gen per trace name
gen1) gen1 "$2" ;;
run)   # VARIANTS (default "rdma loom"): also loom_buf (Loom transmit buffer = the computed ACK window at the cluster's
       # rate, W = ceil(rate x 10 us / 4 KiB) x 4 KiB)
    J=$(mktemp); trap 'rm -f $J' EXIT
    mkdir -p $E/e8_an/sweep/cfg
    lines "$2" | while IFS='|' read -r n model l par b mb seq extra cl; do
        for v in ${VARIANTS:-rdma loom}; do
            c=$E/e8/clusters/$cl/$v.txt
            case $v in
            loom_buf) g=$(awk 'NR==3{print $3+0}' $(awk '$1=="TOPOLOGY_FILE"{print $2}' $E/e8/clusters/$cl/loom.txt))   # host link Gbps
                c=$E/e8_an/sweep/cfg/${cl}_loom_buf.txt
                { cat $E/e8/clusters/$cl/loom.txt; echo; echo "LOOM_TX_BUF_BYTES $(( (g * 10000 / 8 + 4095) / 4096 * 4096 ))"; } > $c ;;
            esac
            echo "sw_${n}__${cl}__$v $T/$n/workload $SYS $c x $T/$n/workload.json"
        done
    done > $J
    $E/tools/run_an_jobs.sh $J "${3:-24}" ;;
*) sed -n '2,11p' "$0"; exit 2 ;;
esac
