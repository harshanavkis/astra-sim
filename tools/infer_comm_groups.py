# Infer ASTRA-sim's comm-group json for a set of Chakra ET traces: a process
# group's members are the ranks whose trace issues collectives on it (pg_name).
# Prints per group: members, collective count per rank, comm types.
#   python -I infer_comm_groups.py <out.json> <rank0.et> <rank1.et> ...   (in rank order)
import sys, json, collections
sys.path.insert(0, "/scratch/harshanavkis/loom-proj/opus-ref/Opus/simulation/symbolic_tensor_graph/symbolic_tensor_graph/chakra/backends/chakra_00_4_backend/et_def")
import et_def_pb2 as pb
from google.protobuf.internal.decoder import _DecodeVarint32
members = collections.defaultdict(set); counts = collections.defaultdict(collections.Counter)
types = collections.defaultdict(collections.Counter)
for rank, path in enumerate(sys.argv[2:]):
    b = open(path, "rb").read(); i = 0; first = True
    while i < len(b):
        n, i = _DecodeVarint32(b, i); raw = b[i:i+n]; i += n
        if first: first = False; continue
        nd = pb.Node(); nd.ParseFromString(raw)
        if nd.type not in (pb.COMM_COLL_NODE, pb.COMM_SEND_NODE, pb.COMM_RECV_NODE): continue
        a = {x.name: x for x in nd.attr}
        pg = a["pg_name"].string_val if "pg_name" in a else ""
        members[pg].add(rank); counts[pg][rank] += 1
        types[pg][pb.CollectiveCommType.Name(a["comm_type"].int64_val) if "comm_type" in a else pb.NodeType.Name(nd.type)] += 1
for pg in sorted(members, key=lambda x: (len(x), x)):
    print(f"pg {pg!r:6} ranks {sorted(members[pg])} ops/rank {sorted(set(counts[pg].values()))} {dict(types[pg])}")
# "" and "0" = the world group in ASTRA-sim (Workload::extract_comm_group); ids must be > 0
json.dump({pg: sorted(m) for pg, m in members.items() if pg not in ("", "0")}, open(sys.argv[1], "w"))
