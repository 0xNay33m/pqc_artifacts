#!/usr/bin/env python3
"""Intel summary + cross-platform figures (reads Intel summary_stats.json if present)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
INTEL_DIR = ROOT / "results_sc_timing_intel"
INTEL_JSON = INTEL_DIR / "summary_stats.json"
AMD_STATS = ROOT / "results_sc_timing" / "summary_stats.json"
INTEL_STATS = ROOT / "thesis_sc_latex" / "data" / "intel_summary_stats.json"
FIG_DIR = ROOT / "thesis_sc_latex" / "figures" / "generated"

MODES = ("mlkem", "bike", "hybrid")
LABELS = {"mlkem": "ML-KEM", "bike": "BIKE", "hybrid": "Hybrid"}


def _intel_fixed_block(summary: dict) -> tuple[str, dict]:
    """Prefer performance-governor fixed decaps when available."""
    if summary.get("fixed_perf") and summary["fixed_perf"].get("bike"):
        return "fixed_perf", summary["fixed_perf"]
    return "fixed", summary["fixed"]


def main() -> None:
    if not INTEL_JSON.exists():
        raise SystemExit(f"Missing {INTEL_JSON} — run analyze_intel_results.py first")

    summary = json.loads(INTEL_JSON.read_text())
    INTEL_STATS.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(INTEL_JSON, INTEL_STATS)

    amd = json.loads(AMD_STATS.read_text())
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    intel_key, intel_fixed = _intel_fixed_block(summary)
    symmetric = intel_key == "fixed_perf"

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    x = np.arange(3)
    w = 0.35
    amd_cv = [amd["fixed"][m]["cv"] * 100 for m in MODES]
    intel_cv = [intel_fixed[m]["cv"] * 100 for m in MODES]
    amd_med = [amd["fixed"][m]["median_ns"] / 1000 for m in MODES]
    intel_med = [intel_fixed[m]["median_ns"] / 1000 for m in MODES]

    intel_label = "Intel (performance)" if symmetric else "Intel (powersave)"
    axes[0].bar(x - w / 2, amd_med, w, label="AMD (performance)", color="#4C72B0")
    axes[0].bar(x + w / 2, intel_med, w, label=intel_label, color="#DD8452")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels([LABELS[m] for m in MODES])
    axes[0].set_ylabel("Median decaps (µs)")
    axes[0].set_title("Cross-platform median latency (fixed decaps)")
    axes[0].legend(fontsize=8)

    axes[1].bar(x - w / 2, amd_cv, w, label="AMD", color="#4C72B0")
    axes[1].bar(x + w / 2, intel_cv, w, label="Intel", color="#DD8452")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels([LABELS[m] for m in MODES])
    axes[1].set_ylabel("Fixed-input CV (%)")
    axes[1].set_title("Cross-platform timing variability")
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "cross_platform.pdf")
    fig.savefig(FIG_DIR / "cross_platform.png", dpi=300)
    plt.close(fig)

    if "dudect" in amd and "dudect" in summary:
        fig, ax = plt.subplots(figsize=(9, 4.5))
        amd_t = [abs(amd["dudect"][m].get("welch_t_raw", 0)) for m in MODES]
        intel_t = [abs(summary["dudect"][m].get("welch_t_raw", 0)) for m in MODES]
        ax.bar(x - w / 2, amd_t, w, label="AMD", color="#4C72B0")
        ax.bar(x + w / 2, intel_t, w, label="Intel", color="#DD8452")
        ax.axhline(4.5, color="red", linestyle="--", label="dudect |t|=4.5")
        ax.set_xticks(x)
        ax.set_xticklabels([LABELS[m] for m in MODES])
        ax.set_ylabel("|Welch t| (raw, dudect)")
        ax.set_title("Cross-platform dudect two-class decaps")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(FIG_DIR / "cross_platform_dudect.pdf")
        fig.savefig(FIG_DIR / "cross_platform_dudect.png", dpi=300)
        plt.close(fig)

    print(f"Copied {INTEL_JSON} -> {INTEL_STATS}")
    print(f"Intel fixed block: {intel_key} (symmetric governor={symmetric})")
    print(f"Wrote {FIG_DIR / 'cross_platform.pdf'}")


if __name__ == "__main__":
    main()
