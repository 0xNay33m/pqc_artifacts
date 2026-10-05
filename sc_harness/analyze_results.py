#!/usr/bin/env python3
"""Statistics and figures for reviewer-hardened side-channel thesis."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
TIMING_DIR = ROOT / "results_sc_timing"
STAB_DIR = TIMING_DIR / "stability"
CACHE_DIR = ROOT / "results_sc_cache"
FIG_DIR = ROOT / "thesis_sc_latex" / "figures"
STATS_OUT = TIMING_DIR / "summary_stats.json"
TEX_SNIPPET = ROOT / "thesis_sc_latex" / "_src" / "chapters" / "_eval_numbers.tex"

MODES = ("mlkem", "bike", "hybrid")
MODE_LABELS = {"mlkem": "ML-KEM-768", "bike": "BIKE-L1", "hybrid": "Hybrid"}
COLORS = ["#4C72B0", "#DD8452", "#55A868"]


def load_ns(path: Path) -> np.ndarray:
    if not path.exists():
        return np.array([], dtype=np.float64)
    vals = []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            vals.append(int(row["elapsed_ns"]))
    return np.array(vals, dtype=np.float64)


def load_dudect_classes(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return (class0 fixed-ct, class1 varying-ct) nanosecond arrays."""
    c0, c1 = [], []
    if not path.exists():
        return np.array([], dtype=np.float64), np.array([], dtype=np.float64)
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            t = int(row["elapsed_ns"])
            if int(row["class"]) == 0:
                c0.append(t)
            else:
                c1.append(t)
    return np.array(c0, dtype=np.float64), np.array(c1, dtype=np.float64)


def bootstrap_ci_cv(arr: np.ndarray, n_boot: int = 1000, seed: int = 42) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    cvs = []
    for _ in range(n_boot):
        sample = rng.choice(arr, size=len(arr), replace=True)
        m = np.mean(sample)
        if m > 0:
            cvs.append(float(np.std(sample, ddof=1) / m))
    if not cvs:
        return 0.0, 0.0, 0.0
    return float(np.mean(cvs)), float(np.percentile(cvs, 2.5)), float(np.percentile(cvs, 97.5))


def bootstrap_ci_median(arr: np.ndarray, n_boot: int = 1000, seed: int = 42) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    meds = [float(np.median(rng.choice(arr, size=len(arr), replace=True))) for _ in range(n_boot)]
    if not meds:
        return 0.0, 0.0, 0.0
    return float(np.median(arr)), float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5))


def format_p(p: float) -> str:
    if p == 0.0 or p < 1e-300:
        return "< 10^{-300}"
    if p < 1e-6:
        return f"{p:.2e}"
    return f"{p:.6f}"


def dudect_analyze(c0: np.ndarray, c1: np.ndarray) -> dict:
    """Welch t-tests on raw timings and centered second moments (dudect-style)."""
    if len(c0) < 2 or len(c1) < 2:
        return {}
    t_raw, p_raw = stats.ttest_ind(c0, c1, equal_var=False)
    all_t = np.concatenate([c0, c1])
    mu = float(np.mean(all_t))
    m0 = (c0 - mu) ** 2
    m1 = (c1 - mu) ** 2
    t_mom, p_mom = stats.ttest_ind(m0, m1, equal_var=False)
    med0, med1 = float(np.median(c0)), float(np.median(c1))
    leak_mom = bool(abs(t_mom) > 4.5)
    leak_raw = bool(abs(t_raw) > 4.5)
    return {
        "n_class0": int(len(c0)),
        "n_class1": int(len(c1)),
        "median_class0_ns": med0,
        "median_class1_ns": med1,
        "median_delta_ns": med1 - med0,
        "welch_t_raw": float(t_raw),
        "welch_p_raw": float(p_raw),
        "welch_p_raw_fmt": format_p(float(p_raw)),
        "welch_t_moment": float(t_mom),
        "welch_p_moment": float(p_mom),
        "welch_p_moment_fmt": format_p(float(p_mom)),
        "leakage_flag_raw": leak_raw,
        "leakage_flag_moment": leak_mom,
        "no_leakage_detected": not (leak_raw or leak_mom),
    }


