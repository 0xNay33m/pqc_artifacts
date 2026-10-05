#!/usr/bin/env bash
# Intel Kali — steps 5–8 + analysis (after steps 1–4 are done).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
HARNESS="$ROOT/sc_harness"
OUT="$ROOT/results_sc_timing_intel"
STAB="$OUT/stability"
CPU="${CPU:-2}"
DUDECT_SAMPLES="${DUDECT_SAMPLES:-500000}"

export LD_LIBRARY_PATH="$ROOT/vendor/liboqs-install/lib:${LD_LIBRARY_PATH:-}"

mkdir -p "$OUT" "$STAB"

if [[ ! -x "$HARNESS/dudect_bench" ]]; then
  echo "Building sc_harness..."
  make -C "$HARNESS" clean all
fi

echo "=== CPU governor: performance ==="
chmod +x "$HARNESS/setup_cpu.sh"
sudo "$HARNESS/setup_cpu.sh"
echo "Governor now: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo unknown)"

cd "$HARNESS"

echo "=== [5] Dudect two-class (${DUDECT_SAMPLES} per class) ==="
for mode in mlkem bike hybrid; do
  echo "  -> dudect $mode ..."
  ./dudect_bench --mode "$mode" --samples-per-class "$DUDECT_SAMPLES" --warmup 200 --cpu "$CPU" \
    --out "$OUT/${mode}_dudect.csv"
done

echo "=== [6] Noise floor 50k ==="
./noise_bench --samples 50000 --warmup 200 --cpu "$CPU" --out "$OUT/noise_floor.csv"

echo "=== [7] Hybrid legs 10k ==="
./leg_bench --samples 10000 --warmup 100 --cpu "$CPU" --out "$OUT/hybrid_legs.csv"

echo "=== [8] Stability 5x10k ==="
for run in 1 2 3 4 5; do
  for mode in mlkem bike hybrid; do
    ./timing_bench --mode "$mode" --op decaps --input fixed --samples 10000 --warmup 100 --cpu "$CPU" \
      --out "$STAB/${mode}_run${run}.csv"
  done
done

echo "=== Analyzing ==="
python3 analyze_intel_results.py
python3 analyze_intel.py 2>/dev/null || true

echo ""
echo "DONE. Results: $OUT"
echo "  tar czf intel_results_for_amd.tar.gz -C $ROOT results_sc_timing_intel"
