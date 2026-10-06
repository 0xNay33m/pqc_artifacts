# Artifact: Timing Behavior of ML-KEM-768 / BIKE-L1 Hybrid Decapsulation

Measurement harness, structural verification suite, raw timing traces, and analysis scripts for the paper

> *Timing Observability of Serial Post-Quantum Hybrid Key Encapsulation: A Measurement Study of ML-KEM and BIKE Decapsulation on Commodity x86 Processors* (submitted to IEEE Access).

Every statistic reported in the paper can be recomputed from the raw traces in this repository with the two scripts in `analysis/`.

## Layout

| Path | Contents |
|------|----------|
| `sc_harness/` | C harness: ML-KEM-768, BIKE-L1, and the serial ML-KEM → BIKE → HKDF-SHA256 hybrid (`hybrid_kem.c`); timing, two-class (dudect-style), per-leg, noise-floor, and cache-proxy benchmarks; run scripts; CPU governor setup (`setup_cpu.sh`) |
| `sc_harness/intel_run/` | Run scripts used for the Platform B (Intel) batteries and the harness revision those batteries were built from (`timing_bench_jun2026.c`) |
| `sidechannel_verification/` | Structural checks: ctgrind-style secret poisoning, compiler matrix, chosen-ciphertext tests, callgrind cache probe; all logs in `results/`, summary in `results/FINDINGS.md` |
| `results_sc_timing/` | Platform A (AMD Ryzen 5 5500U) raw traces |
| `results_sc_timing_intel/` | Platform B (Intel Core i5-8350U) earlier sessions; run logs in `provenance/` |
| `results_sc_timing_intel_jun29_perf/` | Platform B full battery with the `performance` governor logged throughout (`run.log`, `platform_info.txt`) |
| `results_sc_cache/` | Cache-proxy (Tier 1) cold/warm traces |
| `analysis/` | `revision_analysis.py`, `revision_analysis_extra.py`, and their outputs (`revision_stats*.json`) |
| `vendor/` | `build_liboqs.sh` (fetches and builds liboqs 0.14.0, commit `94b421e`) and the `oqsconfig.h` of the measured build |

## Which data backs which result

| Paper result | Platform A | Platform B |
|--------------|------------|------------|
| Fixed-input statistics, HTAF (Table "Fixed-Input Decapsulation Statistics") | `results_sc_timing/{mlkem,bike,hybrid}_fixed.csv` | `results_sc_timing_intel/{mlkem,bike,hybrid}_fixed_perf.csv` (consistency check: `results_sc_timing_intel_jun29_perf/*_fixed.csv`) |
| Repeated sessions (5 × 10,000) | `results_sc_timing/stability/` | `results_sc_timing_intel_jun29_perf/stability/` |
| Per-leg attribution | `results_sc_timing/hybrid_legs.csv` | `results_sc_timing_intel_jun29_perf/hybrid_legs.csv` |
| Key-rotation isolation (legacy / corrected / cooled) | `results_sc_timing/keygen_isolation_perf/*_varying_key{_legacy,,_cool}.csv` | — |
| Historical key-rotation session (HTAF 17.6) | `results_sc_timing/*_varying_key.csv` | — |
| Two-class tests (5 × 10^5 per class) | `results_sc_timing/*_dudect.csv` | `results_sc_timing_intel_jun29_perf/*_dudect.csv` |
| Earlier Platform B two-class session (excluded from primary inference) | — | `results_sc_timing_intel/*_dudect.csv` |
| Cache proxy and simulation, ctgrind, compiler matrix, chosen ciphertext | `results_sc_cache/`, `sidechannel_verification/results/` | — |

### Platform B sessions

