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
    d = {(r["app"], r["ranks"], r["system"]): int(r["wall_cycles"]) for r in rows}
    apps = sorted({(r["app"], int(r["ranks"])) for r in rows})
    parts = []
    for app, ranks in apps:
        key = (app, str(ranks))
        if (*key, "loom") in d and (*key, "b1_gpu_rdma") in d:
            g = gain(d[(*key, "b1_gpu_rdma")], d[(*key, "loom")])
            parts.append(f"{app} {ranks} ranks **{g:+.2f}%**")
    return [f"- {label} (`{csv_name}`): " + "; ".join(parts) + " vs B1."]


def matrix_lines(csv_name="matrix.csv", label="Matrix"):
    rows = read(csv_name)
    if not rows:
        return []
    cells = collections.defaultdict(dict)
    for r in rows:
        cells[(r["topology"], r["collective"], r["size_mb"])][r["system"]] = \
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
    # vs the other baselines
    for other, name in (("b2_cpu_proxy", "B2"), ("b3_ideal", "B3")):
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
    return [f"- Regime map (`regime_map.csv`): **{lo['gain_pct']}%** at "
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
    return [f"- Break-even t_pipe (`sweep_tpipe.csv`): **{breakeven:.0f} ns** "
            f"(linear, {slope:.0f} cycles/ns)."]


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


def build():
    out = ["## 5. Results (GENERATED by summarize_results.py from",
           "## results/*.csv - do not hand-edit inside the markers)", ""]
    for fn in (smoke_lines, credits_lines, tpipe_lines, regime_lines):
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
