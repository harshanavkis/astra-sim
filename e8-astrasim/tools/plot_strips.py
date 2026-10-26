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
# 2026-10-22 (owner): RUNS=loop plots the runs with the GPU's measured send loops (an_declp_*, an_lpmoe_*); SWEEP_TSV /
# STAGES_TSV point strip C at other data (defaults: the paper's current files); COLL_TSV / E2E_TSV strip B's collectives and
# training (RUNS=loop: the collectives rerun with the staging copy).
LOOP = os.environ.get('RUNS') == 'loop'
DEC, MOE = ('declp', 'lpmoe') if LOOP else ('dec', 'moe')
SWEEP_TSV = os.environ.get('SWEEP_TSV', os.path.join(pe.X, pe.SWEEP))
STAGES_TSV = os.environ.get('STAGES_TSV', os.path.join(E, 'e8_an/loop/stages.tsv'))
COLL_TSV = os.environ.get('COLL_TSV', os.path.join(E, 'e8_an/loop/coll/coll.tsv' if LOOP else 'e8_an/coll/coll.tsv'))
E2E_TSV = os.environ.get('E2E_TSV', os.path.join(E, 'e8_an/e2e/e2e_full.tsv'))
W, HGT = 7.0, 1.37                      # inches: ACM text width; one row of panels + the legend row above
# 2026-10-26 (owner: "all plots are too tall in the evaluation ... shorter but consistent everywhere"): HGT 1.62 -> 1.37,
# every panel 0.67 in high (was 0.92; PANEL_H, also used by plot_coll_ratio.py's two rows)
PANEL_H = HGT - 0.70
FONT = dict(tick=6.5, label=7.0, title=7.0, legend=7.0, note=6.0)
# 2026-10-26 (owner: "plot text same or smaller than the caption font, at least as rendered"): the paper's own font, Linux
# Libertine (fonts/, copied from the TeX tree), so 7 pt in a plot looks like the 7 pt caption (DejaVu Sans 7 pt rendered ~25%
# larger: bigger x-height)
from matplotlib import font_manager as _fm
for _f in ('LinLibertine_R.ttf', 'LinLibertine_RB.ttf', 'LinLibertine_RI.ttf'):   # TrueType (fonts/otf2ttf.py): Type 42 needs glyf outlines
    _fm.fontManager.addfont(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts', _f))
plt.rcParams.update({'font.family': 'Linux Libertine O', 'mathtext.fontset': 'custom', 'mathtext.rm': 'Linux Libertine O'})
plt.rcParams.update({'font.size': FONT['tick'], 'axes.linewidth': 0.6, 'xtick.major.width': 0.5, 'ytick.major.width': 0.5,
                     'xtick.major.size': 2.0, 'ytick.major.size': 2.0, 'xtick.major.pad': 1.5, 'ytick.major.pad': 1.5,
                     'axes.labelpad': 1.5, 'grid.linewidth': 0.4, 'hatch.linewidth': 0.5, 'legend.handlelength': 1.8,
                     'pdf.fonttype': 42})
RDMA, LOOM = pe.SYSTEMS['rdma'][1], pe.SYSTEMS['loom'][1]
LN = dict(linewidth=1.1, markersize=3.4, markeredgecolor='k', markeredgewidth=0.4)
MODEL_LN = dict(linestyle=':', linewidth=1.0, markersize=3.4, markerfacecolor='white', markeredgewidth=0.8)
UP, DOWN = '(higher is better ↑)', '(lower is better ↓)'   # owner 2026-10-21: say which direction is better (Jigsaw)
TITLE_H = 0.12                          # inches: the direction's second title line


def strip(n, legend_rows=2, ratios=None, bottom=0.47, extra=0.0):
    h = HGT + 0.07 + 0.13 * (legend_rows - 1) + TITLE_H + extra   # extra: taller panels (2026-10-25, Fig 9 with 5 bars in (b))
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


# Fig 9 (d) reads (owner 2026-10-25: latency, breakdown, throughput, READS; the collectives move to their own figure; plot
# the existing data, optimize later). MEASURED, ~/loom-experiments/e2/20261025_1101_reads (run_reads_20261025.sh, standard
# images, 3 runs, median of the runs' medians): amy reads rose's host memory. Loom: get_bench CPU loads (32 B streaming
# loads; 8 B = one 8 B load) and the PTDMA engine reading the window (--ptq); RDMA: rdma_pingpong --read --size S (one READ,
# the client polls the last word).
READS_DIR = os.environ.get('READS_DIR', '/home/harshanavkis/loom-experiments/e2/20261025_1101_reads')
READS_SIZES = (8, 256, 4096, 65536, 1048576, 16777216)
# 2026-10-26 (owner: "show the two ceilings: normal rdma and the 256B per rdma read rdma"; Loom's window reads reach the
# switch as 256 B pieces): RDMA with one READ per 256 B, posted back to back (rdma_pingpong --read --chunk 256), MEASURED,
# ~/loom-experiments/e2/<time>_rdchunk (run_rdchunk_20261026.sh, interleaved with the normal READ, 3 runs, median of medians)
READS256_DIR = os.environ.get('READS256_DIR', '')
NORA = dict(color=LOOM, marker='D', markerfacecolor='#c7e9c0', linestyle='-.')   # Loom's DMA engine without read-ahead


def reads_data():
    """{'loads' | 'ptdma' | 'rdma': {size: us}}, the median over the runs"""
    import glob, re, statistics
    runs = {'loads': {}, 'ptdma': {}, 'rdma': {}, 'rdma256': {}, 'ptdma_nora': {}}
    # 2026-10-26 (owner: Loom with and without read-ahead): loom_getnora_run* = get_bench --ra-off on the same image,
    # interleaved with the loom_get_run* runs; only its DMA-engine reads are plotted
    for f in sorted(glob.glob(os.path.join(READS_DIR, 'loom_getnora_run*.client.log'))):
        sec = None
        for l in open(f, errors='replace'):
            if l.startswith('dma'): sec = 'ptdma_nora'
            elif l.startswith('parallel'): sec = None
            m = re.match(r'\s+ok\s+(\d+) B: median\s+([\d.]+) us', l)
            if sec and m:
                runs[sec].setdefault(int(m.group(1)), []).append(float(m.group(2)))
    for f in sorted(glob.glob(os.path.join(READS_DIR, 'loom_get_run*.client.log'))):
        sec = None
        for l in open(f, errors='replace'):
            if l.startswith('latency'): sec = 'lat'
            elif l.startswith('bulk'): sec = 'loads'
            elif l.startswith('dma'): sec = 'ptdma'
            elif l.startswith('parallel'): sec = None
            m = re.match(r'\s+ok\s+8 B load: median\s+([\d.]+) us', l)
            if sec == 'lat' and m:
                runs['loads'].setdefault(8, []).append(float(m.group(1)))
            m = re.match(r'\s+ok\s+(\d+) B: median\s+([\d.]+) us', l)
            if sec in ('loads', 'ptdma') and m:
                runs[sec].setdefault(int(m.group(1)), []).append(float(m.group(2)))
    for f in glob.glob(os.path.join(READS_DIR, 'rdma_read_*_run*.client.log')):
        m = re.search(r'read (\d+) B round trip \(ns.*?p50 (\d+)', open(f, errors='replace').read())
        if m:
            runs['rdma'].setdefault(int(m.group(1)), []).append(float(m.group(2)) / 1e3)
    for f in glob.glob(os.path.join(READS256_DIR, 'rdma_chunk256_*_run*.client.log')) if READS256_DIR else ():
        m = re.search(r'read (\d+) B in 256 B READs round trip \(ns.*?p50 (\d+)', open(f, errors='replace').read())
        if m:
            runs['rdma256'].setdefault(int(m.group(1)), []).append(float(m.group(2)) / 1e3)
    return {k: {s: statistics.median(v) for s, v in d.items()} for k, d in runs.items()}


def strip_a(out, dpanel='coll'):
    """(a) one-way latency, (b) throughput (measured, model hollow dotted), (c) collectives at two ranks: RDMA time / Loom
    time per data size (measured; model dotted for all-gather and all-to-all, which only move data: reduce-scatter and
    all-reduce add the CPU's reduction, the same for both systems). dpanel='reads' (2026-10-25 preview, strip 'A2'): (d) = the
    time of one remote read instead of the collectives."""
    fig, axes = strip(4, ratios=(1, 1.12, 1, 1), extra=0.6 if dpanel == 'reads' and pe.FIG9 else 0.0)   # (b) = the breakdown, after the latency (owner)
    fig.subplots_adjust(right=0.985, wspace=0.45)
    V = pe.val_model()
    SIZES = (0, 64, 256, 1024, 4096, 16384, 65536)
    ax = axes[0]
    for k, color, mk, ls in (('h_rdma64', RDMA, 's', '--'), ('h_rdma1', RDMA, '^', '-'), ('h_stores', LOOM, 'o', '--'),
                             ('h_ptdma', LOOM, 'D', '-')):
        v = pe.lat(k, SIZES)
        ax.plot(range(len(SIZES)), [x[0] if x else np.nan for x in v], color=color, marker=mk, linestyle=ls, **LN)
    STG = dict(color=RDMA, marker='v', linestyle='-.')   # 2026-10-25 (FIG9_DIR): RDMA staged by the CPU, measured
    if dpanel == 'reads' and pe.FIG9:
        v = pe.lat('h_rdma1_stg', SIZES)
        ax.plot(range(len(SIZES)), [x[0] if x else np.nan for x in v], **STG, **LN)
    for sy, color, mk in (('rdma', RDMA, '^'), ('loom_stores', LOOM, 'o')):
        mv = [V.get(('e2', sy, str(s), 'oneway_us'), np.nan) for s in SIZES]
        ax.plot(range(len(SIZES)), mv, color=color, marker=mk, markeredgecolor=color, **MODEL_LN)
    ax.set_yscale('log'); ax.set_ylim(3, 400)
    size_ticks(ax, SIZES)
    finish(ax, 'One-way latency [µs]')
    title(ax, '(a) Latency ' + DOWN)
    ax = axes[2]
    d = pe.e1_series_h()
    sizes = [s for s, *_ in d['loom']]
    for key, color, mk in (('rdma', RDMA, '^'), ('loom', LOOM, 'D')):
        ax.plot(range(len(sizes)), [t[1] for t in d[key]], color=color, marker=mk, **LN)
        mv = [V.get(('e1', key, str(s), 'gbps'), np.nan) for s in sizes]
        ax.plot(range(len(sizes)), mv, color=color, marker={'rdma': '^', 'loom': 'D'}[key], markeredgecolor=color, **MODEL_LN)
    if dpanel == 'reads' and 'rdma_stg' in d:
        ax.plot(range(len(sizes)), [dict((t[0], t[1]) for t in d['rdma_stg']).get(s, np.nan) for s in sizes], **STG, **LN)
    ax.set_ylim(0, 14)
    ax.set_yticks((0, 5, 10))
    size_ticks(ax, sizes)
    finish(ax, 'Throughput [GB/s]')
    title(ax, '(c) Throughput ' + UP)
    ax = axes[3]
    if dpanel == 'reads':
        R = reads_data()
        for k, color, mk, ls in (('rdma', RDMA, '^', '-'), ('rdma256', RDMA, 's', '--'), ('loads', LOOM, 'o', '--'),
                                 ('ptdma', LOOM, 'D', '-')):
            if R[k]:
                ax.plot(range(len(READS_SIZES)), [R[k].get(s, np.nan) for s in READS_SIZES], color=color, marker=mk,
                        linestyle=ls, **LN)
        if R['ptdma_nora']:   # the DMA engine's reads without read-ahead (hollow + dotted is the model's style);
            # (d) only, so its legend entry sits inside (d), in the empty upper left
            ax.plot(range(len(READS_SIZES)), [R['ptdma_nora'].get(s, np.nan) for s in READS_SIZES], **NORA, **LN)
            ax.legend([Line2D([0], [0], **NORA, **LN)], ['Loom, no\nread-ahead'], loc='upper left',
                      fontsize=FONT['legend'], frameon=False, handlelength=1.6, handletextpad=0.4, borderaxespad=0.3)
        ax.set_yscale('log')
        size_ticks(ax, READS_SIZES)
        ax.set_xticklabels([pe.size_label(s) for s in READS_SIZES], fontsize=FONT['tick'], rotation=40, ha='right',
                           rotation_mode='anchor')
        finish(ax, 'Time per read [µs]')
        ax.yaxis.set_major_formatter(mticker.LogFormatterSciNotation())
        title(ax, '(d) Reads ' + DOWN)
    if dpanel == 'reads':
        _, res = {}, {}
    else:
        _, res = pe.e5_data_h()
    sizes = sorted({k[2] for k in res})
    for c, name, color, mk in COLLS:
        y = [res[('rdma', c, s)][0] / res[('loom', c, s)][0] if ('rdma', c, s) in res and ('loom', c, s) in res else np.nan
             for s in sizes]
        ax.plot(range(len(sizes)), y, color=color, marker=mk, **LN)
        if c in ('ag', 'a2a'):
            mr = [V.get(('e5', 'rdma', f'{c}_{s}', 'us'), np.nan) / V.get(('e5', 'loom', f'{c}_{s}', 'us'), np.nan) for s in sizes]
            ax.plot(range(len(sizes)), mr, color=color, marker=mk, markeredgecolor=color, **MODEL_LN)
    if dpanel != 'reads':
        ax.axhline(1.0, color='k', linewidth=0.6)
        ax.set_ylim(0.8, 2.1)
        size_ticks(ax, sizes)
        finish(ax, 'RDMA / Loom time')
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:g}×'))
        title(ax, '(d) Collectives ' + UP)
    for a in (axes[0], axes[2], axes[3]):
        a.set_xlabel('Data per message' if a is not axes[3] else ('Data per read' if dpanel == 'reads' else 'Data per rank'),
                     fontsize=FONT['label'])
    # (d) where one 8 B message's time goes (owner 2026-10-22: measured on the prototype, perf_rdma vs Loom's CPU stores)
    cats = PROTO_STAGE_CATS
    if dpanel == 'reads' and pe.FIG9:   # writes and reads: the PCIe stages carry both, the far side's read is a host read
        cats = tuple((k, {'PCIe write': 'PCIe', 'NIC read': 'host read'}.get(n, n), c) for k, n, c in cats)
    panel_stages(axes[1], '(b) Where the time goes ' + DOWN, tsv=PROTO_STAGES_TSV, cats=cats, xmax=9.5,
                 xticks=(0, 2, 4, 6, 8), two_line=True, leg_cols=2,
                 band=-2.45 if not (dpanel == 'reads' and pe.FIG9) else -3.2,
                 gpu_stage_ns=350 if dpanel == 'reads' and pe.FIG9 else None)
    h = [Line2D([0], [0], color=RDMA, marker='^', **LN), Line2D([0], [0], color=RDMA, marker='s', linestyle='--', **LN),
         Line2D([0], [0], color=LOOM, marker='D', **LN), Line2D([0], [0], color=LOOM, marker='o', linestyle='--', **LN),
         Line2D([0], [0], color='0.4', marker='o', markeredgecolor='0.4', **MODEL_LN)]
    lab = ['RDMA (one write)', 'RDMA (write per 64 B)', 'Loom (DMA engine)', 'Loom (CPU stores)', 'model']
    if dpanel == 'reads':   # one legend for all panels: (d) draws the same styles for reads
        lab = ['RDMA (one write or read)', 'RDMA (64 B writes, 256 B reads)' if READS256_DIR else 'RDMA (write per 64 B)',
               'Loom (DMA engine)', 'Loom (CPU stores or loads)', 'model']
        if pe.FIG9:
            h.insert(1, Line2D([0], [0], **STG, **LN))
            lab.insert(1, 'RDMA (one write), staged by the CPU')
        legend(fig, h, lab, ncol=3 if pe.FIG9 else 5)
        save(fig, out, 'strip-a2')
        return
    h += [Line2D([0], [0], color=c, marker=m, **LN) for _, _, c, m in COLLS]
    lab += [n for _, n, _, _ in COLLS]
    legend(fig, h, lab, ncol=5)
    save(fig, out, 'strip-a')


