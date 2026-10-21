#!/usr/bin/env python3
"""Evaluation figures as Jigsaw-style strips (owner 2026-10-21: one style for every evaluation figure, as the Jigsaw NSDI
paper: one full-width row of equal panels per figure, navy bold titles with the direction, one shared legend row, the
same font sizes everywhere). Drawn at print size for the ACM template (text width 506.3 pt = 7.0 in), fonts in points.
Data loaders from plot_eval.py (MODEL=an: the LoomNet model). PREVIEWS until the owner approves.
  MODEL=an python3 -I plot_strips.py <out dir> [A,B,C]"""
import csv, os, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

os.environ.setdefault('MODEL', 'an')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plot_eval as pe

E = pe.E
W, HGT = 7.0, 1.62                      # inches: ACM text width; one row of panels + the legend row above
FONT = dict(tick=6.5, label=7.0, title=7.0, legend=7.0, note=6.0)
plt.rcParams.update({'font.size': FONT['tick'], 'axes.linewidth': 0.6, 'xtick.major.width': 0.5, 'ytick.major.width': 0.5,
                     'xtick.major.size': 2.0, 'ytick.major.size': 2.0, 'xtick.major.pad': 1.5, 'ytick.major.pad': 1.5,
                     'axes.labelpad': 1.5, 'grid.linewidth': 0.4, 'hatch.linewidth': 0.5, 'legend.handlelength': 1.8,
                     'pdf.fonttype': 42})
RDMA, LOOM = pe.SYSTEMS['rdma'][1], pe.SYSTEMS['loom'][1]
LN = dict(linewidth=1.1, markersize=3.4, markeredgecolor='k', markeredgewidth=0.4)
MODEL_LN = dict(linestyle=':', linewidth=1.0, markersize=3.4, markerfacecolor='white', markeredgewidth=0.8)
UP, DOWN = '(higher is better ↑)', '(lower is better ↓)'   # owner 2026-10-21: say which direction is better (Jigsaw)
TITLE_H = 0.12                          # inches: the direction's second title line


def strip(n, legend_rows=2, ratios=None, bottom=0.47):
    h = HGT + 0.07 + 0.13 * (legend_rows - 1) + TITLE_H
    fig, axes = plt.subplots(1, n, figsize=(W, h), gridspec_kw={'width_ratios': ratios} if ratios else None)
    fig.subplots_adjust(left=0.062, right=0.995, top=1 - (0.30 + 0.13 * (legend_rows - 1) + TITLE_H) / h,
                        bottom=bottom / h, wspace=0.42)
    return fig, axes


def title(ax, text):
    """Panel name, the direction on a second line (too wide for one line in a 4-panel strip)."""
    if ' (' in text:
        head, tail = text.rstrip().rsplit(' (', 1)
        text = f'{head}\n({tail}'
    ax.set_title(text, fontsize=FONT['title'], color='navy', fontweight='bold', pad=2.5)


def finish(ax, ylabel=None, xlabel=None):
    ax.grid(True, alpha=0.35)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=FONT['label'])
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=FONT['label'])
    ax.tick_params(labelsize=FONT['tick'])
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:g}'))


def legend(fig, handles, labels, ncol):
    fig.legend(handles, labels, loc='upper center', bbox_to_anchor=(0.53, 1.005), ncol=ncol, frameon=False,
               fontsize=FONT['legend'], columnspacing=1.2, handletextpad=0.4, borderaxespad=0.1)


def save(fig, out, name):
    fig.savefig(os.path.join(out, f'{name}.pdf'), metadata={'CreationDate': None})
    fig.savefig(os.path.join(out, f'{name}.png'), dpi=300)
    plt.close(fig)
    print(os.path.join(out, f'{name}.png'))


def size_ticks(ax, sizes):
    ax.set_xticks(range(len(sizes)))
    ax.set_xticklabels([pe.size_label(s) if s else '8 B' for s in sizes], fontsize=FONT['tick'], rotation=40, ha='right',
                       rotation_mode='anchor')


# ------------------------------------------------------------------------------------------------- A: prototype
COLLS = (('ag', 'all-gather', 'tab:orange', 's'), ('a2a', 'all-to-all', 'tab:cyan', 'D'),
         ('rs', 'reduce-scatter', 'tab:olive', 'v'), ('ar_ring', 'all-reduce', 'tab:purple', 'o'))


