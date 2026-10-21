#!/usr/bin/env python3
"""alpha-beta view of the LoomNet model (SCALE / NCCL notation, T(n) = alpha + n / beta) for one message between two GPUs:
runs bin/an_replay on a cluster config (one put + the 8 B signal, as the ASTRA-sim frontend sends a message) and fits
alpha and beta to the delivered time and to the sender's release over 64 KiB .. 64 MiB; prints the small-message times.
   alpha_beta.py <cluster dir, e.g. e8/clusters/n64nm> [src dst]      (model numbers)"""
import os, subprocess, sys, tempfile
E = '/scratch/harshanavkis/loom-proj/e8-astrasim'
cl = sys.argv[1]; src, dst = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (0, 8)
sizes = [8, 64, 512, 4096, 16384, 65536, 262144, 1 << 20, 4 << 20, 16 << 20, 64 << 20]
def run(v, s):
    d = tempfile.mkdtemp(dir=os.environ.get('TMPDIR', '/tmp'))
    open(f'{d}/r', 'w').write(f'flow 0 {src} {dst} 0 1 {s} 1 0 0 start 0\n')
    subprocess.run([f'{E}/bin/an_replay', f'{E}/{cl}/{v}.txt', f'{d}/r', f'{d}/o'], check=True)
    f = open(f'{d}/o').read().split()
    sig, cqe, out = int(f[5]), int(f[6]), int(f[7])
    return sig, (out if v == 'loom' else cqe)
def fit(xs, ys):
    n = len(xs); mx, my = sum(xs) / n, sum(ys) / n
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return my - b * mx, 1 / b
print(f'# {cl}: GPU {src} -> GPU {dst}, one message = one put + 8 B signal (model)')
print(f'{"bytes":>10} {"RDMA deliv":>11} {"RDMA release":>13} {"Loom deliv":>11} {"Loom release":>13}   ns')
R = {v: {s: run(v, s) for s in sizes} for v in ('rdma', 'loom')}
for s in sizes:
    print(f'{s:>10} {R["rdma"][s][0]:>11} {R["rdma"][s][1]:>13} {R["loom"][s][0]:>11} {R["loom"][s][1]:>13}')
big = [s for s in sizes if s >= 65536]
for v in ('rdma', 'loom'):
    for i, what in ((0, 'delivered'), (1, 'sender released')):
        a, b = fit(big, [R[v][s][i] for s in big])
        print(f'{v:5} {what:16} alpha {a / 1e3:7.3f} us  beta {b:6.2f} GB/s')
