# Collect E8 workload runs (runs/ns3_e8__<workload>__<cluster>__<variant>_<time>.log)
# into results/e8.tsv: newest run per (workload, cluster, variant).
#   python -I collect_e8.py
import glob, os, re
E = "/scratch/harshanavkis/loom-proj/e8-astrasim"
rows = {}
for log in sorted(glob.glob(os.path.join(E, "runs", "ns3_e8__*.log"))):
    m = re.match(r"ns3_e8__(.+)__(.+)__(.+)_(\d{8}_\d{6})\.log$", os.path.basename(log))
    if not m:
        continue
    wl, cl, var, t = m.groups()
    txt = open(log, errors="replace").read()
    fin = [int(x) for x in re.findall(r"sys\[\d+\] finished, (\d+) cycles", txt)]
    exp = [int(x) for x in re.findall(r"exposed communication (\d+) cycles", txt)]
    wall = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): (\S+)", txt)
    npus = re.search(r"There are (\d+) npus", txt)
    # done = every rank reported its iteration (ASTRA-sim may hang or crash in
    # its post-run statistics afterwards; the times are logged before that)
    if npus and len(fin) == int(npus.group(1)):
        status = "done"
    else:
        status = "failed" if wall else "running"
    # progress: simulated time of the newest finished flow (fct: ... start_ns fct_ns ...)
    prog = ""
    fct = glob.glob(os.path.join(log[:-4], "*fct*"))
    if fct and os.path.getsize(fct[0]) > 0:
        with open(fct[0], "rb") as f:
            f.seek(max(0, os.path.getsize(fct[0]) - 4096))
            last = f.read().decode(errors="replace").strip().splitlines()[-1].split()
        if len(last) >= 7:
            prog = int(last[5]) + int(last[6])
    rows[(wl, cl, var)] = (t, len(fin), max(fin) if fin else "", max(exp) if exp else "",
                           prog, wall.group(1) if wall else "", status, log)
os.makedirs(os.path.join(E, "results"), exist_ok=True)
out = os.path.join(E, "results", "e8.tsv")
with open(out, "w") as f:
    f.write("workload\tcluster\tvariant\tstarted\tranks_done\titer_ns\texposed_comm_ns\tsim_progress_ns\twall\tstatus\tlog\n")
    for k in sorted(rows):
        f.write("\t".join(map(str, k + rows[k])) + "\n")
print(open(out).read().rstrip())
