#!/usr/bin/env python3
"""Loom evaluation figures, in the style of ~/jigsaw-plotting-scripts/plot_hw_exp.py and the paper's
Fig 3 (motivation-experiments plots/plot_motivation.py): jigsaw font sizes, Loom green, the GPU-initiated
RDMA baseline blue, lines with black-edged markers, navy bold panel titles with the direction, one
figure-level legend per figure.

  python3 -I plot_eval.py <out dir> [png dir]     (in the E8 nix shell; writes <name>.pdf, PNGs to png dir)

Figures (every number read from committed result files; MODEL.md says what the model is):
  eval-validation  model vs measured: the RDMA NIC model on the Section 2 dispatch/combine runs (steve,
                   val_dispatch/20261010_ring/model_base/compare.tsv) and the Loom model on the E4
                   prototype runs (val_e4/20261010_1144_dispatch_v80/compare.tsv)
  eval-moe         MoE dispatch / combine at scale (e8/moe/moe.tsv): slowest GPU's sender busy and
                   delivery vs EP size, 1 / 16 / 128 tokens, model
  eval-coll        collectives at scale (e8/coll/coll.tsv): GPU-initiated / Loom completion time vs size
"""
import csv, os, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

E = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# MODEL=an: data of the LoomNet analytical model (ANALYTICAL.md) instead of the ns-3 model; previews only until approved
AN = os.environ.get('MODEL') == 'an'
D8 = 'e8_an' if AN else 'e8'

# ===== FONT AND STYLE SETTINGS (as in jigsaw plot_hw_exp.py and the paper's Fig 3) =====
SINGLE_COLUMN_FIGURE_SIZE = (10, 5)
SINGLE_COLUMN_FONT_SIZES = {'label': 18, 'tick': 16, 'legend': 15, 'annotation': 16}
E2E_COMBINED_FIGURE_SIZE = (48, 7)
COMBINED_FONT_SIZES = {'label': 40, 'tick': 36, 'legend': 34, 'annotation': 36}
plt.rcParams['mathtext.fontset'] = 'cm'
plt.rcParams['font.size'] = 10

# system -> (label, color); jigsaw / Fig 3 convention: the system green, the baseline blue
SYSTEMS = {'rdma': ('RDMA (pull)', 'tab:blue'), 'loom': ('Loom (push)', 'tab:green')}   # owner 2026-10-19: the two names everywhere
TOKEN_MARKERS = {1: 'o', 16: 's', 128: '^'}
LINE = dict(markersize=12, linewidth=2, markeredgecolor='k', alpha=0.9)
# the full-width figures are drawn 48 in wide (printed at ~7 in, as Fig 3): thicker lines, bigger markers
LINE_BIG = dict(markersize=24, linewidth=4.5, markeredgecolor='k', markeredgewidth=1.5, alpha=0.9)


def title(ax, text, size):
    ax.text(0.5, 1.0, text, transform=ax.transAxes, ha='center', va='bottom', fontsize=size, color='navy',
            fontweight='bold', clip_on=False)


def save(fig, out_dir, png_dir, name):
    fig.savefig(os.path.join(out_dir, f'{name}.pdf'), bbox_inches='tight', metadata={'CreationDate': None})
    if png_dir:
        fig.savefig(os.path.join(png_dir, f'{name}.png'), bbox_inches='tight', dpi=150)
    plt.close(fig)


def tsv(path):
    return list(csv.DictReader((l for l in open(path) if not l.startswith('#')), delimiter='\t'))


# ---------------------------------------------------------------------------------------------- validation
def figure_validation(out_dir, png_dir):
    fs = SINGLE_COLUMN_FONT_SIZES
    fig, ax = plt.subplots(figsize=SINGLE_COLUMN_FIGURE_SIZE)
    lo, hi = 2, 1500
    xs = np.array([lo, hi])
    ax.fill_between(xs, xs * 0.9, xs * 1.1, color='0.85', zorder=0, label='±10%')
    ax.plot(xs, xs, color='k', linewidth=1, zorder=1)
    rd = [r for r in tsv(os.path.join(E, 'val_dispatch/20261010_ring/model_base/compare.tsv'))
          if not r['config'].endswith('_local') and r['quantity'] in ('seen', 'arr_last')]
    pts = []
    for q, mk, lab in (('seen', 'o', 'RDMA (pull): signal seen'), ('arr_last', 's', 'RDMA (pull): last arrival')):
        x = [float(r['measured_us']) for r in rd if r['quantity'] == q]
        y = [float(r['model_us']) for r in rd if r['quantity'] == q]
        ax.plot(x, y, linestyle='', marker=mk, color=SYSTEMS['rdma'][1], label=lab, **LINE)
        pts += [(q, a, b) for a, b in zip(x, y)]
    lm = tsv(os.path.join(E, 'val_e4/20261010_1144_dispatch_v80/compare.tsv'))
    for q, mk, lab in (('delivered', 'o', 'Loom (push): signal seen'), ('sender', '^', 'Loom (push): sender busy')):
        x = [float(r[f'{q}_measured_us']) for r in lm]
        y = [float(r[f'{q}_model_us']) for r in lm]
        ax.plot(x, y, linestyle='', marker=mk, color=SYSTEMS['loom'][1], label=lab, **LINE)
    for r in lm:   # the prototype's one-token deliveries sit below the band (open: receiver start-up cost)
        if r['tokens'] == '1':
            ax.annotate(f"{r['op']}, 1 token", (float(r['delivered_measured_us']), float(r['delivered_model_us'])),
                        xytext=(12, -4), textcoords='offset points', fontsize=fs['annotation'] - 4,
                        color=SYSTEMS['loom'][1], va='center')
    ax.set_xscale('log'); ax.set_yscale('log')
    ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
    ax.set_xlabel('Measured [us]', fontsize=fs['label'])
    ax.set_ylabel('Model [us]', fontsize=fs['label'])
    for a in (ax.xaxis, ax.yaxis):
        a.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:g}'))
    ax.tick_params(labelsize=fs['tick'])
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper left', fontsize=fs['legend'] - 2, frameon=True, labelspacing=0.3, handletextpad=0.3)
    title(ax, '(closer to the diagonal is better)', fs['annotation'])
    save(fig, out_dir, png_dir, 'eval-validation')
    # numbers for the text
    err = [(r['config'], r['tokens'], r['quantity'], float(r['err_pct'])) for r in rd]
    print('validation RDMA (seen, arr_last): err %', min(e[3] for e in err), max(e[3] for e in err))
    for r in lm:
        print('validation Loom', r['op'], r['tokens'], 'sender', r['sender_err_pct'], 'delivered', r['delivered_err_pct'])


