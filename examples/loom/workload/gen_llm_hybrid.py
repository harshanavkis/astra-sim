#!/usr/bin/env python3
"""Generate a hybrid-parallel LLM training iteration in ASTRA-sim's legacy
text workload format, then (optionally) convert to Chakra ET via the in-tree
converter (W-B in the eval plan).

Model: uniform transformer layers; per layer, forward compute + fwd comm,
backward-input compute + comm, backward-weight compute + comm (all-reduce for
the data-parallel dimension). SM reservation for baselines is applied to the
compute times exactly as in gen_moe_alltoall.py.

Example (from repo root; conversion needs the chakra package importable):
  python3 examples/loom/workload/gen_llm_hybrid.py --layers 8 \
      --fwd-us 900 --bwd-us 1800 --comm-mb 64 --sm-comm 20 --out /tmp/llm_b1
"""

import argparse
import os
import subprocess
import sys


def generate(args):
    sm_factor = args.sm_total / (args.sm_total - args.sm_comm)
    fwd = round(args.fwd_us * sm_factor)
    bwd_ig = round(args.bwd_us / 2 * sm_factor)
    bwd_wg = round(args.bwd_us / 2 * sm_factor)
    comm_bytes = args.comm_mb * 1024 * 1024

    os.makedirs(args.out, exist_ok=True)
    txt = os.path.join(args.out, "llm.txt")
    with open(txt, "w") as f:
        f.write(f"{args.parallelism}\n")
        f.write(f"{args.layers}\n")
        for i in range(args.layers):
            f.write(  # col 1 is reserved/ignored by the Text converter
                f"layer{i} -1 {fwd} ALLREDUCE {comm_bytes} "
                f"{bwd_ig} ALLREDUCE {comm_bytes} "
                f"{bwd_wg} ALLREDUCE {comm_bytes} 10\n"
            )
    print(f"wrote {txt} (sm_factor {sm_factor:.3f})")

    if args.convert:
        cmd = [
            sys.executable, "-m",
            "extern.graph_frontend.chakra.src.converter.converter", "Text",
            "--input", txt,
            "--output", os.path.join(args.out, "llm"),
            "--num-npus", str(args.npus),
            "--num-passes", str(args.passes),
        ]
        print("+", " ".join(cmd))
        subprocess.run(cmd, check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--parallelism", default="HYBRID_DATA_MODEL")
    p.add_argument("--layers", type=int, default=8)
    p.add_argument("--fwd-us", type=int, default=900)
    p.add_argument("--bwd-us", type=int, default=1800)
    p.add_argument("--comm-mb", type=int, default=64)
    p.add_argument("--sm-total", type=int, default=132)
    p.add_argument("--sm-comm", type=int, default=0,
                   help="SMs reserved for communication (0 = Loom)")
    p.add_argument("--npus", type=int, default=8)
    p.add_argument("--passes", type=int, default=1)
    p.add_argument("--convert", action="store_true",
                   help="also run the in-tree Text->Chakra converter")
    p.add_argument("--out", required=True)
    generate(p.parse_args())


if __name__ == "__main__":
    main()
