#!/usr/bin/env bash
# Host-side wrapper: run the whole suite in the official image, then plot.
# env bash, not /bin/bash: this script runs on the HOST, and some hosts
# (NixOS) have no /bin/bash at all.
set -e
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
docker image inspect astra-sim:loom >/dev/null 2>&1 || docker build -t astra-sim:loom "$REPO"
docker run --rm -v "$REPO":/app/astra-sim astra-sim:loom ./examples/loom/run_all.sh
# plot inside the image too: many hosts lock host pip (PEP 668), so the
# old host-side invocation silently skipped every figure.
docker run --rm -v "$REPO":/app/astra-sim astra-sim:loom \
    bash -c 'pip3 install -q matplotlib && python3 examples/loom/plot_results.py' || \
    echo "plotting skipped"
