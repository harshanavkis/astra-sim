#!/bin/bash
# Host-side wrapper: run the whole suite in the official image, then plot.
set -e
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
docker image inspect astra-sim:loom >/dev/null 2>&1 || docker build -t astra-sim:loom "$REPO"
docker run --rm -v "$REPO":/app/astra-sim astra-sim:loom ./examples/loom/run_all.sh
python3 "$REPO/examples/loom/plot_results.py" || \
    echo "plotting skipped (needs: pip install matplotlib)"
