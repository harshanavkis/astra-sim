#!/usr/bin/env python3
"""Point-to-point map on the LoomNet model (owner 2026-10-21: where Loom is worse, better, equal): message size x link
rate, between two GPUs behind one switch (the link-rate sweep's p2p configs, val_model/sweep_an/current/p2p_<v>_<rate>.txt:
PCIe Gen5 <= 400 G, Gen6 800 G, Gen7 1,600 G). Variants (config lines added to the base config):
  rdma, loom                  the paper's systems
  loom_buf                    Loom's transmit buffer = the computed ACK window, W = ceil(rate x 10 us / 4 KiB) x 4 KiB
Per point: one message (put + 8 B signal): delivered and sender released. Model results.   python3 -I sweep_p2p.py <out.tsv>"""
import os, subprocess, sys, tempfile

E = '/scratch/harshanavkis/loom-proj/e8-astrasim'
CFG = '/home/harshanavkis/loom-experiments/val_model/sweep_an/current'
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


def replay(c, size, n):
    r, o = f'{tmp}/r', f'{tmp}/o'
    open(r, 'w').write(f'flow 0 0 1 0 {n} {size} 1 0 0 start 0\n')
    subprocess.run([f'{E}/bin/an_replay', c, r, o], check=True, stdout=subprocess.DEVNULL)
    f = open(o).read().split()
    return float(f[5]), float(f[6]), float(f[7])      # signal seen, all completions, sender out (ns)


rows = ['rate\tvariant\tbytes\tdeliv_ns\treleased_ns']
for name, sysname, extra, rates in VARIANTS:
    for rate in rates:
        c = cfg(name, sysname, extra(rate), rate)
        for s in SIZES:
            sig, cqe, out = replay(c, s, 1)
            rel = cqe if sysname == 'rdma' else out
            rows.append(f'{rate}\t{name}\t{s}\t{sig:.0f}\t{rel:.0f}')
open(sys.argv[1], 'w').write('\n'.join(rows) + '\n')
print(f'{len(rows) - 1} rows -> {sys.argv[1]}')
