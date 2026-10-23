# R1 plots (jigsaw-plotting-scripts style) from e8/r1/jobs.txt.tsv:
#  figures/r1_latency: dispatch and combine latency vs EP size at TOKENS tokens per rank,
#     per-token puts, every variant; Loom's speedup over DeepEP (ordered) on top.
#  figures/r1_speedup: Loom's speedup over DeepEP (ordered) vs tokens per rank,
#     per token (solid) and per peer (dashed), one line per EP size.
#   python -I plot_r1.py [tokens, default 128]
import os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

E = "/scratch/harshanavkis/loom-proj/e8-astrasim"
plt.rcParams.update({"mathtext.fontset": "cm", "font.size": 10, "axes.labelsize": 18,
                     "xtick.labelsize": 16, "ytick.labelsize": 16, "legend.fontsize": 13})
VARS = [("deepep_flush", "RDMA, DeepEP post, flush", "tab:red"),
        ("deepep_ordered", "RDMA, DeepEP post, ordered", "tab:orange"),
        ("minimal_ordered", "RDMA, minimal post, ordered", "tab:blue"),
        ("loom", "Loom", "tab:green")]
TOK = int(sys.argv[1]) if len(sys.argv) > 1 else 128

df = pd.read_csv(os.path.join(E, "e8", "r1", "jobs.txt.tsv"), sep="\t")
df = df[(df.ranks_done == df.ranks) & (df.ranks_done > 0)].copy()
parts = df.name.str.split("__", expand=True)
df["op"], df["ep"], df["tok"], df["gran"], df["var"] = parts[1], parts[2].str[2:].astype(int), parts[3].str[1:].astype(int), parts[4], parts[5]


def save(fig, name):
    out = os.path.join(E, "figures", name)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out + ".png", dpi=300, bbox_inches="tight")
    fig.savefig(out + ".pdf", bbox_inches="tight")
    print(out + ".{png,pdf}")


fig, axes = plt.subplots(1, 2, figsize=(14, 5))
for ax, op in zip(axes, ("dispatch", "combine")):
    d = df[(df.op == op) & (df.tok == TOK) & (df.gran == "token")]
    eps = sorted(d.ep.unique())
    w = 0.8 / len(VARS)
    for j, (v, label, color) in enumerate(VARS):
        for i, ep in enumerate(eps):
            r = d[(d.ep == ep) & (d["var"] == v)]
            if r.empty:
                continue
            x = i + (j - (len(VARS) - 1) / 2) * w
            ax.bar(x, r.mean_us.iloc[0], w, color=color, edgecolor="k", alpha=0.8, label=label if i == 0 else None)
            if v == "loom":
                base = d[(d.ep == ep) & (d["var"] == "deepep_ordered")]
                if not base.empty:
                    ax.text(x, r.mean_us.iloc[0], f"{base.mean_us.iloc[0] / r.mean_us.iloc[0]:.2f}x", ha="center",
                            va="bottom", fontsize=11, color="navy", fontweight="bold")
    ax.set_xticks(range(len(eps))); ax.set_xticklabels([str(e) for e in eps])
    ax.set_xlabel("EP size"); ax.set_title(f"{op.capitalize()}, {TOK} tokens per GPU", fontsize=18)
    ax.grid(True, axis="y", alpha=0.3)
    ax.set_ylim(0, d.mean_us.max() * 1.5)
axes[0].set_ylabel("Latency (µs)")
axes[0].legend(loc="upper left", ncol=2, frameon=True)
save(fig, "r1_latency")

fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
colors = plt.cm.viridis([i / 4 for i in range(5)])
for ax, op in zip(axes, ("dispatch", "combine")):
    d = df[df.op == op]
    for c, ep in zip(colors, sorted(d.ep.unique())):
        for gran, ls in (("token", "-"), ("peer", "--")):
            g = d[(d.ep == ep) & (d.gran == gran)]
            base = g[g["var"] == "deepep_ordered"].set_index("tok").mean_us
            loom = g[g["var"] == "loom"].set_index("tok").mean_us
            sp = (base / loom).dropna().sort_index()
            if sp.empty:
                continue
            ax.plot(sp.index, sp.values, ls, color=c, marker="o", markersize=8, linewidth=2, markeredgecolor="k",
                    label=f"EP {ep}" if gran == "token" else None)
    ax.set_xscale("log", base=2); ax.set_xticks(sorted(d.tok.unique())); ax.set_xticklabels(sorted(d.tok.unique()))
    ax.set_xlabel("Tokens per GPU"); ax.set_title(op.capitalize(), fontsize=18)
    ax.axhline(1, color="k", linewidth=1); ax.grid(True, alpha=0.3)
axes[0].set_ylabel("Loom speedup over DeepEP (ordered)")
h, l = axes[0].get_legend_handles_labels()
h += [plt.Line2D([0], [0], color="k", ls="-"), plt.Line2D([0], [0], color="k", ls="--")]
l += ["per token", "per peer"]
axes[0].legend(h, l, loc="upper right", ncol=2, frameon=True)
save(fig, "r1_speedup")
