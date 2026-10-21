# Copy a Chakra ET trace so ASTRA-sim accepts it: drop ctrl/data deps on node
# ids the trace does not contain (the downloaded traces point at node 0: "Node 0
# in ctrl_dep graph, but not found in index") and drop METADATA_NODEs
# (Statistics.cc asserts on them), rewiring their dependents to their deps.
#   python -I fix_ctrl_deps.py <in.et> <out.et>
import sys
sys.path.insert(0, "/scratch/harshanavkis/loom-proj/opus-ref/Opus/simulation/symbolic_tensor_graph/symbolic_tensor_graph/chakra/backends/chakra_00_4_backend/et_def")
import et_def_pb2 as pb
from google.protobuf.internal.decoder import _DecodeVarint32
from google.protobuf.internal.encoder import _VarintBytes
b = open(sys.argv[1], "rb").read(); i = 0; raws = []
while i < len(b):
    n, i = _DecodeVarint32(b, i); raws.append(b[i:i+n]); i += n
nodes = []
for raw in raws[1:]:
    nd = pb.Node(); nd.ParseFromString(raw); nodes.append(nd)
meta = {nd.id: list(nd.ctrl_deps) + list(nd.data_deps) for nd in nodes if nd.type == pb.METADATA_NODE}
nodes = [nd for nd in nodes if nd.id not in meta]
ids = {nd.id for nd in nodes}; dropped = 0
def resolve(d, seen=()):
    if d not in meta: return [d]
    return [x for m in meta[d] if m not in seen for x in resolve(m, seen + (d,))]
with open(sys.argv[2], "wb") as f:
    f.write(_VarintBytes(len(raws[0])) + raws[0])
    for nd in nodes:
        for field in (nd.ctrl_deps, nd.data_deps):
            keep = list(dict.fromkeys(x for d in field for x in resolve(d) if x in ids))
            dropped += keep != list(field)
            if keep != list(field):
                del field[:]; field.extend(keep)
        s = nd.SerializeToString(); f.write(_VarintBytes(len(s)) + s)
print(f"{sys.argv[1]}: {len(nodes)} nodes, {len(meta)} metadata nodes removed, {dropped} dep lists changed")