# --------------------------------------------------------------------------------------------- MoE at scale
def figure_moe(out_dir, png_dir):
    fs = COMBINED_FONT_SIZES
    rows = tsv(os.path.join(E, D8, 'moe/moe.tsv'))
    eps = sorted({int(r['ep']) for r in rows})
    def get(op, ep, T, v, col):
        return [float(r[col]) for r in rows if r['op'] == op and int(r['ep']) == ep and int(r['tokens']) == T
                and r['variant'] == v][0]
    fig, axes = plt.subplots(1, 4, figsize=(E2E_COMBINED_FIGURE_SIZE[0], 8.5))
    fig.subplots_adjust(left=0.04, right=0.99, top=0.88, bottom=0.30, wspace=0.22)
    panels = (('dispatch', 'send_max_us', '(a) Dispatch: sender busy', 'Sender busy [us]'),
              ('dispatch', 'recv_max_us', '(b) Dispatch: delivered', 'Delivered [us]'),
              ('combine', 'send_max_us', '(c) Combine: sender busy', 'Sender busy [us]'),
              ('combine', 'recv_max_us', '(d) Combine: delivered', 'Delivered [us]'))
    x = np.arange(len(eps))
    for ax, (op, col, ttl, ylab) in zip(axes, panels):
        for T, mk in TOKEN_MARKERS.items():
            r = np.array([get(op, ep, T, 'rdma', col) for ep in eps])
            l = np.array([get(op, ep, T, 'loom', col) for ep in eps])
            ax.plot(x, r, color=SYSTEMS['rdma'][1], marker=mk, **LINE_BIG)
            ax.plot(x, l, color=SYSTEMS['loom'][1], marker=mk, **LINE_BIG)
            # gpu-initiated / loom at the largest EP, right of the last points
            ax.text(x[-1] + 0.18, np.sqrt(r[-1] * l[-1]), f'{r[-1] / l[-1]:.1f}x', ha='left', va='center',
                    fontsize=fs['annotation'] - 4, color='#a04040')
        ax.set_yscale('log')
        ax.set_xticks(x); ax.set_xticklabels([str(e) for e in eps], fontsize=fs['tick'])
        ax.set_xlim(-0.35, len(eps) - 1 + 1.15)
        ax.set_xlabel('GPUs (EP size)', fontsize=fs['label'])
        ax.set_ylabel(ylab, fontsize=fs['label'])
        ax.tick_params(axis='y', labelsize=fs['tick'])
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:g}'))
        ax.grid(True, alpha=0.3)
        title(ax, ttl, fs['annotation'])
    h = [Line2D([0], [0], color=SYSTEMS[s][1], linewidth=8) for s in SYSTEMS]
    lab = [SYSTEMS[s][0] for s in SYSTEMS]
    for T, mk in TOKEN_MARKERS.items():
        h.append(Line2D([0], [0], color='gray', linestyle='', marker=mk, markersize=24, markeredgecolor='k'))
        lab.append(f'{T} token{"s" if T > 1 else ""} per GPU')
    h.append(Line2D([0], [0], color='white', linestyle=''))
    lab.append('labels: RDMA / Loom at EP256; lower is better')
    fig.legend(h, lab, loc='upper center', bbox_to_anchor=(0.5, 0.135), ncol=len(lab), frameon=False,
               fontsize=fs['legend'] - 4, handlelength=1.6, columnspacing=1.6, borderaxespad=0)
    save(fig, out_dir, png_dir, 'eval-moe')
    for op in ('dispatch', 'combine'):
        for col in ('send_max_us', 'recv_max_us'):
            for T in TOKEN_MARKERS:
                rs = [get(op, ep, T, 'rdma', col) / get(op, ep, T, 'loom', col) for ep in eps]
                print(f'moe {op} {col} {T} tok: gpu-initiated/loom {min(rs):.2f}-{max(rs):.2f}x')


# --------------------------------------------------------------------------------------------- collectives
COLL = {'ALL_REDUCE': ('all-reduce', 'tab:purple', 'o'), 'ALL_GATHER': ('all-gather', 'tab:orange', 's'),
        'ALL_TO_ALL': ('all-to-all', 'tab:red', '^'), 'REDUCE_SCATTER': ('reduce-scatter', 'tab:brown', 'D')}


def size_label(b):
    for u, d in (('MiB', 1 << 20), ('KiB', 1 << 10)):
        if b >= d:
            return f'{b // d} {u}'
    return f'{b} B'


def figure_coll(out_dir, png_dir):
    """2026-10-20 (owner): one collective per panel, like the prototype's collectives figure (eval-e5): time per collective
    against the size per GPU, RDMA and Loom, 16 GPUs solid and 64 GPUs dashed, labels = RDMA / Loom per point (model)."""
    rows = tsv(os.path.join(E, D8, 'coll/coll.tsv'))
    sizes = sorted({int(r['bytes']) for r in rows})
    gpus = sorted({int(r['gpus']) for r in rows})
    t = {(r['op'], int(r['gpus']), int(r['bytes']), r['variant']): float(r['time_us']) for r in rows}
    fs = COMBINED_FONT_SIZES
    ops = (('ALL_GATHER', 'All-gather'), ('ALL_TO_ALL', 'All-to-all'), ('REDUCE_SCATTER', 'Reduce-scatter'), ('ALL_REDUCE', 'All-reduce'))
    fig, axes = plt.subplots(1, len(ops), figsize=(E2E_COMBINED_FIGURE_SIZE[0], 8.5))
    fig.subplots_adjust(left=0.04, right=0.99, top=0.88, bottom=0.30, wspace=0.18)
    x = np.arange(len(sizes))
    for ax, (op, ttl) in zip(axes, ops):
        for g, ls in zip(gpus, ('-', '--')):
            for sysname, mk in (('rdma', 's'), ('loom', 'o')):
                y = [t[(op, g, s_, sysname)] for s_ in sizes]
                ax.plot(x, y, color=SYSTEMS[sysname][1], marker=mk, **dict(LINE_BIG, linestyle=ls))
            for i, s_ in enumerate(sizes):   # labels: the larger GPU count above its pair, the smaller below its pair
                r, l = t[(op, g, s_, 'rdma')], t[(op, g, s_, 'loom')]
                up = g == gpus[-1]
                ax.text(x[i], max(r, l) * 1.35 if up else min(r, l) / 1.35, f'{r / l:.1f}x', ha='center',
                        va='bottom' if up else 'top', fontsize=fs['annotation'] - 12, color='#a04040')
            print(f'coll {op} {g} GPUs: ' + ' '.join(f'{size_label(s_)} {t[(op, g, s_, "rdma")] / t[(op, g, s_, "loom")]:.2f}x' for s_ in sizes))
        ax.set_yscale('log')
        ax.set_xticks(x); ax.set_xticklabels([size_label(s_) for s_ in sizes], fontsize=fs['tick'] - 12, rotation=30)
        ax.tick_params(axis='y', labelsize=fs['tick'] - 6)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:g}'))
        ax.grid(True, alpha=0.3)
        lo, hi = ax.get_ylim()
        ax.set_ylim(lo / 3, hi * 3)
        title(ax, ttl, fs['annotation'] - 8)
    axes[0].set_ylabel('Time [us]', fontsize=fs['label'])
    h = [Line2D([0], [0], color=SYSTEMS[k][1], marker=m, **LINE_BIG) for k, m in (('rdma', 's'), ('loom', 'o'))]
    lab = [SYSTEMS['rdma'][0], SYSTEMS['loom'][0]]
    h += [Line2D([0], [0], color='gray', linestyle=ls, linewidth=4.5) for ls in ('-', '--')]
    lab += [f'{g} GPUs' for g in gpus]
    fig.legend(h + [Line2D([0], [0], color='white')], lab + [f'x: size per GPU; labels: RDMA / Loom ({gpus[-1]} GPUs above, {gpus[0]} below)'], loc='upper center',
               bbox_to_anchor=(0.5, 0.135), ncol=5, frameon=False, fontsize=fs['legend'] - 6, borderaxespad=0)
    save(fig, out_dir, png_dir, 'eval-coll')


def figure_coll_ratio(out_dir, png_dir):
    """(until 2026-10-20) the single-column ratio plot of the same data"""
    fs = SINGLE_COLUMN_FONT_SIZES
    rows = tsv(os.path.join(E, D8, 'coll/coll.tsv'))
    sizes = sorted({int(r['bytes']) for r in rows})
    gpus = sorted({int(r['gpus']) for r in rows})
    t = {(r['op'], int(r['gpus']), int(r['bytes']), r['variant']): float(r['time_us']) for r in rows}
    fig, ax = plt.subplots(figsize=SINGLE_COLUMN_FIGURE_SIZE)
    x = np.arange(len(sizes))
    ax.axhline(1.0, color='k', linewidth=1)
    # reduce-scatter first, with bigger markers: all-reduce lies on it (1.57-1.62x) and shows inside its diamonds
    big = dict(LINE, markersize=17)
    for op in sorted(COLL, key=lambda o: o != 'REDUCE_SCATTER'):
        lab, color, mk = COLL[op]
        for g, ls in zip(gpus, ('-', '--')):
            y = [t[(op, g, s, 'rdma')] / t[(op, g, s, 'loom')] for s in sizes]
            ax.plot(x, y, color=color, linestyle=ls, marker=mk, **(big if op == 'REDUCE_SCATTER' else LINE))
            print(f'coll {op} {g} GPUs: ' + ' '.join(f'{size_label(s)} {v:.2f}x' for s, v in zip(sizes, y)))
    ax.set_xticks(x); ax.set_xticklabels([size_label(s) for s in sizes], fontsize=fs['tick'])
    ax.set_xlabel('Size per GPU', fontsize=fs['label'])
    ax.set_ylabel('RDMA (pull) / Loom (push)', fontsize=fs['label'])
    ax.tick_params(axis='y', labelsize=fs['tick'])
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:g}x'))
    ax.grid(True, alpha=0.3)
    h = [Line2D([0], [0], color=c, marker=m, markersize=17 if op == 'REDUCE_SCATTER' else 12, markeredgecolor='k',
                linewidth=2) for op, (_, c, m) in COLL.items()]
    lab = [l for (l, _, _) in COLL.values()]
    h += [Line2D([0], [0], color='gray', linestyle=ls, linewidth=2) for ls in ('-', '--')]
    lab += [f'{g} GPUs' for g in gpus]
    ax.legend(h, lab, loc='upper right', ncol=2, fontsize=fs['legend'] - 3, frameon=True, labelspacing=0.3,
              columnspacing=0.8, handletextpad=0.4)
    title(ax, '(higher = loom faster)', fs['annotation'])
    save(fig, out_dir, png_dir, 'eval-coll')