# Fig 8, strip 'A3' (owner 2026-10-26: "too tall, make them shorter"; no RDMA write per 64 B; the breakdown last; "in jigsaw
# we had very clean legends"): as Jigsaw, factored legends: color = the system, marker + line = how the data moves, short
# labels; the breakdown's stage legend above it; no legend inside a panel; the height of strips B and C.
ENG = dict(marker='D', linestyle='-')                                    # RDMA's NIC (one write or READ) / Loom's copy engine
CPU = dict(marker='o', linestyle='--')                                   # Loom's CPU stores or loads
STAGED = dict(marker='v', linestyle='-.')                                # RDMA after the CPU's copy into a registered buffer
R256 = dict(marker='s', linestyle='--')                                  # RDMA, one READ per 256 B
NORA3 = dict(marker='D', linestyle='-.', markerfacecolor='#c7e9c0')      # Loom's copy engine without read-ahead


def panel_breakdown(ax, ttl, tsv, cats, xmax=12.5):
    """Breakdown as pairs (owner 2026-10-26 "what the fuck is going on in 8d?" at 7 bars grouped by system): RDMA over Loom
    for seen (the receiver sees the message), free (the sender may reuse its buffer) and read (an 8 B remote read); each bar
    named at its end in its system's color. No staged bar (a 0.35 us computed GPU copy: a sliver; the text gives it)."""
    rows = list(csv.DictReader(open(tsv), delimiter='\t'))
    col = {k: c for k, _, c in cats}
    col['Loom pipeline'] = col['network']   # Loom's 21 + 7 ns pipelines: too short to see, drawn with the network
    groups = (('seen', 'receiver'), ('free', 'sender'), ('read', 'read'))
    y, ticks = 0.0, []
    for name, bar in groups:
        for sy, sname, scol in (('rdma', 'RDMA', RDMA), ('loom', 'Loom', LOOM)):
            segs = [r for r in rows if r['system'] == sy and r['bar'] == bar]
            for r in segs:
                a, b = float(r['start_ns']) / 1e3, float(r['end_ns']) / 1e3
                ax.barh(y, b - a, left=a, height=0.8, color=col[r['category']], edgecolor='k', linewidth=0.3)
            end = max(float(r['end_ns']) for r in segs) / 1e3
            ax.text(end + 0.2, y, f'{sname} ' + (f'{end:.1f}' if end >= 1 else f'{end:.2f}'), va='center', ha='left',
                    fontsize=FONT['note'], color=scol, fontweight='bold')
            y += 1
        ticks.append((y - 1.5, name))
        y += 0.6
    ax.set_xlim(0, xmax)
    ax.set_xticks((0, 2, 4, 6, 8, 10))
    finish(ax, None, 'Time [µs]')
    ax.set_yticks([t for t, _ in ticks])
    ax.set_yticklabels([n for _, n in ticks], fontsize=FONT['label'])
    ax.tick_params(axis='y', length=0)
    ax.set_ylim(y - 0.5 - 0.1, -0.6)
    ax.grid(False, axis='y')
    title(ax, ttl)


