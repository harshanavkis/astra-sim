# Results of a jobs file (tools/run_jobs.sh): newest log per job name ->
# <jobs file>.tsv with name, ranks done / total, mean and max finish time (us).
#   python -I collect_jobs.py <jobs file>
import glob, os, re, sys
E = "/scratch/harshanavkis/loom-proj/e8-astrasim"
jobs = [l.split()[0] for l in open(sys.argv[1]) if l.strip() and not l.startswith("#")]
out = sys.argv[1] + ".tsv"
with open(out, "w") as f:
    f.write("name\tranks_done\tranks\tmean_us\tmax_us\n")
    for name in jobs:
        logs = sorted(glob.glob(os.path.join(E, "runs", f"ns3_{name}_2*.log")))
        if not logs:
            f.write(f"{name}\t0\t\t\t\n"); continue
        txt = open(logs[-1], errors="replace").read()
        fin = [int(x) for x in re.findall(r"sys\[\d+\] finished, (\d+) cycles", txt)]
        n = re.search(r"There are (\d+) npus", txt)
        mean = f"{sum(fin) / len(fin) / 1000:.2f}" if fin else ""
        mx = f"{max(fin) / 1000:.2f}" if fin else ""
        f.write(f"{name}\t{len(fin)}\t{n.group(1) if n else ''}\t{mean}\t{mx}\n")
print(out)
