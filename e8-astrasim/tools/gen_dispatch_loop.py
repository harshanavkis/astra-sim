# Chakra ET for the steve loopback dispatch/combine (dispatch_bd.cu): rank 0 sends
# MSGS messages of H bytes to rank 1 (one comm op, split into puts by
# MSG_SPLIT_BYTES = H), then an 8 B signal; rank 1 receives both. The receiver
# finishing = it has seen the signal and every message.
#   python -I gen_dispatch_loop.py <out dir> <msgs> <H>   -> <out dir>/d.{0,1}.et
import sys, os
sys.path.insert(0, "/scratch/harshanavkis/loom-proj/opus-ref/Opus/simulation/symbolic_tensor_graph/symbolic_tensor_graph/chakra/backends/chakra_00_4_backend/et_def")
import et_def_pb2 as pb
from google.protobuf.internal.encoder import _VarintBytes
out, msgs, H = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
os.makedirs(out, exist_ok=True)
def node(i, send, size, dep=None):
    nd = pb.Node(id=i, name=("send" if send else "recv") + str(i),
                 type=pb.COMM_SEND_NODE if send else pb.COMM_RECV_NODE)
    if dep: nd.ctrl_deps.append(dep)
    nd.attr.add(name="comm_size", int64_val=size)
    nd.attr.add(name="comm_tag", int32_val=i)
    nd.attr.add(name="comm_dst" if send else "comm_src", int32_val=1 if send else 0)
    nd.attr.add(name="is_cpu_op", bool_val=False)
    return nd
for r, nodes in ((0, [node(1, True, msgs * H), node(2, True, 8, dep=1)]),
                 (1, [node(1, False, msgs * H), node(2, False, 8)])):
    with open(f"{out}/d.{r}.et", "wb") as f:
        gm = pb.GlobalMetadata(); gm.attr.add(name="schema", string_val="loom-hif-test")
        for m in [gm] + nodes:
            s = m.SerializeToString(); f.write(_VarintBytes(len(s)) + s)
print(f"{out}: {msgs} x {H} B + signal")
