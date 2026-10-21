#!/usr/bin/env bash
# Optimized ns-3 build (ns-3 build profile "optimized": -O3, NS_LOG and asserts compiled out) in a copy of
# astra-sim-fresh (astra-sim-opt), so runs on the default build keep running. Binaries:
#   astra-sim-opt/extern/network_backend/ns-3/build/scratch/ns3.42-{AstraSimNetwork,LoomReplay}-optimized
#   bash build_ns3_opt.sh      (log: astra-sim-opt/logs/build_opt.log)
set -euo pipefail
[ -n "${E8_SHELL:-}" ] || exec nix-shell /scratch/harshanavkis/loom-proj/e8-astrasim/shell.nix --run "$(printf '%q ' bash "$0" "$@")"
S=/scratch/harshanavkis/loom-proj/astra-sim-fresh; D=/scratch/harshanavkis/loom-proj/astra-sim-opt
mkdir -p $D/logs
rsync -a --delete --exclude '/extern/network_backend/ns-3/build/' --exclude '/extern/network_backend/ns-3/cmake-cache/' \
      --exclude '/build/astra_*/build/' --exclude '/logs/' $S/ $D/
echo "copied $(git -C $S rev-parse --short HEAD) (ns-3 $(git -C $S/extern/network_backend/ns-3 rev-parse --short HEAD))" | tee $D/logs/build_opt.log
cd $D/build/astra_ns3 && protoc et_def.proto --proto_path ../../extern/graph_frontend/chakra/schema/protobuf/ \
      --cpp_out ../../extern/graph_frontend/chakra/schema/protobuf/ 2>/dev/null || true
cd $D/extern/network_backend/ns-3
./ns3 configure --enable-mpi --build-profile optimized >> $D/logs/build_opt.log 2>&1
./ns3 build AstraSimNetwork LoomReplay -j $(nproc) >> $D/logs/build_opt.log 2>&1
ls -la build/scratch/ | grep -E 'optimized'
