#!/usr/bin/env python3
"""PREVIEW of a new Fig 14 (training sweeps, model; NOT in the paper): one panel per varied parameter, Opus-style bar pairs
(RDMA | Loom, slowest GPU's iteration normalised to RDMA, solid = compute, hatched = that GPU's exposed communication),
Loom vs RDMA in % above each pair. Data: newest runs_an/an_sw_<name>__<cluster>__{rdma,loom}_*.log (as tools/sweep_collect.py).
   python3 -I fig14_preview.py <out.png>"""
import glob, os, re, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.transforms import blended_transform_factory

E = "/scratch/harshanavkis/loom-proj/e8-astrasim"
SYSTEMS = {"rdma": ("RDMA (pull)", "tab:blue"), "loom": ("Loom (push)", "tab:green")}


def run(name, cl, v):
    logs = sorted(glob.glob(f"{E}/runs_an/an_sw_{name}__{cl}__{v}_2*.log"))
    if not logs:
        return None
    txt = open(logs[-1], errors="replace").read()
    if "loomnet: simulation finished" not in txt:
        return None
    fin = [(int(c), int(x)) for c, x in re.findall(r"sys\[\d+\] finished, (\d+) cycles, exposed communication (\d+) cycles", txt)]
    return (max(fin)[0] / 1e6, max(fin)[1] / 1e6, txt.splitlines()[0].split()[2]) if fin else None


N, M = "n64nm", "n64nm"
# panel: (title, [(group label, [(name, cluster, tick, nominal)])])
PANELS = [
    ("(a) Parallelism", [("", [("dp", N, "DP", 0), ("fsdp", N, "FSDP", 0), ("cp", N, "CP 32K", 0), ("pp", N, "PP", 0),
                               ("hybrid", N, "TP+PP+DP", 0), ("l80", "n128nm", "TP+PP+DP 80B", 0),
                               ("moe_mixed_ep64", M, "MoE EP+TP+DP", 0), ("moe_scaleout_ep8", M, "MoE EP+DP", 0)])]),
    ("(b) Micro-batch", [("PP", [(f"pp_mb{m}" if m != 8 else "pp", N, str(m), m == 8) for m in (1, 2, 4, 8, 16)]),
                         ("TP+PP+DP", [(f"hybrid_mb{m}" if m != 8 else "hybrid", N, str(m), m == 8) for m in (1, 2, 4, 8, 16)])]),
    ("(c) TP across servers", [("mb 1", [(f"tp{t}_mb1", N, f"TP{t}", 0) for t in (8, 16, 32, 64)]),
                               ("mb 8", [(f"tp{t}_mb8", N, f"TP{t}", 0) for t in (8, 16, 32, 64)]),
                               ("seq 1K", [(f"tp{t}_seq1k", N, f"TP{t}", 0) for t in (16, 32)])]),
    ("(d) Sequence (CP)", [("CP8", [("cp" if s == 32 else f"cp_s{s}k", N, f"{s}K", s == 32) for s in (8, 16, 32, 64, 128)]
                            + [("cp_s32k_mb1", N, "32K, mb 1", 0)])]),
    ("(e) GPU count", [("DP weak", [("dp", N, "64", 1), ("dp_w128", "n128nm", "128", 0), ("dp_w256", "n256", "256", 0), ("dp_w512", "n512", "512", 0)]),
                       ("DP strong", [("dp", N, "64", 1), ("dp_s128", "n128nm", "128", 0), ("dp_s256", "n256", "256", 0), ("dp_s512", "n512", "512", 0)]),
                       ("TP+PP+DP", [("hybrid", N, "64", 1), ("hybrid_256", "n256", "256", 0), ("hybrid_512", "n512", "512", 0)])]),
    ("(f) Global batch", [("DP", [("dp_b64", N, "64", 0), ("dp_b128", N, "128", 0), ("dp", N, "256", 1), ("dp_b512", N, "512", 0),
                                  ("fsdp_mb32", N, "FSDP, mb 32", 0)])]),
    ("(g) Link rate [Gbps]", [(w, [(n, N if g == 400 else f"n64_l{g}", str(g), g == 400) for g in (100, 200, 400, 800, 1600)])
                              for w, n in (("DP", "dp"), ("PP", "pp"), ("CP", "cp"), ("TP+PP+DP", "hybrid"), ("TP32", "tp32_mb1"))]),
    ("(h) MoE", [("64 GPUs", [(f"moe_mixed_ep{e}", M, f"EP{e}", e == 64) for e in (8, 16, 32, 64)] + [("moe_scaleout_ep8", M, "EP+DP 8", 1)]),
                 ("EP64", [(f"moe_mixed_ep64_tok{t.lower()}" if t != "4K" else "moe_mixed_ep64", M, f"{t} tok", t == "4K") for t in ("64", "256", "1K", "4K")]),
                 ("EP+DP 8", [(f"moe_scaleout_ep8_tok{t.lower()}" if t != "4K" else "moe_scaleout_ep8", M, f"{t} tok", t == "4K") for t in ("64", "256", "1K", "4K")]),
                 ("256 GPUs", [(f"moe256_mixed_ep{e}", "n256", f"EP{e}", 0) for e in (8, 32, 64, 256)]
                  + [("moe256_mixed_ep256_tok64", "n256", "EP256, 64 tok", 0), ("moe256_scaleout_ep8", "n256", "EP+DP 8", 0),
                     ("moe256_scaleout_ep32", "n256", "EP+DP 32", 0)])]),
]
ROWS = [PANELS[:5], PANELS[5:]]
GAP = 0.6                                    # extra x space between groups inside a panel
W = 0.38                                     # bar width
FS = dict(tick=12, group=12, title=14, ylabel=14, legend=14, pct=12)   # drawn at 2x print size -> ~6-6.5 pt printed