def strip_a3(out):
    fig, axes = strip(4, ratios=(1, 1, 1, 1.0))
    fig.subplots_adjust(right=0.985, wspace=0.45)
    V = pe.val_model()
    plot = lambda ax, xs, ys, color, st, **kw: ax.plot(range(len(xs)), ys, color=color, **{**LN, **st, **kw})
    # (a) one-way latency
    SIZES = (0, 64, 256, 1024, 4096, 16384, 65536)
    ax = axes[0]
    for k, color, st in (('h_rdma1', RDMA, ENG), ('h_rdma1_stg', RDMA, STAGED), ('h_ptdma', LOOM, ENG), ('h_stores', LOOM, CPU)):
        plot(ax, SIZES, [x[0] if x else np.nan for x in pe.lat(k, SIZES)], color, st)
    for sy, color, st in (('rdma', RDMA, ENG), ('loom_stores', LOOM, CPU)):
        plot(ax, SIZES, [V.get(('e2', sy, str(s), 'oneway_us'), np.nan) for s in SIZES], color, {**MODEL_LN, 'marker': st['marker']},
             markeredgecolor=color)
    ax.set_yscale('log'); ax.set_ylim(3, 400)
    size_ticks(ax, SIZES)
    finish(ax, 'One-way latency [µs]', 'Data per message')
    title(ax, '(a) Write latency ' + DOWN)   # owner 2026-10-26: "say write latency in 8a"
    # (b) throughput
    ax = axes[1]
    d = pe.e1_series_h()
    sizes = [s for s, *_ in d['loom']]
    for key, color in (('rdma', RDMA), ('loom', LOOM)):
        plot(ax, sizes, [t[1] for t in d[key]], color, ENG)
        plot(ax, sizes, [V.get(('e1', key, str(s), 'gbps'), np.nan) for s in sizes], color, {**MODEL_LN, 'marker': 'D'},
             markeredgecolor=color)
    stg = dict((t[0], t[1]) for t in d.get('rdma_stg', ()))
    plot(ax, sizes, [stg.get(s, np.nan) for s in sizes], RDMA, STAGED)
    ax.set_ylim(0, 14)
    ax.set_yticks((0, 5, 10))
    size_ticks(ax, sizes)
    finish(ax, 'Throughput [GB/s]', 'Data per message')
    title(ax, '(b) Throughput ' + UP)
    # (c) reads
    ax = axes[2]
    R = reads_data()
    for k, color, st in (('rdma', RDMA, ENG), ('rdma256', RDMA, R256), ('ptdma_nora', LOOM, NORA3), ('loads', LOOM, CPU),
                         ('ptdma', LOOM, ENG)):
        if R[k]:
            plot(ax, READS_SIZES, [R[k].get(s, np.nan) for s in READS_SIZES], color, st)
    ax.set_yscale('log')
    size_ticks(ax, READS_SIZES)
    ax.set_xticklabels([pe.size_label(s) for s in READS_SIZES], fontsize=FONT['tick'], rotation=40, ha='right',
                       rotation_mode='anchor')
    finish(ax, 'Time per read [µs]', 'Data per read')
    ax.yaxis.set_major_formatter(mticker.LogFormatterSciNotation())
    title(ax, '(c) Reads ' + DOWN)
    # (d) where the time goes
    cats = (('PCIe write', 'PCIe', '#9ecae1'), ('NIC read', 'host read', '#fc9272'), ('network', 'network', '#fdae6b'),
            ('ACK and completion', 'ACK + completion', '#d9f0d3'), ('CPU', 'CPU', '0.6'))
    panel_breakdown(axes[3], '(d) Latency breakdown ' + DOWN, PROTO_STAGES_TSV, cats)
    cats = cats[:-1]   # the CPU's 40-60 ns are too short to see: no legend entry (the text gives them)
    # legends: (a)-(c) factored (Jigsaw), the stages above (d)
    g = '0.25'
    h = [Line2D([0], [0], color=RDMA, linewidth=1.6), Line2D([0], [0], color=LOOM, linewidth=1.6)]
    lab = ['RDMA', 'Loom']
    for st, name in ((ENG, 'NIC or copy engine'), (CPU, 'CPU stores or loads'), (STAGED, 'CPU copy first'),
                     (R256, 'READ per 256 B'), ({**NORA3, 'markerfacecolor': '0.85'}, 'no read-ahead')):
        h.append(Line2D([0], [0], color=g, **{**LN, 'markerfacecolor': g, **st}))
        lab.append(name)
    h.append(Line2D([0], [0], color=g, **{**MODEL_LN, 'marker': 'o'}, markeredgecolor=g))
    lab.append('model')
    x0, x1 = axes[0].get_position().x0, axes[2].get_position().x1
    fig.legend(h, lab, loc='upper center', bbox_to_anchor=((x0 + x1) / 2, 1.005), ncol=4, frameon=False,
               fontsize=FONT['legend'], columnspacing=1.2, handletextpad=0.4, borderaxespad=0.1)
    fig.legend([Patch(facecolor=c, edgecolor='k', linewidth=0.3, hatch='////' if c == 'white' else None) for _, _, c in cats],
               [n for _, n, _ in cats], loc="upper right", bbox_to_anchor=(0.998, 1.005), ncol=2, frameon=False,
               fontsize=FONT['note'], handlelength=0.9, columnspacing=0.6, handletextpad=0.3, borderaxespad=0.1,
               labelspacing=0.35)
    save(fig, out, 'strip-a3')


