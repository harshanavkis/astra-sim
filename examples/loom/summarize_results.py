#!/usr/bin/env python3
"""Generate the CHECKPOINT results section from results/*.csv.

Every result number in the docs is derived here and nowhere else. The docs
used to quote numbers by hand, and they drifted: mixtral-64, the break-even
t_pipe, the regime map and the worst matrix cell were all wrong in
README/CODE-MAP while CHECKPOINT was right (HANDOFF section 3.2). Prose
about WHY a number matters stays hand-written; the numbers themselves are
regenerated.

Usage:
    python3 examples/loom/summarize_results.py            # print to stdout
    python3 examples/loom/summarize_results.py --write    # splice into
                                                          # CHECKPOINT.md

--write replaces whatever sits between the marker lines

    <!-- BEGIN GENERATED RESULTS -->
    <!-- END GENERATED RESULTS -->

and leaves the rest of the file untouched.
"""
import argparse
import collections
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
BEGIN = "<!-- BEGIN GENERATED RESULTS -->"
END = "<!-- END GENERATED RESULTS -->"


def read(name):
    path = os.path.join(RES, name)
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return list(csv.DictReader(fh))


def gain(base, new):
    """Percent improvement of `new` over `base` (positive = new is faster)."""
    return 100.0 * (base - new) / base


def apps_lines(csv_name="apps.csv", label="Apps"):
    rows = read(csv_name)
    if not rows:
        return []
    d = {(r["app"], r["ranks"], r["system"]): (int(r["wall_cycles"]),
                                               int(r["exposed_comm"])) for r in rows}
    apps = sorted({(r["app"], int(r["ranks"])) for r in rows})
    parts, table = [], []
    for app, ranks in apps:
        key = (app, str(ranks))
        if (*key, "loom") not in d or (*key, "b1_gpu_rdma") not in d:
            continue
        lw, le = d[(*key, "loom")]
        bw, be = d[(*key, "b1_gpu_rdma")]
        g = gain(bw, lw)
        parts.append(f"{app} {ranks} ranks **{g:+.2f}%**")
        # split the gain: communication time vs (wall - comm) compute time
        table.append(f"| {app} | {ranks} | {100*be/bw:.1f}% | "
                     f"{gain(be, le):+.1f}% | {gain(bw-be, lw-le):+.1f}% | "
                     f"**{g:+.2f}%** |")
    out = [f"- {label} (`{csv_name}`): " + "; ".join(parts) + " vs B1."]
    if table:
        out += ["", f"  Gain decomposition ({csv_name}) - the compute column is",
                "  SM reclamation, structurally capped at "
                f"{100*(1-839/989):.1f}% (= 1 - 839/989, the 20/132",
                "  SM reservation); the comm column is per-operation initiation,",
                "  which amortizes away on large messages:", "",
                "| app | ranks | exposed comm | comm gain | compute gain | wall gain |",
                "|---|---|---|---|---|---|"] + table + [""]
    return out


