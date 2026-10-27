# Chakra ET for a broadcast as the prototype's tools run it (ce_colln / rdma_colln --coll bc; ASTRA-sim has no broadcast
# collective): rank 0 sends SIZE bytes to every other rank, each receiver acknowledges with an 8 B message, and the root's
# next broadcast starts once it has every acknowledgement; COUNT broadcasts one after the other.
#   python -I gen_bcast.py <out dir> <npus> <size> [count]   -> <out dir>/bc.<rank>.et
import sys, os
sys.path.insert(0, "/scratch/harshanavkis/loom-proj/opus-ref/Opus/simulation/symbolic_tensor_graph/symbolic_tensor_graph/chakra/backends/chakra_00_4_backend/et_def")
import et_def_pb2 as pb
from google.protobuf.internal.encoder import _VarintBytes
out, npus, size = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
count = int(sys.argv[4]) if len(sys.argv) > 4 else 1
os.makedirs(out, exist_ok=True)


def node(i, send, peer, b, tag, deps):
    nd = pb.Node(id=i, name=f"{'send' if send else 'recv'}{i}", type=pb.COMM_SEND_NODE if send else pb.COMM_RECV_NODE)
    nd.ctrl_deps.extend(deps)
    nd.attr.add(name="comm_size", int64_val=b)
    nd.attr.add(name="comm_tag", int32_val=tag)
    nd.attr.add(name="comm_dst" if send else "comm_src", int32_val=peer)
    nd.attr.add(name="is_cpu_op", bool_val=False)
    return nd


def tag(it, q, ack):   # one tag per broadcast, receiver and direction
    return (it * npus + q) * 2 + ack


for r in range(npus):
    nodes, nid, prev = [], 0, []
    for it in range(count):
        if r == 0:
            sends = []
            for q in range(1, npus):
                nid += 1; nodes.append(node(nid, True, q, size, tag(it, q, 0), prev)); sends.append(nid)
            acks = []
            for q in range(1, npus):
                nid += 1; nodes.append(node(nid, False, q, 8, tag(it, q, 1), prev)); acks.append(nid)
            prev = acks + sends
        else:
            nid += 1; nodes.append(node(nid, False, 0, size, tag(it, r, 0), prev)); rcv = nid
            nid += 1; nodes.append(node(nid, True, 0, 8, tag(it, r, 1), [rcv])); prev = [nid]
    with open(f"{out}/bc.{r}.et", "wb") as f:
        gm = pb.GlobalMetadata(); gm.attr.add(name="schema", string_val="loom-hif-test")
        for m in [gm] + nodes:
            s = m.SerializeToString(); f.write(_VarintBytes(len(s)) + s)
print(f"{out}: {npus} ranks, {count} x broadcast {size} B")
