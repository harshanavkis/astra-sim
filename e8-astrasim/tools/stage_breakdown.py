#!/usr/bin/env python3
"""Where a small message's time goes (owner 2026-10-22, plan A; Fig 11a): one 64 B message + its 8 B signal between two
GPUs on one switch at 400 Gbps (run_sweep_an.py's p2p configs), each system's path from the GPU's first instruction
until (a) the receiver sees the signal and (b) the sender may reuse its buffer. The model's per-put trace
(LOOMNET_TRACE, ASTRA-sim via tools/astra_p2p.py since 2026-10-27; was bin/an_replay) gives each stage's end; every stage is one measured latency (H200 + CX-7, steve:
e8/cfg/steve_nic/base.txt) or Loom's RTL cycles, plus the GPU's measured work per message in front (GPU_POST_NS of
run_sweep_an.py). Prints and writes <out tsv>: system, bar, stage, start_ns, end_ns, source.
  stage_breakdown.py <p2p config dir> <out tsv>"""
import os, sys
E = '/scratch/harshanavkis/loom-proj/e8-astrasim'
sys.path.insert(0, f'{E}/tools')
from astra_p2p import one_message
cdir, out = sys.argv[1], sys.argv[2]
GPU = {'rdma': (2560, "DeepEP's post call (measured)"), 'loom': (710, 'stores + release signal, one warp (measured)')}
# 2026-10-27 (owner: every model number through ASTRA-sim): the message runs in AstraSim_Analytical_Loom (tools/astra_p2p.py,
# the GPU's work as a compute node before the send, gen_p2p.py --pre); the frontend adds RDMA's staging copy (STAGE_COPY,
# after the post call in the model's order), so every time below is absolute. Was bin/an_replay with both added here.


def trace(v):
    r = one_message(f'{cdir}/p2p_{v}_400.txt', 64, pre=GPU[v][0], trace=True)
    return r['puts'], r['cqes']


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
for bar in ('receiver', 'sender'):
    seg('rdma', bar, 'GPU posts', 'GPU', 0, g, gsrc)
    seg('rdma', bar, 'GPU copies into its registered buffer', 'GPU', g, sig['post'], 'copy: 64 B at 2.4 TB/s (H200 spec)')
    seg('rdma', bar, 'doorbell', 'PCIe write', sig['post'], sig['db'], 'PCIe write, measured')
    seg('rdma', bar, 'NIC fetches request', 'NIC read', sig['db'], data['wqe'], 'PCIe read, measured')
    seg('rdma', bar, "NIC fetches signal's request", 'NIC read', data['wqe'], sig['wqe'], 'PCIe read, measured')
    seg('rdma', bar, "NIC reads signal's payload", 'NIC read', sig['wqe'], sig['data1'], 'PCIe read, measured')
    seg('rdma', bar, 'network stack (send)', 'network stack', sig['data1'], sig['wire0'], 'NIC pipeline, measured')
    seg('rdma', bar, 'wire and switch', 'wire', sig['wire0'], sig['a1'], 'links + switch, model')
    seg('rdma', bar, 'network stack (receive)', 'network stack', sig['a1'], sig['a1'] + rx, 'NIC pipeline, measured')
    if bar == 'receiver':
        seg('rdma', bar, 'write visible', 'PCIe write', sig['a1'] + rx, sig['seen'], 'PCIe write, measured')
    else:
        seg('rdma', bar, 'acknowledgement on the wire', 'wire', sig['a1'] + rx, sig_cqe['ack'], 'links + switch, model')
        seg('rdma', bar, 'completion written', 'PCIe write', sig_cqe['ack'], sig_cqe['cqe'], 'PCIe write, measured')
puts, _ = trace('loom')
sig = [p for p in puts if p['bytes'] == 8][0]
rx = cfgval('loom', 'NIC_RX_NS')
g, gsrc = GPU['loom']
seg('loom', 'receiver', 'GPU stores', 'GPU', 0, sig['post'], gsrc)
seg('loom', 'receiver', 'stores reach the switch', 'PCIe write', sig['post'], sig['data1'], 'PCIe write, measured')
seg('loom', 'receiver', 'Loom pipeline (send)', 'Loom pipeline', sig['data1'], sig['data1'] + PIPE['tx'], 'RTL cycles')
seg('loom', 'receiver', 'network stack (send)', 'network stack', sig['data1'] + PIPE['tx'], sig['wire0'], 'NIC pipeline, measured')
seg('loom', 'receiver', 'wire and switch', 'wire', sig['wire0'], sig['a1'], 'links + switch, model')
seg('loom', 'receiver', 'network stack (receive)', 'network stack', sig['a1'], sig['a1'] + rx - PIPE['rx'], 'NIC pipeline, measured')
seg('loom', 'receiver', 'Loom pipeline (receive)', 'Loom pipeline', sig['a1'] + rx - PIPE['rx'], sig['a1'] + rx, 'RTL cycles')
seg('loom', 'receiver', 'write visible', 'PCIe write', sig['a1'] + rx, sig['seen'], 'PCIe write, measured')
seg('loom', 'sender', 'GPU stores', 'GPU', 0, max(sig['out'], g), gsrc + '; stores out of the GPU')
with open(out, 'w') as o:
    o.write('system\tbar\tstage\tcategory\tstart_ns\tend_ns\tsource\n')
    for r in rows:
        o.write(f'{r[0]}\t{r[1]}\t{r[2]}\t{r[3]}\t{r[4]:.0f}\t{r[5]:.0f}\t{r[6]}\n')
for r in rows:
    print(f'{r[0]:5s} {r[1]:8s} {r[2]:30s} {r[3]:14s} {r[4] / 1e3:6.2f} -> {r[5] / 1e3:6.2f} us  ({(r[5] - r[4]) / 1e3:5.2f})')