def matrix_lines(csv_name="matrix.csv", label="Matrix"):
    rows = read(csv_name)
    if not rows:
        return []
    cells = collections.defaultdict(dict)
    for r in rows:
        cells[(r["cluster"], r["collective"], r["size_mb"])][r["system"]] = \
            int(r["wall_cycles"])
    per_size = collections.defaultdict(list)
    negatives = []
    for key, sysmap in cells.items():
        if "loom" not in sysmap or "b1_gpu_rdma" not in sysmap:
            continue
        g = gain(sysmap["b1_gpu_rdma"], sysmap["loom"])
        per_size[key[2]].append(g)
        if g < 0:
            negatives.append((g, key))
    out = []
    spans = ", ".join(
        f"{min(per_size[s]):+.1f}...{max(per_size[s]):+.1f}% @{s} MB"
        for s in sorted(per_size, key=int))
    out.append(f"- {label} (`{csv_name}`, {len(cells)} Loom-vs-B1 cells): {spans}.")
    if negatives:
        worst_g, worst_k = sorted(negatives)[0]
        by_coll = collections.Counter(k[1] for _, k in negatives)
        breakdown = ", ".join(f"{n}x {c}" for c, n in sorted(by_coll.items()))
        out.append(
            f"  {len(negatives)} negative cells ({breakdown}); worst "
            f"**{worst_g:.2f}%** ({worst_k[0]} {worst_k[1]} {worst_k[2]} MB).")
    else:
        out.append("  No negative cells.")
    # Exact ties are NOT wins - they are cells where the model cannot
    # distinguish the systems at all, and reporting them inside a positive
    # range would repeat, in the opposite direction, the mistake the
    # negative cells caused. Call them out explicitly.
    ties = [k for k, v in cells.items()
            if "loom" in v and "b1_gpu_rdma" in v
            and abs(gain(v["b1_gpu_rdma"], v["loom"])) < 0.001]
    if ties:
        listed = ", ".join(f"{k[0]} {k[1]} {k[2]} MB" for k in sorted(ties))
        out.append(
            f"  {len(ties)} cells are EXACTLY identical (+0.000%), carrying no "
            f"information rather than showing a win: {listed}. At these sizes "
            f"the model hides dim1 latency for both systems (chunk overlap, "
            f"see 5a) and dim0 is identical by construction, so nothing CAN "
            f"differ. Do not cite them in either direction.")
    # vs the other baselines
    for other, name in (("b2_cpu_proxy", "B2"),):
        gs = [gain(v[other], v["loom"]) for v in cells.values()
              if other in v and "loom" in v]
        if not gs:
            continue
        if min(gs) > 0:
            out.append(f"  vs {name}: Loom wins all {len(gs)} cells "
                       f"({min(gs):+.1f}...{max(gs):+.1f}%).")
        else:
            off = [-g for g in gs]
            out.append(f"  vs {name}: {min(off):+.1f}...{max(off):+.1f}% off "
                       f"{name} across all {len(gs)} cells.")
    return out


def regime_lines():
    rows = read("regime_map.csv")
    if not rows:
        return []
    lo, hi = rows[0], rows[-1]
    neg = [r for r in rows if float(r["gain_pct"]) < 0]
    return ["- Regime map (`regime_map.csv`) — STANDALONE, not in the default "
            "suite; runs `--pipe-ns 500` so its Loom is NOT the Loom of the "
            "other experiments (see 5a.5). Rerun it before quoting:",
            f"  **{lo['gain_pct']}%** at "
            f"{lo['loom_exposed_comm_pct']}% exposed comm -> "
            f"**{hi['gain_pct']}%** at {hi['loom_exposed_comm_pct']}%. "
            f"{'No negative point.' if not neg else str(len(neg)) + ' negative points.'}"]


def tpipe_lines():
    rows = read("sweep_tpipe.csv")
    if not rows:
        return []
    loom = sorted(((float(r["t_pipe_ns"]), int(r["wall_cycles"]))
                   for r in rows if r["system"] == "loom"))
    b1 = [int(r["wall_cycles"]) for r in rows if r["system"] == "b1_gpu_rdma"]
    if not loom or not b1:
        return []
    target = b1[0]
    slope = ((loom[-1][1] - loom[0][1]) / (loom[-1][0] - loom[0][0])
             if loom[-1][0] != loom[0][0] else 0)
    breakeven = None
    for (t0, w0), (t1, w1) in zip(loom, loom[1:]):
        if w0 <= target <= w1:
            breakeven = t0 + (target - w0) * (t1 - t0) / (w1 - w0)
            break
    if breakeven is None:
        return [f"- Break-even t_pipe (`sweep_tpipe.csv`): outside the swept "
                f"range {loom[0][0]:.0f}-{loom[-1][0]:.0f} ns."]
    return [f"- Break-even t_pipe (`sweep_tpipe.csv`) — STANDALONE, not in the "
            f"default suite (optional reviewer-proofing; T3 will measure "
            f"t_pipe): **{breakeven:.0f} ns** (linear, {slope:.0f} cycles/ns). "
            f"Its durable use is showing the design tolerates a slow FPGA "
            f"clock."]


