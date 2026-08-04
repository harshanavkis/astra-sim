#!/usr/bin/env python3
"""Plot the Loom experiment-suite CSVs (examples/loom/results/*.csv -> .pdf).
Requires matplotlib; skips any experiment whose CSV is missing.

Axes are in TIME, not "cycles". The analytical backend ticks 1 cycle = 1 ns
(verified against the model: in-rack 4 KB p2p is 8472 cycles for 8 iters =
1059 ns each, vs 2x500 ns dim0 + 4 KiB/64 GiB/s = 1059.6 ns predicted), so
every cycle count here is divided into us/ms rather than reported raw.
"""

import collections
import csv
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def read(name):
    path = os.path.join(RES, name)
    if not os.path.exists(path):
        print(f"skip: {name} not found")
        return None
    with open(path) as f:
        return list(csv.DictReader(f))


WRITTEN = []


def save(fig, name):
    out = os.path.join(RES, name)
    WRITTEN.append(name)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}")


def plot_smoke():
    rows = read("smoke.csv")
    if not rows:
        return
    fig, ax = plt.subplots(figsize=(4, 3))
    systems = [r["system"] for r in rows]
    wall = [int(r["wall_cycles"]) / 1e3 for r in rows]        # ns -> us
    exposed = [int(r["exposed_comm_cycles"]) / 1e3 for r in rows]
    x = range(len(rows))
    ax.bar(x, wall, 0.6, label="wall", color="#8db4e2")
    ax.bar(x, exposed, 0.6, label="exposed comm", color="#c00000")
    ax.set_xticks(x, systems, rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("time (us)")
    ax.set_title("Shipped all-to-all microbench (comm-only)", fontsize=9)
    ax.legend(fontsize=8)
    save(fig, "smoke.pdf")


def plot_victim():
    rows = read("victim.csv")
    if not rows:
        return
    fig, ax = plt.subplots(figsize=(4, 3))
    cases = [r["case"] for r in rows]
    fct = [int(r["victim_fct_cycles"]) / 1e3 for r in rows]
    colors = ["#70ad47", "#70ad47", "#c00000"]
    ax.bar(cases, fct, 0.6, color=colors[: len(rows)])
    for i, v in enumerate(fct):
        ax.text(i, v, f"{v:.0f}", ha="center", va="bottom", fontsize=8)
    ax.set_ylabel("victim FCT (us)")
    ax.set_title("Victim isolation: ToR egress discipline (Sim-V1)", fontsize=9)
    save(fig, "victim.pdf")


def plot_credits():
    rows = read("sweep_credits.csv")
    if not rows:
        return
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot([int(r["read_credits"]) for r in rows],
            [int(r["wall_cycles"]) / 1e3 for r in rows], "o-", color="#4472c4")  # ns -> us
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xlabel("read credits per NPU")
    ax.set_ylabel("completion time (us)")
    ax.set_title("Read-credit cap sensitivity (S-5)", fontsize=9)
    save(fig, "credits.pdf")


def plot_tpipe():
    rows = read("sweep_tpipe.csv")
    if not rows:
        return
    loom = [(int(r["t_pipe_ns"]), int(r["wall_cycles"])) for r in rows if r["system"] == "loom"]
    b1 = [int(r["wall_cycles"]) for r in rows if r["system"] == "b1_gpu_rdma"]
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot([t for t, _ in loom], [w / 1e6 for _, w in loom], "o-",  # ns -> ms
            color="#4472c4", label="Loom")
    if b1:
        ax.axhline(b1[0] / 1e6, ls="--", color="#c00000", label="B1 GPU-RDMA")
    ax.set_xscale("log")
    ax.set_xlabel("t_pipe (ns)")
    ax.set_ylabel("completion time (ms)")
    ax.set_title("Switch-latency sensitivity, STG MoE (S-1)", fontsize=9)
    ax.legend(fontsize=8)
    save(fig, "tpipe.pdf")


def plot_regime():
    rows = read("regime_map.csv")
    if not rows:
        return
    fig, ax = plt.subplots(figsize=(4, 3))
    x = [float(r["loom_exposed_comm_pct"]) for r in rows]
    y = [float(r["gain_pct"]) for r in rows]
    ax.plot(x, y, "o-", color="#4472c4")
    ax.axhline(0, ls=":", color="grey")
    ax.axhline(100 * (1 - 839 / 989), ls="--", color="#70ad47",
               label="SM-reclamation ceiling")
    ax.set_xlabel("exposed communication (% of wall time)")
    ax.set_ylabel("Loom gain over B1 (%)")
    ax.set_title("Regime map: where Loom wins", fontsize=9)
    ax.legend(fontsize=8)
    save(fig, "regime.pdf")


def plot_matrix():
    rows = read("matrix.csv")
    if not rows:
        return
    clusters = sorted({r["cluster"] for r in rows}, key=lambda c: int(c.split("gpu")[0]))
    colls = sorted({r["collective"] for r in rows})
    # every size present, not one hard-coded slice: the size dependence IS
    # the result (gain shrinks as buffers grow), and a single-size grid hid
    # both the small-message wins and the negative large-message cells.
    sizes = sorted({r["size_mb"] for r in rows}, key=int)
    fig, axes = plt.subplots(len(sizes), len(clusters),
                             figsize=(3 * len(clusters), 2.8 * len(sizes)),
                             sharey="row", squeeze=False)
    for i, size in enumerate(sizes):
        for j, topo in enumerate(clusters):
            ax = axes[i][j]
            gains = []
            for c in colls:
                sel = {r["system"]: int(r["wall_cycles"]) for r in rows
                       if r["cluster"] == topo and r["collective"] == c
                       and r["size_mb"] == size}
                gains.append(100 * (sel["b1_gpu_rdma"] - sel["loom"]) / sel["b1_gpu_rdma"]
                             if "loom" in sel and "b1_gpu_rdma" in sel else 0)
            colors = ["#70ad47" if g >= 0 else "#c00000" for g in gains]
            ax.bar(range(len(colls)), gains, 0.6, color=colors)
            ax.axhline(0, color="grey", lw=0.8)
            ax.set_xticks(range(len(colls)),
                          [c.replace("_", "\n") for c in colls], fontsize=7)
            if i == 0:
                ax.set_title(topo, fontsize=9)
        axes[i][0].set_ylabel(f"gain over B1 (%)\n{size} MB", fontsize=8)
    fig.tight_layout()
    save(fig, "matrix.pdf")


def plot_p2p():
    """M2: cross-rack p2p cost and its per-op amortization.

    Two panels, cross-rack only, because cross-rack is the only route with a
    meaningful baseline comparison: in-rack, Loom and B1 are identical by
    construction (in-rack peer access is a plain store for every system) and
    B2 differed only via the global rendezvous flag. Loom's in-rack curve is
    still drawn in panel 1 as the reference floor - same binary, same store,
    routed locally - but nothing is compared against it.

    Time, not "cycles": this backend ticks 1 cycle = 1 ns. Checked against
    the model both ways - in-rack 4 KB is 8472 for 8 iterations = 1059 ns
    each vs 2x500 ns dim0 + 4 KiB/64 GiB/s = 1059.6 ns predicted, and
    cross-rack 1 GB is 168.98e6 vs 168.4e6 predicted from bandwidth alone.
    """
    rows = read("p2p_sweep.csv")
    if not rows:
        return
    data = {}
    for r in rows:
        data.setdefault(r["route"], {}).setdefault(r["system"], {})[
            int(r["size_kb"])] = int(r["wall_cycles"])
    if "cross_rack" not in data:
        return
    NS_PER_ITER = 8  # run_p2p_sweep.sh --iters; report per-transfer time

    def us(cycles):  # cycles are ns; report microseconds per transfer
        return cycles / 1e3 / NS_PER_ITER

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4))

    ax = axes[0]
    for sysname, label, colour, lw, ls in (
            ("loom", "Loom (cross-rack)", "#70ad47", 2.0, "-"),
            ("b1_gpu_rdma", "B1 GPU-initiated RDMA", "#8db4e2", 1.4, "--"),
            ("b2_cpu_proxy", "B2 CPU proxy", "#c00000", 1.4, "-")):
        series = data["cross_rack"].get(sysname)
        if not series:
            continue
        sizes = sorted(series)
        ax.plot([s / 1024 for s in sizes], [us(series[s]) for s in sizes],
                marker="o", ms=3, lw=lw, ls=ls, label=label, color=colour)
    floor = data.get("in_rack", {}).get("loom")
    if floor:
        sizes = sorted(floor)
        ax.plot([s / 1024 for s in sizes], [us(floor[s]) for s in sizes],
                lw=1.0, ls=":", color="#555555",
                label="Loom in-rack (reference floor)")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("transfer size (MB)")
    ax.set_ylabel("time per transfer (us)")
    ax.set_title("Cross-rack send/recv cost", fontsize=9)
    ax.legend(fontsize=7)

    ax = axes[1]
    loom = data["cross_rack"].get("loom")
    for base_name, label, colour in (("b1_gpu_rdma", "vs B1 (GPU RDMA)", "#70ad47"),
                                     ("b2_cpu_proxy", "vs B2 (CPU proxy)", "#c00000")):
        base = data["cross_rack"].get(base_name)
        if not (loom and base):
            continue
        sizes = sorted(set(loom) & set(base))
        ax.plot([s / 1024 for s in sizes],
                [100 * (base[s] - loom[s]) / base[s] for s in sizes],
                marker="o", ms=3, lw=1.2, label=label, color=colour)
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_xscale("log")
    ax.set_xlabel("transfer size (MB)")
    ax.set_ylabel("Loom gain (%)")
    ax.set_title("Per-operation cost amortizes away", fontsize=9)
    ax.legend(fontsize=7)
    save(fig, "p2p.pdf")



