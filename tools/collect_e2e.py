#!/usr/bin/env python3
"""Fig 14 (At Scale "Training", Phase A 2026-10-20) data: per bar group the RDMA and Loom iteration (slowest GPU) and that
GPU's exposed communication, from the newest run log of each (run_e2e_phaseA.sh; Opus MoE rows = pilotfix runs). Refuses a
log whose first line is not "ns3 build OK" (stale-binary guard). Model results.
  python3 -I collect_e2e.py [out.tsv]     (default e8/e2e/e2e_phaseA.tsv)
"""
import glob, os, re, sys

E = "/scratch/harshanavkis/loom-proj/e8-astrasim"
GROUPS = (  # key, run name, cluster, label (n64nm = n64 with the queue monitor off: cycle-identical, verified on DP)
    ("dp", "e2e_dp", "n64nm", "DP"), ("fsdp", "e2e_fsdp", "n64nm", "FSDP"), ("pp", "e2e_pp", "n64nm", "PP"),
    ("cp", "e2e_cp", "n64nm", "CP"),
    # hybrid: trace with cross-server collectives in program order (tools/order_coll.py; the raw STAGE trace deadlocks ns-3,
    # MODEL.md 6, 2026-10-20 ~19:30)
    ("hybrid", "e2e_hybrid_ord", "n64nm", "TP+PP+DP"),
    ("l80", "e2e_l80", "n128nm", "Llama-80B"), ("moe_mixed", "pilotfix_opus_mixed_ep64", "n64nm", "MoE EP+TP+DP"),
    ("moe_scaleout", "pilotfix_opus_scaleout_ep8", "n64nm", "MoE EP+DP"), ("depth16", "e2e_depth16", "n64nm", "DP, 16 layers"))


AN = os.environ.get("AN") == "1"   # AN=1: the LoomNet analytical model (runs_an/an_*, ANALYTICAL.md)


def run(name, cl, v):
    if AN:
        name = {"e2e_hybrid_ord": "e2e_hybrid"}.get(name, name)   # the analytical model runs the STAGE trace as is
        logs = sorted(glob.glob(os.path.join(E, "runs_an", f"an_{name}__{cl}__{v}_2*.log")))
        if not logs:
            return None
        txt = open(logs[-1], errors="replace").read()
        if not txt.startswith("loomnet bin") or "loomnet: simulation finished" not in txt:
            return None
        fin = [(int(c), int(x)) for c, x in re.findall(r"sys\[\d+\] finished, (\d+) cycles, exposed communication (\d+) cycles", txt)]
        if not fin:
            return None
        it, exp = max(fin)
        return it / 1e6, exp / 1e6, len(fin), os.path.basename(logs[-1])
    logs = sorted(glob.glob(os.path.join(E, "runs", f"ns3_e8__{name}__{cl}__{v}_2*.log")))
    if not logs:
        return None
    txt = open(logs[-1], errors="replace").read()
    # 2026-10-20 16:00: in-server NVLink = bandwidth only (no port queue); only runs on that build count:
    # astra-sim-opt2 e59e7ee3 (or astra-sim-fresh default 63b98faf)
    if not (txt.startswith("ns3 build OK") and re.search(r"md5 (e59e7ee3|63b98faf)", txt.splitlines()[0])):
        return None
    if "Elapsed (wall" not in txt:
        return None
    fin = [(int(c), int(x)) for c, x in re.findall(r"sys\[\d+\] finished, (\d+) cycles, exposed communication (\d+) cycles", txt)]
    if not fin:
        return None
    it, exp = max(fin)
    return it / 1e6, exp / 1e6, len(fin), os.path.basename(logs[-1])


out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(E, "e8_an/e2e/e2e_phaseA.tsv" if AN else "e8/e2e/e2e_phaseA.tsv")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w") as f:
    f.write("key\tlabel\tvariant\titer_ms\texposed_ms\tgpus\tlog\n")
    for key, name, cl, lab in GROUPS:
        r = {v: run(name, cl, v) for v in ("rdma", "loom")}
        for v, x in r.items():
            if x:
                f.write(f"{key}\t{lab}\t{v}\t{x[0]:.3f}\t{x[1]:.3f}\t{x[2]}\t{x[3]}\n")
        if r["rdma"] and r["loom"]:
            print(f"{lab:16s} RDMA {r['rdma'][0]:9.2f} ms (exposed {r['rdma'][1]:8.2f})  Loom {r['loom'][0]:9.2f} ms "
                  f"(exposed {r['loom'][1]:8.2f})  Loom/RDMA {r['loom'][0] / r['rdma'][0]:.4f}")
        else:
            print(f"{lab:16s} pending ({', '.join(v for v in r if not r[v])})")
print(out)
