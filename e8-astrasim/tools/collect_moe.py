#!/usr/bin/env python3
"""Results of run_moe.sh: per job (newest log per name), over the GPUs, the median and maximum of the
last send release (the sender busy until it may reuse its buffers) and the last arrival (dispatch /
combine delivered), us; then RDMA vs Loom side by side.   collect_moe.py <jobs file>  -> <dir>/moe.tsv"""
import glob, os, re, statistics as S, sys

jobs = [l.split()[0] for l in open(sys.argv[1]) if l.strip()]
E = "/scratch/harshanavkis/loom-proj/e8-astrasim"
res = {}
for name in jobs:
    logs = sorted(glob.glob(os.path.join(E, os.environ.get("LOGS", "runs/ns3_") + f"{name}_2*.log")))  # LOGS=runs_an/an_: analytical model
    if not logs:
        continue
    rel, rcv = [], []
    for line in open(logs[-1], errors="replace"):
        m = re.match(r"loom_rank (\d+) sends_released_ns (\d+) last_recv_ns (\d+)", line)
        if m:
            rel.append(int(m[2]) / 1e3); rcv.append(int(m[3]) / 1e3)
    _, op, ep, t, v = name.split("__")
    res[(op, int(ep[2:]), int(t[1:]), v)] = (len(rel), rel, rcv)
out = open(os.path.join(os.path.dirname(sys.argv[1]), "moe.tsv"), "w")
out.write("op\tep\ttokens\tvariant\tranks\tsend_med_us\tsend_max_us\trecv_med_us\trecv_max_us\n")
print(f"{'op':9}{'EP':>5}{'tok':>5}   {'sender busy (max GPU)':>24}   {'delivered (last GPU)':>24}")
print(f"{'':19}   {'rdma':>8}{'loom':>8}{'x':>7}   {'rdma':>8}{'loom':>8}{'x':>7}")
for (op, ep, t) in sorted({k[:3] for k in res}, key=lambda k: (k[0] != "dispatch", k[1], k[2])):
    row = {}
    for v in ["rdma", "loom"]:
        if (op, ep, t, v) in res:
            n, rel, rcv = res[(op, ep, t, v)]
            if n:
                row[v] = (max(rel), max(rcv))
                out.write(f"{op}\t{ep}\t{t}\t{v}\t{n}\t{S.median(rel):.2f}\t{max(rel):.2f}\t{S.median(rcv):.2f}\t{max(rcv):.2f}\n")
    if "rdma" in row and "loom" in row:
        r, l = row["rdma"], row["loom"]
        print(f"{op:9}{ep:5d}{t:5d}   {r[0]:8.1f}{l[0]:8.1f}{r[0] / max(l[0], 1e-3):6.1f}x   {r[1]:8.1f}{l[1]:8.1f}{r[1] / max(l[1], 1e-3):6.1f}x")
