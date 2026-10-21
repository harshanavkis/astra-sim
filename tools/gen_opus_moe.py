#!/usr/bin/env python3
"""DeepSeek-V3-style MoE training traces from Opus's generator (SIGCOMM artifact, MIT; opus-ref/Opus,
simulation/reconfig_backend/examples/large_scale_ep_sweeps{,_scaleout}/sweep_ep.py, generate_workload).

Opus's own workload (MLA attention, 256 experts top-8, expert FFN 2048, d 7168; standard EP: every GPU holds its
own tokens; per layer TP all-reduce, EP all-to-all dispatch/combine, DP all-gather/reduce-scatter of the attention
and expert weights; PP send/recv; compute = FLOPs / (989 TFLOPS x 0.8) as fixed durations). We take its
electrical-switch variant ("eps": no reconfiguration attributes) and its plain all-to-all ("all_to_all", uniform
routing: same bytes per GPU as its top-k all_to_allv, split evenly), so ASTRA-sim + ns-3 run it unchanged.
Placements as Opus Fig. 14: "mixed" = EP+TP+DP (EP groups are consecutive ranks: inside a server, then
spilling over servers), "scaleout" = EP+DP (an EP group = one rail across servers, all of its all-to-all crosses).
Run with a system config WITHOUT the roofline (fixed durations; e8/cfg/system_nccl.json).

  gen_opus_moe.py <out dir> placement=mixed|scaleout ep=E [total=64] [pp=1] [mb=4] [gbs=256] [lps=2] [seq=4096]
Writes <out dir>/workload/workload.<rank>.et, comm_group.json, workload_meta.json.
"""
import sys
from pathlib import Path

OPUS = Path("/scratch/harshanavkis/loom-proj/opus-ref/Opus/simulation/reconfig_backend")
sys.path.insert(0, str(OPUS))

a = dict(kv.split("=", 1) for kv in sys.argv[2:])
out = Path(sys.argv[1])
if a.get("placement", "mixed") == "scaleout":
    from examples.large_scale_ep_sweeps_scaleout import sweep_ep as so
    gen = so.base           # the scale-out module patches the base module's groups/validation in place
else:
    from examples.large_scale_ep_sweeps import sweep_ep as gen

cfg = {"total_gpus": int(a.get("total", 64)), "gpus_per_node": 8, "pp": int(a.get("pp", 1)),
       "microbatches": int(a.get("mb", 4)), "global_batch_size": int(a.get("gbs", 256)),
       "layers_per_stage": int(a.get("lps", 2)), "seq_len": int(a.get("seq", 4096)),
       "ep_comm_pattern": "all_to_all", "moe_routing": "uniform", "ep_sizes": [int(a["ep"])],
       "scale_out_Gbps": 400.0, "sweep_variants": ["eps"]}
# load_config's defaults (DeepSeek-V3 shape, 989 TFLOPS x 0.8, ...) without reading a file
p = out / "opus_cfg.json"; out.mkdir(parents=True, exist_ok=True)
import json; p.write_text(json.dumps(cfg, indent=1))
cfg = gen.load_config(p)
err = gen.validate_config(cfg)
if err:
    sys.exit("\n".join(err))
gen.generate_workload(out, cfg, int(a["ep"]), "eps")

# Opus numbers comm groups from 0; our ASTRA-sim reads pg "0" as "all ranks" (Workload.cc extract_comm_group),
# so shift every group id by one, in comm_group.json and in every node's pg_name.
from google.protobuf.internal.decoder import _DecodeVarint32
from google.protobuf.internal.encoder import _VarintBytes
sys.path.insert(0, "/scratch/harshanavkis/loom-proj/opus-ref/Opus/simulation/symbolic_tensor_graph/symbolic_tensor_graph/"
                   "chakra/backends/chakra_00_4_backend/et_def")
import et_def_pb2 as pb
cg = out / "comm_group.json"
cg.write_text(json.dumps({str(int(k) + 1): v for k, v in json.loads(cg.read_text()).items()}))
for et in sorted((out / "workload").glob("workload.*.et")):
    b, i, msgs = et.read_bytes(), 0, []
    while i < len(b):
        n, i = _DecodeVarint32(b, i); msgs.append(b[i:i + n]); i += n
    res = [_VarintBytes(len(msgs[0])) + msgs[0]]
    for raw in msgs[1:]:
        nd = pb.Node(); nd.ParseFromString(raw)
        for at in nd.attr:
            if at.name == "pg_name":
                at.string_val = str(int(at.string_val) + 1)
        r = nd.SerializeToString(); res.append(_VarintBytes(len(r)) + r)
    et.write_bytes(b"".join(res))
s = gen.WorkloadShape(cfg, int(a["ep"]))
print(f"{out}: {cfg['total_gpus']} GPUs pp {cfg['pp']} ep {a['ep']} ({a.get('placement', 'mixed')}), "
      f"local tokens {s.local_seq}, all-to-all {s.comm_size / 2**20:.1f} MiB per GPU, layers {s.total_layers}, "
      f"attn {s.attn_compute_us} us, expert {s.expert_compute_us} us, expert grads {s.expert_grad_size / 2**20:.0f} MiB")
