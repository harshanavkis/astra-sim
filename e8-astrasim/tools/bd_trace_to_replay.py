#!/usr/bin/env python3
"""dispatch_bd traces (steve: ~/loom-experiments/gpu-posted/bd_trace, run_bd_trace.sh) -> LoomReplay
run files, plus what was measured.

Each traced run gives, per message, its destination slot (r, s), the posting warp, the post stamp and
the arrival stamp (receiver), and per CTA its loop end; the CSV row gives the run's signal, drain and
seen times. The QP and doorbell of each message follow dispatch_bd.cu / DeepEP V1's post path:
  ordered (--qp dest --nq 3): QP r*3 + s%3, message index s//3 on that QP; one signal (atomic) per QP
      (24) posted at the measured signal time.
  flush (--qp warp): QP warp % 24, message index = the warp's own count; every CTA rings every QP at
      its loop end and waits for the completions; then 8 signals (QPs 0..7), posted the measured
      signal - drain time after the drain ends.
  doorbell: a message rings its QP when (index + 1) % 4 == 0 (kNumRequestInBatch = 4); signals always.
Traces of the trace build (dispatch_bd_ring, bd_trace_ring/) also log every doorbell rung (QP, producer
index, time); then the run file carries them ("ring" / "atomic" lines) and LoomReplay uses those instead
of the rules above (the flush path's CTA doorbells wait on DeepEP's per-QP post lock, measured 2-10 us
after the CTA's loop end). A QP's WQEs of the run go in post order (data, then its signal); a WQE is
written no later than the first doorbell that covers it (a put's stamp comes after its own doorbell).

Local runs (the GPU's own memory, TMA stores) become push runs for the Loom what-if: each store goes
out as soon as it is issued (one stream per destination), the 8 signals are plain writes behind each
destination's data, at the measured signal time.

  bd_trace_to_replay.py <bd_trace dir> <out dir>
writes <out>/runs/<config>_r<k>_t<T>.run, <out>/runs/<config>_r<k>_t<T>.meas (id post arr, ns) and
<out>/measured.tsv (one row per run, us)."""
import csv, os, re, sys

NQP_WARP, NQ = 24, 3
SIG_FLUSH = list(range(8))


def blocks(err):
    out, cur = [], None
    for line in open(err, errors="replace"):
        f = line.split()
        if not f:
            continue
        if f[0] == "cta" and f[1] == "0" and f[2] == "start":
            cur = {"cta": [], "msg": [], "qpmap": {}, "ring": []}
            out.append(cur)
        if cur is None:
            continue
        if f[0] == "cta" and len(f) == 10:
            cur["cta"].append(float(f[5]))  # loop end
        elif f[0] == "qpmap":
            cur["qpmap"][int(f[2])] = int(f[1])  # qpn -> QP index
        elif f[0] == "ring":
            cur["ring"].append((int(f[2]), int(f[4]), float(f[6])))  # qpn, upto, us
        elif f[0] == "msg":
            m = re.match(r"msg r(\d+) s(\d+) warp (\d+) post ([\d.]+) arr ([\d.]+)", line.strip())
            if m:
                r, s, w = int(m[1]), int(m[2]), int(m[3])
                cur["msg"].append((r, s, w, float(m[4]), float(m[5])))
    return out


def rows(csvf):
    data = [r for r in csv.reader(open(csvf)) if r and not r[0].startswith(("#", "WARN"))]
    hdr = data[0]
    return [dict(zip(hdr, r)) for r in data[1:] if len(r) == len(hdr)]


def ns(us):
    return int(round(float(us) * 1000))


