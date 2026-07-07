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
    size = "16"  # representative size for the headline grid
    fig, axes = plt.subplots(1, len(topos), figsize=(3 * len(topos), 3),
                             sharey=True)
    for ax, topo in zip(axes, topos):
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
        ax.set_title(topo, fontsize=9)
    axes[0].set_ylabel(f"Loom gain over B1 (%), {size}MB")
    save(fig, "matrix.pdf")


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
