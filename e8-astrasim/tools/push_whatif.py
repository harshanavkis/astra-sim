#!/usr/bin/env python3
"""Summary of tests/run_push_whatif.sh: per operation and token count, medians over the runs (us) of
when the receiver has seen every signal (and the last message): measured local, RDMA ordered and flush
(measured and NIC model), and Loom push (model, 250 MHz and 1 GHz).   push_whatif.py <val_dispatch dir>"""
import csv, glob, os, statistics as S, sys

d = sys.argv[1]
meas = {}
for r in csv.DictReader(open(os.path.join(d, "measured.tsv")), delimiter="\t"):
    meas.setdefault((r["config"], int(r["tokens"])), []).append(r)
def model(sub, cfg, T, col):
    v = []
    for f in glob.glob(os.path.join(d, sub, f"{cfg}_r*_t{T}.out")):
        for line in open(f):
            if line.startswith("sum"):
                x = int(line.split()[col])
                if x >= 0:
                    v.append(x / 1e3)
    return S.median(v) if v else float("nan")
def m(cfg, T, c):
    return S.median(float(r[c]) for r in meas[(cfg, T)])
out = open(os.path.join(d, "push_whatif.tsv"), "w")
hdr = ["op", "tokens", "what", "local_meas", "ordered_meas", "ordered_model", "flush_meas", "flush_model", "push250_model", "push1000_model"]
out.write("\t".join(hdr) + "\n")
print(f"{'op':9}{'tok':>4} {'':9}{'local':>8}{'ord meas':>10}{'ord mod':>9}{'fl meas':>9}{'fl mod':>8}{'push250':>9}{'push1G':>8}")
for op in ["dispatch", "combine"]:
    for T in [1, 16, 128]:
        for what, c, col in [("seen", "seen_us", 5), ("arr_last", "arr_last_us", 2)]:
            row = [m(f"{op}_local", T, c), m(f"{op}_ordered-destL3", T, c), model("model_base", f"{op}_ordered-destL3", T, col),
                   m(f"{op}_flush-warpL", T, c), model("model_base", f"{op}_flush-warpL", T, col),
                   model("model_push_250mhz", f"{op}_local", T, col), model("model_push_1000mhz", f"{op}_local", T, col)]
            out.write(f"{op}\t{T}\t{what}\t" + "\t".join(f"{x:.2f}" for x in row) + "\n")
            print(f"{op:9}{T:4d} {what:9}" + "".join(f"{x:9.2f}" for x in row))
