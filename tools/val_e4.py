# Loom side of the model vs the E4 prototype runs (ce_dispatch: amy's V80 copy engine stores the
# dispatch / combine through both U280 Loom switches into rose's V80 HBM, then the signal; the
# receiver's engine acks the signal). Inputs: the E4 logs (message counts, sizes, medians) and the
# LoomReplay outputs of tests/run_val_e4.sh.
#   python -I val_e4.py runs <e4 dir> <out dir>        -> <out dir>/runs/*.run (one per E4 point)
#   python -I val_e4.py compare <e4 dir> <out dir>     -> <out dir>/compare.tsv (+ stdout)
# Measured: sender = the engine's "signal issued" stamp; delivered = "ack back" minus the one-way flag
# trip (half the 0-token round trip). Model: sender = the signal store has left the V80 over PCIe
# (LoomReplay sender_out), delivered = the receiver sees the signal (seen).
import os, re, sys, glob, statistics

def points(e4):
    out = []
    for log in sorted(glob.glob(os.path.join(e4, '*.client.log'))):
        txt = open(log).read()
        m = re.search(r'^(dispatch|combine) (\d+) tokens, (\d+) x (\d+) B \(us, \d+ runs, median \[min max\]\): '
                      r'copies \S+ \[[^]]*\]\s+signal issued (\S+) \[[^]]*\]\s+ack back (\S+)', txt, re.M)
        if not m:
            continue
        op, T, n, H, sig, ack = m.groups()
        out.append(dict(op=op, T=int(T), n=int(n), H=int(H), sig=float(sig), ack=float(ack),
                        name=f'{op}_t{T}'))
    return out

def write_runs(e4, out):
    os.makedirs(os.path.join(out, 'runs'), exist_ok=True)
    for p in points(e4):
        with open(os.path.join(out, 'runs', p['name'] + '.run'), 'w') as f:
            # one QP (one Loom binding), every store posted at time 0 (zero GPU-side cost), the signal a plain
            # 8 B write behind the data
            f.write('path ordered\nnodes 0 1\nnqp 1\nsigkind write\nreap 0\nsignal 0 0\n')
            for i in range(p['n']):
                f.write(f"msg {i} 0 0 {p['H']} 1\n")

def model(out, name):
    s = open(os.path.join(out, 'model', name + '.out')).read()
    m = re.search(r'^sum (\S+) (\S+) (\S+) (\S+) (\S+) (\S+) (\S+)', s, re.M)
    v = [float(x) for x in m.groups()]
    return dict(seen=v[4] / 1000, sender=v[6] / 1000)

def compare(e4, out):
    ps = points(e4)
    zero = [p for p in ps if p['T'] == 0][0]
    oneway = zero['ack'] / 2
    rows = []
    for p in ps:
        if p['T'] == 0:
            continue
        mo = model(out, p['name'])
        dl = p['ack'] - oneway
        rows.append((p['op'], p['T'], p['n'], p['H'], p['sig'], mo['sender'], dl, mo['seen']))
    hdr = 'op\ttokens\tmsgs\tbytes_each\tsender_measured_us\tsender_model_us\tsender_err_pct\tdelivered_measured_us\tdelivered_model_us\tdelivered_err_pct'
    lines = [hdr]
    for op, T, n, H, sm, smo, dm, dmo in rows:
        lines.append(f'{op}\t{T}\t{n}\t{H}\t{sm:.2f}\t{smo:.2f}\t{(smo - sm) / sm * 100:+.1f}\t{dm:.2f}\t{dmo:.2f}\t{(dmo - dm) / dm * 100:+.1f}')
    z = model(out, 'dispatch_t0')
    lines.append(f'# one-way flag: measured {oneway:.2f} us (0-token round trip / 2), model {z["seen"]:.2f} us (fitted)')
    open(os.path.join(out, 'compare.tsv'), 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))

if __name__ == '__main__':
    cmd, e4, out = sys.argv[1:4]
    {'runs': write_runs, 'compare': compare}[cmd](e4, out)
