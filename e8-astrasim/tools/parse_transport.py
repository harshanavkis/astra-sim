# Parse ~/loom-experiments/transport-val (steve perftest runs) into
# tests/transport_measured.tsv: test, series, size, value (median over repeats), unit.
#   python -I parse_transport.py
import os, re, statistics, collections
S = os.path.expanduser("~/loom-experiments/transport-val")
OUT = "/scratch/harshanavkis/loom-proj/e8-astrasim/tests/transport_measured.tsv"
rows = []
# T1: ib_write_lat -a, three repeats per series; column 5 = t_typical (us, one-way)
lat = collections.defaultdict(list); series = None
for l in open(os.path.join(S, "t1_lat.txt")):
    m = re.match(r"# T1 rep \d+ \S+ (.*)$", l)
    if m: series = m.group(1).replace("memory ", "").replace(" ", "_").replace("(", "").replace(")", ""); continue
    f = l.split()
    if series and len(f) >= 5 and f[0].isdigit() and f[1].isdigit():
        lat[(series, int(f[0]))].append(float(f[4]))
for (s, size), v in sorted(lat.items()):
    rows.append(("T1_latency", s, size, statistics.median(v), "us"))
# T2: ib_write_bw -a; column 4 = BW average (MiB/s) -> GB/s
series = None
for l in open(os.path.join(S, "t2_bw.txt")):
    m = re.match(r"# T2 \S* ?GPU memory, (\d+) QPs?", l)
    if m: series = f"gpu_{m.group(1)}qp"; continue
    f = l.split()
    if series and len(f) >= 5 and f[0].isdigit() and f[1].isdigit():
        rows.append(("T2_bandwidth", series, int(f[0]), float(f[3]) * 1.048576 / 1000, "GB/s"))
# T3: QP sweep
size = q = None
for l in open(os.path.join(S, "t3_qps.txt")):
    m = re.match(r"# T3 size (\d+) qps (\d+)", l)
    if m: size, q = int(m.group(1)), int(m.group(2)); continue
    f = l.split()
    if size and len(f) >= 5 and f[0] == str(size) and f[1].isdigit():
        rows.append(("T3_qps", f"gpu_{size}B", q, float(f[3]) * 1.048576 / 1000, "GB/s"))
# T4: latency idle vs loaded
state = None
for l in open(os.path.join(S, "t4_lat_load.txt")):
    if l.startswith("# T4"): state = "idle" if "idle" in l else "loaded"; continue
    f = l.split()
    if state and len(f) >= 5 and f[0].isdigit() and f[1].isdigit():
        rows.append(("T4_latency", f"gpu_{state}", int(f[0]), float(f[4]), "us"))
with open(OUT, "w") as o:
    o.write("test\tseries\tsize\tvalue\tunit\n")
    for r in rows:
        o.write("\t".join(map(str, r[:3])) + f"\t{r[3]:.3f}\t{r[4]}\n")
print(OUT, len(rows), "rows")
