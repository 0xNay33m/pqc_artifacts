#!/usr/bin/env python3
"""Build Intel summary_stats.json from results_sc_timing_intel CSVs."""

from __future__ import annotations

import json
from pathlib import Path

from analyze_results import (
    bootstrap_ci_cv,
    bootstrap_ci_median,
    dudect_analyze,
    load_dudect_classes,
    load_ns,
    summarize,
)

ROOT = Path(__file__).resolve().parents[1]
INTEL_DIR = ROOT / "results_sc_timing_intel"
STATS_OUT = INTEL_DIR / "summary_stats.json"
MODES = ("mlkem", "bike", "hybrid")


def summarize_block(base: str) -> dict:
    block: dict = {}
    for mode in MODES:
        path = INTEL_DIR / f"{mode}_{base}.csv"
        block[mode] = summarize(load_ns(path))
    return block


def enrich_block(base: str, block: dict) -> None:
    for mode in MODES:
        arr = load_ns(INTEL_DIR / f"{mode}_{base}.csv")
        if len(arr) == 0 or mode not in block or not block[mode]:
            continue
        mean_cv, lo, hi = bootstrap_ci_cv(arr)
        block[mode]["cv_bootstrap_mean"] = mean_cv
        block[mode]["cv_bootstrap_ci95"] = [lo, hi]
        _, med_lo, med_hi = bootstrap_ci_median(arr)
        block[mode]["median_bootstrap_ci95_us"] = [med_lo / 1000, med_hi / 1000]


def main() -> None:
    existing = {}
    if STATS_OUT.exists():
        existing = json.loads(STATS_OUT.read_text())

    summary: dict = {
        "platform": existing.get("platform", "Intel Core i5-8350U"),
        "governor_notes": {
            "fixed": "powersave (initial session steps 1-4)",
            "fixed_perf": "performance (RUN_STEPS_1_4_PERFORMANCE.sh, June 2026)",
            "dudect": "performance",
        },
        "fixed": summarize_block("fixed"),
        "fixed_perf": summarize_block("fixed_perf"),
        "encaps_fixed": summarize_block("encaps_fixed"),
        "encaps_fixed_perf": summarize_block("encaps_fixed_perf"),
        "varying_ct": summarize_block("varying_ct"),
        "varying_ct_perf": summarize_block("varying_ct_perf"),
        "varying_key": summarize_block("varying_key"),
        "varying_key_perf": summarize_block("varying_key_perf"),
        "varying_key_50k": summarize_block("varying_key_50k"),
        "dudect": {},
        "noise_floor": summarize(load_ns(INTEL_DIR / "noise_floor.csv")),
        "hybrid_legs": existing.get("hybrid_legs", {}),
    }

    for base in (
        "fixed",
        "fixed_perf",
        "encaps_fixed",
        "encaps_fixed_perf",
        "varying_ct",
        "varying_ct_perf",
        "varying_key",
        "varying_key_perf",
        "varying_key_50k",
    ):
        enrich_block(base, summary[base])

    for mode in MODES:
        c0, c1 = load_dudect_classes(INTEL_DIR / f"{mode}_dudect.csv")
        summary["dudect"][mode] = dudect_analyze(c0, c1)

    # Per-leg from hybrid_legs.csv if present
    leg_path = INTEL_DIR / "hybrid_legs.csv"
    if leg_path.exists():
        import csv

        import numpy as np

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

    STATS_OUT.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Wrote {STATS_OUT}")
    if summary["fixed_perf"].get("bike"):
        b = summary["fixed_perf"]["bike"]
        print(f"  Intel fixed_perf BIKE: med={b['median_ns']/1000:.1f}µs CV={b['cv']*100:.1f}%")


if __name__ == "__main__":
    main()