# ----------------------------------------------------------------------- C: sensitivity (model)
STAGE_CATS = (('GPU', 'GPU', '0.6'), ('PCIe write', 'PCIe write', '#9ecae1'), ('NIC read', 'NIC read', '#fc9272'),
              ('network stack', 'net. stack', '#fdae6b'),
              ('wire', 'wire', '#d9f0d3'))   # wire = links + switch (caption)
# the prototype's breakdown (Fig 9 (d), MEASURED, ~/loom-experiments/e2/breakdown_stages.py): the network one way is one
# measured segment (READ - WRITE: RoCE stack, wire, switch); RDMA's ACK and completion are one measured remainder
PROTO_STAGE_CATS = (('CPU', 'CPU', '0.6'), ('PCIe write', 'PCIe write', '#9ecae1'), ('NIC read', 'NIC read', '#fc9272'),
                    ('network', 'network', '#fdae6b'), ('ACK and completion', 'ACK + completion', '#d9f0d3'))
PROTO_STAGES_TSV = os.environ.get('PROTO_STAGES_TSV', '/home/harshanavkis/loom-experiments/e2/20261022_1443_breakdown/stages.tsv')


def panel_stages(ax, ttl, tsv=None, cats=STAGE_CATS, xmax=14, xticks=(0, 5, 10), two_line=False, leg_cols=3, band=-1.55,
                 gpu_stage_ns=None):
    """Plan A (owner 2026-10-22): one 64 B message between two GPUs on one switch (tools/stage_breakdown.py): each
    system's stages until the receiver sees the signal ("seen") and until the sender may reuse its buffer ("free")."""
    rows = list(csv.DictReader(open(tsv or STAGES_TSV), delimiter='\t'))
    bars = (('rdma', 'receiver', 'RDMA, seen'), ('rdma', 'sender', 'RDMA, free'),
            ('loom', 'receiver', 'Loom, seen'), ('loom', 'sender', 'Loom, free'))
    if gpu_stage_ns:   # 2026-10-25 (owner): RDMA staged by a GPU = the measured RDMA receiver bar after a computed GPU copy
        g = [dict(r, system='rdma_gpu', start_ns=str(float(r['start_ns']) + gpu_stage_ns), end_ns=str(float(r['end_ns']) + gpu_stage_ns))
             for r in rows if r['system'] == 'rdma' and r['bar'] == 'receiver']
        rows += g + [dict(system='rdma_gpu', bar='receiver', stage='GPU staging copy', category='GPU copy',
                          start_ns='0', end_ns=str(gpu_stage_ns), source='computed')]
        bars = bars[:1] + (('rdma_gpu', 'receiver', 'Staged, seen'),) + bars[1:]   # RDMA staged by a GPU (caption)
    if any(r['bar'] == 'read' for r in rows):   # 2026-10-25: one 8 B remote read per system (breakdown_stages.py <dir> <reads>)
        bars = bars + (('rdma', 'read', 'RDMA, read'), ('loom', 'read', 'Loom, read'))
        cats = cats + (('GPU copy', 'GPU copy', 'white'),)
    col = {k: c for k, _, c in cats}
    col['Loom pipeline'] = col['network stack' if 'network stack' in col else 'network']   # Loom's 21 + 7 ns pipelines: too short to see, drawn with the stack (caption)
    for i, (sy, bar, _) in enumerate(bars):
        y = len(bars) - 1 - i
        segs = [r for r in rows if r['system'] == sy and r['bar'] == bar]
        for r in segs:
            a, b = float(r['start_ns']) / 1e3, float(r['end_ns']) / 1e3
            ax.barh(y, b - a, left=a, height=0.62, color=col[r['category']], edgecolor='k', linewidth=0.3,
                    hatch='////' if r['category'] == 'GPU copy' else None)
        end = max(float(r['end_ns']) for r in segs) / 1e3
        ax.text(end + 0.15, y, f'{end:.1f}' if end >= 1 else f'{end:.2f}', va='center', ha='left', fontsize=FONT['note'])
    ax.set_xlim(0, xmax)
    ax.set_xticks(xticks)
    finish(ax, None, 'Time [µs]')
    ax.set_yticks(range(len(bars)))
    ax.set_yticklabels([lab.replace(', ', '\n') if two_line else lab for *_, lab in bars][::-1], fontsize=FONT['tick'],
                       linespacing=0.9)
    ax.set_ylim(band, len(bars) - 0.5)   # a band below the bars for the stage legend
    ax.grid(False, axis='y')
    title(ax, ttl)
    ax.legend([Patch(facecolor=c, edgecolor='k', linewidth=0.3, hatch='////' if c == 'white' else None) for _, _, c in cats],
              [n for _, n, _ in cats],
              loc='lower center', ncol=leg_cols, fontsize=FONT['note'] - 0.5, frameon=False, handlelength=0.9, columnspacing=0.5,
              labelspacing=0.15, handletextpad=0.3, borderaxespad=0.15)


