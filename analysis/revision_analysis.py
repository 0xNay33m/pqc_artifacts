#!/usr/bin/env python3
"""Re-analysis of the raw timing traces for the IEEE Access revision.

Adds robust dispersion (IQR, MAD), autocorrelation-aware block-bootstrap CIs,
exact/log-scale p-values, covariance-aware per-leg variance attribution,
instrumentation-effect checks, distribution-level class tests, and
cross-session stability. Writes revision_stats.json next to this script.

Usage: python revision_analysis.py
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / "results_sc_timing"
B = ROOT / "results_sc_timing_intel"
# Platform B full battery with the performance governor logged throughout
# (source of the per-leg, repeated-session, and two-class Platform B results).
B2 = ROOT / "results_sc_timing_intel_jun29_perf"
OUT = Path(__file__).resolve().parent / "revision_stats.json"
RNG = np.random.default_rng(20261006)
MODES = ("mlkem", "bike", "hybrid")


def load(path: Path, col: str = "elapsed_ns", cls: bool = False):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    x = np.array([float(r[col]) for r in rows])
    if cls:
        return x, np.array([int(r["class"]) for r in rows])
    return x


def lag1(x):
    x = x - x.mean()
    return float(np.dot(x[:-1], x[1:]) / np.dot(x, x))


def block_boot(x, fn, block=500, reps=1000):
    n = len(x)
    nb = math.ceil(n / block)
    starts = RNG.integers(0, n - block, size=(reps, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(reps, -1)[:, :n]
    vals = np.array([fn(x[i]) for i in idx])
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def cv(x):
    return float(x.std(ddof=1) / x.mean())


def rcv_mad(x):
    med = np.median(x)
    return float(1.4826 * np.median(np.abs(x - med)) / med)


def iqr_rel(x):
    q1, q3 = np.percentile(x, [25, 75])
    return float((q3 - q1) / np.median(x))


def describe(x, boot=True):
    med = float(np.median(x))
    p95, p99, p999 = np.percentile(x, [95, 99, 99.9])
    d = {
        "n": int(len(x)),
        "median_us": med / 1e3,
        "mean_us": float(x.mean()) / 1e3,
        "cv": cv(x),
        "iqr_us": float(np.subtract(*np.percentile(x, [75, 25]))) / 1e3,
        "iqr_rel": iqr_rel(x),
        "mad_rcv": rcv_mad(x),
        "p95_us": float(p95) / 1e3,
        "p99_us": float(p99) / 1e3,
        "p999_us": float(p999) / 1e3,
        "p99_over_med": float(p99 / med),
        "frac_gt_10x_median": float(np.mean(x > 10 * med)),
        "lag1_autocorr": lag1(x),
    }
    if boot:
        d["cv_iid_ci"] = [float(v) for v in np.percentile(
            [cv(x[RNG.integers(0, len(x), len(x))]) for _ in range(1000)], [2.5, 97.5])]
        d["cv_block_ci"] = block_boot(x, cv)
    return d


def log10_p_mw(a, b):
    res = stats.mannwhitneyu(a, b, alternative="two-sided", method="asymptotic")
    n1, n2 = len(a), len(b)
    mu = n1 * n2 / 2
    sigma = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
    z = (res.statistic - mu) / sigma
    log10p = (stats.norm.logsf(abs(z)) + math.log(2)) / math.log(10)
    delta = 2 * res.statistic / (n1 * n2) - 1
    return {"U": float(res.statistic), "z": float(z), "log10_p": float(log10p), "cliffs_delta": float(delta)}


def ks(a, b):
    r = stats.ks_2samp(a, b, method="asymp")
    lp = math.log10(r.pvalue) if r.pvalue > 0 else None
    return {"D": float(r.statistic), "p": float(r.pvalue), "log10_p": lp}


def ratios(d):
    m, b, h = d["mlkem"], d["bike"], d["hybrid"]
    out = {}
    for key in ("cv", "iqr_rel", "mad_rcv", "p99_over_med"):
        out[f"htaf_{key}"] = h[key] / max(m[key], b[key])
    out["abs_p99_ratio"] = h["p99_us"] / max(m["p99_us"], b["p99_us"])
    out["abs_p95_ratio"] = h["p95_us"] / max(m["p95_us"], b["p95_us"])
    out["median_ratio_h_over_b"] = h["median_us"] / b["median_us"]
    out["median_ratio_b_over_m"] = b["median_us"] / m["median_us"]
    return out


def fixed_block(base: Path, suffix: str):
    data = {m: load(base / f"{m}_fixed{suffix}.csv") for m in MODES}
    desc = {m: describe(x) for m, x in data.items()}
    return data, {"describe": desc, "ratios": ratios(desc),
                  "hyb_vs_bike_mw": log10_p_mw(data["hybrid"], data["bike"]),
                  "hyb_vs_bike_ks": ks(data["hybrid"], data["bike"]),
                  "hyb_vs_mlkem_mw": log10_p_mw(data["hybrid"], data["mlkem"]),
                  "hyb_vs_mlkem_ks": ks(data["hybrid"], data["mlkem"])}


def legs_block(path: Path, blackbox: np.ndarray):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    m = np.array([float(r["mlkem_ns"]) for r in rows])
    b = np.array([float(r["bike_ns"]) for r in rows])
    k = np.array([float(r["hkdf_ns"]) for r in rows])
    t = np.array([float(r["total_ns"]) for r in rows])
    s = m + b + k

    def shares(idx):
        mm, bb, kk = m[idx], b[idx], k[idx]
        tot = mm + bb + kk
        vt = tot.var(ddof=1)
        return {
            "bike_cov_share": float(np.cov(bb, tot)[0, 1] / vt),
            "mlkem_cov_share": float(np.cov(mm, tot)[0, 1] / vt),
            "hkdf_cov_share": float(np.cov(kk, tot)[0, 1] / vt),
            "bike_var_only_share": float(bb.var(ddof=1) / vt),
        }

    full = shares(np.arange(len(m)))
    boots = [shares(RNG.integers(0, len(m), len(m))) for _ in range(1000)]
    ci = {key: [float(np.percentile([bt[key] for bt in boots], 2.5)),
                float(np.percentile([bt[key] for bt in boots], 97.5))] for key in full}
    vt = s.var(ddof=1)
    cov_terms = 2 * (np.cov(m, b)[0, 1] + np.cov(m, k)[0, 1] + np.cov(b, k)[0, 1])
    return {
        "n": int(len(m)),
        "median_us": {"mlkem": float(np.median(m)) / 1e3, "bike": float(np.median(b)) / 1e3,
                      "hkdf": float(np.median(k)) / 1e3, "total": float(np.median(t)) / 1e3},
        "bike_median_share": float(np.median(b) / np.median(s)),
        "bike_mean_share": float(b.mean() / s.mean()),
        "shares": full,
        "shares_ci95": ci,
        "covariance_terms_frac_of_var": float(cov_terms / vt),
        "corr": {"mlkem_bike": float(np.corrcoef(m, b)[0, 1]), "mlkem_hkdf": float(np.corrcoef(m, k)[0, 1]),
                 "bike_hkdf": float(np.corrcoef(b, k)[0, 1])},
        "timer_overhead_median_us": float(np.median(t - s)) / 1e3,
        "instrumented_vs_blackbox": {
            "median_ratio": float(np.median(t) / np.median(blackbox)),
            "ks": ks(t, blackbox),
            "cv_instrumented": cv(t), "cv_blackbox": cv(blackbox),
        },
    }


def dudect_block(base: Path):
    out = {}
    for mode in MODES:
        p = base / f"{mode}_dudect.csv"
        if not p.exists():
            continue
        x, c = load(p, cls=True)
        a, b = x[c == 0], x[c == 1]
        w = stats.ttest_ind(a, b, equal_var=False)
        ca, cb = (a - a.mean()) ** 2, (b - b.mean()) ** 2
        w2 = stats.ttest_ind(ca, cb, equal_var=False)
        crops = {}
        for q in (50, 75, 90, 95, 99):
            thr = np.percentile(x, q)
            r = stats.ttest_ind(a[a <= thr], b[b <= thr], equal_var=False)
            crops[str(q)] = float(abs(r.statistic))
        out[mode] = {
            "n_per_class": [int(len(a)), int(len(b))],
            "welch_t": float(w.statistic), "welch_p": float(w.pvalue),
            "second_order_t": float(w2.statistic),
            "max_abs_t_cropped": max(crops.values()), "cropped_t": crops,
            "ks_classes": ks(a, b),
            "median_diff_ns": float(np.median(a) - np.median(b)),
        }
    return out


def stability_block(base: Path):
    runs = {}
    for i in range(1, 6):
        d = {m: describe(load(base / "stability" / f"{m}_run{i}.csv"), boot=False) for m in MODES}
        r = ratios(d)
        runs[f"run{i}"] = {"cv": {m: d[m]["cv"] for m in MODES},
                           "median_us": {m: d[m]["median_us"] for m in MODES},
                           "htaf_cv": r["htaf_cv"], "htaf_iqr_rel": r["htaf_iqr_rel"],
                           "median_ratio_h_over_b": r["median_ratio_h_over_b"]}
    vals = lambda key: [v[key] for v in runs.values()]
    return {"runs": runs,
            "htaf_cv_range": [min(vals("htaf_cv")), max(vals("htaf_cv"))],
            "htaf_iqr_rel_range": [min(vals("htaf_iqr_rel")), max(vals("htaf_iqr_rel"))],
            "median_ratio_range": [min(vals("median_ratio_h_over_b")), max(vals("median_ratio_h_over_b"))]}


def keygen_block(base: Path):
    out = {}
    for proto, suf in (("legacy", "_legacy"), ("corrected", ""), ("cooled", "_cool")):
        d = {m: describe(load(base / f"{m}_varying_key{suf}.csv"), boot=False) for m in MODES}
        out[proto] = {"ratios": ratios(d), "cv": {m: d[m]["cv"] for m in MODES},
                      "iqr_rel": {m: d[m]["iqr_rel"] for m in MODES}}
    return out


def main():
    res = {}
    a_fixed, res["A_fixed"] = fixed_block(A, "")
    b_fixed, res["B_fixed_perf"] = fixed_block(B, "_perf")
    res["A_legs"] = legs_block(A / "hybrid_legs.csv", a_fixed["hybrid"])
    res["B_legs"] = legs_block(B / "hybrid_legs.csv", b_fixed["hybrid"])
    res["A_dudect"] = dudect_block(A)
    res["B_dudect"] = dudect_block(B)
    res["A_stability"] = stability_block(A)
    res["B_stability"] = stability_block(B)
    b2_fixed, res["B2_fixed"] = fixed_block(B2, "")
    res["B2_legs"] = legs_block(B2 / "hybrid_legs.csv", b2_fixed["hybrid"])
    res["B2_dudect"] = dudect_block(B2)
    res["B2_stability"] = stability_block(B2)
    res["A_keygen_perf"] = keygen_block(A / "keygen_isolation_perf")
    OUT.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
