#!/usr/bin/env python3
"""Cross-platform dudect follow-up: class separation, composition vs single-leg."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
AMD_DIR = ROOT / "results_sc_timing"
INTEL_DIR = ROOT / "results_sc_timing_intel"
OUT = ROOT / "thesis_sc_latex" / "data" / "dudect_followup.json"

MODES = ("mlkem", "bike", "hybrid")


def load_classes(path: Path) -> tuple[np.ndarray, np.ndarray]:
    c0, c1 = [], []
    if not path.exists():
        return np.array([]), np.array([])
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            t = int(row["elapsed_ns"])
            (c0 if int(row["class"]) == 0 else c1).append(t)
    return np.array(c0, dtype=np.float64), np.array(c1, dtype=np.float64)


def analyze_platform(label: str, base: Path) -> dict:
    out: dict = {"platform": label, "modes": {}}
    for m in MODES:
        c0, c1 = load_classes(base / f"{m}_dudect.csv")
        if len(c0) < 2 or len(c1) < 2:
            continue
        t_raw, p_raw = stats.ttest_ind(c0, c1, equal_var=False)
        med0, med1 = float(np.median(c0)), float(np.median(c1))
        out["modes"][m] = {
            "n_class0": int(len(c0)),
            "n_class1": int(len(c1)),
            "median_class0_us": med0 / 1000,
            "median_class1_us": med1 / 1000,
            "median_delta_us": (med1 - med0) / 1000,
            "welch_t_raw": float(t_raw),
            "welch_p_raw": float(p_raw),
            "leakage_flag": bool(abs(t_raw) > 4.5),
        }
    return out


def main() -> None:
    amd = analyze_platform("AMD Ryzen 5500U (performance)", AMD_DIR)
    intel = analyze_platform("Intel i5-8350U (dudect under performance)", INTEL_DIR)

    # Composition hypothesis: hybrid class delta vs bike class delta on Intel
    followup: dict = {"amd": amd, "intel": intel, "interpretation": {}}
    if "hybrid" in intel["modes"] and "bike" in intel["modes"]:
        h = intel["modes"]["hybrid"]
        b = intel["modes"]["bike"]
        followup["interpretation"]["intel_hybrid_median_delta_us"] = h["median_delta_us"]
        followup["interpretation"]["intel_bike_median_delta_us"] = b["median_delta_us"]
        followup["interpretation"]["intel_hybrid_excess_delta_us"] = h["median_delta_us"] - b["median_delta_us"]
        followup["interpretation"]["intel_hybrid_flags_but_bike_not"] = h["leakage_flag"] and not b["leakage_flag"]

    if "hybrid" in amd["modes"]:
        followup["interpretation"]["amd_hybrid_leakage_flag"] = amd["modes"]["hybrid"]["leakage_flag"]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(followup, indent=2) + "\n")
    print(f"Wrote {OUT}")
    for plat in (amd, intel):
        print(f"\n{plat['platform']}:")
        for m, d in plat["modes"].items():
            print(
                f"  {m}: Δmed={d['median_delta_us']:.2f}µs |t|={abs(d['welch_t_raw']):.2f} "
                f"leak={d['leakage_flag']}"
            )


if __name__ == "__main__":
    main()