def credits_lines():
    rows = read("sweep_credits.csv")
    if not rows:
        return []
    pts = sorted((int(r["read_credits"]), int(r["wall_cycles"])) for r in rows)
    base = pts[0][1]
    finite = [(c, w) for c, w in pts if c <= 64]
    linear = all(abs(w - base / c) <= 1 for c, w in finite)
    inf = [w for c, w in pts if c > 1024]
    tail = ""
    if inf:
        capped64 = [w for c, w in pts if c == 64]
        same = capped64 and capped64[0] == inf[0]
        tail = (f" Uncapped row present and {'equal to' if same else 'differs from'}"
                f" the 64-credit row.")
    return [f"- Read credits (`sweep_credits.csv`, caps {pts[0][0]}-{pts[-1][0]}): "
            f"{'exact linear 1/N scaling' if linear else 'NON-linear scaling'}"
            f" from {base} cycles.{tail}"]


def smoke_lines():
    rows = read("smoke.csv")
    if not rows:
        return []
    d = {r["system"]: int(r["wall_cycles"]) for r in rows}
    order = " < ".join(f"{k} {v}" for k, v in sorted(d.items(), key=lambda kv: kv[1]))
    line = f"- Smoke (`smoke.csv`, 4-NPU 1 MB all-to-all): {order}."
    if "loom" in d and "b1_gpu_rdma" in d:
        g = gain(d["b1_gpu_rdma"], d["loom"])
        line += f" Loom vs B1 **{g:+.2f}%**."
    return [line]


def p2p_lines():
    rows = read("p2p_sweep.csv")
    if not rows:
        return []
    d = collections.defaultdict(dict)
    for r in rows:
        d[(r["route"], int(r["size_kb"]))][r["system"]] = int(r["wall_cycles"])
    out = ["- P2P sweep (`p2p_sweep.csv`, M2) - one send/recv pair, the only "
           "experiment with no collective chunk-overlap to hide per-operation "
           "cost, hence the cleanest read on the constant the headline depends "
           "on:", "",
           "| route | size | Loom vs B1 | Loom vs B2 |", "|---|---|---|---|"]
    for route, size in sorted(d):
        v = d[(route, size)]
        if "loom" not in v:
            continue
        label = f"{size} KB" if size < 1024 else f"{size // 1024} MB"
        cells = [f"{gain(v[b], v['loom']):+.1f}%" if b in v else "-"
                 for b in ("b1_gpu_rdma", "b2_cpu_proxy")]
        out.append(f"| {route} | {label} | {cells[0]} | {cells[1]} |")
    # crossover: largest size where Loom still beats B1 cross-rack
    cross = sorted((s, v) for (r, s), v in d.items() if r == "cross_rack")
    wins = [s for s, v in cross
            if "b1_gpu_rdma" in v and gain(v["b1_gpu_rdma"], v["loom"]) > 0]
    if wins:
        big = max(wins)
        out += ["", f"  Cross-rack crossover: Loom leads B1 up to "
                    f"{big if big < 1024 else big // 1024}"
                    f"{' KB' if big < 1024 else ' MB'}, then converges."]
    return out + [""]


def build():
    out = ["## 5. Results (GENERATED by summarize_results.py from",
           "## results/*.csv - do not hand-edit inside the markers)", ""]
    for fn in (smoke_lines, p2p_lines, credits_lines, tpipe_lines, regime_lines):
        out += fn()
    out += matrix_lines()
    out += apps_lines()
    direct = matrix_lines("matrix_direct.csv", "Matrix F2 (direct algorithms)")
    direct += apps_lines("apps_direct.csv", "Apps F2 (direct algorithms)")
    if direct:
        out += [""] + direct
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="splice into CHECKPOINT.md between the markers")
    args = ap.parse_args()
    text = build()
    if not args.write:
        print(text)
        return
    path = os.path.join(HERE, "CHECKPOINT.md")
    with open(path) as fh:
        doc = fh.read()
    if BEGIN not in doc or END not in doc:
        sys.exit(f"markers {BEGIN} / {END} not found in {path}")
    head, rest = doc.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    with open(path, "w") as fh:
        fh.write(head + BEGIN + "\n" + text + "\n" + END + tail)
    print(f"spliced {len(text.splitlines())} lines into {path}")


if __name__ == "__main__":
    main()
