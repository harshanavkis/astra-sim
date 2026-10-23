#!/usr/bin/env python3
"""Results of a training sweep (tools/sweep_train.sh): per line the RDMA and Loom iteration (slowest GPU), that GPU's
exposed communication, and RDMA/Loom (> 1: Loom faster) per Loom variant (loom, loom_buf), from the newest runs_an/an_sw_<name>__<cluster>__<v>_*.log.
Model results (LoomNet).   python3 -I sweep_collect.py <sweep file> [out.tsv]"""
import glob, os, re, sys

E = "/scratch/harshanavkis/loom-proj/e8-astrasim"


def run(name, cl, v):
    logs = sorted(glob.glob(os.path.join(E, "runs_an", f"an_sw_{name}__{cl}__{v}_2*.log")))
    if not logs:
        return None
    txt = open(logs[-1], errors="replace").read()
    if not txt.startswith("loomnet bin") or "loomnet: simulation finished" not in txt:
        return None
    fin = [(int(c), int(x)) for c, x in re.findall(r"sys\[\d+\] finished, (\d+) cycles, exposed communication (\d+) cycles", txt)]
    if not fin:
        return None
    it, exp = max(fin)
    return it / 1e6, exp / 1e6, txt.splitlines()[0].split()[2]


VARS = ("loom", "loom_buf")   # RDMA/<variant> per column, where the run exists
rows, seen = [], set()
for line in open(sys.argv[1]):
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    f = line.split("|")
    name, cl = f[0], f[-1]
    if (name, cl) in seen:
        continue
    seen.add((name, cl))
    r = run(name, cl, "rdma")
    if not r:
        rows.append(f"{name}\t{cl}\tMISSING")
        continue
    cols = []
    for v in VARS:
        x = run(name, cl, v)
        cols.append(f"{r[0] / x[0]:.4f}" if x else "")
    l = run(name, cl, "loom")
    rows.append(f"{name}\t{cl}\t{r[0]:.3f}\t{l[0] if l else float('nan'):.3f}\t" + "\t".join(cols) +
                f"\t{r[1] / r[0] * 100:.1f}\t{r[2]}")
out = ("name\tcluster\trdma_ms\tloom_ms\t" + "\t".join(f"rdma_over_{v}" for v in VARS) + "\trdma_exposed_pct\tbin\n"
       + "\n".join(rows) + "\n")
if len(sys.argv) > 2:
    open(sys.argv[2], "w").write(out)
print(out, end="")