def strip_c(out):
    """Sensitivity only (owner 2026-10-22: the time breakdown moves to the prototype's Fig 9, measured): (a-c) Loom's lead
    vs the link rate, PCIe latencies and network stack, as Fig 13 (one message 64 B .. 64 KiB, all-to-all of 16 KiB per GPU
    on 16 GPUs), (d) Loom's own pipeline depth (plan B; run_sweep_an.py pipe<k>: 21 + 7 cycles x k)."""
    # 2026-10-26: no rotated ticks -> 0.17 in less below; the legend in one row (owner); same panel height
    fig, axes = strip(4, legend_rows=1, bottom=0.30, extra=-0.17)
    rows = [l.split('\t') for l in open(SWEEP_TSV).read().splitlines()[1:]]
    v = {(r[0], r[1], r[2], int(r[3])): float(r[4]) for r in rows}
    scales = (0.25, 0.5, 1, 1.5, 2)
    # narrower panels than the 3-panel strip: fewer tick labels (every point keeps its marker)
    cols = ((axes[0], [(t, g) for t, g in pe.SWEEP_RATES], 400, 'Link rate [Gbps]', '(a) Link rate ' + UP, lambda g: str(g)),
            (axes[1], [('400' if k == 1 else f'pcie{k:g}', k) for k in (0, 0.125, 0.25, 0.5, 0.75, 1)], 1, 'PCIe latency [× meas.]',
             '(b) PCIe latency ' + UP, lambda k: f'{k:g}'),
            # (c) RDMA's GPU work (owner 2026-10-22, replaces the network stack): its copy + post call x k, Loom unchanged
            (axes[2], [('400' if k == 1 else f'gpuw{k:g}', k) for k in (0, 0.25, 0.5, 0.75, 1)], 1, 'RDMA GPU work [× meas.]',
             "(c) RDMA's GPU work " + UP, lambda k: f'{k:g}'),
            (axes[3], [('400' if k == 1 else f'pipe{k:g}', k) for k in (1, 4, 16, 64, 128, 256)], 1, 'Pipeline [× RTL]',
             '(d) Pipeline depth ' + UP, lambda k: f'{k:g}'))
    # PCIe (owner 2026-10-22): the measured latencies are the highest point, down to 0 (linear axis: 0 has no log position)
    TICKS = {0: (100, 400, 1600), 1: (0, 0.25, 0.5, 0.75, 1), 2: (0, 0.25, 0.5, 0.75, 1), 3: (1, 4, 16, 64, 256)}
    series = [('lat', s, c, mk, pe.size_label(s)) for s, c, mk in zip((64, 4096, 16384, 65536), pe.SIZE_COLORS, 'osD^')]
    series.append(('a2a', 16384, 'k', 'v', 'all-to-all'))
    for ax, pts, nominal, xl, ttl, fmt in cols:
        xs = [x for _, x in pts]
        for e, s, c, mk, _ in series:
            ax.plot(xs, [v[(e, 'rdma', t, s)] / v[(e, 'loom', t, s)] for t, _ in pts], color=c, marker=mk,
                    linestyle='--' if e == 'a2a' else '-', **LN)
        ax.axvline(nominal, color='grey', linestyle=':', linewidth=0.8)
        if ax not in (axes[1], axes[2]):
            ax.set_xscale('log', base=2)
        else:
            ax.set_xlim(-0.06, 1.06)
        ticks = TICKS[list(axes).index(ax)]
        ax.set_xticks(ticks); ax.set_xticklabels([fmt(x) for x in ticks], fontsize=FONT['tick'])
        ax.xaxis.set_minor_locator(mticker.NullLocator())
        ax.axhline(1.0, color='k', linewidth=0.6)
        ax.set_ylim(0.5, 3.6)
        finish(ax, 'RDMA / Loom' if ax is axes[0] else None, xl)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda q, _: f'{q:g}×'))
        title(ax, ttl)
    axes[3].axvline(300 / 28, color='grey', linestyle='-.', linewidth=0.8)   # one switch hop (the model's 300 ns)
    # 2026-10-26 (owner: "what is nominal", "legends in a single row"): one row, "one message:" once in front of its sizes;
    # "nominal" = the dotted line at each parameter's setup value -> "setup's value" (the caption's words)
    # later (owner: "do we really need to say 'one message'?"): no; the caption says one message of 64 B-64 KiB
    h = [Line2D([0], [0], color=c, marker=mk, linestyle='--' if e == 'a2a' else '-', **LN) for e, _, c, mk, _ in series]
    lab = [n if e == 'lat' else 'all-to-all, 16 KiB/GPU' for e, _, _, _, n in series]
    h += [Line2D([0], [0], color='grey', linestyle=':', linewidth=0.8), Line2D([0], [0], color='grey', linestyle='-.', linewidth=0.8)]
    lab += ["setup's value", 'one switch hop (300 ns)']
    fig.legend(h, lab, loc='upper center', bbox_to_anchor=(0.53, 1.005), ncol=len(h), frameon=False, fontsize=FONT['legend'],
               columnspacing=1.0, handletextpad=0.4, borderaxespad=0.1)
    save(fig, out, 'strip-c')


