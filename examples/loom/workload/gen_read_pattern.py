#!/usr/bin/env python3
"""Generate a read-heavy Chakra ET (independent MEM_LOAD nodes) to exercise
the LOOM_PEER_READS credit cap (eval S-5): every rank issues --loads
independent peer reads of --size-kb; the credit budget throttles concurrency.

  python3 examples/loom/workload/gen_read_pattern.py --npus 4 --loads 64 \
      --size-kb 4 --out /tmp/reads
"""

import argparse
import os

from extern.graph_frontend.chakra.schema.protobuf.et_def_pb2 import (
    GlobalMetadata,
    MEM_LOAD_NODE,
)
from extern.graph_frontend.chakra.schema.protobuf.et_def_pb2 import (
    AttributeProto as ChakraAttr,
)
from extern.graph_frontend.chakra.schema.protobuf.et_def_pb2 import Node as ChakraNode
from extern.graph_frontend.chakra.src.third_party.utils.protolib import (
    encodeMessage as encode_message,
)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--npus", type=int, required=True)
    p.add_argument("--loads", type=int, default=64)
    p.add_argument("--size-kb", type=int, default=4)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    os.makedirs(args.out, exist_ok=True)
    for rank in range(args.npus):
        with open(os.path.join(args.out, f"reads.{rank}.et"), "wb") as et:
            encode_message(et, GlobalMetadata(version="0.0.4"))
            for i in range(args.loads):
                node = ChakraNode()
                node.id = i
                node.name = f"peer_read_{i}"
                node.type = MEM_LOAD_NODE
                node.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
                node.attr.append(
                    ChakraAttr(name="tensor_size", uint64_val=args.size_kb * 1024))
                encode_message(et, node)
    print(f"wrote {args.npus} ranks x {args.loads} loads to {args.out}/reads.*.et")


if __name__ == "__main__":
    main()
