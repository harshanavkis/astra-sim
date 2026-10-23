# R2 plot (jigsaw-plotting-scripts style) from e8/r2/jobs.txt.tsv: Loom's speedup over
# RDMA (GDAKI, NCCL's device API) vs collective size, one panel per collective,
# 16 GPUs solid, 64 GPUs dashed -> figures/r2_collectives.{png,pdf}
#   python -I plot_r2.py
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

E = "/scratch/harshanavkis/loom-proj/e8-astrasim"
plt.rcParams.update({"mathtext.fontset": "cm", "font.size": 10, "axes.labelsize": 18,
                     "xtick.labelsize": 14, "ytick.labelsize": 16, "legend.fontsize": 14})
df = pd.read_csv(os.path.join(E, "e8", "r2", "jobs.txt.tsv"), sep="\t")
df = df[(df.ranks_done == df.ranks) & (df.ranks_done > 0)].copy()
p = df.name.str.split("__", expand=True)
df["op"], df["n"], df["size"], df["var"] = p[1], p[2].str[1:].astype(int), p[3].str[1:].astype(int), p[4]
NAMES = {"ALL_REDUCE": "All-reduce", "ALL_GATHER": "All-gather", "ALL_TO_ALL": "All-to-all"}


def lab(b):
    return f"{b >> 20} MiB" if b >= 1 << 20 else f"{b >> 10} KiB"


fig, axes = plt.subplots(1, 3, figsize=(18, 5), sharey=True)
for ax, op in zip(axes, NAMES):
    d = df[df.op == op]
    for n, ls in ((16, "-"), (64, "--")):
        g = d[d.n == n]
        base = g[g["var"] == "gdaki"].set_index("size").mean_us
        loom = g[g["var"] == "loom"].set_index("size").mean_us
        sp = (base / loom).dropna().sort_index()
        ax.plot(sp.index, sp.values, ls, color="tab:green", marker="o", markersize=9, linewidth=2,
                markeredgecolor="k", label=f"{n} GPUs")
    sizes = sorted(d["size"].unique())
    ax.set_xscale("log", base=2); ax.set_xticks(sizes); ax.set_xticklabels([lab(s) for s in sizes])
    ax.set_xlabel("Collective size"); ax.set_title(NAMES[op], fontsize=18)
    ax.axhline(1, color="k", linewidth=1); ax.grid(True, alpha=0.3)
axes[0].set_ylabel("Loom speedup over RDMA (GDAKI)")
axes[0].legend(loc="upper right", frameon=True)
out = os.path.join(E, "figures", "r2_collectives")
fig.savefig(out + ".png", dpi=300, bbox_inches="tight")
fig.savefig(out + ".pdf", bbox_inches="tight")
print(out + ".{png,pdf}")