| Session | Governor | Used for |
|---------|----------|----------|
| June 22 (`results_sc_timing_intel/*.csv` without `_perf`, `*_dudect.csv`, `stability/`, `hybrid_legs.csv`) | `powersave` recorded at session start | Reported only for completeness |
| June 23 (`results_sc_timing_intel/*_perf.csv`) | `performance` | Fixed-input table |
| June 28 (`results_sc_timing_intel/*_varying_key_50k.csv`, `provenance/`) | `powersave` | Not used for primary inference |
| June 29 (`results_sc_timing_intel_jun29_perf/`) | `performance`, logged before the battery and before the class tests | Per-leg, repeated sessions, two-class tests |

## CSV formats

All times are nanoseconds from `CLOCK_MONOTONIC_RAW` around a single decapsulation call.

| Files | Columns |
|-------|---------|
| `*_fixed*.csv`, `*_varying_*.csv`, `stability/*.csv` | `iteration,mode,input,op,elapsed_ns` |
| `*_dudect.csv` | `iteration,mode,class,elapsed_ns` (class 0: ciphertext of the previous iteration; class 1: ciphertext encapsulated immediately before the timer) |
| `hybrid_legs.csv` | `iteration,mlkem_ns,bike_ns,hkdf_ns,total_ns` |
| `results_sc_cache/*.csv` | `iteration,mode,condition,elapsed_ns` |
| `noise_floor.csv` | `iteration,mode,input,elapsed_ns` |

## Reproducing the statistics (no special hardware needed)

```bash
pip install -r analysis/requirements.txt
python analysis/revision_analysis.py        # -> analysis/revision_stats.json
python analysis/revision_analysis_extra.py  # -> analysis/revision_stats_extra.json
```

The scripts compute medians, quantiles, coefficient of variation, IQR- and MAD-based dispersion, all HTAF forms, lag-1 autocorrelation, moving-block bootstrap intervals (1000 replicates; block lengths 500/2000, or 200/1000 for 10,000-sample traces), Mann–Whitney, Kolmogorov–Smirnov, Cliff's δ, covariance-based per-leg variance shares, and the raw, second-order, cropped, and KS two-class statistics. Bootstrap seeds are fixed.

## Re-running the measurements (Linux, x86-64)

Requirements: `gcc`, `cmake`, `ninja`, `git`, `python3` with numpy and scipy; `valgrind` (≥ 3.24) and `clang` for the structural checks. The paper's builds used GCC 14.2.0 with `-O2`.

```bash
./vendor/build_liboqs.sh                   # liboqs 0.14.0, OQS_USE_OPENSSL=OFF, OQS_DIST_BUILD=ON
cd sc_harness && make
export LD_LIBRARY_PATH=../vendor/liboqs-install/lib:$LD_LIBRARY_PATH
sudo ./setup_cpu.sh                        # performance governor on all cores
./run_experiments.sh                       # fixed, varying, two-class, per-leg, stability
./run_keygen_isolation.sh                  # legacy / corrected / cooled key-rotation protocols
```

**The run scripts write into `results_sc_timing/` and overwrite the shipped traces.** Re-run in a separate clone, or move the shipped results aside first.

Processes are pinned to CPU 2 with `sched_setaffinity`; 200 warm-up iterations are discarded for the 50,000-sample and two-class runs, and 100 for the 10,000-sample runs. The structural checks are described in `sidechannel_verification/README.md`.

Exact coefficient values depend on the processor, operating system, and background load. The structural results are the ones expected to replicate: BIKE dominance of hybrid medians and variance, robust HTAF at or below 1, non-reproduction of the historical key-rotation amplification under a fixed governor, and the behavior of the class tests under the stated design.

## Known limitations

- The two-class design gives class 1 an encapsulation immediately before the timer and class 0 none, so class is confounded with pre-measurement processor state. Classes are not partitioned by secret-key value.
- Configurations within a regime were measured sequentially, not interleaved.
- No `isolcpus`; hardware performance counters were unavailable (`perf_event_paranoid=3`).
- The Platform A operating system has since been replaced; its run logs record governor and frequency only.
