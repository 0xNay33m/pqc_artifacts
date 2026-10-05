#!/usr/bin/env bash
# Full experiment battery (reviewer-hardened): cpufreq performance + dudect + encaps.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
OUT="${ROOT}/../results_sc_timing"
STAB="${OUT}/stability"
CPU="${CPU:-2}"
DUDECT_SAMPLES="${DUDECT_SAMPLES:-500000}"
export LD_LIBRARY_PATH="${ROOT}/../vendor/liboqs-install/lib:${LD_LIBRARY_PATH:-}"

chmod +x "$ROOT/setup_cpu.sh"
"$ROOT/setup_cpu.sh"

make -C "$ROOT" clean all
mkdir -p "$OUT" "$STAB"

echo "=== [1] Fixed-input decaps timing (50k) ==="
for mode in mlkem bike hybrid; do
  "$ROOT/timing_bench" --mode "$mode" --op decaps --input fixed --samples 50000 --warmup 200 --cpu "$CPU" \
    --out "$OUT/${mode}_fixed.csv"
done

echo "=== [2] Fixed-input encaps timing (50k) ==="
for mode in mlkem bike hybrid; do
  "$ROOT/timing_bench" --mode "$mode" --op encaps --input fixed --samples 50000 --warmup 200 --cpu "$CPU" \
    --out "$OUT/${mode}_encaps_fixed.csv"
done

echo "=== [3] Varying-ciphertext decaps timing (10k) ==="
for mode in mlkem bike hybrid; do
  "$ROOT/timing_bench" --mode "$mode" --op decaps --input varying-ct --samples 10000 --warmup 100 --cpu "$CPU" \
    --out "$OUT/${mode}_varying_ct.csv"
done

echo "=== [4] Varying-key decaps timing (50k) ==="
for mode in mlkem bike hybrid; do
  "$ROOT/timing_bench" --mode "$mode" --op decaps --input varying-key --samples 50000 --warmup 200 --cpu "$CPU" \
    --out "$OUT/${mode}_varying_key.csv"
done

echo "=== [5] Dudect two-class decaps (${DUDECT_SAMPLES} per class, 1M+ total per mode) ==="
for mode in mlkem bike hybrid; do
  "$ROOT/dudect_bench" --mode "$mode" --samples-per-class "$DUDECT_SAMPLES" --warmup 200 --cpu "$CPU" \
    --out "$OUT/${mode}_dudect.csv"
done

echo "=== [6] Noise floor (50k memcpy) ==="
"$ROOT/noise_bench" --samples 50000 --warmup 200 --cpu "$CPU" --out "$OUT/noise_floor.csv"

echo "=== [7] Hybrid per-leg attribution (10k) ==="
"$ROOT/leg_bench" --samples 10000 --warmup 100 --cpu "$CPU" --out "$OUT/hybrid_legs.csv"

echo "=== [8] Stability: 5 independent fixed decaps runs (10k each) ==="
for run in 1 2 3 4 5; do
  for mode in mlkem bike hybrid; do
    "$ROOT/timing_bench" --mode "$mode" --op decaps --input fixed --samples 10000 --warmup 100 --cpu "$CPU" \
      --out "$STAB/${mode}_run${run}.csv"
  done
done

echo "Experiments complete. Run: python3 analyze_results.py"
