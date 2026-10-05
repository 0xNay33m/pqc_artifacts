#!/usr/bin/env python3
"""Summarize keygen-isolation CSVs: CV, HTAF, R99, abs P99 ratio."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np


def load_ns(path: Path) -> np.ndarray:
    with path.open() as f:
        rows = list(csv.DictReader(f))
    return np.array([float(r["elapsed_ns"]) for r in rows], dtype=float)


def bootstrap_cv_ci(x: np.ndarray, B: int = 1000, seed: int = 0):
    rng = np.random.default_rng(seed)
    n = len(x)
    cvs = []
    for _ in range(B):
        s = rng.choice(x, n, replace=True)
        m = s.mean()
        cvs.append(s.std(ddof=1) / m if m else np.nan)
    lo, hi = np.percentile(cvs, [2.5, 97.5])
    cv = x.std(ddof=1) / x.mean()
    return float(cv), float(lo), float(hi)


def summarize(x: np.ndarray) -> dict:
    med = float(np.median(x))
    p99 = float(np.percentile(x, 99))
    cv, lo, hi = bootstrap_cv_ci(x)
    return {
        "n": int(len(x)),
        "median_us": med / 1e3,
        "p99_us": p99 / 1e3,
        "cv": cv,
        "cv_pct": cv * 100,
        "cv_ci95_pct": [lo * 100, hi * 100],
        "p99_over_med": p99 / med if med else None,
        "frac_gt_10x_med": float(np.mean(x > 10 * med)),
    }


def htaf(block: dict) -> dict:
    m, b, h = block["mlkem"], block["bike"], block["hybrid"]
    cv_htaf = h["cv"] / max(m["cv"], b["cv"])
    r99 = h["p99_over_med"] / max(m["p99_over_med"], b["p99_over_med"])
    abs_p99 = h["p99_us"] / max(m["p99_us"], b["p99_us"])
    return {
        "cv_htaf": cv_htaf,
        "r99": r99,
        "abs_p99_ratio": abs_p99,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, required=True)
    args = ap.parse_args()
    out_dir = args.dir

    protocols = {
        "corrected": "varying_key",
        "cooled": "varying_key_cool",
        "legacy": "varying_key_legacy",
    }
    summary: dict = {"protocols": {}}

    for label, suffix in protocols.items():
        block = {}
        missing = False
        for mode in ("mlkem", "bike", "hybrid"):
            path = out_dir / f"{mode}_{suffix}.csv"
            if not path.exists():
                missing = True
                break
            block[mode] = summarize(load_ns(path))
        if missing:
            continue
        block["htaf"] = htaf(block)
        summary["protocols"][label] = block
        h = block["htaf"]
        print(f"\n=== {label} ===")
        for mode in ("mlkem", "bike", "hybrid"):
            s = block[mode]
            print(
                f"  {mode:6s} n={s['n']} med={s['median_us']:.1f}us "
                f"CV={s['cv_pct']:.1f}% [{s['cv_ci95_pct'][0]:.1f},{s['cv_ci95_pct'][1]:.1f}] "
                f"P99/med={s['p99_over_med']:.2f}"
            )
        print(
            f"  HTAF: CV={h['cv_htaf']:.2f}  R99={h['r99']:.2f}  "
            f"absP99={h['abs_p99_ratio']:.2f}"
        )

    out_json = out_dir / "keygen_isolation_summary.json"
    out_json.write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {out_json}")


if __name__ == "__main__":
    main()
