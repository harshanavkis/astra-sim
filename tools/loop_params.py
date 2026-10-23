#!/usr/bin/env python3
"""The GPU's send loop per operation and token count, from the traced Section 2 runs (owner 2026-10-22: the model charges
the measured GPU-side work; LoomNet POST_LOOP_NS + gen_decode.py LOOP): medians over the runs of
  loop_ns   the time from the sender's first CTA start until the signal is issued (measured signal_us),
  first / last  the first and last data post as fractions of the loop (posts are spread evenly between them).
rdma = the ordered path (DeepEP V1 low latency, --reap-inline), loom = the local path (TMA stores into the GPU's own
HBM, the same kernel to a scale-up peer: a lower bound).   (MEASURED, steve: H200 + CX-7)
With an untraced run dir (Section 2's dispatch_bd, bd_one.sh: <op>_<local|reap_ordered-destL3>.csv), loop_ns is the median
signal_us of those runs (the traced build logs every doorbell and runs up to ~4% longer); first / last stay from the traces.
  loop_params.py <converted trace dir (bd_trace_to_replay.py)> <out tsv> [untraced run dir]"""
import csv, glob, os, statistics as S, sys

src, out = sys.argv[1], sys.argv[2]
untraced = sys.argv[3] if len(sys.argv) > 3 else None
meas = {(r['config'], int(r['run']), int(r['tokens'])): r
        for r in csv.DictReader(open(os.path.join(src, 'measured.tsv')), delimiter='\t')}
rows = {}
for f in glob.glob(os.path.join(src, 'runs', '*.run')):
    cfg, rk, tk = os.path.basename(f)[:-4].rsplit('_', 2)
    path = {'reap_ordered-destL3': 'rdma', 'local': 'loom'}.get(cfg.split('_', 1)[1])
    if path is None:
        continue
    op, run, tok = cfg.split('_', 1)[0], int(rk[1:]), int(tk[1:])
    sig = float(meas[(cfg, run, tok)]['signal_us']) * 1e3
    posts = [int(l.split()[2]) for l in open(f) if l.startswith('msg ')]
    rows.setdefault((op, path, tok), []).append((sig, min(posts) / sig, max(posts) / sig))
loop = {}
if untraced:
    for op in ('dispatch', 'combine'):
        for cfg, path in (('local', 'loom'), ('reap_ordered-destL3', 'rdma')):
            lines = [l for l in open(os.path.join(untraced, f'{op}_{cfg}.csv')) if l.strip() and not l.startswith(('WARN', '#'))]
            for r in csv.DictReader(lines):
                loop.setdefault((op, path, int(r['tokens'])), []).append(float(r['signal_us']) * 1e3)
with open(out, 'w') as o:
    o.write('op\tpath\ttokens\tloop_ns\tfirst\tlast\truns\n')
    for (op, path, tok), v in sorted(rows.items()):
        L = S.median(loop[(op, path, tok)]) if untraced else S.median(x[0] for x in v)
        o.write(f'{op}\t{path}\t{tok}\t{L:.0f}\t{S.median(x[1] for x in v):.3f}\t'
                f'{S.median(x[2] for x in v):.3f}\t{len(v)}\n')
print(open(out).read(), end='')
