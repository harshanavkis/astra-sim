#!/usr/bin/env python3
"""Generate Chakra ETs for point-to-point stress patterns (Loom eval S3/S4).

Patterns (rank layout: rank = xpu + xpus_per_rack * rack, dim0 innermost):
  single   one flow: --src -> --dst, --iters chained sends of --size-kb
  incast   every rank in rack 0 (except any victim roles) -> --dst
  victim   victim flow  src=0 (rack 0)      -> --victim-dst (rack 1)
           aggressors   ranks 1..--aggressors (rack 0) -> --congested-dst (rack 1)
           All flows leave rack 0 through the same ToR uplink; with a shared
           egress FIFO the aggressors' backlog head-of-line-blocks the victim,
           with per-destination queues (VOQ) it must not.

Every rank gets an .et file (idle ranks get metadata only). Each flow uses a
unique comm_tag; receivers post matching recvs.

Run from the astra-sim repo root (PYTHONPATH=/app/astra-sim in Docker):
  python3 examples/loom/workload/gen_p2p_patterns.py --pattern victim \
      --racks 2 --xpus-per-rack 4 --size-kb 1024 --iters 8 \
      --victim-dst 4 --congested-dst 5 --aggressors 2 --out /tmp/victim
"""

import argparse
import os
from collections import defaultdict

from extern.graph_frontend.chakra.schema.protobuf.et_def_pb2 import (
    GlobalMetadata,
    COMM_SEND_NODE,
    COMM_RECV_NODE,
    COMP_NODE,
)
from extern.graph_frontend.chakra.schema.protobuf.et_def_pb2 import (
    AttributeProto as ChakraAttr,
)
from extern.graph_frontend.chakra.schema.protobuf.et_def_pb2 import Node as ChakraNode
from extern.graph_frontend.chakra.src.third_party.utils.protolib import (
    encodeMessage as encode_message,
)


def p2p_node(node_id, node_type, src, dst, size, tag, dep):
    node = ChakraNode()
    node.id = node_id
    node.name = f"{'send' if node_type == COMM_SEND_NODE else 'recv'}_t{tag}"
    node.type = node_type
    node.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
    node.attr.append(ChakraAttr(name="comm_src", uint32_val=src))
    node.attr.append(ChakraAttr(name="comm_dst", uint32_val=dst))
    node.attr.append(ChakraAttr(name="comm_size", uint64_val=size))
    node.attr.append(ChakraAttr(name="comm_tag", uint32_val=tag))
    if dep is not None:
        node.data_deps.append(dep)
    return node


def build_flows(args):
    """Return list of (src, dst) flows."""
    if args.pattern == "single":
        return [(args.src, args.dst)]
    if args.pattern == "incast":
        return [(r, args.dst) for r in range(args.xpus_per_rack) if r != args.dst]
    if args.pattern == "victim":
        flows = [(0, args.victim_dst)]
        flows += [(a, args.congested_dst) for a in range(1, 1 + args.aggressors)]
        return flows  # aggressor flows use --aggressor-size-kb
    raise ValueError(args.pattern)


def generate(args):
    npus = args.racks * args.xpus_per_rack
    flows = build_flows(args)
    for src, dst in flows:
        assert 0 <= src < npus and 0 <= dst < npus and src != dst, (src, dst)

    # per-rank node lists
    nodes = defaultdict(list)
    for tag, (src, dst) in enumerate(flows, start=1):
        is_aggressor = args.pattern == "victim" and tag > 1
        size = (args.aggressor_size_kb if is_aggressor else args.size_kb) * 1024
        send_dep = recv_dep = None
        for it in range(args.iters):
            snd = p2p_node(len(nodes[src]), COMM_SEND_NODE, src, dst, size, tag, send_dep)
            rcv = p2p_node(len(nodes[dst]), COMM_RECV_NODE, src, dst, size, tag, recv_dep)
            send_dep, recv_dep = snd.id, rcv.id
            nodes[src].append(snd)
            nodes[dst].append(rcv)

    os.makedirs(args.out, exist_ok=True)
    for rank in range(npus):
        with open(os.path.join(args.out, f"p2p.{rank}.et"), "wb") as et:
            encode_message(et, GlobalMetadata(version="0.0.4"))
            if not nodes[rank]:  # the feeder rejects empty traces
                idle = ChakraNode()
                idle.id = 0
                idle.name = "idle"
                idle.type = COMP_NODE
                idle.duration_micros = 1
                idle.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
                nodes[rank].append(idle)
            for node in nodes[rank]:
                encode_message(et, node)
    roles = ", ".join(f"{s}->{d}" for s, d in flows)
    print(f"wrote {npus} ranks to {args.out}/p2p.*.et ({args.pattern}: {roles}, "
          f"{args.iters} x {args.size_kb} KB per flow)")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pattern", choices=("single", "incast", "victim"), required=True)
    p.add_argument("--racks", type=int, default=2)
    p.add_argument("--xpus-per-rack", type=int, default=4)
    p.add_argument("--size-kb", type=int, default=1024)
    p.add_argument("--aggressor-size-kb", type=int, default=4096,
                   help="flow size for aggressors in the victim pattern")
    p.add_argument("--iters", type=int, default=8)
    p.add_argument("--src", type=int, default=0)
    p.add_argument("--dst", type=int, default=None)
    p.add_argument("--victim-dst", type=int, default=None)
    p.add_argument("--congested-dst", type=int, default=None)
    p.add_argument("--aggressors", type=int, default=2)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    m = args.xpus_per_rack
    if args.dst is None:
        args.dst = m  # first XPU of rack 1
    if args.victim_dst is None:
        args.victim_dst = m
    if args.congested_dst is None:
        args.congested_dst = m + 1
    generate(args)


if __name__ == "__main__":
    main()