def strip_a(out):
    """(a) one-way latency, (b) throughput (measured, model hollow dotted), (c) collectives at two ranks: RDMA time / Loom
    time per data size (measured; model dotted for all-gather and all-to-all, which only move data: reduce-scatter and
    all-reduce add the CPU's reduction, the same for both systems)."""
    fig, axes = strip(3)
    V = pe.val_model()
    SIZES = (0, 64, 256, 1024, 4096, 16384, 65536)
    ax = axes[0]
    for k, color, mk, ls in (('h_rdma64', RDMA, 's', '--'), ('h_rdma1', RDMA, '^', '-'), ('h_stores', LOOM, 'o', '--'),
                             ('h_ptdma', LOOM, 'D', '-')):
        v = pe.lat(k, SIZES)
        ax.plot(range(len(SIZES)), [a for a, _, _ in v], color=color, marker=mk, linestyle=ls, **LN)
    for sy, color, mk in (('rdma', RDMA, '^'), ('loom_stores', LOOM, 'o')):
        mv = [V.get(('e2', sy, str(s), 'oneway_us'), np.nan) for s in SIZES]
        ax.plot(range(len(SIZES)), mv, color=color, marker=mk, markeredgecolor=color, **MODEL_LN)
    ax.set_yscale('log'); ax.set_ylim(3, 400)
    size_ticks(ax, SIZES)
    finish(ax, 'One-way latency [µs]')
    title(ax, '(a) Latency ' + DOWN)
    ax = axes[1]
    d = pe.e1_series_h()
    sizes = [s for s, *_ in d['loom']]
    for key, color, mk in (('rdma', RDMA, '^'), ('loom', LOOM, 'D')):
        ax.plot(range(len(sizes)), [t[1] for t in d[key]], color=color, marker=mk, **LN)
        mv = [V.get(('e1', key, str(s), 'gbps'), np.nan) for s in sizes]
        ax.plot(range(len(sizes)), mv, color=color, marker={'rdma': '^', 'loom': 'D'}[key], markeredgecolor=color, **MODEL_LN)
    ax.set_ylim(0, 14)
    size_ticks(ax, sizes)
    finish(ax, 'Throughput [GB/s]')
    title(ax, '(b) Throughput ' + UP)
    ax = axes[2]
    _, res = pe.e5_data_h()
    sizes = sorted({k[2] for k in res})
    for c, name, color, mk in COLLS:
        y = [res[('rdma', c, s)][0] / res[('loom', c, s)][0] if ('rdma', c, s) in res and ('loom', c, s) in res else np.nan
             for s in sizes]
        ax.plot(range(len(sizes)), y, color=color, marker=mk, **LN)
        if c in ('ag', 'a2a'):
            mr = [V.get(('e5', 'rdma', f'{c}_{s}', 'us'), np.nan) / V.get(('e5', 'loom', f'{c}_{s}', 'us'), np.nan) for s in sizes]
            ax.plot(range(len(sizes)), mr, color=color, marker=mk, markeredgecolor=color, **MODEL_LN)
    ax.axhline(1.0, color='k', linewidth=0.6)
    ax.set_ylim(0.8, 2.1)
    size_ticks(ax, sizes)
    finish(ax, 'RDMA / Loom time')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:g}×'))
    title(ax, '(c) Collectives ' + UP)
    for a in axes:
        a.set_xlabel('Data per message' if a is not axes[2] else 'Data per rank', fontsize=FONT['label'])
    h = [Line2D([0], [0], color=RDMA, marker='^', **LN), Line2D([0], [0], color=RDMA, marker='s', linestyle='--', **LN),
         Line2D([0], [0], color=LOOM, marker='D', **LN), Line2D([0], [0], color=LOOM, marker='o', linestyle='--', **LN),
         Line2D([0], [0], color='0.4', marker='o', markeredgecolor='0.4', **MODEL_LN)]
    lab = ['RDMA (one write)', 'RDMA (write per 64 B)', 'Loom (DMA engine)', 'Loom (CPU stores)', 'model']
    h += [Line2D([0], [0], color=c, marker=m, **LN) for _, _, c, m in COLLS]
    lab += [n for _, n, _, _ in COLLS]
    legend(fig, h, lab, ncol=5)
    save(fig, out, 'strip-a')