# ----------------------------------------------------------------------------- testbed microbenchmarks (E1/E2)
X = os.path.expanduser('~/loom-experiments')
# 2026-10-19 redo on the standard images of that day (U280 loom-switch-qdma64 / perf_rdma-qdma, V80 loom-ce-rawin)
RL = 'redo_20261019/20261019_0914_loom_session'     # (V80 era, kept for reference) Loom session
RR = 'redo_20261019/20261019_0839_rdma_session'     # (V80 era) RDMA session
RE1 = 'e1/20261019_0842_samedata_rdma_ack'           # (V80 era) RDMA E1
# 2026-10-19 evening (owner): host memory + PTDMA everywhere, every sender waits for its ack, controlled CPU environment
H = 'e5_ptdma/20261019_2103_e124'                    # E1 / E2 / E4, both systems (run_e124_session.sh)
HB = 'e5_ptdma/20261019_2141_e124'                   # E2 RDMA with one WRITE per message (RE2TAG=bulk), same environment
# E5 two ranks, searched in order (first match wins): 2026-10-20 night final (run_e5_final_20261020.sh: Loom block + RDMA per
# point on a fresh setup from ag 256K) and the per-point run for RDMA ag 1K-64K; was 20261020_1616_e5rerun (RDMA slow state)
H5 = ('e5_ptdma/20261020_2218_e5fin', 'e5_ptdma/20261020_1922_e5pp')
# 2026-10-19 night (owner): the model validated on the prototype, drawn next to the measurements (hollow markers, dotted):
# ~/loom-experiments/val_model/run_val.py (the NIC model at the prototype's links, one fitted link delay); runs/current ->
# the run used in the paper. compare.tsv rows: exp, system, point, metric, measured, model, err_pct.
VAL = 'val_model/runs_an/current/compare.tsv' if AN else 'val_model/runs/current/compare.tsv'
MODEL_STYLE = dict(linestyle=':', markerfacecolor='white', markeredgewidth=2, zorder=5)


def model_style(base, color, **kw):
    """hollow markers edged in the system's colour, dotted line, a bit smaller than the measured markers"""
    return dict(base, **dict(MODEL_STYLE, markeredgecolor=color, markersize=base['markersize'] * 0.75, **kw))


def val_model():
    p = os.path.join(X, VAL)
    if not os.path.exists(p):
        print('model overlay: no', p); return {}
    d = {}
    for l in open(p).read().splitlines()[1:]:
        exp, sy, pt, met, _, mo, _ = l.split('\t')
        d[(exp, sy, pt, met)] = float(mo)
    return d
E2_LAT = {   # one-way latency samples (ns), 4,000 per size, one-way = round trip / 2
    # 2026-10-19 evening, host memory on both sides: CPU stores vs one RDMA WRITE per 64 B (dashed pair), PTDMA vs one RDMA
    # WRITE per message (solid pair); each with the 8 B flag behind it, the receiver's CPU polls host memory
    'h_stores': (H + '/e2_stores_{s}.oneway_ns.txt', 'Loom: CPU stores'),
    'h_ptdma': (H + '/e2_ptdma_{s}.oneway_ns.txt', 'Loom: PTDMA'),
    'h_rdma64': (H + '/e2_rdma_{s}.oneway_ns.txt', 'RDMA: 64 B writes'),
    'h_rdma1': (HB + '/e2_rdma_bulk_{s}.oneway_ns.txt', 'RDMA: one write'),
    # (a) per posting (2026-10-16, e2/20261016_0706_lat, same images): source V80 HBM, landing in the peer's host memory,
    # a CPU starts every transfer (Loom: a preloaded V80 program, ce_pingpong --host; RDMA: one posted WRITE + the 8 B
    # flag WRITE, rdma_pingpong --src-v80 --read-ahead 0 or 6: the better median per size) and polls the flag in host memory
    'loom_ce': ('e2/20261016_0706_lat/loom_{s}.oneway_ns.txt', 'Loom (push)'),
    'rdma_bulk': ('e2/20261016_0706_lat/rdma_ra6_{s}.oneway_ns.txt', 'RDMA (pull)'),   # read-ahead WINDOW (owner 2026-10-19: one mode only)
    # (b) CPU stores (uwin_pingpong) vs one RDMA WRITE per 64 B chunk through a 32-entry send queue (rdma_pingpong
    # --chunk 64 --sq 32), host to host
    'loom_cpu': (RL + '/e2_loom_cpu_{s}.oneway_ns.txt', 'loom: cpu stores'),
    'rdma_chunk': (RR + '/e2_rdma_chunk64_sq32_{s}.oneway_ns.txt', 'rdma: 64 B writes, 32-deep queue'),
}
E2_SIZES = (0, 64, 256, 1024, 4096, 16384, 65536)


def lat(key, sizes=None):
    """(median, p99, alternative index) per size in us; with several sample files per size (RDMA read-ahead 0 / 6)
    the one with the lower median"""
    out = []
    paths = E2_LAT[key][0] if isinstance(E2_LAT[key][0], tuple) else (E2_LAT[key][0],)
    for s in (sizes or E2_SIZES):
        best = None
        for i, pth in enumerate(paths):
            f = os.path.join(X, pth.format(s=s))
            if not os.path.exists(f):
                continue
            v = sorted(float(l) for l in open(f) if l.strip())
            if len(v) < 100:    # a failed run (e.g. RDMA WINDOW at 1 MiB, 2026-10-16) leaves no samples
                continue
            m = (statistics_median(v) / 1000, v[int(0.99 * (len(v) - 1))] / 1000, i)
            if best is None or m[0] < best[0]:
                best = m
        out.append(best)
    return out


