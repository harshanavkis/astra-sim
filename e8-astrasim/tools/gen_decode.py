#!/usr/bin/env python3
"""Chakra ETs for one MoE DECODE step of DeepSeek-V3 (owner 2026-10-21: end-to-end decode for the evaluation; compute from
ASTRA-sim's roofline, as the training traces: run with a roofline system file, e.g. e8/cfg/system_decode.json).

Deployment as DeepSeek's inference: attention data parallel (every GPU attends for its own T sequences, one new token
each, over a context of L tokens), experts spread evenly over the EP GPUs (256 / EP each), the shared expert and the
first 3 dense layers replicated. Per MoE layer and micro-batch, on every GPU:
  ATT (MLA, absorbed for decode, + router) -> dispatch: one send per destination GPU of n x 7168 B (FP8 tokens, n = the
  tokens with an expert there; a token's own GPU needs no network) -> EXPERT (the routed tokens that landed here) ->
  combine: n x 14336 B (BF16) back to each token's GPU -> next layer's ATT; SHARED (shared expert) runs beside.
Routing: top-8 of 256 by a hash of (GPU, token, layer) (gen_moe.py's routing, seeded per layer). A send may reuse its
buffer two layers later (double buffering, as DeepEP's low-latency mode): it depends on the same kind of sends two layers
back. With 2 micro-batches (DeepSeek's decode overlap) the GPU's compute alternates between them. After the last layer,
the LM head. Tags: dispatch 1 + 1000 m + l, combine 100001 + 1000 m + l (unique per message pair; run with
MSG_SPLIT_BYTES 7168 + MSG_SPLIT_HIGH_TAG 100000 14336: one put per token, as Fig 11, and ASTRA_CONCURRENT_SENDS=1).
Compute nodes: num_ops = FLOPs, tensor_size = bytes read and written (weights FP8, KV cache and activations BF16).
DeepSeek-V3 (its config.json): hidden 7168, 61 layers (3 dense, FFN 18432), 256 routed experts (FFN 2048) + 1 shared,
top-8, 128 heads, q_lora 1536, kv_lora 512, rope 64, nope 128, v_head 128, vocabulary 129280.
  gen_decode.py <out dir> <EP = GPUs> <tokens per GPU T> <context L> <micro-batches 1|2>   -> <out>/decode.<rank>.et
LOOP=<dispatch ns>,<combine ns> (owner 2026-10-22): the GPU is busy for its measured send loop (Section 2's harness) after
the attention (dispatch) and the experts (combine); the shared expert, the experts and the next layer wait for it. The
network config spreads the loop's posts (POST_LOOP_NS). Without LOOP the traces are as before (byte-identical)."""
import os, sys
sys.path.insert(0, "/scratch/harshanavkis/loom-proj/opus-ref/Opus/simulation/symbolic_tensor_graph/symbolic_tensor_graph/chakra/backends/chakra_00_4_backend/et_def")
import et_def_pb2 as pb
from google.protobuf.internal.encoder import _VarintBytes

H, LAYERS, DENSE, FFN, MFFN, E, TOPK = 7168, 61, 3, 18432, 2048, 256, 8
HEADS, QL, KVL, ROPE, NOPE, VH, VOCAB = 128, 1536, 512, 64, 128, 128, 129280
DTOK, CTOK = H, 2 * H                                   # dispatch FP8, combine BF16 bytes per token
ATTN_W = H * QL + QL * HEADS * (NOPE + ROPE) + H * (KVL + ROPE) + KVL * HEADS * (NOPE + VH) + HEADS * VH * H + H * E
EXP_W, DENSE_W, HEAD_W = 3 * H * MFFN, 3 * H * FFN, VOCAB * H
M32 = 0xffffffff


def hsh(x):
    x &= M32
    x ^= x >> 16; x = (x * 0x7feb352d) & M32
    x ^= x >> 15; x = (x * 0x846ca68b) & M32
    x ^= x >> 16
    return x


def experts(g, t, l):
    got, j = [], 0
    while len(got) < TOPK:
        e = hsh(g * 1000003 + t * 131 + l * 7919 + j) % E
        j += 1
        if e not in got:
            got.append(e)
    return got


out, ep, T, L, MB = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
LOOP = tuple(float(x) for x in os.environ['LOOP'].split(',')) if os.environ.get('LOOP') else None   # ns
assert E % ep == 0 and MB in (1, 2) and T >= MB
os.makedirs(out, exist_ok=True)
per = E // ep
toks = [list(range(T))[m::MB] for m in range(MB)]       # a GPU's tokens per micro-batch
nodes = {r: [] for r in range(ep)}
comp_ns = {r: 0.0 for r in range(ep)}                    # roofline compute per GPU (printed only; ASTRA-sim computes it)


def add(r, nd, deps=()):
    nd.id = len(nodes[r]) + 1
    nd.data_deps.extend(sorted(set(d for d in deps if d)))
    nodes[r].append(nd)
    return nd.id


