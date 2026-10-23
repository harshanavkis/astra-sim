#!/usr/bin/env python3
"""Collect tools/sweep_micro.sh results (model): per job the slowest rank's finish (collectives) or the last sender
release and the last arrival (MoE), from the newest runs_an/an_<job>_*.log.
  python3 -I sweep_micro_collect.py coll|moe <jobs file> <out.tsv>"""
import glob, os, re, sys

E = "/scratch/harshanavkis/loom-proj/e8-astrasim"
kind, jobs, out = sys.argv[1], sys.argv[2], sys.argv[3]
rows, missing = [], 0
for line in open(jobs):
    name = line.split()[0]
    logs = sorted(glob.glob(os.path.join(E, "runs_an", f"an_{name}_2*.log")))
    txt = open(logs[-1], errors="replace").read() if logs else ""
    key = name.split("__")[1:]                    # op, n/ep, s/t, variant
    if kind == "coll":
        fin = [int(m[1]) for m in re.finditer(r"loom_rank \d+ .* finished_ns (\d+)", txt)]
        if not fin or "an_exit 0" not in txt:
            missing += 1; continue
        rows.append("\t".join(key) + f"\t{max(fin) / 1e3:.3f}\t{len(fin)}")
    else:
        m = [(int(a), int(b)) for a, b in re.findall(r"loom_rank \d+ sends_released_ns (\d+) last_recv_ns (\d+)", txt)]
        if not m or "an_exit 0" not in txt:
            missing += 1; continue
        rows.append("\t".join(key) + f"\t{max(a for a, _ in m) / 1e3:.3f}\t{max(b for _, b in m) / 1e3:.3f}\t{len(m)}")
head = "op\tn\tsize\tvariant\ttime_us\tranks" if kind == "coll" else "op\tep\ttokens\tvariant\treleased_us\tdelivered_us\tranks"
open(out, "w").write(head + "\n" + "\n".join(rows) + "\n")
print(f"{len(rows)} rows, {missing} missing -> {out}")