def panel_training(ax, ttl):
    """Training at full depth (Fig 14's 8 groups): slowest GPU's iteration, normalised to RDMA, compute + exposed."""
    ORDER = (('dp', 'DP'), ('fsdp', 'FSDP'), ('cp', 'CP'), ('pp', 'PP'), ('hybrid', '3D'), ('l80', '3D 80B'),
             ('moe_mixed', 'MoE mix'), ('moe_scaleout', 'MoE out'))
    t = {}
    for l in open(E2E_TSV).read().splitlines()[1:]:
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
    title(ax, ttl + DOWN)


# ----------------------------------------------------------------------- B: MoE decode + collectives at scale (model)
def decode_point(ep, t, mb, var):
    """Slowest GPU's decode step (us) and its exposed communication from the newest runs_an/an_dec_* log, or None."""
    import glob, re
    logs = sorted(glob.glob(os.path.join(E, 'runs_an', f'an_{DEC}_ep{ep}_t{t}_l4096_mb{mb}__{var}_2*.log')))
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
    f = sorted(glob.glob(os.path.join(E, 'runs_an', f'an_{MOE}__{op}__ep{ep}__t{t}__{var}_2*.log')))[-1]
    r = re.findall(r'^loom_rank \d+ sends_released_ns (\d+) last_recv_ns (\d+)', open(f).read(), re.M)
    return np.array([int(a) for a, _ in r]) / 1e3, np.array([int(b) for _, b in r]) / 1e3


