# Validation plots for the E8 host-interface model (jigsaw-plotting-scripts style).
#   python -I plot_val.py [testbed.tsv] [h200ib.tsv]   (default: newest tests/val_*.tsv)
# -> figures/val_testbed.{png,pdf}, figures/val_h200ib.{png,pdf}
import glob, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

E = "/scratch/harshanavkis/loom-proj/e8-astrasim"
FIG = os.path.join(E, "figures")
plt.rcParams.update({"mathtext.fontset": "cm", "font.size": 10, "axes.labelsize": 18,
                     "xtick.labelsize": 16, "ytick.labelsize": 16, "legend.fontsize": 15})
COLORS = {"pull": "tab:blue", "push": "tab:green"}
NAMES = {"pull": "RDMA", "push": "Loom"}


def newest(pattern):
    files = sorted(glob.glob(os.path.join(E, "tests", pattern)))
    if not files:
        sys.exit(f"no {pattern}")
    return files[-1]


def save(fig, name):
    os.makedirs(FIG, exist_ok=True)
    out = os.path.join(FIG, name)
    fig.savefig(out + ".png", dpi=300, bbox_inches="tight")
    fig.savefig(out + ".pdf", bbox_inches="tight")
    print(out + ".{png,pdf}")


def size_label(b):
    return f"{b // 1024} KiB" if b >= 1024 else f"{b} B"


def plot_testbed(tsv):
    df = pd.read_csv(tsv, sep="\t")
    df = df[df.model_us != "FAIL"].astype({"model_us": float, "measured_us": float})
    fig, ax = plt.subplots(figsize=(10, 5))
    for mode in ("pull", "push"):
        d = df[df["mode"] == mode].sort_values("size")
        ax.plot(d["size"], d["measured_us"], color=COLORS[mode], marker="o", markersize=9,
                linewidth=2, markeredgecolor="k", alpha=0.9, label=f"{NAMES[mode]} testbed")
        ax.plot(d["size"], d["model_us"], color=COLORS[mode], marker="s", markersize=9,
                linewidth=2, linestyle="--", markerfacecolor="white", markeredgecolor=COLORS[mode],
                label=f"{NAMES[mode]} model")
    sizes = sorted(df["size"].unique())
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xticks(sizes)
    ax.set_xticklabels([size_label(s) for s in sizes])
    ax.set_xlabel("Message size")
    ax.set_ylabel("One-way latency (µs)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", ncol=2, frameon=True)
    save(fig, "val_testbed")
    plt.close(fig)


def plot_h200ib(tsv):
    df = pd.read_csv(tsv, sep="\t")
    fig, ax = plt.subplots(figsize=(10, 5))
    x = range(len(df))
    w = 0.38
    ax.bar([i - w / 2 for i in x], df["paper_ns"] / 1000, w, color="tab:gray", edgecolor="k",
           alpha=0.8, label="2610.01380 (H200 + CX-7)")
    ax.bar([i + w / 2 for i in x], df["model_ns"] / 1000, w, color=COLORS["pull"], edgecolor="k",
           alpha=0.8, hatch="///", label="Model (pull)")
    ax.set_xticks(list(x))
    ax.set_xticklabels([m.replace(" (fitted)", "\n(fitted)").replace(" inline", "\ninline")
                        .replace(" non-inline", "\nnon-inline") for m in df["metric"]], fontsize=12)
    ax.set_ylabel("Time (µs)")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper left", frameon=True)
    save(fig, "val_h200ib")
    plt.close(fig)


if __name__ == "__main__":
    plot_testbed(sys.argv[1] if len(sys.argv) > 1 else newest("val_testbed_*.tsv"))
    plot_h200ib(sys.argv[2] if len(sys.argv) > 2 else newest("val_h200ib_*.tsv"))