# ----------------------------------------------------------------------- C: sensitivity + training (model)
def strip_c(out):
    """(a-c) sensitivity of Loom's lead, as Fig 13 (one message 64 B .. 64 KiB, all-to-all of 16 KiB per GPU on 16 GPUs),
    (d) training at full depth (Fig 14's 8 groups): slowest GPU's iteration, normalised to RDMA, compute + exposed."""
    fig, axes = strip(4, ratios=(1, 1, 1, 1.35), bottom=0.47)
    rows = [l.split('\t') for l in open(os.path.join(pe.X, pe.SWEEP)).read().splitlines()[1:]]
    v = {(r[0], r[1], r[2], int(r[3])): float(r[4]) for r in rows}
    scales = (0.25, 0.5, 1, 1.5, 2)
    cols = ((axes[0], [(t, g) for t, g in pe.SWEEP_RATES], 400, 'Link rate [Gbps]', '(a) Link rate ' + UP, lambda g: str(g)),
            (axes[1], [('400' if k == 1 else f'pcie{k:g}', k) for k in scales], 1, 'PCIe latency [× measured]',
             '(b) PCIe latency ' + UP, lambda k: f'{k:g}'),
            (axes[2], [('400' if k == 1 else f'stack{k:g}', k) for k in scales], 1, 'Network stack [× measured]',
             '(c) Network stack ' + UP, lambda k: f'{k:g}'))
    series = [('lat', s, c, mk, pe.size_label(s)) for s, c, mk in zip((64, 4096, 16384, 65536), pe.SIZE_COLORS, 'osD^')]
    series.append(('a2a', 16384, 'k', 'v', 'all-to-all'))
    for ax, pts, nominal, xl, ttl, fmt in cols:
        xs = [x for _, x in pts]
        for e, s, c, mk, _ in series:
            ax.plot(xs, [v[(e, 'rdma', t, s)] / v[(e, 'loom', t, s)] for t, _ in pts], color=c, marker=mk,
                    linestyle='--' if e == 'a2a' else '-', **LN)
        ax.axvline(nominal, color='grey', linestyle=':', linewidth=0.8)
        ax.set_xscale('log', base=2)
        ax.set_xticks(xs); ax.set_xticklabels([fmt(x) for x in xs], fontsize=FONT['tick'])
        ax.xaxis.set_minor_locator(mticker.NullLocator())
        ax.axhline(1.0, color='k', linewidth=0.6)
        ax.set_ylim(0.8, 3.6)
        finish(ax, 'RDMA / Loom' if ax is axes[0] else None, xl)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda q, _: f'{q:g}×'))
        title(ax, ttl)
    ax = axes[3]
    ORDER = (('dp', 'DP'), ('fsdp', 'FSDP'), ('cp', 'CP'), ('pp', 'PP'), ('hybrid', '3D'), ('l80', '3D 80B'),
             ('moe_mixed', 'MoE mix'), ('moe_scaleout', 'MoE out'))
    t = {}
    for l in open(os.path.join(E, 'e8_an/e2e/e2e_full.tsv')).read().splitlines()[1:]:
        k, lab, var, it, ex, n, log = l.split('\t')
        t[(k, var)] = (float(it), float(ex))
    Wb = 0.38
    for i, (k, _) in enumerate(ORDER):
        base = t[(k, 'rdma')][0]
        for j, var in enumerate(('rdma', 'loom')):
            it, ex = t[(k, var)]
            x = i + (j - 0.5) * Wb
            c = RDMA if var == 'rdma' else LOOM
            ax.bar(x, (it - ex) / base, Wb, color=c, alpha=0.55, edgecolor='k', linewidth=0.4)
            ax.bar(x, ex / base, Wb, bottom=(it - ex) / base, color='white', edgecolor=c, hatch='//////', linewidth=0.4)
            ax.bar(x, it / base, Wb, fill=False, edgecolor='k', linewidth=0.4)
    ax.set_xticks(range(len(ORDER)))
    ax.set_xticklabels([lab for _, lab in ORDER], fontsize=FONT['tick'], rotation=40, ha='right', rotation_mode='anchor')
    ax.set_xlim(-0.6, len(ORDER) - 0.4); ax.set_ylim(0, 1.15)
    finish(ax, 'Iteration [norm.]')
    ax.grid(False, axis='x')
    title(ax, '(d) Training ' + DOWN)
    h = [Line2D([0], [0], color=c, marker=mk, linestyle='--' if e == 'a2a' else '-', **LN) for e, _, c, mk, _ in series]
    lab = [f'one message, {n}' if e == 'lat' else 'all-to-all, 16 KiB/GPU' for e, _, _, _, n in series]
    h += [Line2D([0], [0], color='grey', linestyle=':', linewidth=0.8),
          Patch(facecolor=RDMA, alpha=0.55, edgecolor='k', linewidth=0.4), Patch(facecolor=LOOM, alpha=0.55, edgecolor='k', linewidth=0.4),
          Patch(facecolor='white', edgecolor='k', hatch='//////', linewidth=0.4)]
    lab += ['nominal', 'RDMA', 'Loom', 'exposed comm.']
    legend(fig, h, lab, ncol=5)
    save(fig, out, 'strip-c')


