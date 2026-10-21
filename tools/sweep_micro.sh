#!/usr/bin/env bash
# Microbenchmark maps on the LoomNet model (owner 2026-10-21: where Loom is worse, better, equal); model results.
#   tools/sweep_micro.sh coll [parallel]   all-reduce / all-gather / reduce-scatter (ring) and all-to-all (direct),
#        1 KiB .. 256 MiB per GPU, 16 .. 512 GPUs (clusters n16 n64nm n128nm n256 n512)
#   tools/sweep_micro.sh moe [parallel]    MoE dispatch / combine (tools/gen_moe.py, 7 KiB tokens, top-8 of 256 experts),
#        1 .. 512 tokens per GPU, EP 16 .. 256 (configs e8/moe/cfg as Fig 11)
#   tools/sweep_micro.sh buf [parallel]    the MoE map and 64-GPU collectives with Loom's transmit buffer (LOOM_TX_BUF_BYTES
#        = the computed ACK window at 400 G, 123 x 4 KiB) instead of an unlimited one
#   tools/sweep_micro.sh var <name> <rdma|loom> '<config lines>' [parallel]   the same with any config variant
# Jobs: e8_an/sweep/<coll|moe>_jobs.txt, logs runs_an/an_sw<coll|moe>__*; results: tools/sweep_micro_collect.py.
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
E=/scratch/harshanavkis/loom-proj/e8-astrasim; O=$E/e8_an/sweep; mkdir -p $O/cfg
case ${1:-} in
coll)
    D=$E/e8/coll; J=$O/coll_jobs.txt; : > $J
    for nc in "16 n16" "64 n64nm" "128 n128nm" "256 n256" "512 n512"; do
        read -r n cl <<< "$nc"; C=$E/e8/clusters/$cl
        for op in ALL_REDUCE ALL_GATHER REDUCE_SCATTER ALL_TO_ALL; do
            for s in 1024 4096 16384 65536 262144 1048576 4194304 16777216 67108864 268435456; do
                wl=$D/wl/${op}_n${n}_s$s
                [ -f $wl/coll.$((n - 1)).et ] || python3 -I $E/tools/gen_coll.py $wl $n $op $s > /dev/null
                for v in rdma loom; do
                    echo "swcoll__${op}__n${n}__s${s}__$v $wl/coll $E/e8/cfg/system_nccl.json $C/$v.txt $C/logical.json" >> $J
                done
            done
        done
    done
    echo "$(grep -c . $J) jobs"; $E/tools/run_an_jobs.sh $J "${2:-32}" ;;
moe)
    D=$E/e8/moe; J=$O/moe_jobs.txt; : > $J
    for op in dispatch combine; do for ep in 16 32 64 128 256; do for t in 1 2 4 8 16 32 64 128 256 512; do
        wl=$D/wl/${op}_ep${ep}_t$t
        [ -f $wl/moe.$((ep - 1)).et ] || python3 -I $E/tools/gen_moe.py $wl $ep $t $op 7168 > /dev/null
        for v in rdma loom; do
            echo "swmoe__${op}__ep${ep}__t${t}__$v $wl/moe $E/e8/cfg/system_direct.json $D/cfg/${v}_ep${ep}_$op.txt $E/e8/clusters/n16/logical.json" >> $J
        done
    done; done; done
    echo "$(grep -c . $J) jobs"; ASTRA_CONCURRENT_SENDS=1 $E/tools/run_an_jobs.sh $J "${2:-32}" ;;
buf)   # Loom transmit buffer = the computed ACK window at 400 G (123 x 4 KiB): MoE map + collectives at 64 GPUs
    J=$O/buf_jobs.txt; : > $J; B=$((123 * 4096))
    buf_cfg() { local p=$O/cfg/$2_buf.txt; { cat $1; echo; echo "LOOM_TX_BUF_BYTES $B"; } > $p; echo $p; }
    for op in dispatch combine; do for ep in 16 32 64 128 256; do for t in 1 2 4 8 16 32 64 128 256 512; do
        echo "swmoe__${op}__ep${ep}__t${t}__loom_buf $E/e8/moe/wl/${op}_ep${ep}_t$t/moe $E/e8/cfg/system_direct.json $(buf_cfg $E/e8/moe/cfg/loom_ep${ep}_$op.txt moe_loom_ep${ep}_$op) $E/e8/clusters/n16/logical.json" >> $J
    done; done; done
    C=$E/e8/clusters/n64nm
    for op in ALL_REDUCE ALL_GATHER REDUCE_SCATTER ALL_TO_ALL; do
        for s in 1024 4096 16384 65536 262144 1048576 4194304 16777216 67108864 268435456; do
            echo "swcoll__${op}__n64__s${s}__loom_buf $E/e8/coll/wl/${op}_n64_s$s/coll $E/e8/cfg/system_nccl.json $(buf_cfg $C/loom.txt n64_loom) $C/logical.json" >> $J
        done
    done
    echo "$(grep -c . $J) jobs"; ASTRA_CONCURRENT_SENDS=1 $E/tools/run_an_jobs.sh <(grep swmoe $J) "${2:-32}"
    $E/tools/run_an_jobs.sh <(grep swcoll $J) "${2:-32}" ;;
var)   # <variant name> <rdma|loom> <config lines, \n-separated>: MoE map + collectives at 64 GPUs with that variant
    VN=$2 VS=$3 VX=$4; J=$O/var_${VN}_jobs.txt; : > $J
    var_cfg() { local p=$O/cfg/$2_$VN.txt; { cat $1; echo; printf '%b\n' "$VX"; } > $p; echo $p; }
    for op in dispatch combine; do for ep in 16 32 64 128 256; do for t in 1 2 4 8 16 32 64 128 256 512; do
        echo "swmoe__${op}__ep${ep}__t${t}__$VN $E/e8/moe/wl/${op}_ep${ep}_t$t/moe $E/e8/cfg/system_direct.json $(var_cfg $E/e8/moe/cfg/${VS}_ep${ep}_$op.txt moe_${VS}_ep${ep}_$op) $E/e8/clusters/n16/logical.json" >> $J
    done; done; done
    C=$E/e8/clusters/n64nm
    for op in ALL_REDUCE ALL_GATHER REDUCE_SCATTER ALL_TO_ALL; do
        for s in 1024 4096 16384 65536 262144 1048576 4194304 16777216 67108864 268435456; do
            echo "swcoll__${op}__n64__s${s}__$VN $E/e8/coll/wl/${op}_n64_s$s/coll $E/e8/cfg/system_nccl.json $(var_cfg $C/$VS.txt n64_$VS) $C/logical.json" >> $J
        done
    done
    echo "$(grep -c . $J) jobs"; ASTRA_CONCURRENT_SENDS=1 $E/tools/run_an_jobs.sh <(grep swmoe $J) "${5:-32}"
    $E/tools/run_an_jobs.sh <(grep swcoll $J) "${5:-32}" ;;
*) sed -n '2,8p' "$0"; exit 2 ;;
esac
