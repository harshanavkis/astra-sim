#!/usr/bin/env python3
"""Model vs model: the LoomNet analytical model (e8_an/*) against the ns-3 model (e8/*) on the same jobs.
   cmp_an_ns3.py [coll|moe|all]   prints per point both values, the difference, and the RDMA/Loom ratios."""
import csv, sys, statistics as S
E = '/scratch/harshanavkis/loom-proj/e8-astrasim/'
what = sys.argv[1] if len(sys.argv) > 1 else 'all'
def load(p, key, vals):
    d = {}
    for r in csv.DictReader(open(p), delimiter='\t'):
        d[tuple(r[k] for k in key)] = tuple(float(r[v]) for v in vals)
    return d
def pct(a, b): return (a - b) / b * 100
errs = []
if what in ('coll', 'all'):
    n = load(E + 'e8/coll/coll.tsv', ('op', 'gpus', 'bytes', 'variant'), ('time_us',))
    a = load(E + 'e8_an/coll/coll.tsv', ('op', 'gpus', 'bytes', 'variant'), ('time_us',))
    print('collectives (us): ns-3 / analytical (diff); ratio RDMA/Loom ns-3 / analytical')
    for k in sorted({k[:3] for k in n}, key=lambda k: (k[0], int(k[1]), int(k[2]))):
        if k + ('rdma',) not in a or k + ('loom',) not in a: continue
        nr, nl, ar, al = n[k + ('rdma',)][0], n[k + ('loom',)][0], a[k + ('rdma',)][0], a[k + ('loom',)][0]
        errs += [abs(pct(ar, nr)), abs(pct(al, nl))]
        print(f'{k[0]:14}{k[1]:>4}{k[2]:>10}  rdma {nr:9.1f} {ar:9.1f} ({pct(ar, nr):+5.1f}%)  loom {nl:9.1f} {al:9.1f} ({pct(al, nl):+5.1f}%)  x {nr / nl:5.2f} {ar / al:5.2f}')
if what in ('moe', 'all'):
    n = load(E + 'e8/moe/moe.tsv', ('op', 'ep', 'tokens', 'variant'), ('send_max_us', 'recv_max_us'))
    a = load(E + 'e8_an/moe/moe.tsv', ('op', 'ep', 'tokens', 'variant'), ('send_max_us', 'recv_max_us'))
    print('MoE (us, max GPU): sender busy and delivered, ns-3 / analytical (diff)')
    for k in sorted({k[:3] for k in n}, key=lambda k: (k[0], int(k[1]), int(k[2]))):
        s = f'{k[0]:9}{k[1]:>4}{k[2]:>4}'
        for v in ('rdma', 'loom'):
            if k + (v,) in a:
                (ns, nr), (as_, ar) = n[k + (v,)], a[k + (v,)]
                errs += [abs(pct(as_, ns)), abs(pct(ar, nr))]
                s += f' | {v} busy {ns:7.1f} {as_:7.1f} ({pct(as_, ns):+4.0f}%) deliv {nr:7.1f} {ar:7.1f} ({pct(ar, nr):+4.0f}%)'
        print(s)
if errs:
    print(f'|diff| over {len(errs)} values: median {S.median(errs):.1f}%, max {max(errs):.1f}%')