# ----------------------------------------------------------------------- B: MoE decode + collectives at scale (model)
def decode_point(ep, t, mb, var):
    """Slowest GPU's decode step (us) and its exposed communication from the newest runs_an/an_dec_* log, or None."""
    import glob, re
    logs = sorted(glob.glob(os.path.join(E, 'runs_an', f'an_dec_ep{ep}_t{t}_l4096_mb{mb}__{var}_2*.log')))
    if not logs:
        return None
    txt = open(logs[-1], errors='replace').read()
    if 'loomnet: simulation finished' not in txt:
        return None
    fin = [(int(c), int(x)) for c, x in re.findall(r'sys\[\d+\] finished, (\d+) cycles, exposed communication (\d+) cycles', txt)]
    it, ex = max(fin)
    return it / 1e3, ex / 1e3


def moe_ranks(op, ep, t, var):
    """Per-GPU sender release and last arrival (us) of one Fig 11 run (newest runs_an/an_moe_* log)."""
    import glob, re
    f = sorted(glob.glob(os.path.join(E, 'runs_an', f'an_moe__{op}__ep{ep}__t{t}__{var}_2*.log')))[-1]
    r = re.findall(r'^loom_rank \d+ sends_released_ns (\d+) last_recv_ns (\d+)', open(f).read(), re.M)
    return np.array([int(a) for a, _ in r]) / 1e3, np.array([int(b) for _, b in r]) / 1e3


TOKENS = (1, 4, 16, 64, 128)


def panel_moe(fig, gs, op, ttl):
    """Fig 4's form (owner 2026-10-21): one linear sub-panel per token count; bars = slowest of the 256 GPUs until the
    sender may reuse its buffer (RDMA, Loom), dashed = until the receiver has all tokens (slowest GPU); red = RDMA / Loom
    sender time."""
    sub = gs.subgridspec(1, 3, wspace=0.7)
    Wb = 0.62
    for i, t in enumerate((1, 16, 128)):
        ax = fig.add_subplot(sub[0, i])
        v = {var: [moe_ranks(op, 256, t, var)[k].max() for k in (0, 1)] for var in ('rdma', 'loom')}
        top = max(max(x) for x in v.values())
        for j, var in enumerate(('rdma', 'loom')):
            snd, rcv = v[var]
            ax.bar(j, snd, Wb, color=RDMA if var == 'rdma' else LOOM, alpha=0.55, edgecolor='k', linewidth=0.4)
            ax.hlines(rcv, j - Wb / 2 - 0.06, j + Wb / 2 + 0.06, colors='k', linestyles='--', linewidth=1.0)
        ax.text(0.5, top * 1.04, f'{v["rdma"][0] / v["loom"][0]:.1f}×', ha='center', va='bottom', fontsize=FONT['note'],
                color='firebrick')
        ax.set_xticks([0.5]); ax.set_xticklabels([str(t)]); ax.tick_params(axis='x', length=0)
        ax.set_xlim(-0.6, 1.6); ax.set_ylim(0, top * 1.25)
        ax.yaxis.set_major_locator(mticker.MaxNLocator(3))
        finish(ax, 'Sender busy [µs]' if i == 0 else None, 'Tokens per GPU' if i == 1 else None)
        ax.grid(False, axis='x')
        if i == 1:
            title(ax, ttl + DOWN)


