# Chakra ET with one collective per rank (all ranks, world group).
#   python -I gen_coll.py <out dir> <npus> <ALL_TO_ALL|ALL_REDUCE|ALL_GATHER|REDUCE_SCATTER> <bytes> [count]
#   -> <out dir>/coll.<rank>.et ; count collectives one after the other
import sys, os
sys.path.insert(0, "/scratch/harshanavkis/loom-proj/opus-ref/Opus/simulation/symbolic_tensor_graph/symbolic_tensor_graph/chakra/backends/chakra_00_4_backend/et_def")
import et_def_pb2 as pb
from google.protobuf.internal.encoder import _VarintBytes
out, npus, ctype, size = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
count = int(sys.argv[5]) if len(sys.argv) > 5 else 1
os.makedirs(out, exist_ok=True)
for r in range(npus):
    with open(f"{out}/coll.{r}.et", "wb") as f:
        gm = pb.GlobalMetadata(); gm.attr.add(name="schema", string_val="loom-hif-test")
        msgs = [gm]
        for i in range(1, count + 1):
            nd = pb.Node(id=i, name=f"{ctype}{i}", type=pb.COMM_COLL_NODE)
            if i > 1: nd.ctrl_deps.append(i - 1)
            nd.attr.add(name="comm_type", int64_val=pb.CollectiveCommType.Value(ctype))
            nd.attr.add(name="comm_size", int64_val=size)
            nd.attr.add(name="is_cpu_op", bool_val=False)
            msgs.append(nd)
        for m in msgs:
            s = m.SerializeToString(); f.write(_VarintBytes(len(s)) + s)
print(f"{out}: {npus} ranks, {count} x {ctype} {size} B")
