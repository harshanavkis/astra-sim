# Fill an empty pg_name on a rank's collective when that rank belongs to exactly
# one of the groups that run that collective type (comm_groups.json from
# infer_comm_groups.py).
# Mixtral-8x22B rank 20 has one ALL_TO_ALL without pg_name (its 895 others use 173).
#   python -I fill_pg_name.py <in.et> <out.et> <rank> <comm_groups.json> <pg used by this comm type, e.g. ALL_TO_ALL=173,174,175,176>
import sys, json
sys.path.insert(0, "/scratch/harshanavkis/loom-proj/opus-ref/Opus/simulation/symbolic_tensor_graph/symbolic_tensor_graph/chakra/backends/chakra_00_4_backend/et_def")
import et_def_pb2 as pb
from google.protobuf.internal.decoder import _DecodeVarint32
from google.protobuf.internal.encoder import _VarintBytes
src, dst, rank, groups = sys.argv[1], sys.argv[2], int(sys.argv[3]), json.load(open(sys.argv[4]))
ctype, pgs = sys.argv[5].split("="); pgs = pgs.split(",")
mine = [pg for pg in pgs if rank in groups[pg]]
assert len(mine) == 1, mine
b = open(src, "rb").read(); i = 0; raws = []
while i < len(b):
    n, i = _DecodeVarint32(b, i); raws.append(b[i:i+n]); i += n
filled = 0
with open(dst, "wb") as f:
    f.write(_VarintBytes(len(raws[0])) + raws[0])
    for raw in raws[1:]:
        nd = pb.Node(); nd.ParseFromString(raw)
        if nd.type == pb.COMM_COLL_NODE:
            a = {x.name: x for x in nd.attr}
            if pb.CollectiveCommType.Name(a["comm_type"].int64_val) == ctype and ("pg_name" not in a or a["pg_name"].string_val == ""):
                if "pg_name" in a: a["pg_name"].string_val = mine[0]
                else: nd.attr.add(name="pg_name", string_val=mine[0])
                filled += 1; raw = nd.SerializeToString()
        f.write(_VarintBytes(len(raw)) + raw)
print(f"{src}: rank {rank} filled {filled} {ctype} pg_name -> {mine[0]}")
