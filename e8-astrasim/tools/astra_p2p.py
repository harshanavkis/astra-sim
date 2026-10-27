"""One message through ASTRA-sim (2026-10-27, owner: every model number on the ASTRA-sim layer, no hand-written replayer):
a Chakra trace of COUNT messages of SIZE bytes from GPU SRC to GPU DST (tools/gen_p2p.py; the other GPUs of the network
config's topology get empty traces), run in AstraSim_Analytical_Loom with a roofline system file at 1 op per ns (--pre NS =
the sender's GPU work first) and ASTRA_CONCURRENT_SENDS=1, as run_val_astra.py / run_sweep_astra.py. Returns the times the
model gives (ns): delivered = DST's finish (the last message seen), released = SRC's finish (its sends released: Loom's
stores out, RDMA's completions), and with trace=True LoomNet's per-put stages of SRC (LOOMNET_TRACE).
  from astra_p2p import one_message; r = one_message(cfg, 64, pre=2560, trace=True)"""
import json, os, re, subprocess, sys, tempfile
E = '/scratch/harshanavkis/loom-proj/e8-astrasim'
A = '/scratch/harshanavkis/loom-proj/astra-sim-fresh'
BIN = f'{A}/build/astra_analytical/build/bin/AstraSim_Analytical_Loom'
MEM = f'{A}/examples/remote_memory/analytical/no_memory_expansion.json'
SYSCFG = {'scheduling-policy': 'FIFO', 'endpoint-delay': 0, 'active-chunks-per-dimension': 1, 'preferred-dataset-splits': 1,
          'collective-optimization': 'localBWAware', 'local-mem-bw': 4800, 'boost-mode': 0,
          'all-reduce-implementation': ['direct'], 'all-gather-implementation': ['direct'],
          'reduce-scatter-implementation': ['direct'], 'all-to-all-implementation': ['direct'],
          'roofline-enabled': 1, 'peak-perf': 0.001}   # compute nodes: num_ops = ns


def npus_of(cfg):   # GPUs of the config's topology: nodes minus switches (first line: nodes switches links)
    topo = [l.split()[1] for l in open(cfg) if l.split()[:1] == ['TOPOLOGY_FILE']][0]
    n, s = map(int, open(topo).readline().split()[:2])
    return n - s


def stages(lines, kind):
    return [dict(zip(l.split()[1::2], map(float, l.split()[2::2]))) for l in lines if l.startswith(kind)]


def one_message(cfg, size, src=0, dst=1, npus=None, pre=0, count=1, trace=False, workdir=None):
    d = workdir or tempfile.mkdtemp(dir=os.environ.get('TMPDIR', '/tmp'))
    os.makedirs(d, exist_ok=True)
    npus = npus or npus_of(cfg)
    a = [sys.executable, '-I', f'{E}/tools/gen_p2p.py', f'{d}/wl', str(size), str(count),
         '--npus', str(npus), '--src', str(src), '--dst', str(dst)] + (['--pre', str(pre)] if pre else [])
    subprocess.run(a, check=True, capture_output=True)
    sysj = f'{d}/system_roofline.json'
    json.dump(SYSCFG, open(sysj, 'w'), indent=1)
    env = dict(os.environ, ASTRA_CONCURRENT_SENDS='1')
    if trace:
        env['LOOMNET_TRACE'] = str(src)
    args = [BIN, f'--workload-configuration={d}/wl/p2p', f'--system-configuration={sysj}',
            f'--remote-memory-configuration={MEM}', f'--network-configuration={cfg}']
    r = subprocess.run(args, capture_output=True, text=True, env=env)
    open(f'{d}/astra.log', 'w').write(' '.join(args) + '\n' + r.stdout + r.stderr)
    fin = {int(m[1]): int(m[2]) for m in re.finditer(r'^loom_rank (\d+) .* finished_ns (\d+)', r.stdout, re.M)}
    if r.returncode or src not in fin or dst not in fin:
        raise RuntimeError(f'ASTRA-sim exit {r.returncode}: {d}/astra.log')
    out = {'delivered': fin[dst], 'released': fin[src], 'log': f'{d}/astra.log'}
    if trace:
        lines = (r.stdout + r.stderr).splitlines()
        out['puts'], out['cqes'] = stages(lines, 'loomnet_put'), stages(lines, 'loomnet_cqe')
    return out
