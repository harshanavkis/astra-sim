#!/usr/bin/env python3
"""Fig 3's end point, the sender busy until it has issued the arrival signal (us, medians over the runs):
local and RDMA measured (steve, MTU 4096), RDMA from the NIC model, and ideal Loom from the push replay of
the local runs (Loom takes every store at once; the signal store leaves the GPU over its PCIe link behind
every data store).   sender_side.py <val_dispatch dir>   (after run_val_dispatch.sh and run_push_whatif.sh)"""
import csv, glob, os, statistics as S, sys

d = sys.argv[1]
meas = {}
for r in csv.DictReader(open(os.path.join(d, "measured.tsv")), delimiter="\t"):
    meas.setdefault((r["config"], int(r["tokens"])), []).append(r)
def sums(sub, cfg, T):
    out = {}
    for f in glob.glob(os.path.join(d, sub, f"{cfg}_r*_t{T}.out")):
        k = int(os.path.basename(f).split("_r")[-1].split("_t")[0])
        for line in open(f):
            if line.startswith("sum"):
                out[k] = [int(x) for x in line.split()[1:]]
    return out
def med(v):
    v = [x for x in v if x == x]
    return S.median(v) if v else float("nan")
def m(cfg, T, c):
    return med([float(r[c]) for r in meas[(cfg, T)] if r[c] not in ("", None)])
rows = []
for op in ["dispatch", "combine"]:
    for T in [1, 16, 128]:
        o, fl, rp = f"{op}_ordered-destL3", f"{op}_flush-warpL", f"{op}_reap_ordered-destL3"
        # flush model: the modelled drain + the GPU's measured drain -> signal time of the same run
        fm = sums("model_base", fl, T)
        flush_model = med([fm[r["run"] and int(r["run"])][2] / 1e3 + float(r["signal_us"]) - float(r["drain_end_us"])
                           for r in meas[(fl, T)] if int(r["run"]) in fm and fm[int(r["run"])][2] >= 0])
        reap_model = med([v[5] / 1e3 for v in sums("model_base", rp, T).values() if v[5] >= 0])
        loom = med([v[6] / 1e3 for v in sums("model_push_1000mhz", f"{op}_local", T).values() if len(v) > 6 and v[6] >= 0])
        rows.append((op, T, m(f"{op}_local", T, "signal_us"), m(o, T, "signal_us"), m(rp, T, "reaped_us"), reap_model,
                     m(fl, T, "signal_us"), flush_model, loom))
hdr = ["op", "tokens", "local_meas", "ordered_signal_meas", "ordered_reaped_meas", "ordered_reaped_model",
       "flush_signal_meas", "flush_signal_model", "loom_ideal_model"]
with open(os.path.join(d, "sender_side.tsv"), "w") as f:
    f.write("\t".join(hdr) + "\n")
    for r in rows:
        f.write("\t".join([r[0], str(r[1])] + [f"{x:.2f}" for x in r[2:]]) + "\n")
print(f"{'op':9}{'tok':>4}{'local':>8}{'ord sig':>9}{'reaped':>9}{'reap mod':>9}{'flush':>9}{'fl mod':>9}{'Loom':>8}")
for r in rows:
    print(f"{r[0]:9}{r[1]:4d}" + "".join(f"{x:9.2f}" for x in r[2:]))