def statistics_median(v):
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def e1_series_h():
    """E1 (2026-10-19 evening, host memory): same data re-sent, min(64 MiB/m, 1024) messages a run, 11 runs (run 0 = warm-up),
    rose -> amy's host memory, the sender's rate up to the receiver's acknowledgement (Loom: ce_remote --engine ptdma --ack;
    RDMA: landing_client --contig 0 --wait 1 --ack 1). Returns {series: [(size, median, ci_lo, ci_hi)]}."""
    import re, math
    def mci(v):
        v = sorted(v); n = len(v); med = (v[(n - 1) // 2] + v[n // 2]) / 2; k = None
        for j in range(1, n // 2 + 1):
            if 1 - 2 * sum(math.comb(n, i) for i in range(j)) / 2 ** n >= 0.95:
                k = j
        return (med, v[k - 1], v[n - k]) if k else (med, med, med)
    sizes = (4096, 8192, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864)
    out = {'loom': [], 'rdma': []}
    for s in sizes:
        for key, pat, rx in (('loom', f'{H}/e1_loom_{s}{{}}.client.log', r'ack back \S+ us after the first start \((\S+) GB/s'),
                             ('rdma', f'{H}/e1_rdma_{s}{{}}.client.log', r'^ok +run (?:[1-9]\d*): .* = (\S+) GB/s')):
            v = []
            for suf in ('', '_retry', '_try2', '_try3'):
                f = os.path.join(X, pat.format(suf))
                if os.path.exists(f):
                    v = [float(x) for x in re.findall(rx, open(f).read(), re.M)]
                    if key == 'loom':
                        v = v[1:]          # run 0 = warm-up
                    if v:
                        break
            if v:
                out[key].append((s, *mci(v)))
    return out


def e1_series():
    """E1 (2026-10-19), same data per message (one m-byte source in rose's V80 HBM re-sent, min(64 MiB/m, 1024) messages
    a run, 10 runs), rose -> amy's V80 HBM; the sender's rate up to the receiver's acknowledgement (Loom: ce_remote --prog
    --ack; RDMA: landing_client --wait 1 --ack 1, read-ahead 0 or 6: the better median per size).
    Returns {series: [(size, median, best, alt)]}, alt = RDMA read-ahead index (0 none, 1 WINDOW)."""
    import re
    def med(v):
        return statistics_median(sorted(v)) if v else float('nan')
    sizes = (4096, 8192, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864)
    loom, rdma, get = [], [], []
    for s in sizes:
        v = []
        for f in (f'{RL}/e1_loom_v80_{s}.client.log', f'{RL}/e1_loom_v80_{s}_r20.client.log'):   # 16/64 MiB: + 20-run recheck
            if os.path.exists(os.path.join(X, f)):
                v += [float(x) for x in re.findall(r'ack back \S+ us after the first start \((\S+) GB/s', open(os.path.join(X, f)).read())]
        loom.append((s, med(v), max(v), 0))
        cand = []
        for i, ra in ((1, 6),):   # read-ahead WINDOW only (owner 2026-10-19)
            f = os.path.join(X, f'{RE1}/v80_to_v80_{s}_ra{ra}.client.log')
            v = [float(x) for x in re.findall(r'^ok +run \d+: .* = (\S+) GB/s', open(f).read(), re.M)]
            if v:
                cand.append((s, med(v), max(v), i))
        rdma.append(max(cand, key=lambda c: c[1]))
    # Loom gets (V80 engine reads a remote export; regress/20261015_loom-ce-rawin, same images, 3 runs a size)
    g = {}
    for l in open(os.path.join(X, 'regress/20261015_loom-ce-rawin/ceget_net_client.log')):
        x = re.match(r'ok\s+get\s+(\d+) bytes:\s+\S+ us \(\s*(\S+) GB/s\)', l)
        if x:
            g.setdefault(int(x.group(1)), []).append(float(x.group(2)))
    get = [(s, med(v), max(v), 0) for s, v in sorted(g.items())]
    return {'loom': loom, 'rdma': rdma, 'get': get}


def figure_micro(out_dir, png_dir):
    # 2026-10-19 (owner): one memory everywhere: the data starts in XPU (V80) memory in both systems; (a) one-way latency of one
    # message (Loom copy engine vs one RDMA write), (b) throughput of the same message re-sent. CPU stores are left out.
    # Single-column figure (owner 2026-10-19): one shared legend above both panels.
    fs = SINGLE_COLUMN_FONT_SIZES
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4))
    fig.subplots_adjust(left=0.09, right=0.99, top=0.80, bottom=0.25, wspace=0.28)
    LN = dict(LINE, markersize=8, linewidth=1.8)
    # 2026-10-19 evening (owner): host memory on both sides; (a) CPU stores, PTDMA and RDMA on one plot: colour = system,
    # line style = the like-for-like pair (dashed: CPU stores vs one RDMA write per 64 B; solid: PTDMA vs one RDMA write per
    # message); medians with p99 whiskers; log scale (4 to 350 us)
    SIZES = (0, 64, 256, 1024, 4096, 16384, 65536)
    ax = axes[0]
    x = np.arange(len(SIZES))
    labels = [size_label(s) if s else '8 B' for s in SIZES]   # size 0 = the 8-byte flag write alone
    for k, color, mk, ls, dx in (('h_rdma64', SYSTEMS['rdma'][1], 's', '--', 0.09), ('h_rdma1', SYSTEMS['rdma'][1], '^', '-', 0.03),
                                 ('h_stores', SYSTEMS['loom'][1], 'o', '--', -0.03), ('h_ptdma', SYSTEMS['loom'][1], 'D', '-', -0.09)):
        v = lat(k, SIZES)
        if any(e is None for e in v):
            print(f'E2 {k}: missing samples'); continue
        med = np.array([a for a, _, _ in v]); p99 = np.array([b for _, b, _ in v])
        ax.plot(x, med, color=color, marker=mk, label=E2_LAT[k][1], **dict(LN, linestyle=ls))
        ax.errorbar(x + dx, med, yerr=[np.zeros_like(med), p99 - med], fmt='none', ecolor=color, elinewidth=1.2, capsize=4,
                    capthick=1.2, alpha=0.8)
        print(f'E2 {k}: ' + ' '.join(f'{lb} {a:.2f}/{b:.2f}' for lb, (a, b, _) in zip(labels, v)) + ' (median/p99 us)')
    V = val_model()   # model: one Loom line (a source's posted writes) and one RDMA line (one write per message)
    for sy, color, mk, lab in (('rdma', SYSTEMS['rdma'][1], '^', 'RDMA (model)'), ('loom_stores', SYSTEMS['loom'][1], 'o', 'Loom (model)')):
        mv = [V.get(('e2', sy, str(s), 'oneway_us'), np.nan) for s in SIZES]
        if not all(np.isnan(mv)):
            ax.plot(x, mv, color=color, marker=mk, label=lab, **model_style(LN, color))
            print(f'E2 model {sy}: ' + ' '.join(f'{lb} {v:.2f}' for lb, v in zip(labels, mv)))
    ax.set_yscale('log')
    ax.set_ylim(3, 500)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=fs['tick'] - 4, rotation=45, ha='right', rotation_mode='anchor')
    ax.set_xlabel('Message size', fontsize=fs['label'])
    ax.set_ylabel('One-way latency [us]', fontsize=fs['label'])
    title(ax, '(a) Latency (lower is better)', fs['annotation'] - 2)
    ax = axes[1]
    d = e1_series_h()   # (b) PTDMA vs one RDMA write per message, both up to the receiver's ack; whiskers = 95% CI of the median
    sizes = [s_ for s_, *_ in d['loom']]
    xi = {s_: i for i, s_ in enumerate(sizes)}
    for key, color, mk in (('rdma', SYSTEMS['rdma'][1], '^'), ('loom', SYSTEMS['loom'][1], 'D')):
        ser = d[key]
        xs = [xi[t[0]] for t in ser]; md = np.array([t[1] for t in ser])
        lo = np.array([t[2] for t in ser]); hi = np.array([t[3] for t in ser])
        ax.plot(xs, md, color=color, marker=mk, **LN)
        ax.errorbar(xs, md, yerr=[md - lo, hi - md], fmt='none', ecolor=color, elinewidth=1.2, capsize=4, capthick=1.2, alpha=0.8)
        print(f'E1 {key}: ' + ' '.join(f'{size_label(t[0])} {t[1]:.2f} [{t[2]:.2f} {t[3]:.2f}]' for t in ser) + ' GB/s (median [95% CI])')
        mv = [V.get(('e1', key, str(s_), 'gbps'), np.nan) for s_ in sizes]
        if not all(np.isnan(mv)):
            ax.plot(range(len(sizes)), mv, color=color, marker={'rdma': '^', 'loom': 'o'}[key], **model_style(LN, color))
    ax.set_xticks(range(len(sizes)))
    ax.set_xticklabels([size_label(s_) for s_ in sizes], fontsize=fs['tick'] - 4, rotation=45, ha='right', rotation_mode='anchor')
    ax.set_xlabel('Message size', fontsize=fs['label'])
    ax.set_ylabel('Throughput [GB/s]', fontsize=fs['label'])
    ax.set_ylim(0, 14)
    title(ax, '(b) Throughput (higher is better)', fs['annotation'] - 2)
    for a in axes:
        a.tick_params(axis='y', labelsize=fs['tick'])
        a.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:g}'))
        a.grid(True, alpha=0.3)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc='upper center', bbox_to_anchor=(0.54, 1.02), ncol=3, frameon=False, fontsize=fs['legend'] - 2)
    save(fig, out_dir, png_dir, 'eval-micro')


