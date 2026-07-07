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

for EXP in smoke victim sweep_credits sweep_tpipe regime_map matrix apps; do
    SCRIPT=examples/loom/run_${EXP}.sh
    echo ">>> $EXP"
    $SCRIPT > $RES/$EXP.csv
    sed "s/,/\t/g" $RES/$EXP.csv | sed 's/^/    /'
done
echo ">>> results in $RES/"