def main():
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(os.path.join(out, "runs"), exist_ok=True)
    tsv = open(os.path.join(out, "measured.tsv"), "w")
    cols = ["msgs", "post_last_us", "arr_first_us", "arr_last_us", "drain_end_us", "signal_us", "seen_us", "reaped_us"]
    tsv.write("config\top\tpath\treap\trun\ttokens\t" + "\t".join(cols) + "\n")
    for cfg in sorted(os.listdir(src)):
        d = os.path.join(src, cfg)
        if not os.path.isdir(d):
            continue
        op = cfg.split("_")[0]
        path = "flush" if "flush" in cfg else "local" if "local" in cfg else "ordered"
        reap = "reap" in cfg
        H = 7168 if op == "dispatch" else 14336
        for f in sorted(os.listdir(d)):
            if not f.endswith(".csv"):
                continue
            k = int(f[3:-4])
            rs, bs = rows(os.path.join(d, f)), blocks(os.path.join(d, f[:-4] + ".err"))
            if len(rs) != len(bs):
                print(f"skip {cfg}/{f}: {len(rs)} rows, {len(bs)} traces", file=sys.stderr)
                continue
            for row, b in zip(rs, bs):
                T, M = int(row["tokens"]), int(row["msgs"])
                if len(b["msg"]) != M:
                    print(f"skip {cfg}/{f} T={T}: {len(b['msg'])} of {M} messages", file=sys.stderr)
                    continue
                name = f"{cfg}_r{k}_t{T}"
                msgs = []  # id, post_ns, qp, ring, arr_ns
                if path == "local":
                    for i, (r, s, w, post, arr) in enumerate(b["msg"]):
                        msgs.append((i, ns(post), r, True, ns(arr)))
                    nqp, sig_t, sig_q = 8, ns(row["signal_us"]), list(range(8))
                elif path == "ordered":
                    for i, (r, s, w, post, arr) in enumerate(b["msg"]):
                        idx = s // NQ
                        msgs.append((i, ns(post), r * NQ + s % NQ, (idx + 1) % 4 == 0, ns(arr)))
                    nqp, sig_t, sig_q = 8 * NQ, ns(row["signal_us"]), list(range(8 * NQ))
                else:
                    # the warp's own message index: dispatch (one token per warp here): lane (= r) order;
                    # combine (one message per unit, several per warp): posting order
                    byw = {}
                    for i, (r, s, w, post, arr) in enumerate(b["msg"]):
                        byw.setdefault(w, []).append(i)
                    idx = {}
                    for w, ids in byw.items():
                        if op == "dispatch":
                            assert len({b["msg"][i][0] for i in ids}) == len(ids), "one token per warp expected"
                            ids.sort(key=lambda i: b["msg"][i][0])
                        else:
                            ids.sort(key=lambda i: b["msg"][i][3])
                        for j, i in enumerate(ids):
                            idx[i] = j
                    for i, (r, s, w, post, arr) in enumerate(b["msg"]):
                        msgs.append((i, ns(post), w % NQP_WARP, (idx[i] + 1) % 4 == 0, ns(arr)))
                    nqp, sig_q = NQP_WARP, SIG_FLUSH
                    sig_t = ns(row["signal_us"]) - ns(row["drain_end_us"])
                rings, atoms = [], []
                if b["ring"]:  # measured doorbells
                    sigs = {q: i for i, q in enumerate(sig_q)}
                    data = {}
                    for i, post, q, ring, arr in sorted(msgs, key=lambda m: m[1]):
                        data.setdefault(q, []).append(i)
                    per = {}
                    for qpn, upto, t in b["ring"]:
                        per.setdefault(b["qpmap"][qpn], []).append((ns(t), upto))
                    wtime = {}  # WQE id -> written no later than the first doorbell covering it
                    post_of = {i: post for i, post, q, ring, arr in msgs}
                    for q, rl in per.items():
                        nd = len(data.get(q, []))
                        total = nd + (q in sigs)
                        base = max(u for t, u in rl) - total
                        for t, u in sorted(rl):
                            c = u - base
                            assert 1 <= c <= total, (name, q, c, total)
                            rings.append((q, t, c))
                            for j in range(c):
                                if j < nd:
                                    i = data[q][j]
                                    wtime[i] = min(wtime.get(i, post_of[i]), t)
                                else:
                                    wtime[("sig", q)] = min(wtime.get(("sig", q), t), t)
                    msgs = [(i, min(post, wtime.get(i, post)), q, ring, arr) for i, post, q, ring, arr in msgs]
                    for q, i in sigs.items():
                        if ("sig", q) in wtime:
                            atoms.append((q, wtime[("sig", q)], i))
                with open(os.path.join(out, "runs", name + ".run"), "w") as rf:
                    rf.write(f"path {'ordered' if path == 'local' else path}\nnodes 0 1\nnqp {nqp}\nreap {int(reap)}\n")
                    if path == "local":
                        rf.write("sigkind write\n")
                    rf.write("signal " + str(sig_t) + " " + " ".join(map(str, sig_q)) + "\n")
                    for i, post, q, ring, arr in msgs:
                        rf.write(f"msg {i} {post} {q} {H} {int(ring)}\n")
                    if path == "flush":
                        for t in b["cta"]:
                            rf.write(f"cta {ns(t)}\n")
                        rf.write(f"drain {ns(row['drain_end_us'])}\n")
                    for q, t, i in atoms:
                        rf.write(f"atomic {q} {t} {i}\n")
                    for q, t, c in rings:
                        rf.write(f"ring {q} {t} {c}\n")
                with open(os.path.join(out, "runs", name + ".meas"), "w") as mf:
                    for i, post, q, ring, arr in msgs:
                        mf.write(f"{i} {post} {arr}\n")
                tsv.write(f"{cfg}\t{op}\t{path}\t{int(reap)}\t{k}\t{T}\t" +
                          "\t".join(row.get(c, "") or "" for c in cols) + "\n")
    tsv.close()


if __name__ == "__main__":
    main()
