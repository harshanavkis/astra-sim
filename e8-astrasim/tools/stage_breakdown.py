#!/usr/bin/env python3
"""Where a small message's time goes (owner 2026-10-22, plan A; Fig 11a): one 64 B message + its 8 B signal between two
GPUs on one switch at 400 Gbps (run_sweep_an.py's p2p configs), each system's path from the GPU's first instruction
until (a) the receiver sees the signal and (b) the sender may reuse its buffer. The model's per-put trace
(LOOMNET_TRACE, bin/an_replay) gives each stage's end; every stage is one measured latency (H200 + CX-7, steve:
e8/cfg/steve_nic/base.txt) or Loom's RTL cycles, plus the GPU's measured work per message in front (GPU_POST_NS of
run_sweep_an.py). Prints and writes <out tsv>: system, bar, stage, start_ns, end_ns, source.
  stage_breakdown.py <p2p config dir> <out tsv>"""
import os, re, subprocess, sys, tempfile
E = '/scratch/harshanavkis/loom-proj/e8-astrasim'
cdir, out = sys.argv[1], sys.argv[2]
GPU = {'rdma': (2560, "DeepEP's post call (measured)"), 'loom': (710, 'stores + release signal, one warp (measured)')}
STAGE = 64 / 2400.0   # RDMA copies the message into its registered buffer first (cluster STAGE_COPY: bytes at 2.4 TB/s,
                      # H200 spec; no fixed latency, owner 2026-10-26: was 350 ns); an_replay has no frontend, so it is added here


def trace(v):
    d = tempfile.mkdtemp(dir=os.environ.get('TMPDIR', '/tmp'))
    open(f'{d}/r', 'w').write('flow 0 0 1 0 1 64 1 0 0 start 0\n')
    r = subprocess.run([f'{E}/bin/an_replay', f'{cdir}/p2p_{v}_400.txt', f'{d}/r', f'{d}/o'], capture_output=True, text=True,
                       env=dict(os.environ, LOOMNET_TRACE='0'), check=True)
    puts = [dict(zip(l.split()[1::2], map(float, l.split()[2::2]))) for l in r.stderr.splitlines() if l.startswith('loomnet_put')]
    cqes = [dict(zip(l.split()[1::2], map(float, l.split()[2::2]))) for l in r.stderr.splitlines() if l.startswith('loomnet_cqe')]
    return puts, cqes


rows = []
def cfgval(v, key):
    for l in open(f'{cdir}/p2p_{v}_400.txt'):
        x = l.split()
        if x and x[0] == key:
            return float(x[1])
def seg(sys_, bar, stage, cat, a, b, src):
    rows.append((sys_, bar, stage, cat, a, b, src))

PIPE = {'tx': 21, 'rx': 7}                       # Loom's pipelines, RTL cycles at 1 GHz (run_sweep_an.py LOOM_PIPE)
puts, cqes = trace('rdma')
data, sig = [p for p in puts if p['bytes'] == 64][0], [p for p in puts if p['bytes'] == 8][0]
sig_cqe = [c for c in cqes if c['bytes'] == 8][0]
rx = cfgval('rdma', 'NIC_RX_NS')
g, gsrc = GPU['rdma']
g += STAGE
for bar in ('receiver', 'sender'):
    seg('rdma', bar, 'GPU copies into its registered buffer', 'GPU', 0, STAGE, 'copy: 64 B at the H200 spec')
    seg('rdma', bar, 'GPU posts', 'GPU', STAGE, g, gsrc)
    seg('rdma', bar, 'doorbell', 'PCIe write', g, g + sig['db'], 'PCIe write, measured')
    seg('rdma', bar, 'NIC fetches request', 'NIC read', g + sig['db'], g + data['wqe'], 'PCIe read, measured')
    seg('rdma', bar, "NIC fetches signal's request", 'NIC read', g + data['wqe'], g + sig['wqe'], 'PCIe read, measured')
    seg('rdma', bar, "NIC reads signal's payload", 'NIC read', g + sig['wqe'], g + sig['data1'], 'PCIe read, measured')
    seg('rdma', bar, 'network stack (send)', 'network stack', g + sig['data1'], g + sig['wire0'], 'NIC pipeline, measured')
    seg('rdma', bar, 'wire and switch', 'wire', g + sig['wire0'], g + sig['a1'], 'links + switch, model')
    seg('rdma', bar, 'network stack (receive)', 'network stack', g + sig['a1'], g + sig['a1'] + rx, 'NIC pipeline, measured')
    if bar == 'receiver':
        seg('rdma', bar, 'write visible', 'PCIe write', g + sig['a1'] + rx, g + sig['seen'], 'PCIe write, measured')
    else:
        seg('rdma', bar, 'acknowledgement on the wire', 'wire', g + sig['a1'] + rx, g + sig_cqe['ack'], 'links + switch, model')
        seg('rdma', bar, 'completion written', 'PCIe write', g + sig_cqe['ack'], g + sig_cqe['cqe'], 'PCIe write, measured')
puts, _ = trace('loom')
sig = [p for p in puts if p['bytes'] == 8][0]
rx = cfgval('loom', 'NIC_RX_NS')
g, gsrc = GPU['loom']
seg('loom', 'receiver', 'GPU stores', 'GPU', 0, g, gsrc)
seg('loom', 'receiver', 'stores reach the switch', 'PCIe write', g, g + sig['data1'], 'PCIe write, measured')
seg('loom', 'receiver', 'Loom pipeline (send)', 'Loom pipeline', g + sig['data1'], g + sig['data1'] + PIPE['tx'], 'RTL cycles')
seg('loom', 'receiver', 'network stack (send)', 'network stack', g + sig['data1'] + PIPE['tx'], g + sig['wire0'], 'NIC pipeline, measured')
seg('loom', 'receiver', 'wire and switch', 'wire', g + sig['wire0'], g + sig['a1'], 'links + switch, model')
seg('loom', 'receiver', 'network stack (receive)', 'network stack', g + sig['a1'], g + sig['a1'] + rx - PIPE['rx'], 'NIC pipeline, measured')
seg('loom', 'receiver', 'Loom pipeline (receive)', 'Loom pipeline', g + sig['a1'] + rx - PIPE['rx'], g + sig['a1'] + rx, 'RTL cycles')
seg('loom', 'receiver', 'write visible', 'PCIe write', g + sig['a1'] + rx, g + sig['seen'], 'PCIe write, measured')
seg('loom', 'sender', 'GPU stores', 'GPU', 0, g + max(sig['out'], 0), gsrc + '; stores out of the GPU')
with open(out, 'w') as o:
    o.write('system\tbar\tstage\tcategory\tstart_ns\tend_ns\tsource\n')
    for r in rows:
        o.write(f'{r[0]}\t{r[1]}\t{r[2]}\t{r[3]}\t{r[4]:.0f}\t{r[5]:.0f}\t{r[6]}\n')
for r in rows:
    print(f'{r[0]:5s} {r[1]:8s} {r[2]:30s} {r[3]:14s} {r[4] / 1e3:6.2f} -> {r[5] / 1e3:6.2f} us  ({(r[5] - r[4]) / 1e3:5.2f})')