# ------------------------------------------------------------------------- E4: dispatch / combine on the testbed
def e4_data_h():
    """E4 (2026-10-19 evening, host memory on both sides, H): Loom = ce_dispatch --engine ptdma (copies / signal issued = the
    CPU's submits, engine done = the PTDMA engine wrote everything = the source may be reused, ack back), RDMA = rdma_dispatch
    --src-host ordered / flush; amy sends into rose's host memory, medians of 21 runs (the tools' summary lines)."""
    import re
    rx = re.compile(r'^(dispatch|combine) (\d+) tokens.*?\): (.*)$', re.M)
    def fields(f):
        if not os.path.exists(f):
            return None
        m = rx.search(open(f).read())
        return {k: float(v) for k, v in re.findall(r'(copies|signal issued|completions|ack back|engine done) ([0-9.]+) \[', m[3])} if m else None
    def first(name, word):
        for suf in ('', '_retry', '_try2', '_try3'):
            b = os.path.join(X, H, name + suf)
            if all(os.path.exists(f'{b}.{s}.log') and word in open(f'{b}.{s}.log').read() for s in ('server', 'client')):
                return b + '.client.log'
        return ''
    loom, rdma = {}, {}
    for op, T in (('dispatch', 0), ('dispatch', 1), ('dispatch', 16), ('dispatch', 128), ('combine', 1), ('combine', 16), ('combine', 128)):
        v = fields(first(f'e4_loom_{op}_t{T}', 'DISPATCH PASS'))
        if v:
            loom[(op, T)] = dict(cpu=v['signal issued'], busy=v['engine done'], ack=v['ack back'])
        for mode in ('ordered', 'flush'):
            v = fields(first(f'e4_rdma_{op}_t{T}_{mode}', 'RDMA DISPATCH PASS'))
            if v:
                rdma[(op, T, mode)] = dict(cpu=v['signal issued'], busy=v['completions'] if mode == 'ordered' else v['signal issued'],
                                           ack=v['ack back'])
    lf = loom[('dispatch', 0)]['ack'] / 2; rf = rdma[('dispatch', 0, 'ordered')]['ack'] / 2   # one flag's one-way time
    for v in loom.values(): v['flag'] = lf
    for v in rdma.values(): v['flag'] = rf
    return f'{H}', loom, rdma


def e4_data():
    """E4 (2026-10-19): Loom = ce_dispatch --land-host (RL/e4_loom_*), RDMA = rdma_dispatch (RR/e4_*), amy sends into
    rose's host memory, medians of 21 runs. V80 source: read-ahead 0 or 6, the lower sender busy per point (the 14
    read-ahead-0 points were rerun 2026-10-19 after a run had left WINDOW on; old logs *.wasra6.log)."""
    import glob, re
    loom, rdma = {}, {}
    for f in glob.glob(os.path.join(X, RL, 'e4_loom_*.client.log')):
        m = re.search(r'^(dispatch|combine) (\d+) tokens, (\d+) x (\d+) B \(us, \d+ runs, median \[min max\]\): copies \S+ \[[^]]*\]'
                      r'\s+signal issued (\S+) \[[^]]*\]\s+ack back (\S+)', open(f).read(), re.M)
        if m:
            loom[(m[1], int(m[2]))] = dict(issued=float(m[5]), ack=float(m[6]))
    for f in glob.glob(os.path.join(X, RR, 'e4_*.client.log')):
        if 'wasra6' in f or '/e4_loom' in f:
            continue
        ra = re.search(r'_ra(\d)_', f)
        m = re.search(r'^(dispatch|combine) (\d+) tokens, (\d+) x (\d+) B, (ordered|flush), source (V80|host) \(us, \d+ runs, '
                      r'median \[min max\]\): signal issued (\S+) \[[^]]*\]\s+completions (\S+) \[[^]]*\]\s+ack back (\S+)',
                      open(f).read(), re.M)
        if not m:
            continue
        r = dict(issued=float(m[7]), reaped=float(m[8]), ack=float(m[9]), ra=int(ra[1]) if ra else None)
        r['busy'] = r['reaped'] if m[5] == 'ordered' else r['issued']
        k = (m[1], int(m[2]), m[5], m[6])
        rdma.setdefault(k, []).append(r)
    best = {}
    for k, rs in rdma.items():
        w = [r for r in rs if r['ra'] in (None, 6)]   # V80 source: read-ahead WINDOW only (owner 2026-10-19)
        b = min(w, key=lambda r: r['busy'])
        z = [r for r in rdma.get(('dispatch', 0, k[2], k[3]), []) if r['ra'] == b['ra']]
        b['flag'] = z[0]['ack'] / 2 if z else float('nan')          # one flag's one-way: half the 0-token round trip
        best[k] = b
    if ('dispatch', 0) in loom:
        for v in loom.values():
            v['flag'] = loom[('dispatch', 0)]['ack'] / 2
    return f'loom {RL}, rdma {RR}', loom, best


def figure_e4(out_dir, png_dir):
    figure_e4_h(out_dir, png_dir)   # 2026-10-19 evening: host memory + PTDMA (the V80 version below is kept for reference)


def figure_e4_h(out_dir, png_dir):
    # bars = how long the sender is busy until its buffers may be reused (Loom: the PTDMA engine has written everything; RDMA
    # ordered: completions collected; flush: the signal is posted after every completion); the dark lower part = until its CPU
    # is free (Loom: descriptors submitted; RDMA ordered: signal posted). Labels = ratio to Loom's bar.
    D, loom, rdma = e4_data_h()
    fs = COMBINED_FONT_SIZES
    fig = plt.figure(figsize=(E2E_COMBINED_FIGURE_SIZE[0], 8.5))
    gs = fig.add_gridspec(1, 2, left=0.04, right=0.99, top=0.88, bottom=0.30, wspace=0.10)
    BARS = (('loom', 'Loom', 'Loom (push)', 'tab:green'), ('ordered', 'RDMA\nord.', 'RDMA (pull), ordered', 'lightskyblue'),
            ('flush', 'RDMA\nflush', 'RDMA (pull), flush', 'tab:blue'))
    handles = {}
    for g, op, ttl in ((gs[0, 0], 'dispatch', '(a) Dispatch, 7 KiB tokens (lower is better)'), (gs[0, 1], 'combine', '(b) Combine, 14 KiB tokens (lower is better)')):
        axes = [fig.add_subplot(c) for c in g.subgridspec(1, 3, wspace=0.35)]
        for ax, T in zip(axes, (1, 16, 128)):
            x = np.arange(len(BARS)); vals = []
            for i, (mode, tick, lab, color) in enumerate(BARS):
                r = loom[(op, T)] if mode == 'loom' else rdma[(op, T, mode)]
                b = ax.bar(x[i], r['busy'], 0.7, color=color, edgecolor='black', linewidth=1, label=lab)
                handles.setdefault(lab, b)
                c = ax.bar(x[i], min(r['cpu'], r['busy']), 0.7, color='none', hatch='xx', edgecolor='dimgray', linewidth=0.8)
                handles.setdefault('CPU busy', c)
                vals.append(r['busy'])
            top = max(vals); base = vals[0]
            for i in range(1, len(BARS)):
                ax.text(x[i], vals[i] + 0.05 * top, f'{vals[i] / base:.1f}x', ha='center', va='bottom', fontsize=fs['annotation'] - 14,
                        color='#a04040')
            ax.text(x[0], base + 0.05 * top, f'{base:.0f}', ha='center', va='bottom', fontsize=fs['annotation'] - 14)
            ax.set_ylim(0, top * 1.3)
            ax.set_xticks(x); ax.set_xticklabels([b[1] for b in BARS], fontsize=fs['tick'] - 16)
            ax.tick_params(axis='y', labelsize=fs['tick'] - 6)
            ax.yaxis.set_major_locator(mticker.MaxNLocator(3))
            ax.grid(True, alpha=0.3, axis='y')
            ax.set_xlabel(f'{T} token{"s" if T > 1 else ""}', fontsize=fs['label'] - 4)
        axes[0].set_ylabel('Sender busy [us]', fontsize=fs['label'])
        fig.text((axes[0].get_position().x0 + axes[-1].get_position().x1) / 2, 0.985, ttl, ha='center', va='top',
                 fontsize=fs['annotation'], color='navy', fontweight='bold')
    order = ['Loom (push)', 'RDMA (pull), ordered', 'RDMA (pull), flush', 'CPU busy']
    fig.legend([handles[o] for o in order], order, loc='upper center', bbox_to_anchor=(0.5, 0.115), ncol=4, frameon=False,
               fontsize=fs['legend'] - 10, handlelength=1.6, columnspacing=1.2, borderaxespad=0)
    save(fig, out_dir, png_dir, 'eval-e4')
    print('E4 data:', D)
    for op in ('dispatch', 'combine'):
        for T in (1, 16, 128):
            l = loom[(op, T)]
            row = f"E4 {op} {T}: loom cpu/busy/delivered {l['cpu']:.2f}/{l['busy']:.2f}/{l['ack'] - l['flag']:.2f}"
            for mode in ('ordered', 'flush'):
                r = rdma[(op, T, mode)]
                row += f" | rdma {mode} cpu/busy/delivered {r['cpu']:.2f}/{r['busy']:.2f}/{r['ack'] - r['flag']:.2f}"
            print(row)


