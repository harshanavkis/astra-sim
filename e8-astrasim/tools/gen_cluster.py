# E8 cluster: ns-3 topology + logical topology + ns-3 configs for each host
# interface variant. GPUs sit in servers of GPS (NVLink inside, the frontend's
# path); each GPU has one network device (RDMA NIC or Loom) on a leaf switch;
# leaves connect to every spine (full bisection) when there is more than one.
#   python -I gen_cluster.py <name> <gpus> [--gps 8] [--per-leaf 32] [--gbps 400]
#        [--host-ns 500] [--fabric-ns 200] [--mtu 4096]
# -> e8/clusters/<name>/{topo.txt,logical.json,<variant>.txt}
# Variants: none (upstream), pull (post 0.70 us: mini-gda), pull_deepep (3.07),
# pull_nvshmem (7.33), push (Loom) = the OLD per-message model; rdma (the NIC model,
# HOST_IF_MODE nic, steve's CX-7 + H200 PCIe latencies, validated on Section 2's dispatch /
# combine), loom (ideal Loom on the same model: stores carry the data, 21/7 cycles at 1 GHz),
# loom250 (250 MHz). With rdma/loom the links carry no NIC pipeline (the model has it):
# --host-ns / --fabric-ns are cable + switch traversal. Parameter sources: README.md.
import argparse, json, os

E = "/scratch/harshanavkis/loom-proj/e8-astrasim"
ap = argparse.ArgumentParser()
ap.add_argument("name"); ap.add_argument("gpus", type=int)
ap.add_argument("--gps", type=int, default=8)            # GPUs per server
ap.add_argument("--per-leaf", type=int, default=32)      # GPUs per leaf switch
ap.add_argument("--gbps", type=int, default=400)         # NIC / Loom port and fabric links
ap.add_argument("--host-ns", type=float, default=500)    # host link (fitted to 2610.01380, includes NIC pipelines)
ap.add_argument("--fabric-ns", type=float, default=200)  # leaf-spine link
ap.add_argument("--mtu", type=int, default=4096)
a = ap.parse_args()

out = os.path.join(E, "e8", "clusters", a.name)
os.makedirs(out, exist_ok=True)
n = a.gpus
leaves = (n + a.per_leaf - 1) // a.per_leaf
spines = a.per_leaf if leaves > 1 else 0
leaf0, spine0 = n, n + leaves
links = [(g, leaf0 + g // a.per_leaf, a.host_ns) for g in range(n)]
links += [(leaf0 + l, spine0 + s, a.fabric_ns) for l in range(leaves) for s in range(spines)]
switches = list(range(leaf0, leaf0 + leaves + spines))
with open(os.path.join(out, "topo.txt"), "w") as f:
    f.write(f"{n + len(switches)} {len(switches)} {len(links)}\n")
    f.write(" ".join(map(str, switches)) + "\n")
    for x, y, ns in links:
        f.write(f"{x} {y} {a.gbps}Gbps {ns / 1e6}ms 0\n")
json.dump({"logical-dims": [str(n)]}, open(os.path.join(out, "logical.json"), "w"))

base = open(os.path.join(E, "e8", "cfg", "16n_1sw.txt")).read()
base = base.replace(os.path.join(E, "e8", "topo", "16n_1sw_400g.txt"), os.path.join(out, "topo.txt"))
base = base.replace("PACKET_PAYLOAD_SIZE 1000", f"PACKET_PAYLOAD_SIZE {a.mtu}")
common = f"GPUS_PER_SERVER {a.gps}\nPCIE_GBPS 63\nPCIE_LAT_NS 380\nPCIE_RD_RTT_NS 550\nHIF_CHUNK 4096\n"
# the NIC model (e8/cfg/steve_nic/base.txt: every latency from single-message measurements on steve)
nic = ("HOST_IF_MODE nic\nWIRE_BYTES_PER_PACKET 82\nNIC_POSTER gpu\nNIC_SQ_MEM gpu\nNIC_BUF_MEM gpu\nNIC_CQ_MEM gpu\n"
       "NIC_RX_MEM gpu\nPCIE_MRRS 4096\nWQE_BYTES 64\nWQE_FETCH_MAX 64\nPCIE_LINK_GBPS 57.6\nPCIE_RD_HOST_NS 670\n"
       "PCIE_RD_GPU_NS 1350\nPCIE_DB_HOST_NS 280\nPCIE_WR_HOST_NS 280\nPCIE_DB_GPU_NS 645\nPCIE_WR_GPU_NS 645\n"
       "RX_POLL_NS 0\nCQE_POLL_NS 0\n")
loom = "NIC_PUSH 1\nNIC_BF 1\nINLINE_MAX 1000000000\n"
variants = {
    "none": "",
    "pull": "HOST_IF_MODE pull\nPOST_NS 700\n",
    "pull_deepep": "HOST_IF_MODE pull\nPOST_NS 3070\n",
    "pull_nvshmem": "HOST_IF_MODE pull\nPOST_NS 7330\n",
    "push": "HOST_IF_MODE push\n",
    "rdma": nic + "NIC_BF 0\nINLINE_MAX 0\nNIC_TX_NS 260\nNIC_RX_NS 590\n"
            "STAGE_COPY 350 2400 524288\n",   # staging copy before each post (owner 2026-10-22; LoomNet.hh)
    "loom": nic + loom + "NIC_TX_NS 281\nNIC_RX_NS 597\n",   # 21 / 7 cycles (RTL, 1 ns) + NIC stack 260 / 590 ns
    "loom250": nic + loom + "NIC_TX_NS 84\nNIC_RX_NS 28\n",
}
for v, extra in variants.items():
    with open(os.path.join(out, f"{v}.txt"), "w") as f:
        f.write(base + "\n" + common + extra)
print(f"{out}: {n} GPUs, {n // a.gps} servers, {leaves} leaves, {spines} spines, {a.gbps}G, mtu {a.mtu}")
