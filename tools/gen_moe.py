#!/usr/bin/env python3
"""Chakra ETs for an MoE dispatch or combine at expert parallelism EP (Section 2's shape at scale):
every GPU has T tokens; each token goes to its top-8 of 256 experts (hash routing as dispatch_bd.cu,
seeded by the GPU), the experts spread evenly over the EP GPUs (256 / EP each), so a token goes to the
distinct GPUs holding its experts. Dispatch: one send per (source, destination GPU) of n x H bytes
(n = that destination's tokens; the frontend's MSG_SPLIT_BYTES = H makes it one put per token);
combine: the same pairs the other way (each token's result back to its GPU). A token's own GPU needs
no network and is skipped. Every send and receive starts at time 0 (no dependencies; run with
ASTRA_CONCURRENT_SENDS=1 so a GPU's sends go side by side).
  gen_moe.py <out dir> <ep> <tokens> dispatch|combine <H>   -> <out>/moe.<rank>.et"""
import os, sys
sys.path.insert(0, "/scratch/harshanavkis/loom-proj/opus-ref/Opus/simulation/symbolic_tensor_graph/symbolic_tensor_graph/chakra/backends/chakra_00_4_backend/et_def")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import et_def_pb2 as pb
from google.protobuf.internal.encoder import _VarintBytes

E, TOPK, M32 = 256, 8, 0xffffffff

def hsh(x):
    x &= M32
    x ^= x >> 16; x = (x * 0x7feb352d) & M32
    x ^= x >> 15; x = (x * 0x846ca68b) & M32
    x ^= x >> 16
    return x

def dests(g, t, ep):
    """GPUs holding token t of GPU g's top-8 experts (dispatch_bd.cu's rank_mask, seeded by g)."""
    got, used, j, out = 0, set(), 0, set()
    while got < TOPK:
        e = hsh(g * 1000003 + t * 131 + j) % E
        j += 1
        if e in used:
            continue
        used.add(e); got += 1
        out.add(e // (E // ep))
    return out

out, ep, T, op, H = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], int(sys.argv[5])
assert E % ep == 0 and op in ("dispatch", "combine")
os.makedirs(out, exist_ok=True)
n = {}  # (src GPU of the tokens, destination GPU) -> tokens
for g in range(ep):
    for t in range(T):
        for d in dests(g, t, ep):
            if d != g:
                n[(g, d)] = n.get((g, d), 0) + 1
pairs = n if op == "dispatch" else {(d, g): k for (g, d), k in n.items()}   # combine: back to the token's GPU
nodes = {r: [] for r in range(ep)}
def node(rank, typ, peer, size):
    i = len(nodes[rank]) + 1
    nd = pb.Node(id=i, name=f"{typ}{i}", type=pb.COMM_SEND_NODE if typ == "send" else pb.COMM_RECV_NODE)
    nd.attr.add(name="comm_size", int64_val=size)
    nd.attr.add(name="comm_tag", int32_val=1)
    nd.attr.add(name="comm_dst" if typ == "send" else "comm_src", int32_val=peer)
    nd.attr.add(name="is_cpu_op", bool_val=False)
    nodes[rank].append(nd)
for (s, d), k in sorted(pairs.items()):
    node(s, "send", d, k * H)
    node(d, "recv", s, k * H)
for r in range(ep):
    with open(f"{out}/moe.{r}.et", "wb") as f:
        gm = pb.GlobalMetadata(); gm.attr.add(name="schema", string_val="loom-moe")
        for m in [gm] + nodes[r]:
            s = m.SerializeToString(); f.write(_VarintBytes(len(s)) + s)
msgs = sum(pairs.values())
print(f"{out}: {op} EP{ep} {T} tokens/GPU, H {H}: {len(pairs)} sends, {msgs} token messages, "
      f"{msgs / ep:.1f} per GPU ({msgs * H / ep / 1e6:.2f} MB)")