def figure_e4_v80(out_dir, png_dir):
    d = e4_data()
    if not d:
        print('E4: no data yet'); return
    D, loom, rdma = d
    need = [(op, T) for op in ('dispatch', 'combine') for T in (1, 16, 128)]
    if not all(k in loom for k in need) or not all((op, T, mode, src) in rdma for op, T in need
                                                   for mode in ('ordered', 'flush') for src in ('V80',)):
        print('E4: incomplete in', D); return
    fs = COMBINED_FONT_SIZES
    fig = plt.figure(figsize=(E2E_COMBINED_FIGURE_SIZE[0], 8.5))
    gs = fig.add_gridspec(1, 2, left=0.04, right=0.99, top=0.88, bottom=0.30, wspace=0.10)
    # RDMA bars: colour = completion mode (ordered light, flush dark), hatch = payload source (V80 plain, host dotted);
    # ordered bars carry the completions the sender collects later on top
    BARS = (('loom', None, None, 'Loom (push)', 'tab:green', ''), ('ordered', 'V80', 'RDMA\nord.', 'RDMA (pull), ordered', 'lightskyblue', ''),
            ('flush', 'V80', 'RDMA\nflush', 'RDMA (pull), flush', 'tab:blue', '//'))   # owner 2026-10-19: one memory (XPU) only
    handles = None
    for g, op, ttl in ((gs[0, 0], 'dispatch', '(a) Dispatch, 7 KiB tokens (lower is better)'), (gs[0, 1], 'combine', '(b) Combine, 14 KiB tokens (lower is better)')):
        axes = [fig.add_subplot(c) for c in g.subgridspec(1, 3, wspace=0.35)]
        for ax, T in zip(axes, (1, 16, 128)):
            x = np.arange(len(BARS)); base = loom[(op, T)]['issued']; tops = []; dls = []
            for i, (mode, src, tick, lab, color, hatch) in enumerate(BARS):
                if mode == 'loom':
                    v, reap = base, 0.0; dl = loom[(op, T)]['ack'] - loom[(op, T)]['flag']
                else:
                    r = rdma[(op, T, mode, src)]; v = r['issued']; reap = r['reaped'] - v if mode == 'ordered' else 0.0
                    dl = r['ack'] - r['flag']
                ax.bar(x[i], v, 0.7, color=color, hatch=hatch, edgecolor='black', linewidth=1, label=lab)
                dls.append(0.0)   # delivery: in the text (owner 2026-10-19: no diamonds)
                if reap > 0:
                    ax.bar(x[i], reap, 0.7, bottom=v, color='white', hatch='++', edgecolor='gray', linewidth=1,
                           label='completions collected later')
                tops.append(v + reap)
            top = max(max(tops), max(dls))
            for i in range(1, len(BARS)):
                ax.text(x[i], max(tops[i], dls[i]) + 0.05 * top, f'{tops[i] / base:.1f}x', ha='center', va='bottom',
                        fontsize=fs['annotation'] - 14, color='#a04040')
            ax.text(x[0], max(base, dls[0]) + 0.05 * top, f'{base:.0f}', ha='center', va='bottom', fontsize=fs['annotation'] - 14)
            ax.set_ylim(0, top * 1.3)
            ax.set_xticks(x); ax.set_xticklabels(['Loom'] + [b[2] for b in BARS[1:]], fontsize=fs['tick'] - 16)
            ax.tick_params(axis='y', labelsize=fs['tick'] - 6)
            ax.yaxis.set_major_locator(mticker.MaxNLocator(3))
            ax.grid(True, alpha=0.3, axis='y')
            ax.set_xlabel(f'{T} token{"s" if T > 1 else ""}', fontsize=fs['label'] - 4)
            if handles is None:
                h, l = ax.get_legend_handles_labels(); keep = {}
                for hh, ll in zip(h, l): keep.setdefault(ll, hh)
                handles = (list(keep.values()), list(keep.keys()))
        axes[0].set_ylabel('Sender busy [us]', fontsize=fs['label'])
        fig.text((axes[0].get_position().x0 + axes[-1].get_position().x1) / 2, 0.985, ttl, ha='center', va='top',
                 fontsize=fs['annotation'], color='navy', fontweight='bold')
    order = ['Loom (push)', 'RDMA (pull), ordered', 'RDMA (pull), flush', 'completions collected later']
    hd = dict(zip(handles[1], handles[0]))
    fig.legend([hd[o] for o in order], order, loc='upper center', bbox_to_anchor=(0.5, 0.115), ncol=4, frameon=False,
               fontsize=fs['legend'] - 10, handlelength=1.6, columnspacing=1.2, borderaxespad=0)
    save(fig, out_dir, png_dir, 'eval-e4')
    print('E4 data:', D)
    for op in ('dispatch', 'combine'):
        for T in (0, 1, 16, 128):
            l = loom.get((op, T)); row = f'E4 {op} {T} tok: loom issued/ack ' + (f"{l['issued']:.2f}/{l['ack']:.2f}" if l else '-')
            for src in ('V80', 'host'):
                for mode in ('ordered', 'flush'):
                    r = rdma.get((op, T, mode, src))
                    if r:
                        row += f" | rdma {mode} {src} issued/reaped/ack {r['issued']:.2f}/{r['reaped']:.2f}/{r['ack']:.2f}"
            print(row)


# --------------------------------------------------------------------------------- E5: collectives on the testbed
# 2026-10-20 (owner): four panels, the same collectives as the at-scale figure (eval-coll); at two ranks the ring all-reduce is
# reduce-scatter + all-gather of the halves, so the direct all-reduce adds nothing; the broadcast (one way) is text only.
E5_COLLS = (('ag', 'All-gather'), ('a2a', 'All-to-all'), ('rs', 'Reduce-scatter'), ('ar_ring', 'All-reduce'))
E5_COLLS_ALL = E5_COLLS + (('ar_direct', 'All-reduce, direct'), ('bc', 'Broadcast (+ ack)'))


def e5_data_h():
    """E5 (2026-10-19 evening, H5 = run_coll2_session.sh, host memory, controlled env): Loom = ce_coll --engine ptdma --ptq-user
    --acked (bc: --ack-store --acked, the receiver's ack = one CPU store), RDMA = rdma_coll --host --acked. Per run the slower
    rank's time (both ranks time the same run), the median of the 10 timed runs; a point counts only if both ranks PASS and
    log the controlled environment. res[(sys, c, S)] = (us, None)."""
    import glob, re, statistics
    RUN = re.compile(r'^ +run (\d+): ([\d.]+) us per ', re.M)
    ENV = re.compile(r'^env \S+: governor (\S+) boost (\S+) smt \S+ numa_balancing (\S+) dma_latency (\S+)', re.M)
    def point(prefix, word):
        per = []
        for r in ('r0', 'r1'):
            f = f'{prefix}.{r}.log'
            if not os.path.exists(f):
                return None
            t = open(f).read()
            e = ENV.search(t)
            if word not in t or not e or 'schedutil' in e[1] or e[2] != '0' or e[3] != '0' or e[4] != 'held0':
                return None
            per.append({int(i): float(v) for i, v in RUN.findall(t)})
        idx = sorted(set(per[0]) & set(per[1]))
        return statistics.median([max(per[0][i], per[1][i]) for i in idx]) if idx else None
    res = {}
    for c, _ in E5_COLLS:
        for S in (1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216):
            for sysname, var, word in (('loom', 'ackst_acked' if c == 'bc' else 'useracked', 'COLL PASS'), ('rdma', 'hostacked', 'RDMA COLL PASS')):
                for D in (os.path.join(X, h) for h in H5):
                    for suf in ('', '_retry', '_try2', '_try3'):
                        v = point(f'{D}/{var}{suf}_{c}_{S}', word)
                        if v:
                            res[(sysname, c, S)] = (v, None); break
                    if (sysname, c, S) in res:
                        break
    return ' + '.join(H5), res


