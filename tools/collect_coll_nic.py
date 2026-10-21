#!/usr/bin/env python3
"""Results of run_coll_nic.sh: per job (newest log), the collective's time = the last GPU's finish (us);
RDMA vs Loom side by side.   collect_coll_nic.py <jobs file>  -> <dir>/coll.tsv"""
import glob, os, re, sys

jobs = [l.split()[0] for l in open(sys.argv[1]) if l.strip()]
E = "/scratch/harshanavkis/loom-proj/e8-astrasim"
res = {}
for name in jobs:
    logs = sorted(glob.glob(os.path.join(E, os.environ.get("LOGS", "runs/ns3_") + f"{name}_2*.log")))  # LOGS=runs_an/an_: analytical model
    if not logs:
        continue
    fin = [int(m[1]) / 1e3 for m in re.finditer(r"loom_rank \d+ .* finished_ns (\d+)", open(logs[-1], errors="replace").read())]
    _, op, n, s, v = name.split("__")
    res[(op, int(n[1:]), int(s[1:]), v)] = (len(fin), max(fin) if fin else None)
out = open(os.path.join(os.path.dirname(sys.argv[1]), "coll.tsv"), "w")
out.write("op\tgpus\tbytes\tvariant\tranks\ttime_us\n")
print(f"{'op':12}{'GPUs':>5}{'bytes':>10}   {'rdma':>9}{'loom':>9}{'x':>7}")
for (op, n, s) in sorted({k[:3] for k in res}):
    t = {}
    for v in ["rdma", "loom"]:
        if (op, n, s, v) in res and res[(op, n, s, v)][1] is not None:
            t[v] = res[(op, n, s, v)][1]
            out.write(f"{op}\t{n}\t{s}\t{v}\t{res[(op, n, s, v)][0]}\t{t[v]:.2f}\n")
    if len(t) == 2:
        print(f"{op:12}{n:5d}{s:10d}   {t['rdma']:9.1f}{t['loom']:9.1f}{t['rdma'] / t['loom']:6.2f}x")
