#!/usr/bin/env python3
"""Plot the Loom experiment-suite CSVs (examples/loom/results/*.csv -> .pdf).
Requires matplotlib; skips any experiment whose CSV is missing.

Axes are in TIME, not "cycles". The analytical backend ticks 1 cycle = 1 ns
(verified against the model: in-rack 4 KB p2p is 8472 cycles for 8 iters =
1059 ns each, vs 2x500 ns dim0 + 4 KiB/64 GiB/s = 1059.6 ns predicted), so
every cycle count here is divided into us/ms rather than reported raw.
"""

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


def save(fig, name):
    out = os.path.join(RES, name)
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