def plot_scale():
    rows = read("scale_sweep.csv")
    if not rows:
        return
    d = collections.defaultdict(dict)
    for r in rows:
        d[(int(r["gpus"]), r["collective"], r["size_mb"])][r["system"]] = \
            int(r["wall_cycles"])
    combos = sorted({(k[1], k[2]) for k in d}, key=lambda t: (t[0], int(t[1])))
    gpus = sorted({k[0] for k in d})
    fig, ax = plt.subplots(figsize=(5, 3.4))
    for (coll, size), colour in zip(combos, ["#70ad47", "#4472c4",
                                             "#c00000", "#ed7d31"]):
        xs, ys = [], []
        for g in gpus:
            v = d.get((g, coll, size))
            if not v or "loom" not in v or "b1_gpu_rdma" not in v:
                continue
            xs.append(g)
            ys.append(100 * (v["b1_gpu_rdma"] - v["loom"]) / v["b1_gpu_rdma"])
        ax.plot(xs, ys, marker="o", ms=3, lw=1.4, color=colour,
                label=f"{coll} {size} MB")
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_xscale("log", base=2)
    ax.set_xticks(gpus, [str(g) for g in gpus])  # actual GPU counts, not 2^n
    ax.minorticks_off()
    ax.set_xlabel("cluster size (GPUs, 8 per rack)")
    ax.set_ylabel("Loom gain over B1 (%)")
    ax.set_title("Benefit grows with cluster width", fontsize=9)
    ax.legend(fontsize=7)
    save(fig, "scale.pdf")


