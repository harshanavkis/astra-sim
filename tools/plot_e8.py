# E8 end-to-end plot (jigsaw-plotting-scripts style): per workload, iteration
# time per host-interface variant, the exposed-communication part hatched, and
# Loom's (push) speedup over each RDMA (pull) variant on top.
#   python -I plot_e8.py [results/e8.tsv] [--out figures/e8_iteration]
import os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

E = "/scratch/harshanavkis/loom-proj/e8-astrasim"
plt.rcParams.update({"mathtext.fontset": "cm", "font.size": 10, "axes.labelsize": 18,
                     "xtick.labelsize": 16, "ytick.labelsize": 16, "legend.fontsize": 14})
VARIANTS = [("pull_nvshmem", "RDMA (NVSHMEM post)", "tab:red"),
            ("pull_deepep", "RDMA (DeepEP post)", "tab:orange"),
            ("pull", "RDMA (minimal post)", "tab:blue"),
            ("push", "Loom", "tab:green")]
WL_NAMES = {"mixtral8x22b": "Mixtral 8x22B\n(32 GPUs)", "llama3_70b": "Llama3-70B\n(16 GPUs)",
            "gpt175b": "GPT-175B\n(32 GPUs)"}

args = [a for a in sys.argv[1:] if not a.startswith("--")]
tsv = args[0] if args else os.path.join(E, "results", "e8.tsv")
out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(E, "figures", "e8_iteration")
df = pd.read_csv(tsv, sep="\t")
df = df[df.status == "done"]
wls = [w for w in WL_NAMES if w in set(df.workload)] + sorted(set(df.workload) - set(WL_NAMES))
unit, div = ("s", 1e9) if df.iter_ns.max() >= 1e9 else ("ms", 1e6)
fig, ax = plt.subplots(figsize=(10, 5))
w = 0.8 / len(VARIANTS)
for j, (v, label, color) in enumerate(VARIANTS):
    for i, wl in enumerate(wls):
        r = df[(df.workload == wl) & (df.variant == v)]
        if r.empty:
            continue
        it, ex = r.iter_ns.iloc[0] / div, r.exposed_comm_ns.iloc[0] / div
        x = i + (j - (len(VARIANTS) - 1) / 2) * w
        ax.bar(x, it, w, color=color, edgecolor="k", alpha=0.8, label=label if i == 0 else None)
        ax.bar(x, ex, w, color="none", edgecolor="k", hatch="///", label="exposed comm." if i == 0 and j == 0 else None)
        loom = df[(df.workload == wl) & (df.variant == "push")]
        if v != "push" and not loom.empty:
            ax.text(x, it, f"{it / (loom.iter_ns.iloc[0] / div):.2f}x", ha="center", va="bottom",
                    fontsize=12, color="navy", fontweight="bold")
ax.set_xticks(range(len(wls)))
ax.set_xticklabels([WL_NAMES.get(wl, wl) for wl in wls])
ax.set_ylabel(f"Iteration time ({unit})")
ax.set_ylim(0, df.iter_ns.max() / div * 1.55)  # room for the legend inside the axes
ax.grid(True, axis="y", alpha=0.3)
ax.legend(loc="upper left", ncol=2, frameon=True)
os.makedirs(os.path.dirname(out), exist_ok=True)
fig.savefig(out + ".png", dpi=300, bbox_inches="tight")
fig.savefig(out + ".pdf", bbox_inches="tight")
print(out + ".{png,pdf}")