def e5_data():
    """E5 (2026-10-19): Loom = ce_coll (RL/e5_loom_<c>_<S>.r0/r1.log), RDMA = rdma_coll with read-ahead 0 and 6
    (RR/e5_rdma_<c>_<S>_ra<m>.r0/r1.log; failed attempts kept as *.fail<k>.log). Per point the slower rank's median of
    5 runs (each run = K collectives back to back, us per collective); a point counts only if both ranks PASS; RDMA =
    the read-ahead mode with the lower time. res[(sys, c, S)] = (us, ra index or None)."""
    import glob, re
    pat = re.compile(r'^(server|client) ([a-z_0-9]+) (\d+) B \(us per collective, \d+ runs, median \[min max\]\): (\S+)', re.M)
    def point(prefix):
        t, ok = 0.0, True
        for r in ('r0', 'r1'):
            f = prefix + f'.{r}.log'
            if not os.path.exists(f):
                return None
            txt = open(f).read()
            ok = ok and ('COLL PASS' in txt)
            for m in pat.finditer(txt):
                t = max(t, float(m[4]))
        return t if ok and t > 0 else None
    res = {}
    for f in glob.glob(os.path.join(X, RL, 'e5_loom_*.r0.log')):
        m = re.search(r'e5_loom_([a-z_0-9]+?)_(\d+)\.r0\.log$', f)
        v = point(f[:-7])
        if m and v:
            res[('loom', m[1], int(m[2]))] = (v, None)
    for f in glob.glob(os.path.join(X, RR, 'e5_rdma_*_ra6.r0.log')):   # read-ahead WINDOW only (owner 2026-10-19)
        m = re.search(r'e5_rdma_([a-z_0-9]+?)_(\d+)_ra(\d)\.r0\.log$', f)
        if not m:
            continue
        v = point(f[:-7])
        k = ('rdma', m[1], int(m[2]))
        if v and (k not in res or v < res[k][0]):
            res[k] = (v, (0, 6).index(int(m[3])))
    return f'loom {RL}, rdma {RR}', res


def figure_e5(out_dir, png_dir):
    d = e5_data_h()   # 2026-10-19 evening: host memory, both acked (e5_data() = the V80 version, kept for reference)
    if not d:
        print('E5: no data yet'); return
    D, res = d
    sizes = sorted({k[2] for k in res})
    if not any(k[0] == 'rdma' for k in res):
        print('E5: no RDMA data yet in', D); return
    fs = COMBINED_FONT_SIZES
    fig, axes = plt.subplots(1, len(E5_COLLS), figsize=(E2E_COMBINED_FIGURE_SIZE[0], 8.5))
    fig.subplots_adjust(left=0.04, right=0.99, top=0.88, bottom=0.30, wspace=0.30)
    x = np.arange(len(sizes))
    V = val_model()   # model next to the measurements: ag, a2a and bc (rs / ar include the CPU's reduction, not modelled)
    for ax, (c, ttl) in zip(axes, E5_COLLS):
        for sysname, color, mk, lab in (('rdma', SYSTEMS['rdma'][1], 's', SYSTEMS['rdma'][0]), ('loom', SYSTEMS['loom'][1], 'o', SYSTEMS['loom'][0])):
            y = [res.get((sysname, c, s), (np.nan, None))[0] for s in sizes]
            ax.plot(x, y, color=color, marker=mk, label=lab, **LINE_BIG)
            mv = [V.get(('e5', sysname, f'{c}_{s}', 'us'), np.nan) for s in sizes]
            if not all(np.isnan(mv)):
                ax.plot(x, mv, color=color, marker=mk, label=lab.split(' ')[0] + ' (model)', **model_style(LINE_BIG, color, markeredgewidth=3))
            if sysname == 'rdma':    # hollow: read-ahead off (0) was the better RDMA mode at that point
                for xi_, s in zip(x, sizes):
                    v = res.get((sysname, c, s))
                    if v and v[1] == 0:
                        ax.plot([xi_], [v[0]], marker=mk, markersize=LINE_BIG['markersize'], markerfacecolor='white',
                                markeredgecolor=color, markeredgewidth=3, linestyle='none')
        for i, s in enumerate(sizes):
            r, l = res.get(('rdma', c, s)), res.get(('loom', c, s))
            r, l = (r[0] if r else None), (l[0] if l else None)
            if r and l:
                ax.text(x[i], max(r, l) * 1.35, f'{r / l:.1f}x', ha='center', va='bottom', fontsize=fs['annotation'] - 12, color='#a04040')
        ax.set_yscale('log')
        ax.set_xticks(x); ax.set_xticklabels([size_label(s) for s in sizes], fontsize=fs['tick'] - 12, rotation=30)
        ax.tick_params(axis='y', labelsize=fs['tick'] - 6)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:g}'))
        ax.grid(True, alpha=0.3)
        ax.set_ylim(top=ax.get_ylim()[1] * 3)
        title(ax, ttl, fs['annotation'] - 8)
    axes[0].set_ylabel('Time [us]', fontsize=fs['label'])
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h + [Line2D([0], [0], color='white')], l + ['x: data per rank; labels: RDMA / Loom'], loc='upper center',
               bbox_to_anchor=(0.5, 0.135), ncol=5, frameon=False, fontsize=fs['legend'] - 6, borderaxespad=0)
    save(fig, out_dir, png_dir, 'eval-e5')
    print('E5 data:', D)
    for c, _ in E5_COLLS:
        print(f'E5 {c}: ' + ' '.join(f"{size_label(s)} loom {res.get(('loom', c, s), (float('nan'),))[0]:.1f} rdma {res.get(('rdma', c, s), (float('nan'),))[0]:.1f}" for s in sizes))


# ------------------------------------------------------------------------ link-rate sweep (model)
SWEEP = 'val_model/sweep_an/current/sweep.tsv' if AN else 'val_model/sweep/current/sweep.tsv'   # ~/loom-experiments/val_model/run_sweep.py (owner 2026-10-20)
SWEEP_RATES = (('100', 100), ('200', 200), ('400', 400), ('800', 800), ('1600', 1600))
SIZE_COLORS = ('tab:orange', 'tab:red', 'tab:purple', 'tab:brown')


