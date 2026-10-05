#!/usr/bin/env python3
"""Supplementary revision statistics: block-bootstrap CIs for HTAF and the
BIKE variance share, block-size sensitivity, and tail-event rates per session.
Writes revision_stats_extra.json next to this script."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from revision_analysis import A, B, B2, MODES, load

OUT = Path(__file__).resolve().parent / "revision_stats_extra.json"
RNG = np.random.default_rng(7)


def block_idx(n, block, reps):
    nb = math.ceil(n / block)
    starts = RNG.integers(0, n - block, size=(reps, nb))
    return (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(reps, -1)[:, :n]


def cv(x):
    return x.std(ddof=1) / x.mean()


def htaf_ci(data, block, reps=1000):
    idx = {m: block_idx(len(x), block, reps) for m, x in data.items()}
    vals = []
    for r in range(reps):
        c = {m: cv(data[m][idx[m][r]]) for m in MODES}
        vals.append(c["hybrid"] / max(c["mlkem"], c["bike"]))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def legs_ci(path, block, reps=1000):
    import csv
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    m = np.array([float(r["mlkem_ns"]) for r in rows])
    b = np.array([float(r["bike_ns"]) for r in rows])
    k = np.array([float(r["hkdf_ns"]) for r in rows])
    vals = []
    for i in block_idx(len(m), block, reps):
        t = m[i] + b[i] + k[i]
        vals.append(np.cov(b[i], t)[0, 1] / t.var(ddof=1))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def tail_rates(x):
    med = np.median(x)
    return {"gt10x": float(np.mean(x > 10 * med)), "gt2x": float(np.mean(x > 2 * med))}


def main():
    res = {}
    for tag, base, suf in (("A", A, ""), ("B", B, "_perf"), ("B2", B2, "")):
        data = {m: load(base / f"{m}_fixed{suf}.csv") for m in MODES}
        res[f"{tag}_fixed_htaf_block_ci"] = {str(bl): htaf_ci(data, bl) for bl in (500, 2000)}
        res[f"{tag}_fixed_tail_rates"] = {m: tail_rates(x) for m, x in data.items()}
        res[f"{tag}_legs_bike_share_block_ci"] = {str(bl): legs_ci(base / "hybrid_legs.csv", bl) for bl in (200, 1000)}
        runs = {}
        for i in range(1, 6):
            runs[f"run{i}"] = {m: tail_rates(load(base / "stability" / f"{m}_run{i}.csv")) for m in MODES}
        res[f"{tag}_stability_tail_rates"] = runs
    kg = A / "keygen_isolation_perf"
    res["A_keygen_htaf_block_ci"] = {}
    for proto, suf in (("legacy", "_legacy"), ("corrected", ""), ("cooled", "_cool")):
        data = {m: load(kg / f"{m}_varying_key{suf}.csv") for m in MODES}
        res["A_keygen_htaf_block_ci"][proto] = {str(bl): htaf_ci(data, bl) for bl in (500, 2000)}
    OUT.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