def comp(r, name, flops, nbytes, deps):
    flops, nbytes = max(int(flops), 1), max(int(nbytes), 1)
    nd = pb.Node(name=name, type=pb.COMP_NODE)
    nd.attr.add(name="num_ops", int64_val=flops)
    nd.attr.add(name="tensor_size", uint64_val=nbytes)
    comp_ns[r] += max(nbytes / 4.8e3, flops / 989e3)    # ns at 4.8 TB/s, 989 TFLOP/s (system_decode.json)
    return add(r, nd, deps)


def comm(r, kind, peer, size, tag, deps=()):
    nd = pb.Node(name=f"{kind}{tag}", type=pb.COMM_SEND_NODE if kind == "send" else pb.COMM_RECV_NODE)
    nd.attr.add(name="comm_size", int64_val=size)
    nd.attr.add(name="comm_tag", int32_val=tag)
    nd.attr.add(name="comm_dst" if kind == "send" else "comm_src", int32_val=peer)
    nd.attr.add(name="is_cpu_op", bool_val=False)
    return add(r, nd, deps)


def att(r, b, deps, l):
    kv = b * L * (KVL + ROPE) * 2
    return comp(r, f"att{l}", 2 * b * ATTN_W + b * L * 2 * HEADS * (2 * KVL + ROPE), ATTN_W + kv + 4 * b * H, deps)


msgs = 0
for m in range(MB):
    b = len(toks[m])
    ready = {r: [] for r in range(ep)}                   # deps of the next layer's ATT on each GPU
    sends = {}                                           # (rank, kind, layer) -> send node ids (buffer reuse)
    for l in range(LAYERS):
        a = {r: att(r, b, ready[r], l) for r in range(ep)}
        if l < DENSE:
            ready = {r: [comp(r, f"ffn{l}", 2 * b * DENSE_W, DENSE_W + 4 * b * H, [a[r]])] for r in range(ep)}
            continue
        route = {(g, t): experts(g, toks[m][t] + 0, l) for g in range(ep) for t in range(b)}
        n, pairs, hit = {}, {}, {r: set() for r in range(ep)}
        own = {r: False for r in range(ep)}
        for (g, t), es in route.items():
            for e in es:
                d = e // per
                pairs[d] = pairs.get(d, 0) + 1
                hit[d].add(e)
                if d == g:
                    own[g] = True
            for d in {e // per for e in es}:
                if d != g:
                    n[(g, d)] = n.get((g, d), 0) + 1
        dtag, ctag = 1 + 1000 * m + l, 100001 + 1000 * m + l
        rx = {r: [] for r in range(ep)}
        for (g, d), k in sorted(n.items()):
            sid = comm(g, "send", d, k * DTOK, dtag, [a[g]] + sends.get((g, "d", l - 2), []))
            sends.setdefault((g, "d", l), []).append(sid)
            rx[d].append(comm(d, "recv", g, k * DTOK, dtag))
            msgs += 1
        # the dispatch's send loop: one memory-bound node of LOOP[0] ns (num_ops 1, bytes = ns x 4.8 TB/s)
        busy = {r: [comp(r, f"dloop{l}", 1, LOOP[0] * 4800, [a[r]])] for r in range(ep)} if LOOP else {r: [] for r in range(ep)}
        ex = {r: comp(r, f"exp{l}", 2 * pairs.get(r, 0) * EXP_W, len(hit[r]) * EXP_W + pairs.get(r, 0) * (DTOK + CTOK),
                      [a[r]] + rx[r] + busy[r]) for r in range(ep)}
        sh = {r: comp(r, f"shared{l}", 2 * b * EXP_W, EXP_W + 4 * b * H, [a[r]] + busy[r]) for r in range(ep)}
        crx = {r: [] for r in range(ep)}
        for (g, d), k in sorted(n.items()):                # combine: d returns g's tokens
            sid = comm(d, "send", g, k * CTOK, ctag, [ex[d]] + sends.get((d, "c", l - 2), []))
            sends.setdefault((d, "c", l), []).append(sid)
            crx[g].append(comm(g, "recv", d, k * CTOK, ctag))
            msgs += 1
        cbusy = {r: [comp(r, f"cloop{l}", 1, LOOP[1] * 4800, [ex[r]])] for r in range(ep)} if LOOP else {r: [] for r in range(ep)}
        ready = {r: crx[r] + [sh[r]] + ([ex[r]] if own[r] else []) + cbusy[r] for r in range(ep)}
    for r in range(ep):
        comp(r, "lm_head", 2 * b * HEAD_W, HEAD_W + 4 * b * H, ready[r])

for r in range(ep):
    with open(f"{out}/decode.{r}.et", "wb") as f:
        gm = pb.GlobalMetadata(); gm.attr.add(name="schema", string_val="loom-decode")
        for x in [gm] + nodes[r]:
            s = x.SerializeToString(); f.write(_VarintBytes(len(s)) + s)
print(f"{out}: decode EP{ep}, {T} tokens/GPU, context {L}, {MB} micro-batch(es): {msgs / ep:.0f} messages per GPU, "
      f"{max(len(v) for v in nodes.values())} nodes per GPU, roofline compute {max(comp_ns.values()) / 1e3:.0f} us per GPU")
sys.stdout.flush()
os._exit(0)   # the traces are written; skip freeing millions of nodes (minutes at EP256)
