# Validation plots V3 (steve §2 dispatch/combine) and V4 (DeepEP v1.2.1 README table),
# jigsaw-plotting-scripts style.
#   python -I plot_val_ep.py [val_steve.tsv] [val_deepep.tsv]   (default: newest tests/val_*.tsv)
# -> figures/val_steve.{png,pdf}, figures/val_deepep.{png,pdf}
import glob, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

E = "/scratch/harshanavkis/loom-proj/e8-astrasim"
plt.rcParams.update({"mathtext.fontset": "cm", "font.size": 10, "axes.labelsize": 18,
                     "xtick.labelsize": 14, "ytick.labelsize": 16, "legend.fontsize": 14})


def newest(p):
    f = sorted(glob.glob(os.path.join(E, "tests", p)))
    if not f:
        sys.exit(f"no {p}")
    return f[-1]


def save(fig, name):
    out = os.path.join(E, "figures", name)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out + ".png", dpi=300, bbox_inches="tight")
    fig.savefig(out + ".pdf", bbox_inches="tight")
    print(out + ".{png,pdf}")


def bars(ax, labels, meas, model, mlabel, xlabel=None):
    x = range(len(labels)); w = 0.38
    ax.bar([i - w / 2 for i in x], meas, w, color="tab:gray", edgecolor="k", alpha=0.8, label=mlabel)
    ax.bar([i + w / 2 for i in x], model, w, color="tab:blue", edgecolor="k", alpha=0.8, hatch="///", label="Model (RDMA)")
    for i, (a, b) in enumerate(zip(meas, model)):
        ax.text(i + w / 2, b, f"{(b - a) / a * 100:+.0f}%", ha="center", va="bottom", fontsize=11,
                color="navy", fontweight="bold")
    ax.set_xticks(list(x)); ax.set_xticklabels(labels)
    if xlabel:
        ax.set_xlabel(xlabel)
    ax.grid(True, axis="y", alpha=0.3)


def plot_steve(tsv):
    df = pd.read_csv(tsv, sep="\t")
    df = df[df.check.str.startswith(("dispatch", "combine"))].copy()
    df["op"] = df.check.str.split().str[0]
    df["path"] = df.check.str.split().str[1]
    df["msgs"] = df.check.str.split().str[2].astype(int)
    tokens = {6: 1, 90: 16, 683: 128}
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, op in zip(axes, ("dispatch", "combine")):
        d = df[df.op == op].sort_values(["msgs", "path"], ascending=[True, False])
        labels = [f"{tokens[m]} tok\n{p}" for m, p in zip(d.msgs, d.path)]
        bars(ax, labels, d.measured_us.astype(float).tolist(), d.model_us.astype(float).tolist(),
             "steve (H200 + CX-7)")
        ax.set_yscale("log")
        ax.set_title(op.capitalize(), fontsize=18)
    axes[0].set_ylabel("Remote $-$ local (µs)")
    axes[0].legend(loc="upper left", frameon=True)
    save(fig, "val_steve")


def plot_deepep(tsv):
    df = pd.read_csv(tsv, sep="\t")
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=False)
    for ax, op in zip(axes, ("dispatch", "combine")):
        d = df[df.op == op].sort_values("EP")
        bars(ax, [str(e) for e in d.EP], d.measured_us.astype(float).tolist(), d.model_max_us.astype(float).tolist(),
             "DeepEP v1.2.1 (H800 + CX-7)", "EP size")
        ax.set_title(op.capitalize(), fontsize=18)
        ax.set_ylim(0, d.measured_us.astype(float).max() * 1.45)
    axes[0].set_ylabel("Latency (µs)")
    axes[0].legend(loc="upper left", frameon=True)
    save(fig, "val_deepep")


if __name__ == "__main__":
    plot_steve(sys.argv[1] if len(sys.argv) > 1 else newest("val_steve_*.tsv"))
    plot_deepep(sys.argv[2] if len(sys.argv) > 2 else newest("val_deepep_*.tsv"))