def plot_sm():
    rows = read("sm_sweep.csv")
    if not rows:
        return
    d = collections.defaultdict(dict)
    for r in rows:
        d[(r["app"], int(r["reserved_sms"]))][r["system"]] = (
            int(r["wall_cycles"]), int(r["exposed_comm"]))
    apps = sorted({r["app"] for r in rows})
    ks = sorted({int(r["reserved_sms"]) for r in rows})
    fig, ax = plt.subplots(figsize=(5, 3.4))
    for app, colour in zip(apps, ["#4472c4", "#70ad47", "#c00000"]):
        xs, wall, comm = [], [], []
        for k in ks:
            v = d.get((app, k))
            if not v or "loom" not in v:
                continue
            lw, le = v["loom"]
            bw, be = v["b1_gpu_rdma"]
            xs.append(k)
            wall.append(100 * (bw - lw) / bw)
            comm.append(100 * (be - le) / be)
        ax.plot(xs, wall, marker="o", ms=4, lw=1.6, color=colour, label=f"{app} wall")
        ax.plot(xs, comm, marker="s", ms=3, lw=1.0, ls="--", color=colour,
                alpha=0.6, label=f"{app} exposed comm")
    ax.axvline(20, color="grey", lw=0.8, ls=":")
    ax.annotate("DeepSeek-V3\nreserves 20", xy=(20, ax.get_ylim()[1] * 0.55),
                fontsize=6.5, color="#555555", ha="center")
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_xlabel("SMs reserved for communication by the baseline (of 132)")
    ax.set_ylabel("Loom gain over B1 (%)")
    ax.set_title("k=0 isolates the pure communication benefit", fontsize=9)
    ax.legend(fontsize=6.5)
    save(fig, "sm.pdf")