def hist_entropy(arr: np.ndarray, bins: int = 64) -> float:
    log_us = np.log2(arr / 1000.0 + 1e-9)
    hist, _ = np.histogram(log_us, bins=bins)
    p = hist.astype(float)
    p = p[p > 0]
    p /= p.sum()
    return float(-np.sum(p * np.log2(p)))


def mann_whitney_p(a: np.ndarray, b: np.ndarray) -> float:
    return float(stats.mannwhitneyu(a, b, alternative="two-sided").pvalue)


def summarize(arr: np.ndarray) -> dict:
    if len(arr) == 0:
        return {}
    return {
        "n": int(len(arr)),
        "mean_ns": float(np.mean(arr)),
        "median_ns": float(np.median(arr)),
        "std_ns": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        "cv": float(np.std(arr, ddof=1) / np.mean(arr)) if len(arr) > 1 and np.mean(arr) else 0.0,
        "p95_ns": float(np.percentile(arr, 95)),
        "p99_ns": float(np.percentile(arr, 99)),
        "iqr_ns": float(np.percentile(arr, 75) - np.percentile(arr, 25)),
        "entropy_bits": hist_entropy(arr),
    }


def write_tex_snippet(summary: dict) -> None:
    fixed = summary["fixed"]
    noise = summary["noise_floor"]
    legs = summary.get("hybrid_legs", {})
    cache = summary.get("cache_proxy", {})

    lines = [
        "% Auto-generated by analyze_results.py — do not edit by hand",
        f"\\newcommand{{\\EvalMlkemMedian}}{{{fixed['mlkem']['median_ns']/1000:.1f}}}",
        f"\\newcommand{{\\EvalBikeMedian}}{{{fixed['bike']['median_ns']/1000:.1f}}}",
        f"\\newcommand{{\\EvalHybridMedian}}{{{fixed['hybrid']['median_ns']/1000:.1f}}}",
        f"\\newcommand{{\\EvalMlkemCV}}{{{fixed['mlkem']['cv']*100:.1f}}}",
        f"\\newcommand{{\\EvalBikeCV}}{{{fixed['bike']['cv']*100:.1f}}}",
        f"\\newcommand{{\\EvalHybridCV}}{{{fixed['hybrid']['cv']*100:.1f}}}",
        f"\\newcommand{{\\EvalNoiseCV}}{{{noise['cv']*100:.1f}}}",
    ]
    if legs:
        lines.append(f"\\newcommand{{\\EvalLegBikePct}}{{{legs['bike_frac_cv']*100:.1f}}}")
        lines.append(f"\\newcommand{{\\EvalLegMlkemPct}}{{{legs['mlkem_frac_cv']*100:.1f}}}")
    if cache.get("mlkem"):
        m = cache["mlkem"]
        lines.append(f"\\newcommand{{\\EvalCacheMlkemAbs}}{{{(m['cold_median_ns']-m['warm_median_ns'])/1000:.1f}}}")
    TEX_SNIPPET.write_text("\n".join(lines) + "\n")


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    summary: dict = {
        "fixed": {},
        "encaps_fixed": {},
        "varying_ct": {},
        "varying_key": {},
        "dudect": {},
        "noise_floor": {},
        "tests": {},
        "stability": {},
    }

    for mode in MODES:
        summary["fixed"][mode] = summarize(load_ns(TIMING_DIR / f"{mode}_fixed.csv"))
        summary["encaps_fixed"][mode] = summarize(load_ns(TIMING_DIR / f"{mode}_encaps_fixed.csv"))
        summary["varying_ct"][mode] = summarize(load_ns(TIMING_DIR / f"{mode}_varying_ct.csv"))
        summary["varying_key"][mode] = summarize(load_ns(TIMING_DIR / f"{mode}_varying_key.csv"))
        c0, c1 = load_dudect_classes(TIMING_DIR / f"{mode}_dudect.csv")
        summary["dudect"][mode] = dudect_analyze(c0, c1)

    summary["noise_floor"] = summarize(load_ns(TIMING_DIR / "noise_floor.csv"))

    fixed = {m: load_ns(TIMING_DIR / f"{m}_fixed.csv") for m in MODES}
    ks_hb = stats.ks_2samp(fixed["hybrid"], fixed["bike"])
    ks_hm = stats.ks_2samp(fixed["hybrid"], fixed["mlkem"])
    mw_hb = stats.mannwhitneyu(fixed["hybrid"], fixed["bike"], alternative="two-sided")
    mw_hm = stats.mannwhitneyu(fixed["hybrid"], fixed["mlkem"], alternative="two-sided")
    summary["tests"] = {
        "ks_hybrid_vs_bike_fixed": float(ks_hb.pvalue),
        "ks_hybrid_vs_bike_fixed_fmt": format_p(float(ks_hb.pvalue)),
        "ks_hybrid_vs_mlkem_fixed": float(ks_hm.pvalue),
        "ks_hybrid_vs_mlkem_fixed_fmt": format_p(float(ks_hm.pvalue)),
        "mann_hybrid_vs_bike_fixed": float(mw_hb.pvalue),
        "mann_hybrid_vs_bike_fixed_fmt": format_p(float(mw_hb.pvalue)),
        "mann_hybrid_vs_mlkem_fixed": float(mw_hm.pvalue),
        "mann_hybrid_vs_mlkem_fixed_fmt": format_p(float(mw_hm.pvalue)),
    }

    for mode in MODES:
        cvs = []
        for run in range(1, 6):
            p = STAB_DIR / f"{mode}_run{run}.csv"
            if p.exists():
                arr = load_ns(p)
                if len(arr) and np.mean(arr):
                    cvs.append(float(np.std(arr, ddof=1) / np.mean(arr)))
        if cvs:
            summary["stability"][mode] = {
                "cv_mean": float(np.mean(cvs)),
                "cv_std": float(np.std(cvs, ddof=1)) if len(cvs) > 1 else 0.0,
                "runs": len(cvs),
            }

    for mode in MODES:
        arr = fixed[mode]
        if len(arr):
            mean_cv, lo, hi = bootstrap_ci_cv(arr)
            summary["fixed"][mode]["cv_bootstrap_mean"] = mean_cv
            summary["fixed"][mode]["cv_bootstrap_ci95"] = [lo, hi]
            _, med_lo, med_hi = bootstrap_ci_median(arr)
            summary["fixed"][mode]["median_bootstrap_ci95_us"] = [med_lo / 1000, med_hi / 1000]

    # Per-leg hybrid attribution
    leg_path = TIMING_DIR / "hybrid_legs.csv"
    if leg_path.exists():
        ml, bi, hk, tot = [], [], [], []
        with leg_path.open(newline="") as f:
            for row in csv.DictReader(f):
                ml.append(int(row["mlkem_ns"]))
                bi.append(int(row["bike_ns"]))
                hk.append(int(row["hkdf_ns"]))
                tot.append(int(row["total_ns"]))
        ml_a, bi_a, hk_a, tot_a = map(np.array, (ml, bi, hk, tot))
        summary["hybrid_legs"] = {
            "mlkem_median_us": float(np.median(ml_a) / 1000),
            "bike_median_us": float(np.median(bi_a) / 1000),
            "hkdf_median_us": float(np.median(hk_a) / 1000),
            "bike_frac_cv": float(np.std(bi_a, ddof=1) / np.std(tot_a, ddof=1)) if np.std(tot_a) else 0,
            "mlkem_frac_cv": float(np.std(ml_a, ddof=1) / np.std(tot_a, ddof=1)) if np.std(tot_a) else 0,
            "bike_frac_median": float(np.median(bi_a) / np.median(tot_a)),
        }

    # Cache proxy with absolute deltas
    cache_summary = {}
    for mode in MODES:
        warm_p = CACHE_DIR / f"{mode}_warm_cache.csv"
        cold_p = CACHE_DIR / f"{mode}_cold_cache.csv"
        if warm_p.exists() and cold_p.exists():
            warm = load_ns(warm_p)
            cold = load_ns(cold_p)
            wm, cm = float(np.median(warm)), float(np.median(cold))
            delta = cold - warm
            _, d_lo, d_hi = bootstrap_ci_median(delta)
            entry = {
                "warm_median_ns": wm,
                "cold_median_ns": cm,
                "abs_delta_ns": float(np.median(delta)),
                "rel_pct": (cm / wm - 1.0) * 100.0 if wm else 0.0,
                "abs_delta_bootstrap_ci95_us": [d_lo / 1000, d_hi / 1000],
            }
            cache_summary[mode] = entry
    summary["cache_proxy"] = cache_summary

    STATS_OUT.write_text(json.dumps(summary, indent=2) + "\n")
    write_tex_snippet(summary)

    plt.style.use("seaborn-v0_8-whitegrid")

    # Log-scale histogram
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, m in enumerate(MODES):
        us = fixed[m] / 1000.0
        us = us[us > 0]
        ax.hist(us, bins=80, alpha=0.55, label=MODE_LABELS[m], color=COLORS[i], density=True)
    ax.set_xscale("log")
    ax.set_xlabel("Decapsulation time (µs, log scale)")
    ax.set_ylabel("Density")
    ax.set_title("Timing distributions (fixed input, 50k samples)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "timing_histogram.pdf")
    fig.savefig(FIG_DIR / "timing_histogram.png", dpi=300)
    plt.close(fig)

    # CDF log x
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, m in enumerate(MODES):
        us = np.sort(fixed[m] / 1000.0)
        y = np.arange(1, len(us) + 1) / len(us)
        ax.plot(us, y, label=MODE_LABELS[m], color=COLORS[i], linewidth=2)
    ax.set_xscale("log")
    ax.set_xlabel("Decapsulation time (µs, log scale)")
    ax.set_ylabel("CDF")
    ax.set_title("Cumulative timing distributions (fixed input)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "timing_cdf.pdf")
    fig.savefig(FIG_DIR / "timing_cdf.png", dpi=300)
    plt.close(fig)

    # Fixed vs varying-ct vs varying-key CV comparison
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(MODES))
    w = 0.25
    fixed_cv = [summary["fixed"][m]["cv"] * 100 for m in MODES]
    vary_ct_cv = [summary["varying_ct"][m].get("cv", 0) * 100 for m in MODES]
    vary_key_cv = [summary["varying_key"][m].get("cv", 0) * 100 for m in MODES]
    ax.bar(x - w, fixed_cv, w, label="Fixed input", color="#4C72B0")
    ax.bar(x, vary_ct_cv, w, label="Varying ciphertext", color="#DD8452")
    ax.bar(x + w, vary_key_cv, w, label="Varying key", color="#55A868")
    ax.set_xticks(x)
    ax.set_xticklabels([MODE_LABELS[m] for m in MODES])
    ax.set_ylabel("CV (%)")
    ax.set_title("CV across input regimes")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fixed_vs_varying_cv.pdf")
    fig.savefig(FIG_DIR / "fixed_vs_varying_cv.png", dpi=300)
    plt.close(fig)

    # Summary median + CV with noise floor line
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    medians = [summary["fixed"][m]["median_ns"] / 1000 for m in MODES]
    cvs = [summary["fixed"][m]["cv"] * 100 for m in MODES]
    axes[0].bar([MODE_LABELS[m] for m in MODES], medians, color=COLORS)
    axes[0].set_ylabel("Median (µs)")
    axes[1].bar([MODE_LABELS[m] for m in MODES], cvs, color=COLORS)
    axes[1].axhline(summary["noise_floor"]["cv"] * 100, color="gray", linestyle="--", label="Noise floor (memcpy)")
    axes[1].set_ylabel("CV (%)")
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "timing_summary.pdf")
    fig.savefig(FIG_DIR / "timing_summary.png", dpi=300)
    plt.close(fig)

    # Cache absolute + relative
    if cache_summary:
        labels = [MODE_LABELS[m] for m in MODES]
        abs_d = [cache_summary[m]["abs_delta_ns"] / 1000 for m in MODES]
        rel_d = [cache_summary[m]["rel_pct"] for m in MODES]
        fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
        axes[0].bar(labels, abs_d, color=COLORS)
        axes[0].set_ylabel("Absolute cold-warm Δ (µs)")
        axes[1].bar(labels, rel_d, color=COLORS)
        axes[1].set_ylabel("Relative cold-warm Δ (%)")
        fig.suptitle("Cache-proxy eviction effect")
        fig.tight_layout()
        fig.savefig(FIG_DIR / "cache_proxy.pdf")
        fig.savefig(FIG_DIR / "cache_proxy.png", dpi=300)
        plt.close(fig)

    # Per-leg boxplot if available
    if leg_path.exists():
        fig, ax = plt.subplots(figsize=(7, 4.5))
        data = [np.array(ml) / 1000, np.array(bi) / 1000, np.array(hk) / 1000]
        ax.boxplot(data, tick_labels=["ML-KEM leg", "BIKE leg", "HKDF leg"])
        ax.set_ylabel("Time (µs)")
        ax.set_title("Hybrid decaps per-leg timing (10k samples)")
        fig.tight_layout()
        fig.savefig(FIG_DIR / "hybrid_legs.pdf")
        fig.savefig(FIG_DIR / "hybrid_legs.png", dpi=300)
        plt.close(fig)

    # Dudect class comparison figure
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    t_raw_vals, t_mom_vals = [], []
    for m in MODES:
        d = summary["dudect"].get(m, {})
        t_raw_vals.append(abs(d.get("welch_t_raw", 0)))
        t_mom_vals.append(abs(d.get("welch_t_moment", 0)))
    x = np.arange(len(MODES))
    axes[0].bar([MODE_LABELS[m] for m in MODES], t_raw_vals, color=COLORS)
    axes[0].axhline(4.5, color="red", linestyle="--", label="dudect threshold |t|=4.5")
    axes[0].set_ylabel("|Welch t| (raw timing)")
    axes[0].set_title("Dudect two-class: fixed vs fresh ciphertext")
    axes[0].legend()
    axes[1].bar([MODE_LABELS[m] for m in MODES], t_mom_vals, color=COLORS)
    axes[1].axhline(4.5, color="red", linestyle="--", label="dudect threshold |t|=4.5")
    axes[1].set_ylabel("|Welch t| (centered 2nd moment)")
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "dudect_welch.pdf")
    fig.savefig(FIG_DIR / "dudect_welch.png", dpi=300)
    plt.close(fig)

    # Encaps vs decaps median comparison
    fig, ax = plt.subplots(figsize=(9, 5))
    dec_med = [summary["fixed"][m]["median_ns"] / 1000 for m in MODES]
    enc_med = [summary["encaps_fixed"][m].get("median_ns", 0) / 1000 for m in MODES]
    w = 0.35
    ax.bar(x - w / 2, dec_med, w, label="Decaps (fixed)", color="#4C72B0")
    ax.bar(x + w / 2, enc_med, w, label="Encaps (fixed)", color="#DD8452")
    ax.set_xticks(x)
    ax.set_xticklabels([MODE_LABELS[m] for m in MODES])
    ax.set_ylabel("Median (µs)")
    ax.set_title("Encapsulation vs decapsulation median latency (50k, performance governor)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "encaps_vs_decaps.pdf")
    fig.savefig(FIG_DIR / "encaps_vs_decaps.png", dpi=300)
    plt.close(fig)

    print(f"Wrote {STATS_OUT}")
    print(f"Wrote figures in {FIG_DIR}")


if __name__ == "__main__":
    main()