def strip_b(out):
    """(a) one decode step of DeepSeek-V3 at EP256 (tools/gen_decode.py, roofline compute): slowest GPU, compute + exposed
    communication, normalised to RDMA per token count (only complete RDMA / Loom pairs), red = RDMA / Loom; (b, c)
    dispatch / combine at EP256 (Fig 11's runs) in Fig 4's form (panel_moe); (d) collectives on 64 GPUs."""
    h = HGT + 0.07 + 0.13 + TITLE_H
    fig = plt.figure(figsize=(W, h))
    gs = fig.add_gridspec(1, 4, width_ratios=(0.9, 1.5, 1.5, 1.4), wspace=0.36, left=0.055, right=0.995,
                          top=1 - (0.43 + TITLE_H) / h, bottom=0.47 / h)
    ax = fig.add_subplot(gs[0, 0])
    Wb = 0.38
    for i, t in enumerate(TOKENS):
        r, l = decode_point(256, t, 1, 'rdma'), decode_point(256, t, 1, 'loom')
        if not (r and l):
            continue
        for j, (var, d) in enumerate((('rdma', r), ('loom', l))):
            it, ex = d[0] / r[0], d[1] / r[0]
            x = i + (j - 0.5) * Wb
            c = RDMA if var == 'rdma' else LOOM
            ax.bar(x, it - ex, Wb, color=c, alpha=0.55, edgecolor='k', linewidth=0.4)
            ax.bar(x, ex, Wb, bottom=it - ex, color='white', edgecolor=c, hatch='//////', linewidth=0.4)
            ax.bar(x, it, Wb, fill=False, edgecolor='k', linewidth=0.4)
        ax.annotate(f'{r[0] / l[0]:.2f}×', (i + 0.5 * Wb, l[0] / r[0]), xytext=(0, 1.2), textcoords='offset points',
                    ha='center', va='bottom', rotation=90, fontsize=FONT['note'], color='firebrick')
    ax.set_xticks(range(len(TOKENS))); ax.set_xticklabels([str(t) for t in TOKENS])
    ax.set_xlim(-0.6, len(TOKENS) - 0.4); ax.set_ylim(0, 1.45)
    finish(ax, 'Decode step [norm.]', 'Tokens per GPU')
    ax.grid(False, axis='x')
    title(ax, '(a) Decode step ' + DOWN)
    panel_moe(fig, gs[0, 1], 'dispatch', '(b) Dispatch ')
    panel_moe(fig, gs[0, 2], 'combine', '(c) Combine ')
    ax = fig.add_subplot(gs[0, 3])
    rows = list(csv.DictReader(open(os.path.join(E, 'e8_an/coll/coll.tsv')), delimiter='\t'))
    v = {(r['op'], int(r['gpus']), int(r['bytes']), r['variant']): float(r['time_us']) for r in rows}
    sizes = sorted({k[2] for k in v if k[1] == 64})
    for op, name, c, mk in (('ALL_GATHER', 'all-gather', 'tab:orange', 's'), ('ALL_TO_ALL', 'all-to-all', 'tab:cyan', 'D'),
                            ('REDUCE_SCATTER', 'reduce-scatter', 'tab:olive', 'v'), ('ALL_REDUCE', 'all-reduce', 'tab:purple', 'o')):
        ax.plot(range(len(sizes)), [v[(op, 64, s_, 'rdma')] / v[(op, 64, s_, 'loom')] for s_ in sizes], color=c, marker=mk, **LN)
    ax.axhline(1.0, color='k', linewidth=0.6)
    size_ticks(ax, sizes)
    finish(ax, 'RDMA / Loom time', 'Data per GPU')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda q, _: f'{q:g}\u00d7'))
    title(ax, '(d) Collectives ' + UP)
    hd = [Patch(facecolor=RDMA, alpha=0.55, edgecolor='k', linewidth=0.4), Patch(facecolor=LOOM, alpha=0.55, edgecolor='k', linewidth=0.4),
          Patch(facecolor='0.6', alpha=0.55, edgecolor='k', linewidth=0.4), Patch(facecolor='white', edgecolor='k', hatch='//////', linewidth=0.4),
          Line2D([0], [0], color='k', linestyle='--', linewidth=1.0), Patch(visible=False)]
    lab = ['RDMA', 'Loom', 'compute', 'exposed comm.', 'receiver has all tokens', '']
    hd += [Line2D([0], [0], color=c, marker=m, **LN) for _, _, c, m in COLLS]
    lab += [n for _, n, _, _ in COLLS]
    legend(fig, hd, lab, ncol=5)
    save(fig, out, 'strip-b')


if __name__ == '__main__':
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    only = sys.argv[2].split(',') if len(sys.argv) > 2 else ['A', 'B', 'C']
    for k, fn in (('A', strip_a), ('B', strip_b), ('C', strip_c)):
        if k in only:
            fn(out)
