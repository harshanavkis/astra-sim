#!/usr/bin/env python3
"""Preview figures of the 2026-10-21 sweeps (model; NOT paper figures): where Loom is better (blue, RDMA/Loom > 1),
equal (gray) or worse (red) than RDMA. Reads e8_an/sweep/{p2p,coll,moe}.tsv and the training sweep TSVs; writes
e8_an/sweep/preview/*.png.   python3 -I plot_sweeps.py"""
import csv, math, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, LogNorm

E = "/scratch/harshanavkis/loom-proj/e8-astrasim"
S = f"{E}/e8_an/sweep"
P = f"{S}/preview"
os.makedirs(P, exist_ok=True)
CMAP = LinearSegmentedColormap.from_list("loom", ["#e34948", "#f0efec", "#2a78d6"])   # worse / equal / better
NORM = LogNorm(vmin=0.5, vmax=2.0)
INK, MUTED = "#222222", "#666666"
plt.rcParams.update({"font.size": 8, "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED,
                     "ytick.color": MUTED})


def size_label(b):
    b = int(b)
    return f"{b} B" if b < 1024 else f"{b // 1024} KiB" if b < 1 << 20 else f"{b >> 20} MiB"


def heat(ax, M, rows, cols, title, xlabel, ylabel):
    ax.imshow([[max(min(v, 1e3), 1e-3) for v in r] for r in M], cmap=CMAP, norm=NORM, aspect="auto")
    for i, r in enumerate(M):
        for j, v in enumerate(r):
            ax.text(j, i, "inf" if v > 999 else f"{v:.2f}" if v < 10 else f"{v:.0f}", ha="center", va="center",
                    fontsize=6, color=INK)
    ax.set_xticks(range(len(cols)), cols, rotation=45, ha="right")
    ax.set_yticks(range(len(rows)), rows)
    ax.set_title(title, fontsize=8, color=INK)
    ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
    for s in ax.spines.values():
        s.set_visible(False)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(f"{P}/{name}.png", dpi=160)
    plt.close(fig)
    print(f"{P}/{name}.png")


def p2p():
    R = {(r["rate"], r["variant"], int(r["bytes"])): r for r in csv.DictReader(open(f"{S}/p2p.tsv"), delimiter="\t")}
    sizes = sorted({k[2] for k in R})
    rates = ["100", "200", "400", "800", "1600"]

    def ratio(rate, s, a, b, key, inv=False):   # a = RDMA variant, b = Loom variant; > 1: Loom better
        x, y = float(R[(rate, a, s)][key]), float(R[(rate, b, s)][key])
        return y / x if inv else x / max(y, 1e-9)
    for name, a, b in (("p2p", "rdma", "loom"), ("p2p_loombuf", "rdma", "loom_buf")):
        fig, axs = plt.subplots(1, 2, figsize=(9, 2.8))
        for ax, (key, inv, t) in zip(axs, (("deliv_ns", False, "(a) delivery"), ("released_ns", False, "(b) sender released"))):
            M = [[ratio(r, s, a, b, key, inv) for s in sizes] for r in rates]
            heat(ax, M, [f"{r} Gbps" for r in rates], [size_label(s) for s in sizes], f"{t}, {a} vs {b}", "message size", "link rate")
        save(fig, name)


def coll():
    R = {(r["op"], int(r["n"][1:]), int(r["size"][1:]), r["variant"]): float(r["time_us"])
         for r in csv.DictReader(open(f"{S}/coll.tsv"), delimiter="\t")}
    sizes = sorted({k[2] for k in R}); ns = sorted({k[1] for k in R})
    ops = ("ALL_REDUCE", "REDUCE_SCATTER", "ALL_GATHER", "ALL_TO_ALL")
    fig, axs = plt.subplots(1, 4, figsize=(16, 2.8))
    for ax, op in zip(axs, ops):
        rows = [str(n) for n in ns]
        M = [[R[(op, n, s, "rdma")] / R[(op, n, s, "loom")] for s in sizes] for n in ns]
        heat(ax, M, rows, [size_label(s) for s in sizes], f"{op.lower().replace('_', '-')}, RDMA/Loom", "bytes per GPU", "GPUs")
    save(fig, "coll")


def moe():
    f = f"{S}/moe.tsv"
    if not os.path.exists(f):
        return
    R = {(r["op"], int(r["ep"][2:]), int(r["tokens"][1:]), r["variant"]): r for r in csv.DictReader(open(f), delimiter="\t")}
    eps = sorted({k[1] for k in R}); toks = sorted({k[2] for k in R})
    fig, axs = plt.subplots(2, 2, figsize=(10, 5))
    for i, op in enumerate(("dispatch", "combine")):
        for j, (key, var, t) in enumerate((("released_us", "loom", "sender released"), ("delivered_us", "loom", "delivered"))):
            M = [[float(R[(op, e, t_, "rdma")][key]) / float(R[(op, e, t_, var)][key]) if (op, e, t_, var) in R else float("nan")
                  for t_ in toks] for e in eps]
            heat(axs[i][j], M, [f"EP{e}" for e in eps], [str(t_) for t_ in toks], f"{op} {t}, RDMA/Loom", "tokens per GPU", "")
    save(fig, "moe")


def train():
    rows = []
    for f in (f"{S}/train_dense.tsv", f"{S}/train_moe.tsv"):
        if os.path.exists(f):
            rows += [r for r in csv.DictReader(open(f), delimiter="\t") if r["rdma_ms"] not in ("MISSING", "")]
    if not rows:
        return
    fig, ax = plt.subplots(figsize=(7, 0.16 * len(rows) + 1.2))
    y = list(range(len(rows)))[::-1]
    ax.axvspan(0.99, 1.01, color="#f0efec")
    ax.axvline(1.0, color=MUTED, lw=0.8)
    for col, color, mk, lab in (("rdma_over_loom_buf", "#9ebfe9", "s", "Loom, transmit buffer = ACK window"),
                                ("rdma_over_loom", "#2a78d6", "o", "Loom (paper model)")):
        pts = [(float(r[col]), yy) for r, yy in zip(rows, y) if r.get(col)]
        ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=14, color=color, marker=mk, label=lab, zorder=3)
    ax.set_yticks(y, [f"{r['name']} ({r['cluster']}, comm {r['rdma_exposed_pct']}%)" for r in rows], fontsize=6)
    ax.set_xlabel("iteration time RDMA / Loom (model; > 1: Loom faster; gray band = within 1%)")
    ax.legend(loc="lower left", fontsize=6, frameon=False)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    save(fig, "train")


p2p(); coll(); moe(); train()
