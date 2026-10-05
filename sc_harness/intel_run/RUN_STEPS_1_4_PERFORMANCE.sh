#!/usr/bin/env bash
# Re-run Intel steps 1-4 under performance governor (fixed, encaps, varying-ct, varying-key).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
HARNESS="$ROOT/sc_harness"
OUT="$ROOT/results_sc_timing_intel"
CPU="${CPU:-2}"

export LD_LIBRARY_PATH="$ROOT/vendor/liboqs-install/lib:${LD_LIBRARY_PATH:-}"

sudo "$HARNESS/setup_cpu.sh"
echo "Governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)"

cd "$HARNESS"
make -q timing_bench 2>/dev/null || make timing_bench

echo "=== Fixed decaps 50k (performance) ==="
for mode in mlkem bike hybrid; do
  ./timing_bench --mode "$mode" --op decaps --input fixed --samples 50000 --warmup 200 --cpu "$CPU" \
    --out "$OUT/${mode}_fixed_perf.csv"
done

echo "=== Fixed encaps 50k (performance) ==="
for mode in mlkem bike hybrid; do
  ./timing_bench --mode "$mode" --op encaps --input fixed --samples 50000 --warmup 200 --cpu "$CPU" \
    --out "$OUT/${mode}_encaps_fixed_perf.csv"
done

echo "=== Varying-ct 10k (performance) ==="
for mode in mlkem bike hybrid; do
  ./timing_bench --mode "$mode" --op decaps --input varying-ct --samples 10000 --warmup 100 --cpu "$CPU" \
    --out "$OUT/${mode}_varying_ct_perf.csv"
done

echo "=== Varying-key 50k (performance, parity with AMD) ==="
for mode in mlkem bike hybrid; do
  ./timing_bench --mode "$mode" --op decaps --input varying-key --samples 50000 --warmup 200 --cpu "$CPU" \
    --out "$OUT/${mode}_varying_key_50k.csv"
  cp "$OUT/${mode}_varying_key_50k.csv" "$OUT/${mode}_varying_key_perf.csv"
done

python3 analyze_intel_results.py
python3 analyze_intel.py 2>/dev/null || true
echo "Done. Send updated results_sc_timing_intel/ back to AMD."
