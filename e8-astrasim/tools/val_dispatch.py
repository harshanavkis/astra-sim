#!/usr/bin/env python3
"""Measured vs NIC model for the replayed dispatch/combine runs (tests/run_val_dispatch.sh).
  val_dispatch.py <dir> <model dir>  -> table on stdout and <model dir>/compare.tsv
Per configuration and token count, medians over the runs (us from the sender's first CTA start) of:
arr_first / arr_last (receiver sees the first / last message), drain (flush: completions all seen),
seen (receiver sees every signal), reaped (ordered + reap: every completion seen); and the median
over all messages of the per-message one-way time (arrival - post)."""
import csv, glob, os, statistics as S, sys

d, m = sys.argv[1], sys.argv[2]
meas = {}
for r in csv.DictReader(open(os.path.join(d, "measured.tsv")), delimiter="\t"):
    meas[(r["config"], int(r["run"]), int(r["tokens"]))] = r
rows = {}
for f in glob.glob(os.path.join(m, "*.out")):
    b = os.path.basename(f)[:-4]
    cfg, rk, tk = b.rsplit("_", 2)
    if cfg.endswith("_local"):
        continue  # local runs are push what-if inputs, not RDMA validation
    key = (cfg, int(rk[1:]), int(tk[1:]))
    model_msg, s = {}, None
    for line in open(f):
        x = line.split()
        if x[0] == "msg":
            model_msg[int(x[1])] = int(x[2])
        elif x[0] == "sum":
            s = [int(v) for v in x[1:]]
    ow_m, ow_x = [], []
    for line in open(os.path.join(d, "runs", b + ".meas")):
        i, post, arr = map(int, line.split())
        ow_m.append((arr - post) / 1e3)
        if model_msg.get(i, -1) >= 0:
            ow_x.append((model_msg[i] - post) / 1e3)
    r = meas[key]
    g = rows.setdefault((cfg, key[2]), {"n": 0})
    g["n"] += 1
    for name, mv, xv in [("arr_first", r["arr_first_us"], s[0]), ("arr_last", r["arr_last_us"], s[1]),
                         ("drain", r["drain_end_us"] if "flush" in cfg else "", s[2]),
                         ("seen", r["seen_us"], s[4]), ("reaped", r["reaped_us"], s[5])]:
        if mv in ("", None) or xv < 0:
            continue
        g.setdefault(name, ([], []))
        g[name][0].append(float(mv))
        g[name][1].append(xv / 1e3)
    g.setdefault("oneway", ([], []))
    g["oneway"][0].append(S.median(ow_m))
    g["oneway"][1].append(S.median(ow_x) if ow_x else float("nan"))
out = open(os.path.join(m, "compare.tsv"), "w")
out.write("config\ttokens\tquantity\tmeasured_us\tmodel_us\terr_pct\truns\n")
print(f"{'config':32} {'tok':>4} {'quantity':10} {'meas':>8} {'model':>8} {'err':>7}")
for (cfg, T) in sorted(rows, key=lambda k: (k[0], k[1])):
    g = rows[(cfg, T)]
    for q in ["arr_first", "arr_last", "drain", "oneway", "seen", "reaped"]:
        if q not in g:
            continue
        a, b = S.median(g[q][0]), S.median(g[q][1])
        e = (b - a) / a * 100
        out.write(f"{cfg}\t{T}\t{q}\t{a:.2f}\t{b:.2f}\t{e:+.1f}\t{g['n']}\n")
        print(f"{cfg:32} {T:>4} {q:10} {a:8.2f} {b:8.2f} {e:+6.1f}%")
