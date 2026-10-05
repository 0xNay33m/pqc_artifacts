# Intel Run Guide

## Quick start (one command)

```bash
unzip intel_timing_bundle.zip
cd intel_timing_bundle
chmod +x RUN_INTEL.sh
./RUN_INTEL.sh
```

Enter sudo password when prompted (performance governor).  
When finished, send **`intel_results_for_amd.tar.gz`** back to the AMD machine.

---

## What you are running and why

The thesis needs **Intel varying-key decaps at n=50,000** under **performance** governor to match AMD Platform A. Without this, the cross-platform comparison (AMD 141% vs BIKE 8% CV) uses asymmetric sample depth on Intel (n=10,000).

`RUN_INTEL.sh` runs everything in sequence with error checks at each step.

---

## Script phases

```
Phase 1  Platform info        → results_sc_timing_intel/platform_info.txt
Phase 2  Dependencies         → gcc, python, numpy, liboqs, disk check
Phase 3  Build                 → make clean all
Phase 4  Smoke tests           → 5-sample fixed + 3-sample varying-key
Phase 5  Governor               → sudo setup_cpu.sh, verify performance
Phase 6  Varying-key 50k × 3    → mlkem, bike, hybrid CSVs
Phase 7  Analysis               → summary_stats.json, RUN_REPORT.txt
Phase 8  Package                → intel_results_for_amd.tar.gz
```

If any step fails, the script stops and writes to **`results_sc_timing_intel/run.log`**.

---

## Modes

| Command | Use when |
|---------|----------|
| `./RUN_INTEL.sh` | **Default** — varying-key 50k parity (~30–45 min) |
| `./RUN_INTEL.sh --check-only` | Test setup before leaving machine unattended |
| `./RUN_INTEL.sh --with-dudect` | Also re-run dudect under performance (~2 h) |
| `./RUN_INTEL.sh --full` | First-time full Platform B battery (~1–2 h) |

Environment overrides:

```bash
CPU=1 ./RUN_INTEL.sh
DUDECT_SAMPLES=50000 ./RUN_INTEL.sh --with-dudect
```

---

## Reading RUN_REPORT.txt

After the run, open `results_sc_timing_intel/RUN_REPORT.txt`.

| Intel hybrid CV at n=50k | Meaning |
|--------------------------|---------|
| **&lt; 20%** | Platform-specific tail — Intel does not replicate AMD magnitude |
| **Toward 100%+** | Key-rotation tail may be broader x86 hybrid behaviour |

AMD reference: hybrid **141%** CV, BIKE **8.0%** CV, **~17×** ratio.

---

## On AMD after receiving tarball

```bash
cd /home/wizard/Desktop/thesis
tar xzf intel_results_for_amd.tar.gz -C intel_timing_bundle
python3 intel_timing_bundle/sc_harness/analyze_intel_results.py
# Update thesis Platform B varying-key table if needed
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Script stops at Phase 2 | `sudo apt-get install build-essential python3 python3-pip` |
| Governor not performance | Re-run; ensure sudo works: `sudo sc_harness/setup_cpu.sh` |
| liboqs.so missing | Run from bundle root; check `vendor/liboqs-install/lib/` |
| Partial run | Check `results_sc_timing_intel/run.log`, fix issue, re-run |

---

*Single entry point: `RUN_INTEL.sh` — all other `.sh` files are thin wrappers.*
