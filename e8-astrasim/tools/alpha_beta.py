#!/usr/bin/env python3
"""alpha-beta view of the LoomNet model (SCALE / NCCL notation, T(n) = alpha + n / beta) for one message between two GPUs:
runs one message through ASTRA-sim on a cluster config (tools/astra_p2p.py; 2026-10-27, was bin/an_replay, which has no
frontend: ASTRA-sim adds the frontend's work, e.g. RDMA's staging copy) and fits
alpha and beta to the delivered time and to the sender's release over 64 KiB .. 64 MiB; prints the small-message times.
   alpha_beta.py <cluster dir, e.g. e8/clusters/n64nm> [src dst]      (model numbers)"""
import os, sys
E = '/scratch/harshanavkis/loom-proj/e8-astrasim'
sys.path.insert(0, f'{E}/tools')
from astra_p2p import one_message
cl = sys.argv[1]; src, dst = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (0, 8)
sizes = [8, 64, 512, 4096, 16384, 65536, 262144, 1 << 20, 4 << 20, 16 << 20, 64 << 20]
def run(v, s):   # (delivered, sender released) ns
    r = one_message(f'{E}/{cl}/{v}.txt', s, src=src, dst=dst)
    return r['delivered'], r['released']
def fit(xs, ys):
    n = len(xs); mx, my = sum(xs) / n, sum(ys) / n
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return my - b * mx, 1 / b
print(f'# {cl}: GPU {src} -> GPU {dst}, one message = one put + 8 B signal (model, ASTRA-sim)')
print(f'{"bytes":>10} {"RDMA deliv":>11} {"RDMA release":>13} {"Loom deliv":>11} {"Loom release":>13}   ns')
R = {v: {s: run(v, s) for s in sizes} for v in ('rdma', 'loom')}
for s in sizes:
    print(f'{s:>10} {R["rdma"][s][0]:>11} {R["rdma"][s][1]:>13} {R["loom"][s][0]:>11} {R["loom"][s][1]:>13}')
big = [s for s in sizes if s >= 65536]
for v in ('rdma', 'loom'):
    for i, what in ((0, 'delivered'), (1, 'sender released')):
        a, b = fit(big, [R[v][s][i] for s in big])
        print(f'{v:5} {what:16} alpha {a / 1e3:7.3f} us  beta {b:6.2f} GB/s')