def plot_domain():
    rows = read("domain_sweep.csv")
    if not rows:
        return
    d = collections.defaultdict(dict)
    for r in rows:
        d[(int(r["xpus_per_rack"]), r["collective"], r["size_mb"])][r["system"]] = \
            int(r["wall_cycles"])
    doms = sorted({k[0] for k in d})
    combos = sorted({(k[1], k[2]) for k in d}, key=lambda t: (t[0], int(t[1])))
    total = int(rows[0]["gpus"])
    fig, ax = plt.subplots(figsize=(5, 3.4))
    width = 0.8 / len(combos)
    for i, (coll, size) in enumerate(combos):
        ys = []
        for m in doms:
            v = d.get((m, coll, size))
            ys.append(100 * (v["b1_gpu_rdma"] - v["loom"]) / v["b1_gpu_rdma"]
                      if v else 0)
        ax.bar([x + i * width for x in range(len(doms))], ys, width,
               label=f"{coll} {size} MB")
    ax.set_xticks([x + 0.4 - width / 2 for x in range(len(doms))],
                  [f"{m}/rack\n({total // m} racks)" for m in doms], fontsize=8)
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_ylabel("Loom gain over B1 (%)")
    ax.set_title(f"Bigger scale-up domains shrink the comm win ({total} GPUs)",
                 fontsize=9)
    ax.legend(fontsize=6.5)
    save(fig, "domain.pdf")


def plot_apps():
    rows = read("apps.csv")
    if not rows:
        return
    labels, gains = [], []
    apps = sorted({(r["app"], r["ranks"]) for r in rows}, key=lambda t: (t[0], int(t[1])))
    for app, ranks in apps:
        sel = {r["system"]: int(r["wall_cycles"]) for r in rows
               if r["app"] == app and r["ranks"] == ranks}
        if "loom" in sel and "b1_gpu_rdma" in sel:
            labels.append(f"{app}\n{ranks} ranks")
            gains.append(100 * (sel["b1_gpu_rdma"] - sel["loom"]) / sel["b1_gpu_rdma"])
    fig, ax = plt.subplots(figsize=(4.5, 3))
    colors = ["#70ad47" if g >= 0 else "#c00000" for g in gains]
    ax.bar(range(len(labels)), gains, 0.6, color=colors)
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_xticks(range(len(labels)), labels, fontsize=7)
    ax.set_ylabel("Loom gain over B1 (%)")
    ax.set_title("Applications (published shapes, roofline)", fontsize=9)
    save(fig, "apps.pdf")