def layout(groups):
    xs, x = [], 0.0
    for gi, (_, pts) in enumerate(groups):
        if gi:
            x += GAP
        xs.append([x + i for i in range(len(pts))])
        x += len(pts)
    return xs, x - 1


fig = plt.figure(figsize=(14, 9.0))
outer = fig.add_gridspec(2, 1, hspace=0.78, top=0.92, bottom=0.12, left=0.07, right=0.995)
missing = []
for ri, row in enumerate(ROWS):
    spans = [max(layout(g)[1] + 2.2, 7.5) for _, g in row]   # min width for a narrow panel; same bar width everywhere
    gs = outer[ri].subgridspec(1, len(row), width_ratios=spans, wspace=0.06)
    for pi, (ttl, groups) in enumerate(row):
        ax = fig.add_subplot(gs[pi])
        xs, xmax = layout(groups)
        ticks, labels, bold = [], [], []
        for (glab, pts), gx in zip(groups, xs):
            for (name, cl, tick, nom), x in zip(pts, gx):
                ticks.append(x); labels.append(tick); bold.append(nom)
                r, l = run(name, cl, "rdma"), run(name, cl, "loom")
                if not r or not l:
                    missing.append(f"{name}@{cl}")
                    ax.text(x, 0.5, "running", rotation=90, ha="center", va="center", fontsize=FS["pct"], color="0.5")
                    continue
                base = r[0]
                for j, (v, (it, ex, _)) in enumerate((("rdma", r), ("loom", l))):
                    xb = x + (j - 0.5) * W
                    c = SYSTEMS[v][1]
                    ax.bar(xb, (it - ex) / base, W, color=c, alpha=0.55, edgecolor="black", linewidth=0.6)
                    ax.bar(xb, ex / base, W, bottom=(it - ex) / base, color="white", edgecolor=c, hatch="////", linewidth=0.6)
                    ax.bar(xb, it / base, W, fill=False, edgecolor="black", linewidth=0.6)
                pct = (l[0] / base - 1) * 100
                ax.text(x, 1.025, "0.0%" if abs(pct) < 0.05 else f"{pct:+.1f}%", rotation=90, ha="center", va="bottom",
                        fontsize=FS["pct"])
            if glab:                                     # series name on top of its group
                ax.text((gx[0] + gx[-1]) / 2, 1.42, glab, ha="center", va="bottom", fontsize=FS["group"], color="0.25")
            if gx is not xs[-1]:
                ax.axvline(gx[-1] + 0.5 + GAP / 2, color="0.75", linewidth=0.8)
        ax.set_xticks(ticks)
        ax.set_xticklabels(labels, fontsize=FS["tick"], rotation=90)
        for t, b in zip(ax.get_xticklabels(), bold):
            if b:
                t.set_fontweight("bold")
        pad = (spans[pi] - xmax) / 2
        ax.set_xlim(-pad, xmax + pad)
        ax.set_ylim(0, 1.56)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.tick_params(axis="y", labelsize=FS["tick"], labelleft=(pi == 0))
        ax.tick_params(axis="x", length=2, pad=2)
        ax.grid(True, axis="y", alpha=0.3)
        ax.text(0.5, 1.0, ttl, transform=ax.transAxes, ha="center", va="bottom", fontsize=FS["title"], color="navy",
                fontweight="bold")
        if pi == 0:
            ax.set_ylabel("Iteration time\n(norm. to RDMA)", fontsize=FS["ylabel"])
hs = [Patch(facecolor=SYSTEMS["rdma"][1], alpha=0.55, edgecolor="black", label=SYSTEMS["rdma"][0]),
      Patch(facecolor=SYSTEMS["loom"][1], alpha=0.55, edgecolor="black", label=SYSTEMS["loom"][0]),
      Patch(facecolor="0.6", alpha=0.55, edgecolor="black", label="compute"),
      Patch(facecolor="white", edgecolor="black", hatch="////", label="exposed communication")]
fig.legend(handles=hs, loc="upper center", ncol=4, fontsize=FS["legend"], frameon=False, bbox_to_anchor=(0.5, 1.0))
fig.savefig(sys.argv[1], dpi=150, bbox_inches="tight")
print(sys.argv[1], "missing:", " ".join(missing) if missing else "none")