TOKENS = (1, 4, 16, 64, 128)


def panel_moe(fig, gs, ttl):
    """Fig 4's form (owner 2026-10-22: dispatch and combine in one plot, as Fig 4a): one linear sub-panel per token count
    with a dispatch and a combine group; bars = slowest of the 256 GPUs until the sender may reuse its buffer (RDMA, Loom),
    dashed = until the receiver has all tokens (slowest GPU); red = RDMA / Loom sender time per group."""
    sub = gs.subgridspec(1, 3, wspace=0.36)
    Wb, X0 = 0.42, (('dispatch', 0.0), ('combine', 1.3))
    for i, t in enumerate((1, 16, 128)):
        ax = fig.add_subplot(sub[0, i])
        v = {op: {var: [moe_ranks(op, 256, t, var)[k].max() for k in (0, 1)] for var in ('rdma', 'loom')} for op, _ in X0}
        top = max(max(x) for g in v.values() for x in g.values())
        for op, x0 in X0:
            for j, var in enumerate(('rdma', 'loom')):
                snd, rcv = v[op][var]
                x = x0 + j * Wb
                ax.bar(x, snd, Wb, color=RDMA if var == 'rdma' else LOOM, alpha=0.55, edgecolor='k', linewidth=0.4)
                ax.hlines(rcv, x - Wb / 2 - 0.04, x + Wb / 2 + 0.04, colors='k', linestyles='--', linewidth=1.0)
            g = max(max(x) for x in v[op].values())
            ax.text(x0 + Wb / 2, g + 0.04 * top, f'{v[op]["rdma"][0] / v[op]["loom"][0]:.1f}×', ha='center', va='bottom',
                    fontsize=FONT['note'], color='firebrick')
        ax.set_xticks([x0 + Wb / 2 for _, x0 in X0]); ax.set_xticklabels(['disp.', 'comb.']); ax.tick_params(axis='x', length=0)
        ax.set_xlim(-0.4, X0[-1][1] + Wb + 0.4); ax.set_ylim(0, top * 1.25)
        ax.yaxis.set_major_locator(mticker.MaxNLocator(3))
        finish(ax, 'Sender busy [µs]' if i == 0 else None, f'{t} token{"s" if t > 1 else ""}')
        ax.grid(False, axis='x')
        if i == 1:
            title(ax, ttl + DOWN)