FIGURE_NOTES = {
 "p2p.pdf": ("M2 point-to-point sweep",
  "One send/recv pair, 4 KB-1 GB, 8 iterations, 2 racks x 8 XPUs. Loom vs B1 (GPU-initiated RDMA) and B2 (CPU proxy). `run_p2p_sweep.sh`.",
  "Left: time per transfer (us, log-log). Right: Loom gain (%) vs size.",
  "The ONLY experiment with no collective chunk-overlap, so the fixed per-operation cost Loom removes is directly visible; the gain decays to zero as the transfer grows and that cost amortizes. The in-rack curve is a reference FLOOR only - no baseline is compared against it, because B1 is identical to Loom by construction (in-rack is a plain store for every system) and B2 differed only via the global rendezvous flag."),
 "scale.pdf": ("A5 cluster-scale sweep",
  "8 XPUs/rack FIXED (the deployed scale-up domain); RACK COUNT swept 2..64 = 16..512 GPUs; all_reduce and all_to_all at 1 and 64 MB. `run_scale_sweep.sh`.",
  "Loom gain over B1 (%) vs cluster size.",
  "Loom's benefit is a FUNCTION OF CLUSTER WIDTH - no single gain number is meaningful without stating the scale. A hierarchical collective spreads a roughly constant dim1 byte count over 2(r-1) steps, so per-step bytes fall as ~1/r while per-step latency is fixed: few racks = few fat steps = bandwidth-bound and Loom's latency edge is hidden; many racks = many thin steps = latency-bound and Loom wins. Exact +0.00% points at small rack counts are that hiding, NOT parity."),
 "sm.pdf": ("A6 SM-reservation sweep",
  "There is no SM in ASTRA-sim: the tax is a roofline derating, peak_perf = 989*(132-k)/132, applied to the BASELINE only. k swept 0/8/20/32; k=20 is DeepSeek-V3's disclosed reservation. `run_sm_sweep.sh`.",
  "Loom gain over B1 (%) vs reserved SMs. Solid = wall, dashed = exposed comm (overlap-dependent, not pure comm time).",
  "k=0 isolates the PURE communication benefit. The dense LLM's is ~zero (+0.02%), so its entire gain is SM reclamation; MoE is carried by communication (+13.90% at k=0) with reclamation adding ~1.4pp - quote them separately. Caveat: perf is a min(), so only compute-bound nodes are derated and the compute gain lands below the ideal k/132; the model UNDER-states the SM tax (MEMBW=1 recovers exactly 15.15% at k=20)."),
 "domain.pdf": ("Scale-up domain-size sweep (the NVL72 question)",
  "Cluster held CONSTANT at 576 GPUs while the scale-up domain grows: 8/rack (HGX) -> 36 (NVL36) -> 72 (NVL72), so racks shrink 72 -> 16 -> 8. `run_domain_sweep.sh`.",
  "Loom gain over B1 (%) per collective and size, grouped by domain size.",
  "Runs AGAINST Loom's communication differential and must not be dropped. At a fixed cluster size, NVL72-class racks erase the comm win almost entirely. It BOUNDS which argument carries the paper in which deployment rather than refuting it: SM reclamation is topology-independent (+10.72% either way), Loom is never worse than B1 (the floor is parity), and the removal of QPs/keys/buffers from the accelerator is not modelled here at all."),
 "matrix.pdf": ("Collective matrix",
  "Cluster size x collective x buffer size; one physical topology [Switch, Switch], 8 XPUs/rack. `run_matrix.sh`.",
  "Loom gain over B1 (%), one panel row per buffer size, green positive / red negative.",
  "Gains fall as buffers grow because Loom's advantage is per-operation. Cells reading exactly +0.000% are NOT wins: there the model hides dim1 latency for both systems and dim0 is identical by construction, so nothing can differ."),
 "apps.pdf": ("End-to-end applications",
  "STG-generated Mixtral 8x7B and GPT-3 175B iterations at 16-256 ranks, 8 XPUs/rack, roofline configs carrying the k=20 SM tax. `run_apps.sh`.",
  "Loom gain over B1 (%) per app and rank count.",
  "MoE improves with scale (EP all-to-all is per-operation bound); dense is bandwidth-bound and gains almost nothing on communication. Measured: taking rdma_init 0 -> 2400 ns changes B1's exposed comm by +38.4% for mixtral but only +0.06% for gpt3."),
 "smoke.pdf": ("Endpoint-model sanity check",
  "4-NPU 1 MB all-to-all on the repo's shipped ETs, 2 racks x 2. `run_smoke.sh`.",
  "Wall and exposed-comm time (us) per system.",
  "A canary, not a result: the ordering Loom < B1 < B2 is the check. It caught a real bug - until 2026-08-04 this was the only script reading static configs, which had rotted to a model in which Loom was slower."),
 "credits.pdf": ("M5 read-credit cap",
  "4 ranks x 64 independent 4 KB peer reads through LOOM_PEER_READS; caps 1..64 plus uncapped. `run_sweep_credits.sh`.",
  "Completion time (us) vs credits per NPU, log-log.",
  "A mechanism proof, not a benchmark: exact linear 1/N scaling and the uncapped point collapsing onto the 64-credit point are arithmetic predictions, and matching them exactly is the verification."),
 "tpipe.pdf": ("t_pipe break-even (STANDALONE)",
  "Loom's source-pipeline latency swept against a fixed B1. `run_sweep_tpipe.sh`; not in the default suite.",
  "Completion time (ms) vs t_pipe, with B1 as a horizontal line.",
  "Optional reviewer-proofing; T3 will MEASURE t_pipe and retire it. Its durable use is showing the design tolerates a slow FPGA clock."),
 "regime.pdf": ("Regime map (STANDALONE)",
  "Compute intensity scaled with the SM ratio pinned. `run_regime_map.sh`; not in the default suite.",
  "Loom gain over B1 (%) vs exposed-communication fraction.",
  "Runs --pipe-ns 500, so its Loom is NOT the Loom of the other experiments - rerun before quoting. Largely superseded by the apps gain decomposition, which uses real published workloads for free."),
}


def write_figures_md():
    """Regenerate results/FIGURES.md for exactly the figures just produced."""
    out = ["# Figures - what each plot shows", "",
           "> GENERATED by `plot_results.py`; overwritten every time the plots",
           "> are regenerated. Do not hand-edit. The NUMBERS live in CHECKPOINT",
           "> section 5 (generated by `summarize_results.py` from the same",
           "> CSVs); this file explains what the figures MEAN.", ""]
    for name in WRITTEN:
        note = FIGURE_NOTES.get(name)
        if not note:
            continue
        title, method, metric, reading = note
        out += [f"## `{name}` - {title}", "",
                f"- **Methodology.** {method}",
                f"- **Metric.** {metric}",
                f"- **Reading.** {reading}", ""]
    path = os.path.join(RES, "FIGURES.md")
    with open(path, "w") as fh:
        fh.write("\n".join(out))
    print(f"wrote {path}")


if __name__ == "__main__":
    os.makedirs(RES, exist_ok=True)
    plot_smoke()
    plot_victim()
    plot_credits()
    plot_tpipe()
    plot_regime()
    plot_matrix()
    plot_apps()
    plot_p2p()
    plot_scale()
    plot_sm()
    plot_domain()
    write_figures_md()
