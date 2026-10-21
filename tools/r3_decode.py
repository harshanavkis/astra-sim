# R3: DeepSeek-V3 decode step, RDMA vs Loom, from DeepSeek's own profile (deepseek-ai/
# profile-data decode.json: H800, EP128, 128 requests per GPU as two micro-batches of 64,
# compute and all-to-all overlapped) plus R1's simulated dispatch/combine at EP128.
#  A (no micro-batch overlap, one batch of 128 tokens per GPU): step = the trace's compute
#    (GPU busy time minus the dispatch/combine kernels) + MOE_LAYERS x (dispatch + combine)
#    latency at 128 tokens from R1.
#  B (DeepSeek's overlap): the trace shows the GPU busy ~96% of the step, i.e. the network
#    is hidden; only the communication kernels' own GPU time is on the critical path.
#    Loom removes the posting from those kernels; per-message posting time is taken from
#    steve's dispatch_bd send loops (remote - local, ordered, 128 tokens). An estimate.
# Writes results/r3_decode.tsv.
#   python -I r3_decode.py [decode.json]
import csv, json, os, sys

E = "/scratch/harshanavkis/loom-proj/e8-astrasim"
TRACE = sys.argv[1] if len(sys.argv) > 1 else "/scratch/harshanavkis/loom-proj/deepseek-profile/decode.json"
MOE_LAYERS = 58                # DeepSeek-V3: 61 layers, the first 3 dense
EP, TOK = 128, 128
# steve dispatch_bd t3 (2026-10-08), ordered, 128 tokens = 683 messages: send loop end (us)
POST_US_PER_MSG = {"dispatch": (21.2 - 9.2) / 683, "combine": (32.9 - 24.8) / 683}
MSGS_PER_CALL = 64 * 8         # one micro-batch: 64 tokens x top-8

k = sorted([e for e in json.load(open(TRACE))["traceEvents"]
            if e.get("ph") == "X" and e.get("cat") == "kernel" and e["args"].get("stream") == 7], key=lambda e: e["ts"])
mla = [e for e in k if "mla_kernel" in e["name"] and "combine" not in e["name"]]
s, t = mla[0]["ts"], mla[-1]["ts"]
steady = [e for e in k if s <= e["ts"] <= t]
span = t - s
busy = sum(e["dur"] for e in steady)
is_comm = lambda e: "dispatch_ll" in e["name"] or "combine_ll" in e["name"]
comm_k = sum(e["dur"] for e in steady if is_comm(e))
calls = {op: sum(1 for e in steady if f"{op}_ll" in e["name"]) for op in ("dispatch", "combine")}
layers = len(mla) / 2                      # two micro-batches per layer
scale = 61 / layers                        # steady region -> whole step
compute = (busy - comm_k) * scale

r1 = {}
for row in csv.DictReader(open(os.path.join(E, "e8", "r1", "jobs.txt.tsv")), delimiter="\t"):
    _, op, ep, tok, gran, var = row["name"].split("__")
    if row["mean_us"]:
        r1[(op, int(ep[2:]), int(tok[1:]), gran, var)] = float(row["mean_us"])

rows = []
for var in ("deepep_flush", "deepep_ordered", "minimal_ordered", "loom"):
    d, c = r1.get(("dispatch", EP, TOK, "token", var)), r1.get(("combine", EP, TOK, "token", var))
    if d is None or c is None:
        continue
    rows.append(("A no overlap", var, compute / 1000, MOE_LAYERS * (d + c) / 1000, (compute + MOE_LAYERS * (d + c)) / 1000))
removed = sum(calls[op] * MSGS_PER_CALL * POST_US_PER_MSG[op] for op in calls) * scale
rows.append(("B DeepSeek overlap", "deepep (measured)", (span - comm_k) * scale / 1000, comm_k * scale / 1000, span * scale / 1000))
rows.append(("B DeepSeek overlap", "loom (estimate)", (span - comm_k) * scale / 1000, (comm_k * scale - removed) / 1000,
             (span * scale - removed) / 1000))
out = os.path.join(E, "results", "r3_decode.tsv")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w") as f:
    f.write(f"# trace steady region: {span:.0f} us, {layers:.0f} layers, GPU busy {busy / span * 100:.1f}%, comm kernels {comm_k / span * 100:.1f}%\n")
    f.write("regime\tvariant\tcompute_ms\tcomm_ms\tstep_ms\n")
    for r in rows:
        f.write(f"{r[0]}\t{r[1]}\t{r[2]:.2f}\t{r[3]:.2f}\t{r[4]:.2f}\n")
print(open(out).read())
