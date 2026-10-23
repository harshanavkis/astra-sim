import sys, collections
sys.path.insert(0, "/scratch/harshanavkis/loom-proj/opus-ref/Opus/simulation/symbolic_tensor_graph/symbolic_tensor_graph/chakra/backends/chakra_00_4_backend/et_def")
import et_def_pb2 as pb
from google.protobuf.internal.decoder import _DecodeVarint32
def msgs(path):
    b = open(path, "rb").read(); i = 0
    while i < len(b):
        n, i = _DecodeVarint32(b, i); yield b[i:i+n]; i += n
it = msgs(sys.argv[1]); gm = pb.GlobalMetadata(); gm.ParseFromString(next(it))
cnt = collections.Counter(); size = collections.defaultdict(list); flops = 0
for raw in it:
    nd = pb.Node(); nd.ParseFromString(raw)
    a = {x.name: x for x in nd.attr}
    t = pb.NodeType.Name(nd.type)
    if "comm_type" in a:
        t += ":" + pb.CollectiveCommType.Name(a["comm_type"].int64_val)
    cnt[t] += 1
    if "comm_size" in a: size[t].append(a["comm_size"].int64_val if a["comm_size"].HasField("int64_val") else a["comm_size"].uint64_val)
    if "num_ops" in a: flops += a["num_ops"].int64_val or a["num_ops"].uint64_val
for t, c in sorted(cnt.items()):
    s = size.get(t)
    print(f"{t:40s} {c:5d}" + (f"  size min {min(s)/1024:.0f} KiB med {sorted(s)[len(s)//2]/2**20:.2f} MiB max {max(s)/2**20:.1f} MiB" if s else ""))
print(f"total GFLOP {flops/1e9:.0f}")
