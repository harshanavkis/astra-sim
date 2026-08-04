#!/bin/bash
# Run the full Loom experiment suite; CSVs land in examples/loom/results/.
# Designed to run inside the astra-sim Docker image (see run_all_docker.sh).
set -e
cd "$(dirname "$0")/../.."
RES=examples/loom/results
mkdir -p $RES

# build whatever is missing
[ -x build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware ] || \
    ./build/astra_analytical/build.sh -t congestion_unaware
[ -x build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Aware ] || \
    ./build/astra_analytical/build.sh -t congestion_aware

# victim (VOQ vs shared-FIFO) is NOT part of the standard suite: the paper
# makes no congestion-isolation claim (moved to Discussion, 2026-07-08).
# Run examples/loom/run_victim.sh standalone if the discussion is challenged.
# sweep_tpipe and regime_map are NOT in the default suite (owner sweep
# policy 2026-07-27: FPGA-owned constants are measured, not swept; the
# suite used to contradict it by running both every time):
#   - sweep_tpipe is optional reviewer-proofing, and T3 will MEASURE
#     t_pipe, retiring it. Run it standalone when the "design tolerates a
#     slow FPGA clock" figure is wanted.
#   - regime_map scales compute artificially and runs --pipe-ns 500, so its
#     Loom is not the Loom of every other experiment. The apps
#     comm/compute decomposition in CHECKPOINT section 5 shows the same
#     thing on real published workloads, for free.
# Both scripts still work standalone.
for EXP in smoke p2p_sweep sweep_credits scale_sweep matrix apps; do
    SCRIPT=examples/loom/run_${EXP}.sh
    echo ">>> $EXP"
    $SCRIPT > $RES/$EXP.csv
    sed "s/,/\t/g" $RES/$EXP.csv | sed 's/^/    /'
done
echo ">>> results in $RES/"
