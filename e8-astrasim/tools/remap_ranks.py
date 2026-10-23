#!/usr/bin/env python3
"""Renumber the ranks of a STAGE trace so that a chosen parallel dimension is innermost.

STAGE numbers ranks with DP innermost (innermost first: dp, tp, cp, ep, pp; checked on its comm groups:
dp2 tp4 pp2 -> DP pairs [0,1], TP groups [0,2,4,6], PP blocks of 8). ASTRA-sim puts ranks 8k..8k+7 on one
server, so with DP > 1 the TP groups would straddle servers. This maps STAGE's logical rank to a physical
rank in another order (default: tp, cp, dp, ep, pp = TP inside a server, DP / EP / PP across servers) and
rewrites the trace files (<prefix>.<rank>.et), the comm-group file (<prefix>.json: rank lists) and every
point-to-point peer (comm_src / comm_dst). Prints, per group size, how many groups stay in one server.

  remap_ranks.py <in dir> <prefix> <out dir> dp=D tp=T [cp=C] [ep=E] pp=P [--to tp,cp,dp,ep,pp] [--gpus-per-server 8]
"""
import json, os, sys
from collections import Counter
sys.path.insert(0, "/scratch/harshanavkis/loom-proj/opus-ref/Opus/simulation/symbolic_tensor_graph/symbolic_tensor_graph/chakra/backends/chakra_00_4_backend/et_def")
import et_def_pb2 as pb
from google.protobuf.internal.decoder import _DecodeVarint32
from google.protobuf.internal.encoder import _VarintBytes

STAGE_ORDER = ["dp", "tp", "cp", "ep", "pp"]


def coords(rank, order, size):
    c = {}
    for d in order:
        c[d] = rank % size[d]; rank //= size[d]
    return c


def rank_of(c, order, size):
    r, m = 0, 1
    for d in order:
        r += c[d] * m; m *= size[d]
    return r


def main():
    a = sys.argv[1:]
    src, prefix, dst = a[0], a[1], a[2]
    size = {d: 1 for d in STAGE_ORDER}
    to, gps = ["tp", "cp", "dp", "ep", "pp"], 8
    i = 3
    while i < len(a):
        if a[i] == "--to":
            to = a[i + 1].split(","); i += 2
        elif a[i] == "--gpus-per-server":
            gps = int(a[i + 1]); i += 2
        else:
            k, v = a[i].split("="); size[k] = int(v); i += 1
    n = 1
    for d in STAGE_ORDER:
        n *= size[d]
    perm = {r: rank_of(coords(r, STAGE_ORDER, size), to, size) for r in range(n)}
    assert sorted(perm.values()) == list(range(n))
    os.makedirs(dst, exist_ok=True)
    groups = json.load(open(os.path.join(src, prefix + ".json")))
    new_groups = {k: sorted(perm[r] for r in v) for k, v in groups.items()}
    json.dump(new_groups, open(os.path.join(dst, prefix + ".json"), "w"))
    for r in range(n):
        b = open(os.path.join(src, f"{prefix}.{r}.et"), "rb").read()
        out, j = [], 0
        m, j = _DecodeVarint32(b, j); out.append(b[j:j + m]); j += m      # GlobalMetadata as is
        while j < len(b):
            m, j = _DecodeVarint32(b, j)
            nd = pb.Node(); nd.ParseFromString(b[j:j + m]); j += m
            for at in nd.attr:
                if at.name in ("comm_src", "comm_dst"):
                    at.int32_val = perm[at.int32_val]
            out.append(nd.SerializeToString())
        with open(os.path.join(dst, f"{prefix}.{perm[r]}.et"), "wb") as f:
            for s in out:
                f.write(_VarintBytes(len(s)) + s)
    stat = Counter()
    for v in new_groups.values():
        if len(v) > 1:
            stat[(len(v), "one server" if len({x // gps for x in v}) == 1 else "across servers")] += 1
    print(f"{n} ranks, order {','.join(to)}; groups by size: " +
          ", ".join(f"{k[0]} ranks {k[1]}: {c}" for k, c in sorted(stat.items())))


if __name__ == "__main__":
    main()
