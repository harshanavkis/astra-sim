#!/usr/bin/env python3
"""Generate a Chakra ET for an MoE expert-parallel iteration:

    [dispatch all-to-all] -> [expert compute] -> [combine all-to-all]  x iters

per rank. Carries the SM-reservation model for baselines: production systems
statically reserve SMs for communication (DeepSeek-V3: 20 of an H800's 132),
so baseline traces scale COMP durations by sm_total/(sm_total - sm_comm);
Loom traces use --sm-comm 0 (full-SM compute).

Run from the astra-sim repo root (PYTHONPATH must include the repo, as in the
official Docker image):

  python3 examples/loom/workload/gen_moe_alltoall.py \
      --npus 128 --coll-size-kb 512 --expert-time-us 800 --iters 4 \
      --sm-total 132 --sm-comm 20 --out moe_b1
"""

import argparse
import os

from extern.graph_frontend.chakra.schema.protobuf.et_def_pb2 import (
    GlobalMetadata,
    COMM_COLL_NODE,
    COMP_NODE,
    ALL_TO_ALL,
)
from extern.graph_frontend.chakra.schema.protobuf.et_def_pb2 import (
    AttributeProto as ChakraAttr,
)
from extern.graph_frontend.chakra.schema.protobuf.et_def_pb2 import Node as ChakraNode
from extern.graph_frontend.chakra.src.third_party.utils.protolib import (
    encodeMessage as encode_message,
)


def coll_node(node_id: int, name: str, size_bytes: int, dep: int | None) -> ChakraNode:
    node = ChakraNode()
    node.id = node_id
    node.name = name
    node.type = COMM_COLL_NODE
    node.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
    node.attr.append(ChakraAttr(name="comm_type", int64_val=ALL_TO_ALL))
    node.attr.append(ChakraAttr(name="comm_size", int64_val=size_bytes))
    if dep is not None:
        node.data_deps.append(dep)
    return node


def comp_node(node_id: int, name: str, duration_us: int, dep: int | None) -> ChakraNode:
    node = ChakraNode()
    node.id = node_id
    node.name = name
    node.type = COMP_NODE
    node.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
    node.duration_micros = duration_us
    if dep is not None:
        node.data_deps.append(dep)
    return node


def generate(args) -> None:
    assert 0 <= args.sm_comm < args.sm_total
    # static SM reservation: compute slows by sm_total/(sm_total - sm_comm)
    sm_factor = args.sm_total / (args.sm_total - args.sm_comm)
    expert_us = round(args.expert_time_us * sm_factor)
    size_bytes = args.coll_size_kb * 1024

    os.makedirs(args.out, exist_ok=True)
    for npu in range(args.npus):
        path = os.path.join(args.out, f"moe.{npu}.et")
        with open(path, "wb") as et:
            encode_message(et, GlobalMetadata(version="0.0.4"))
            node_id, dep = 0, None
            for it in range(args.iters):
                for node in (
                    coll_node(node_id, f"dispatch_a2a_{it}", size_bytes, dep),
                    comp_node(node_id + 1, f"expert_comp_{it}", expert_us, node_id),
                    coll_node(node_id + 2, f"combine_a2a_{it}", size_bytes, node_id + 1),
                ):
                    encode_message(et, node)
                dep = node_id + 2
                node_id += 3
    print(
        f"wrote {args.npus} ranks x {args.iters} iters to {args.out}/moe.*.et "
        f"(coll {args.coll_size_kb} KB, expert {expert_us} us, sm_factor {sm_factor:.3f})"
    )


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--npus", type=int, required=True)
    p.add_argument("--coll-size-kb", type=int, default=512,
                   help="all-to-all size per rank per phase (KB)")
    p.add_argument("--expert-time-us", type=int, default=800,
                   help="full-SM expert compute per iteration (us)")
    p.add_argument("--iters", type=int, default=4)
    p.add_argument("--sm-total", type=int, default=132)
    p.add_argument("--sm-comm", type=int, default=0,
                   help="SMs reserved for communication (0 = Loom; 20 = DeepSeek-V3 baseline)")
    p.add_argument("--out", required=True, help="output directory; feeds --workload-configuration=<out>/moe")
    generate(p.parse_args())


if __name__ == "__main__":
    main()
