#!/usr/bin/env python3
"""Plot the Loom experiment-suite CSVs (examples/loom/results/*.csv -> .pdf).
Requires matplotlib; skips any experiment whose CSV is missing.
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
    wall = [int(r["wall_cycles"]) / 1e3 for r in rows]
    exposed = [int(r["exposed_comm_cycles"]) / 1e3 for r in rows]
    x = range(len(rows))
    ax.bar(x, wall, 0.6, label="wall", color="#8db4e2")
    ax.bar(x, exposed, 0.6, label="exposed comm", color="#c00000")
    ax.set_xticks(x, systems, rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("kilocycles")
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
    ax.set_ylabel("victim FCT (kilocycles)")
    ax.set_title("Victim isolation: ToR egress discipline (Sim-V1)", fontsize=9)
    save(fig, "victim.pdf")


def plot_credits():
    rows = read("sweep_credits.csv")
    if not rows:
        return
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot([int(r["read_credits"]) for r in rows],
            [int(r["wall_cycles"]) / 1e3 for r in rows], "o-", color="#4472c4")
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xlabel("read credits per NPU")
    ax.set_ylabel("completion (kilocycles)")
    ax.set_title("Read-credit cap sensitivity (S-5)", fontsize=9)
    save(fig, "credits.pdf")


def plot_tpipe():
    rows = read("sweep_tpipe.csv")
    if not rows:
        return
    loom = [(int(r["t_pipe_ns"]), int(r["wall_cycles"])) for r in rows if r["system"] == "loom"]
    b1 = [int(r["wall_cycles"]) for r in rows if r["system"] == "b1_gpu_rdma"]
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot([t for t, _ in loom], [w / 1e6 for _, w in loom], "o-",
            color="#4472c4", label="Loom")
    if b1:
        ax.axhline(b1[0] / 1e6, ls="--", color="#c00000", label="B1 GPU-RDMA")
    ax.set_xscale("log")
    ax.set_xlabel("t_pipe (ns)")
    ax.set_ylabel("completion (Mcycles)")
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
    topos = sorted({r["topology"] for r in rows})
    colls = sorted({r["collective"] for r in rows})
    # every size present, not one hard-coded slice: the size dependence IS
    # the result (gain shrinks as buffers grow), and a single-size grid hid
    # both the small-message wins and the negative large-message cells.
    sizes = sorted({r["size_mb"] for r in rows}, key=int)
    fig, axes = plt.subplots(len(sizes), len(topos),
                             figsize=(3 * len(topos), 2.8 * len(sizes)),
                             sharey="row", squeeze=False)
    for i, size in enumerate(sizes):
        for j, topo in enumerate(topos):
            ax = axes[i][j]
            gains = []
            for c in colls:
                sel = {r["system"]: int(r["wall_cycles"]) for r in rows
                       if r["topology"] == topo and r["collective"] == c
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
    rows = read("p2p_sweep.csv")
    if not rows:
        return
    data = {}
    for r in rows:
        data.setdefault(r["route"], {}).setdefault(r["system"], {})[
            int(r["size_kb"])] = int(r["wall_cycles"])
    routes = [r for r in ("in_rack", "cross_rack") if r in data]
    colors = {"loom": "#70ad47", "b1_gpu_rdma": "#8db4e2",
              "b2_cpu_proxy": "#c00000"}
    # left column: absolute cost vs size (log-log) - the fixed per-op offset
    # at small sizes is the whole story. right column: gain over B1.
    fig, axes = plt.subplots(len(routes), 2, figsize=(8, 3 * len(routes)),
                             squeeze=False)
    # dashed + varied width so exactly-superimposed curves stay readable:
    # in-rack, Loom and B1 are identical BY CONSTRUCTION (same dim0 config),
    # and a reader must be able to see that rather than assume a missing line.
    style = {"loom": (2.0, "-"), "b1_gpu_rdma": (1.2, "--"),
             "b2_cpu_proxy": (1.2, "-")}
    for i, route in enumerate(routes):
        ax = axes[i][0]
        for sysname, series in sorted(data[route].items()):
            sizes = sorted(series)
            lw, ls = style.get(sysname, (1.2, "-"))
            ax.plot([s / 1024 for s in sizes], [series[s] / 1e3 for s in sizes],
                    marker="o", ms=3, lw=lw, ls=ls, label=sysname,
                    color=colors.get(sysname))
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("transfer size (MB)")
        ax.set_ylabel("kilocycles")
        ax.set_title(f"{route}: cost vs size", fontsize=9)
        if i == 0:
            ax.legend(fontsize=7)

        ax = axes[i][1]
        loom = data[route].get("loom")
        if route == "in_rack":
            # NO baseline comparison is meaningful in-rack, so none is drawn.
            # B1 is identical to Loom BY CONSTRUCTION (the model's own
            # invariant: in-rack peer access is a plain store for every
            # system), and B2 differs ONLY because --rendezvous-protocol is a
            # global flag that charges a large-message handshake to that same
            # plain store - drop the flag and B2 is byte-identical too.
            # What the in-rack route IS good for is the reference floor: the
            # same binary issuing the same store, routed locally instead of
            # across racks. That ratio is the location-transparency result.
            cross = data.get("cross_rack", {}).get("loom")
            if loom and cross:
                sizes = sorted(set(loom) & set(cross))
                ratio = [cross[s] / loom[s] for s in sizes]
                ax.plot([s / 1024 for s in sizes], ratio, marker="o", ms=3,
                        lw=1.2, color="#4472c4")
                ax.axhline(1, color="grey", lw=0.8)
                ax.set_xscale("log")
                ax.set_xlabel("transfer size (MB)")
                ax.set_ylabel("cross-rack / in-rack cost")
                ax.set_title("cost of location, same binary", fontsize=9)
                ax.annotate("No baseline comparison is drawn in-rack:\n"
                            "B1 is identical to Loom by construction\n"
                            "(in-rack is a plain store for every system), and\n"
                            "B2 differs only via the global rendezvous flag.\n"
                            "T3 supplies the empirical in-rack delta.",
                            xy=(0.03, 0.62), xycoords="axes fraction",
                            fontsize=6.5, color="#555555")
        else:
            # B1 and B2 - the two real baselines. The B3 "ideal" system was
            # removed from the suite on 2026-08-04: it is a bound, not a
            # system anyone builds, so "gain over B3" is negative by
            # definition (-160% at 4 KB) and squashed the real curves.
            for base_name, label, colour in (
                    ("b1_gpu_rdma", "vs B1 (GPU RDMA)", "#70ad47"),
                    ("b2_cpu_proxy", "vs B2 (CPU proxy)", "#c00000")):
                base = data[route].get(base_name)
                if not (loom and base):
                    continue
                sizes = sorted(set(loom) & set(base))
                gains = [100 * (base[s] - loom[s]) / base[s] for s in sizes]
                ax.plot([s / 1024 for s in sizes], gains, marker="o", ms=3,
                        lw=1.2, label=label, color=colour)
            ax.axhline(0, color="grey", lw=0.8)
            ax.set_xscale("log")
            ax.set_xlabel("transfer size (MB)")
            ax.set_ylabel("Loom gain (%)")
            ax.set_title(f"{route}: per-op cost amortizes away", fontsize=9)
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
