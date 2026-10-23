#!/usr/bin/env python3
"""LoomReplay runs with zero GPU-side cost: the Section 2 dispatch / combine (dispatch_bd.cu routing:
top-8 of 256 experts, 8 destinations, one message per (token, destination); combine: one H-byte message
per such pair) handed over at time 0, so only the transport makes the sender wait. One QP per
destination, every put rings its doorbell, the signal is an 8 B write behind the data on each QP.
  ordered  signal at 0 behind the data; the sender collects every completion (reap)
  flush    the sender waits for every completion, then signals
  push     Loom: the stores go out at 0, the signal store behind them
  gen_zero_gpu.py <out dir>   -> <out>/<op>_<path>_t<T>.run for op dispatch|combine, T 1 16 128"""
import os, sys

R, E, TOPK = 8, 256, 8
M32 = 0xffffffff

def hsh(x):
    x &= M32
    x ^= x >> 16; x = (x * 0x7feb352d) & M32
    x ^= x >> 15; x = (x * 0x846ca68b) & M32
    x ^= x >> 16
    return x

def rank_mask(t):
    mask, got, used, j = 0, 0, set(), 0
    while got < TOPK:
        e = hsh(t * 131 + j) % E
        j += 1
        if e in used:
            continue
        used.add(e); got += 1
        mask |= 1 << (e // (E // R))
    return mask

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
for op, H in [("dispatch", 7168), ("combine", 14336)]:
    for T in [1, 16, 128]:
        dests = [r for t in range(T) for r in range(R) if rank_mask(t) >> r & 1]
        msgs = "".join(f"msg {i} 0 {r} {H} 1\n" for i, r in enumerate(sorted(dests)))
        sig = "signal 0 " + " ".join(str(r) for r in range(R)) + "\n"
        for path, extra in [("ordered", "reap 1\n"), ("flush", "reap 0\ncta 0\n"), ("push", "reap 0\n")]:
            with open(os.path.join(out, f"{op}_{path}_t{T}.run"), "w") as f:
                f.write(f"path {'flush' if path == 'flush' else 'ordered'}\nnodes 0 1\nnqp {R}\nsigkind write\n{extra}{sig}{msgs}")
        print(op, T, len(dests), "messages")
