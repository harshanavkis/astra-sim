# Chakra ET for host-interface tests: rank 0 sends COUNT messages of SIZE bytes
# to rank 1 (all posted at once, or one after the other with --serial), or with
# --pingpong COUNT round trips (rank 1 replies to each message; rank 0's finish
# time / COUNT = round trip). --ack (2026-10-27, the prototype's throughput test E1): after all COUNT messages rank 1
# sends an 8 B acknowledgement, and rank 0 finishes once it has it (and its sends are released).
# --pre NS (2026-10-27, Fig 11 through ASTRA-sim instead of an_replay): rank 0 computes NS ns (num_ops = NS; run with a
# roofline system file at 1 op per ns) before its sends, the GPU's work per message (RDMA's post call, Loom's stores).
#   python -I gen_p2p.py <out dir> <size> [count] [--serial|--pingpong|--ack] [--pre NS]   -> <out dir>/p2p.{0,1}.et
import sys, os
sys.path.insert(0, "/scratch/harshanavkis/loom-proj/opus-ref/Opus/simulation/symbolic_tensor_graph/symbolic_tensor_graph/chakra/backends/chakra_00_4_backend/et_def")
import et_def_pb2 as pb
from google.protobuf.internal.encoder import _VarintBytes
argv = sys.argv[1:]
PRE = 0
if "--pre" in argv:
    k = argv.index("--pre"); PRE = int(argv[k + 1]); del argv[k:k + 2]
args = [a for a in argv if not a.startswith("--")]
out, size = args[0], int(args[1]); count = int(args[2]) if len(args) > 2 else 1
serial = "--serial" in sys.argv
os.makedirs(out, exist_ok=True)
def write(rank, nodes):
    with open(f"{out}/p2p.{rank}.et", "wb") as f:
        gm = pb.GlobalMetadata(); gm.attr.add(name="schema", string_val="loom-hif-test")
        for m in [gm] + nodes:
            s = m.SerializeToString(); f.write(_VarintBytes(len(s)) + s)
def node(i, typ, peer_key, peer):
    nd = pb.Node(id=i, name=f"{typ}{i}", type=pb.COMM_SEND_NODE if typ == "send" else pb.COMM_RECV_NODE)
    if serial and i > 1: nd.ctrl_deps.append(i - 1)
    nd.attr.add(name="comm_size", int64_val=size)
    nd.attr.add(name="comm_tag", int32_val=i)
    nd.attr.add(name=peer_key, int32_val=peer)
    nd.attr.add(name="is_cpu_op", bool_val=False)
    return nd
if "--pingpong" in sys.argv:
    serial = True  # every node waits for the one before it
    write(0, [node(i, "send" if i % 2 else "recv", "comm_dst" if i % 2 else "comm_src", 1) for i in range(1, 2 * count + 1)])
    write(1, [node(i, "recv" if i % 2 else "send", "comm_src" if i % 2 else "comm_dst", 0) for i in range(1, 2 * count + 1)])
    print(f"{out}: {count} round trips of {size} B")
    sys.exit(0)
if "--ack" in sys.argv:
    ack = count + 1
    a0, a1 = node(ack, "recv", "comm_src", 1), node(ack, "send", "comm_dst", 0)
    a0.attr[0].int64_val = a1.attr[0].int64_val = 8
    a1.ctrl_deps.extend(range(1, count + 1))
    write(0, [node(i, "send", "comm_dst", 1) for i in range(1, count + 1)] + [a0])
    write(1, [node(i, "recv", "comm_src", 0) for i in range(1, count + 1)] + [a1])
    print(f"{out}: {count} x {size} B, all at once, then an 8 B ack")
    sys.exit(0)
sends = [node(i, "send", "comm_dst", 1) for i in range(1, count + 1)]
if PRE:
    pre = pb.Node(id=count + 1, name="pre", type=pb.COMP_NODE)
    pre.attr.add(name="num_ops", int64_val=PRE)
    pre.attr.add(name="tensor_size", int64_val=1)
    pre.attr.add(name="is_cpu_op", bool_val=False)
    for nd in sends:
        nd.ctrl_deps.append(count + 1)
    sends = [pre] + sends
write(0, sends)
write(1, [node(i, "recv", "comm_src", 0) for i in range(1, count + 1)])
print(f"{out}: {count} x {size} B, {'serial' if serial else 'all at once'}")