def strip_b(out):
    """(a) one decode step of DeepSeek-V3 at EP256 (tools/gen_decode.py, roofline compute): slowest GPU, compute + exposed
    communication, normalised to RDMA per token count (only complete RDMA / Loom pairs), red = RDMA / Loom; (b) dispatch
    and combine at EP256 (Fig 11's runs) in one plot, Fig 4's form (panel_moe); (c) collectives on 64 GPUs; (d) training
    (panel_training, moved from strip C, owner 2026-10-22)."""
    h = HGT + 0.07 + 0.13 + TITLE_H
    fig = plt.figure(figsize=(W, h))
    gs = fig.add_gridspec(1, 4, width_ratios=(1.6, 2.3, 1.0, 1.15), wspace=0.36, left=0.055, right=0.995,
                          top=1 - (0.43 + TITLE_H) / h, bottom=0.47 / h)
    # (a) owner 2026-10-22: both cluster sizes the text quotes, 256 and 64 GPUs, as two sub-panels (as (b) splits by tokens)
    sub = gs[0, 0].subgridspec(1, 2, wspace=0.12)
    Wb = 0.38
    for k, ep in enumerate((256, 64)):
        ax = fig.add_subplot(sub[0, k])
        for i, t in enumerate(TOKENS):
            r, l = decode_point(ep, t, 1, 'rdma'), decode_point(ep, t, 1, 'loom')
            if not (r and l):
                continue
            for j, (var, d) in enumerate((('rdma', r), ('loom', l))):
                it, ex = d[0] / r[0], d[1] / r[0]
                x = i + (j - 0.5) * Wb
                c = RDMA if var == 'rdma' else LOOM
                ax.bar(x, it - ex, Wb, color=c, alpha=0.55, edgecolor='k', linewidth=0.4)
                ax.bar(x, ex, Wb, bottom=it - ex, color='white', edgecolor=c, hatch='//////', linewidth=0.4)
                ax.bar(x, it, Wb, fill=False, edgecolor='k', linewidth=0.4)
            ax.annotate(f'{r[0] / l[0]:.2f}×', (i, 1.0), xytext=(0, 1.2), textcoords='offset points',   # above the pair
                        ha='center', va='bottom', rotation=90, fontsize=FONT['note'], color='firebrick')
        ax.set_xticks(range(len(TOKENS))); ax.set_xticklabels([str(t) for t in TOKENS], rotation=45, ha='right', rotation_mode='anchor')
        ax.set_xlim(-0.6, len(TOKENS) - 0.4); ax.set_ylim(0, 1.7)   # 1.45 before the 2026-10-26 shorter panels: the ratios hit the title
        ax.set_yticks((0, 0.5, 1))
        finish(ax, 'Decode step [norm.]' if k == 0 else None, f'{ep} GPUs')
        ax.grid(False, axis='x')
        if k == 1:
            ax.tick_params(axis='y', labelleft=False)
        else:
            title(ax, '(a) Decode step ' + DOWN)
            ax.title.set_x(1.06)   # centred over both sub-panels
    panel_moe(fig, gs[0, 1], '(b) Dispatch and combine ')
    ax = fig.add_subplot(gs[0, 2])
    rows = list(csv.DictReader(open(COLL_TSV), delimiter='\t'))
    v = {(r['op'], int(r['gpus']), int(r['bytes']), r['variant']): float(r['time_us']) for r in rows}
    sizes = sorted({k[2] for k in v if k[1] == 64})
    for op, name, c, mk in (('ALL_GATHER', 'all-gather', 'tab:orange', 's'), ('ALL_TO_ALL', 'all-to-all', 'tab:cyan', 'D'),
                            ('REDUCE_SCATTER', 'reduce-scatter', 'tab:olive', 'v'), ('ALL_REDUCE', 'all-reduce', 'tab:purple', 'o')):
        ax.plot(range(len(sizes)), [v[(op, 64, s_, 'rdma')] / v[(op, 64, s_, 'loom')] for s_ in sizes], color=c, marker=mk, **LN)
    ax.axhline(1.0, color='k', linewidth=0.6)
    size_ticks(ax, sizes)
    finish(ax, 'RDMA / Loom time', 'Data per GPU')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda q, _: f'{q:g}\u00d7'))
    title(ax, '(c) Collectives ' + UP)
    panel_training(fig.add_subplot(gs[0, 3]), '(d) Training ')
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
    for k, fn in (('A', strip_a), ('A2', lambda o: strip_a(o, 'reads')), ('A3', strip_a3), ('B', strip_b), ('C', strip_c)):
        if k in only:
            fn(out)
