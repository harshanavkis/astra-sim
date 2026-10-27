#!/usr/bin/env python3
"""Point-to-point map on the LoomNet model (owner 2026-10-21: where Loom is worse, better, equal): message size x link
rate, between two GPUs behind one switch (the link-rate sweep's p2p configs, val_model/sweep_astra/current/p2p_<v>_<rate>.txt:
PCIe Gen5 <= 400 G, Gen6 800 G, Gen7 1,600 G). Variants (config lines added to the base config):
  rdma, loom                  the paper's systems
  loom_buf                    Loom's transmit buffer = the computed ACK window, W = ceil(rate x 10 us / 4 KiB) x 4 KiB
Per point: one message (put + 8 B signal): delivered and sender released. Model results.   python3 -I sweep_p2p.py <out.tsv>
2026-10-27 (owner: every model number through ASTRA-sim): each point runs in AstraSim_Analytical_Loom (tools/astra_p2p.py);
was bin/an_replay (no frontend, so no RDMA staging copy)."""
import os, subprocess, sys, tempfile

E = '/scratch/harshanavkis/loom-proj/e8-astrasim'
CFG = '/home/harshanavkis/loom-experiments/val_model/sweep_astra/current'
SIZES = [8, 64, 512, 4096, 16384, 65536, 262144, 1 << 20, 4 << 20, 16 << 20, 64 << 20]
RATES = ['100', '200', '400', '800', '1600']
WPKT = {'100': 31, '200': 62, '400': 123, '800': 245, '1600': 489}
VARIANTS = [   # name, system, extra config lines (rate -> str), rates
    ('rdma', 'rdma', lambda r: '', RATES),
    ('loom', 'loom', lambda r: '', RATES),
    ('loom_buf', 'loom', lambda r: f'LOOM_TX_BUF_BYTES {WPKT[r] * 4096}', RATES),
]
tmp = tempfile.mkdtemp(dir=os.environ.get('TMPDIR', '/tmp'))


def cfg(name, sysname, extra, rate):
    p = f'{tmp}/p2p_{name}_{rate}.txt'
    open(p, 'w').write(open(f'{CFG}/p2p_{sysname}_{rate}.txt').read() + f'\n{extra}\n')
    return p


sys.path.insert(0, f'{E}/tools')
from astra_p2p import one_message


def deliver(c, size, n):   # (delivered, sender released) ns
    r = one_message(c, size, count=n, workdir=tempfile.mkdtemp(dir=tmp))
    return float(r['delivered']), float(r['released'])


rows = ['rate\tvariant\tbytes\tdeliv_ns\treleased_ns']
for name, sysname, extra, rates in VARIANTS:
    for rate in rates:
        c = cfg(name, sysname, extra(rate), rate)
        for s in SIZES:
            sig, rel = deliver(c, s, 1)
            rows.append(f'{rate}\t{name}\t{s}\t{sig:.0f}\t{rel:.0f}')
open(sys.argv[1], 'w').write('\n'.join(rows) + '\n')
print(f'{len(rows) - 1} rows -> {sys.argv[1]}')