def figure_sweep(out_dir, png_dir):
    """Sensitivity of the at-scale model (owner 2026-10-21: one parameter at a time, the new Fig 13; was the link-rate
    sweep alone): (a) link rate, PCIe scaled with it (Gen5 up to 400 Gbps, Gen6 at 800, Gen7 at 1600), (b) the GPU's PCIe
    latencies (doorbell/store, NIC read, write: 645 / 1350 / 645 ns measured) x 0.25 .. 2, (c) the network stack (RoCE
    transport, MAC, PHY: the NIC's 260 / 590 ns, which Loom reuses; Loom keeps its 21 / 7 cycles on top) x 0.25 .. 2;
    (b) and (c) at 400 Gbps. Lines: one message between two GPUs (64 B .. 64 KiB) and an all-to-all of 16 KiB per GPU on
    16 GPUs. y = RDMA time / Loom time (higher = Loom faster); dotted = the nominal point. Data: run_sweep_an.py sweep.tsv
    (the stream rows and the Gen5-at-800 point stay there, not shown)."""
    rows = [l.split('\t') for l in open(os.path.join(X, SWEEP)).read().splitlines()[1:]]
    v = {(r[0], r[1], r[2], int(r[3])): float(r[4]) for r in rows}
    fs = COMBINED_FONT_SIZES
    fig, axes = plt.subplots(1, 3, figsize=(E2E_COMBINED_FIGURE_SIZE[0] * 0.75, 9.5), sharey=True)
    fig.subplots_adjust(left=0.06, right=0.99, top=0.88, bottom=0.31, wspace=0.08)
    LN = dict(LINE, markersize=22, linewidth=4)
    scales = (0.25, 0.5, 1, 1.5, 2)
    cols = ((axes[0], [(t, g) for t, g in SWEEP_RATES], 400, 'Link rate [Gbps]', '(a) Link rate', lambda g: str(g)),
            (axes[1], [('400' if k == 1 else f'pcie{k:g}', k) for k in scales], 1, 'PCIe latency [x measured]',
             '(b) PCIe latency', lambda k: f'{k:g}'),
            (axes[2], [('400' if k == 1 else f'stack{k:g}', k) for k in scales], 1, 'Network-stack latency [x measured]',
             '(c) Network-stack latency', lambda k: f'{k:g}'))
    series = [('lat', s_, c, mk, size_label(s_)) for s_, c, mk in zip((64, 4096, 16384, 65536), SIZE_COLORS, 'osD^')]
    series.append(('a2a', 16384, 'k', 'v', 'All-to-all, 16 GPUs, 16 KiB per GPU'))
    for ax, pts, nominal, xl, ttl, fmt in cols:
        xs = [x for _, x in pts]
        for e, s_, c, mk, lab in series:
            y = [v[(e, 'rdma', t, s_)] / v[(e, 'loom', t, s_)] for t, _ in pts]
            ax.plot(xs, y, color=c, marker=mk, label=lab, linestyle='--' if e == 'a2a' else '-', **LN)
            print(f'sens {ttl} {e} {lab}: ' + ' '.join(f'{fmt(x)} {r:.2f}' for x, r in zip(xs, y)))
        ax.axvline(nominal, color='grey', linestyle=':', linewidth=3)
        ax.set_xscale('log', base=2)
        ax.set_xticks(xs); ax.set_xticklabels([fmt(x) for x in xs], fontsize=fs['tick'] - 6)
        ax.xaxis.set_minor_locator(mticker.NullLocator())
        ax.set_xlabel(xl, fontsize=fs['label'] - 4)
        ax.tick_params(axis='y', labelsize=fs['tick'] - 4)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda q, _: f'{q:g}x'))
        ax.grid(True, alpha=0.3)
        ax.axhline(1.0, color='k', linewidth=2)
        title(ax, ttl, fs['annotation'] - 6)
    axes[0].set_ylim(0.8, 3.6)
    axes[0].set_ylabel('RDMA / Loom', fontsize=fs['label'] - 2)
    h, lab = axes[0].get_legend_handles_labels()
    fig.legend(h + [Line2D([0], [0], color='grey', linestyle=':', linewidth=3)],
               [f'one message, {l}' if i < 4 else l for i, l in enumerate(lab)] + ['nominal'],
               loc='upper center', bbox_to_anchor=(0.5, 0.075), ncol=6, frameon=False, fontsize=fs['legend'] - 10,
               borderaxespad=0, handlelength=2.5)
    save(fig, out_dir, png_dir, 'eval-sweep')


# ------------------------------------------------------------------------ end-to-end training (Phase A, 2026-10-20)
def figure_e2e(out_dir, png_dir):
    """Fig 14 (Phase A, owner 2026-10-20, Opus-style): one bar group per parallelism / application, the traffic of the
    parallelism under test crossing servers; RDMA and Loom iteration of the slowest GPU, normalised to RDMA, split into
    compute and exposed communication (that GPU's). Data: e8/e2e/e2e_phaseA.tsv (tools/collect_e2e.py). Model."""
    ORDER = (('dp', 'DP', 'Llama-3 8B'), ('fsdp', 'FSDP', 'Llama-3 8B'), ('cp', 'CP (32K)', 'Llama-3 8B'),
             ('pp', 'PP', 'Llama-3 70B'), ('hybrid', 'TP+PP+DP', 'Llama-3 70B'), ('l80', 'TP+PP+DP', 'Llama-80B'),
             ('moe_mixed', 'EP+TP+DP', 'MoE'), ('moe_scaleout', 'EP+DP', 'MoE'))   # single column (owner 2026-10-20):
    # full labels rotated by 90 degrees
    t = {}
    # owner 2026-10-21: full depth (the training sweep's runs, AN=1 FULL=1 tools/collect_e2e.py -> e2e_full.tsv); the
    # ns-3 model keeps its Phase A (cut-depth) data
    for l in open(os.path.join(E, D8, 'e2e/e2e_full.tsv' if AN else 'e2e/e2e_phaseA.tsv')).read().splitlines()[1:]:
        k, lab, v, it, ex, n, log = l.split('\t')
        t[(k, v)] = (float(it), float(ex), int(n))
    groups = [g for g in ORDER if (g[0], 'rdma') in t and (g[0], 'loom') in t]
    if not groups:
        print('E2E: no finished pairs yet'); return
    fs = SINGLE_COLUMN_FONT_SIZES
    fig, ax = plt.subplots(figsize=(7.0, 5.6))   # printed at \columnwidth (~3.4 in)
    fig.subplots_adjust(left=0.13, right=0.995, top=0.86, bottom=0.42)
    W = 0.36
    for i, (k, par, model) in enumerate(groups):
        base = t[(k, 'rdma')][0]
        for j, v in enumerate(('rdma', 'loom')):
            it, ex, n = t[(k, v)]
            x = i + (j - 0.5) * W
            c = SYSTEMS[v][1]
            ax.bar(x, (it - ex) / base, W, color=c, alpha=0.55, edgecolor='black', linewidth=1)
            ax.bar(x, ex / base, W, bottom=(it - ex) / base, color='white', edgecolor=c, hatch='///', linewidth=1)
            ax.bar(x, it / base, W, fill=False, edgecolor='black', linewidth=1)
        r = t[(k, 'loom')][0] / base
        pct = (r - 1) * 100
        ax.text(i, 1.03, '0.0%' if abs(pct) < 0.05 else f'{pct:+.1f}%', ha='center', va='bottom', fontsize=fs['annotation'] - 3)
        print(f"E2E {k}: rdma {base:.3f} ms loom {t[(k, 'loom')][0]:.3f} ms ({(r - 1) * 100:+.3f}%), exposed "
              f"{t[(k, 'rdma')][1]:.3f} / {t[(k, 'loom')][1]:.3f} ms, {t[(k, 'rdma')][2]} GPUs")
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([f'{par}, {model}, {t[(k, "rdma")][2]} GPUs' for k, par, model in groups], fontsize=fs['tick'] - 3,
                       rotation=90)
    ax.set_xlim(-0.6, len(groups) - 0.4)
    ax.set_ylim(0, 1.2)
    ax.set_ylabel('Iteration time\n(norm. to RDMA)', fontsize=fs['label'] - 2)
    ax.tick_params(axis='y', labelsize=fs['tick'])
    ax.grid(True, alpha=0.3, axis='y')
    from matplotlib.patches import Patch
    hs = [Patch(facecolor=SYSTEMS['rdma'][1], alpha=0.55, edgecolor='black', label=SYSTEMS['rdma'][0]),
          Patch(facecolor=SYSTEMS['loom'][1], alpha=0.55, edgecolor='black', label=SYSTEMS['loom'][0]),
          Patch(facecolor='0.6', alpha=0.55, edgecolor='black', label='compute'),
          Patch(facecolor='white', edgecolor='black', hatch='///', label='exposed communication')]
    fig.legend(handles=hs, loc='upper center', ncol=2, fontsize=fs['legend'] - 2, frameon=False, bbox_to_anchor=(0.55, 1.01),
               columnspacing=1.0, handlelength=1.6)
    save(fig, out_dir, png_dir, 'eval-e2e')


PASTEL_GREEN = '#8de5a1'


if __name__ == '__main__':
    out = sys.argv[1]
    png = sys.argv[2] if len(sys.argv) > 2 else None
    os.makedirs(out, exist_ok=True)
    if png:
        os.makedirs(png, exist_ok=True)
    only = os.environ.get('ONLY')   # e.g. ONLY=micro,e4,e5: just those figures (2026-10-19)
    for name, fn in (('validation', figure_validation), ('moe', figure_moe), ('coll', figure_coll), ('micro', figure_micro),
                     ('e4', figure_e4), ('e5', figure_e5), ('e2e', figure_e2e), ('sweep', figure_sweep)):
        if not only or name in only.split(','):
            fn(out, png)
