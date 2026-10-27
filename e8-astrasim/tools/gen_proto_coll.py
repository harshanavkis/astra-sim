# Chakra ET for the prototype's collectives as its tools run them (ce_colln / rdma_colln --acked-step --flag-in-data;
# 2026-10-27, owner: the prototype's model numbers through ASTRA-sim). ASTRA-sim's own collectives never wait for a
# sender's release; the tools wait for a step's sends once (Loom: the engine done, RDMA: the completions), so each step
# is written out as point-to-point nodes: every rank posts to its peers in rotated order (k + 1, k + 2, ...), receives
# from them, then reduces (rs: N - 1 reductions of its chunk; ar_ring: one per reduce-scatter step); the next step
# depends on all of it. bc: rank 0 sends to every peer, each acknowledges with an 8 B message.
#   --pt NS        a copy engine starts each send: compute node of NS before the first send of a step (the engine's
#                  CPU start + completion), and of the rank's submit time before each further one
#   --sub A,B,..   per rank submit time (ns) of a further copy (default 0); the first send costs NS - SUB[0] + SUB[k]
#   --red FILE     JSON {bytes: ns} of one reduction (measured); a compute node per reduction
#   --nowait       (2026-10-27, owner: both versions) the tools without --acked-step: a step's sends depend only on the
#                  data they forward (the previous step's receives and reductions), never on earlier sends' release
# Compute nodes take num_ops = ns at peak-perf 0.001 TFLOP/s (the system config's roofline: 1 op = 1 ns).
#   python -I gen_proto_coll.py <out dir> <npus> <ag|a2a|rs|ar_ring|bc> <size> [count] [--pt NS --sub A,B,..] [--red FILE] [--nowait]
#   -> <out dir>/coll.<rank>.et
import sys, os, json
sys.path.insert(0, "/scratch/harshanavkis/loom-proj/opus-ref/Opus/simulation/symbolic_tensor_graph/symbolic_tensor_graph/chakra/backends/chakra_00_4_backend/et_def")
import et_def_pb2 as pb
from google.protobuf.internal.encoder import _VarintBytes

args, opts, i = [], {}, 1
while i < len(sys.argv):
    if sys.argv[i] == '--nowait':
        opts['nowait'] = 1; i += 1
    elif sys.argv[i].startswith('--'):
        opts[sys.argv[i][2:]] = sys.argv[i + 1]; i += 2
    else:
        args.append(sys.argv[i]); i += 1
out, N, coll, S = args[0], int(args[1]), args[2], int(args[3])
count = int(args[4]) if len(args) > 4 else 1
PT = int(opts.get('pt', 0))
SUB = [int(x) for x in opts['sub'].split(',')] if 'sub' in opts else [0] * N
RED = {int(k): float(v) for k, v in json.load(open(opts['red'])).items()} if 'red' in opts else {}
os.makedirs(out, exist_ok=True)


def chunk(j):   # rank j's chunk, as the tools (C rounded up to 128 B)
    C = (S + N * 128 - 1) // (N * 128) * 128
    return min(S, (j + 1) * C) - min(S, j * C)


def steps():   # [(sends [(src, dst, bytes, engine)], reduces {rank: [bytes]})] of one iteration
    peers = lambda k: [(k + i) % N for i in range(1, N)]
    if coll == 'ag':
        return [([(k, q, S, 1) for k in range(N) for q in peers(k)], {})]
    if coll in ('a2a', 'rs'):
        return [([(k, q, chunk(q), 1) for k in range(N) for q in peers(k)],
                 {k: [chunk(k)] * (N - 1) for k in range(N)} if coll == 'rs' else {})]
    if coll == 'ar_ring':
        return ([([(k, (k + 1) % N, chunk((k - t) % N), 1) for k in range(N)], {k: [chunk((k - t - 1) % N)] for k in range(N)})
                 for t in range(N - 1)] +
                [([(k, (k + 1) % N, chunk((k + 1 - t) % N), 1) for k in range(N)], {}) for t in range(N - 1)])
    if coll == 'bc':   # data from the root, then the acks (a CPU store / an 8 B WRITE: no engine)
        return [([(0, q, S, 1) for q in range(1, N)], {}), ([(q, 0, 8, 0) for q in range(1, N)], {})]
    raise SystemExit(f'unknown collective {coll}')


ST = steps()
for r in range(N):
    nodes, nid, prev = [], 0, []

    def add(nd):
        global nid
        nid += 1
        nd.id = nid
        nodes.append(nd)
        return nid

    def comp(ns, deps):
        nd = pb.Node(name=f'comp{nid + 1}', type=pb.COMP_NODE)
        nd.ctrl_deps.extend(deps)
        nd.attr.add(name='num_ops', int64_val=max(1, int(round(ns))))
        nd.attr.add(name='tensor_size', int64_val=1)
        nd.attr.add(name='is_cpu_op', bool_val=False)
        return add(nd)

    def comm(send, peer, b, tag, deps):
        nd = pb.Node(name=f"{'send' if send else 'recv'}{nid + 1}", type=pb.COMM_SEND_NODE if send else pb.COMM_RECV_NODE)
        nd.ctrl_deps.extend(deps)
        nd.attr.add(name='comm_size', int64_val=b)
        nd.attr.add(name='comm_tag', int32_val=tag)
        nd.attr.add(name='comm_dst' if send else 'comm_src', int32_val=peer)
        nd.attr.add(name='is_cpu_op', bool_val=False)
        return add(nd)

    for it in range(count):
        for si, (sends, reds) in enumerate(ST):
            tag = lambda src, dst: ((it * len(ST) + si) * N + src) * N + dst
            done, j, last = [], 0, prev
            for (src, dst, b, eng) in sends:
                if src == r:
                    deps = prev
                    if PT and eng:
                        last = [comp(PT - SUB[0] + SUB[r] if j == 0 else SUB[r], last)]
                        deps = last
                        j += 1
                    done.append(comm(True, dst, b, tag(src, dst), deps))
            recvs = [comm(False, src, b, tag(src, dst), prev) for (src, dst, b, _) in sends if dst == r]
            done += recvs
            dep = list(recvs) if 'nowait' in opts else list(done)   # without the wait, reductions follow the data only
            for b in reds.get(r, []):
                dep = [comp(RED[b], dep)]
            if 'nowait' in opts:
                prev = dep if reds.get(r) else recvs   # the next step waits for the data only
            else:
                prev = dep if reds.get(r) else done
    with open(f'{out}/coll.{r}.et', 'wb') as f:
        gm = pb.GlobalMetadata(); gm.attr.add(name='schema', string_val='loom-hif-test')
        for m in [gm] + nodes:
            s = m.SerializeToString(); f.write(_VarintBytes(len(s)) + s)
print(f'{out}: {N} ranks, {count} x {coll} {S} B as point-to-point steps, engine {PT} ns, {len(RED)} reduction sizes')
