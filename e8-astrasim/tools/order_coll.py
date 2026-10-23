# Chain every communication group's collectives in program order (ctrl deps), identically on every rank.
# Why: ASTRA-sim numbers a group's streams in issue order (Sys.cc: communicator_group->num_streams++); when a rank's DAG
# leaves two collectives of one group unordered, members can issue them in different orders and their streams cross-match
# (2026-10-20: STAGE hybrid TP8xPP4xDP2 = DP-group gradient collectives of different layers unordered -> ns-3 deadlock,
# analytical heap corruption). Frameworks issue a process group's collectives in program order on every rank.
# Program order = a deterministic topological order of the rank's DAG (Kahn, ties by node id); the script checks that every
# group's members get the same (type, size) sequence.
# With <comm_group.json> <GPUs per server>: chain only the groups whose members span servers (in-server groups run on
# identical timing; chaining them forces one global schedule and stretched the hybrid iteration 2.6x on the analytical backend).
# TOTAL=1 (env): one chain over ALL of a rank's collectives and sends (one total order per rank) instead of one per group.
#   order_coll.py <in prefix> <out prefix> <ranks> [<comm_group.json> <GPUs per server>]   (traces <prefix>.<rank>.et)
import sys, heapq, collections, json, os
TOTAL = os.environ.get("TOTAL") == "1"
# ORDER_LOG=<ASTRA_ISSUE_LOG file of a symmetric (contention-free) run of the same trace>: program order = the order
# that run issued each rank's nodes (ties: log order), instead of Kahn by node id; with ALL=1 every group is chained
ORDER = {}
if os.environ.get("ORDER_LOG"):
    for i, l in enumerate(open(os.environ["ORDER_LOG"])):
        r, nid, t = l.split()
        ORDER.setdefault((int(r), int(nid)), (int(t), i))
ALL = os.environ.get("ALL") == "1"
sys.path.insert(0, "/scratch/harshanavkis/loom-proj/opus-ref/Opus/simulation/symbolic_tensor_graph/symbolic_tensor_graph/chakra/backends/chakra_00_4_backend/et_def")
import et_def_pb2 as pb
from google.protobuf.internal.decoder import _DecodeVarint32
from google.protobuf.internal.encoder import _VarintBytes

src, dst, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
only = None
if len(sys.argv) > 5 and not ALL:
    gps = int(sys.argv[5])
    only = {g for g, m in json.load(open(sys.argv[4])).items() if len({x // gps for x in m}) > 1}
seqs = collections.defaultdict(dict); added = 0
for r in range(n):
    b = open(f"{src}.{r}.et", "rb").read(); i = 0; raw = []
    while i < len(b):
        k, i = _DecodeVarint32(b, i); raw.append(b[i:i+k]); i += k
    gm = pb.GlobalMetadata(); gm.ParseFromString(raw[0])
    nodes = []
    for x in raw[1:]:
        nd = pb.Node(); nd.ParseFromString(x); nodes.append(nd)
    byid = {nd.id: nd for nd in nodes}
    indeg = {nd.id: 0 for nd in nodes}; succ = collections.defaultdict(list)
    for nd in nodes:
        for d in set(nd.data_deps) | set(nd.ctrl_deps):
            indeg[nd.id] += 1; succ[d].append(nd.id)
    h = [x for x, c in indeg.items() if c == 0]; heapq.heapify(h); topo = []
    while h:
        x = heapq.heappop(h); topo.append(x)
        for y in succ[x]:
            indeg[y] -= 1
            if indeg[y] == 0: heapq.heappush(h, y)
    assert len(topo) == len(nodes), f"rank {r}: cycle in the input DAG"
    if ORDER:
        miss = [x for x in topo if (r, x) not in ORDER]
        assert not miss, f"rank {r}: {len(miss)} nodes not in ORDER_LOG"
        topo.sort(key=lambda x: ORDER[(r, x)])
    last = {}
    for x in topo:
        nd = byid[x]
        t = pb.NodeType.Name(nd.type)
        if TOTAL and t == "COMM_SEND_NODE":
            g = "*"
            if g in last and last[g] not in nd.data_deps and last[g] not in nd.ctrl_deps:
                nd.ctrl_deps.append(last[g]); added += 1
            last[g] = x
            continue
        if t != "COMM_COLL_NODE": continue
        a = {t.name: t for t in nd.attr}
        g = a["pg_name"].string_val
        seqs[g].setdefault(r, []).append((a["comm_type"].int64_val,
                                          a["comm_size"].int64_val or a["comm_size"].uint64_val))
        if only is not None and g not in only: continue
        if TOTAL: g = "*"
        if g in last and last[g] not in nd.data_deps and last[g] not in nd.ctrl_deps:
            nd.ctrl_deps.append(last[g]); added += 1
        last[g] = x
    with open(f"{dst}.{r}.et", "wb") as f:
        for m in [gm] + nodes:
            s = m.SerializeToString(); f.write(_VarintBytes(len(s))); f.write(s)
bad = [g for g, m in seqs.items() if len({tuple(v) for v in m.values()}) > 1]
print(f"ranks {n}, groups {len(seqs)} (chained: {'all' if only is None else len(only & set(seqs))}), ctrl deps added {added}, groups whose members disagree: {bad or 'none'}")
sys.exit(1 if bad else 0)
