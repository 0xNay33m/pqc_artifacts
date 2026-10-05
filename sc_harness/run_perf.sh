#!/usr/bin/env bash
# Collect perf stat counters during decaps loops (one summary per mode).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="${ROOT}/../results_sc_cache"
SAMPLES="${PERF_SAMPLES:-5000}"
CPU="${CPU:-2}"

export LD_LIBRARY_PATH="${ROOT}/../vendor/liboqs-install/lib:${LD_LIBRARY_PATH:-}"

make -C "$ROOT" -q timing_bench 2>/dev/null || make -C "$ROOT" all
mkdir -p "$OUT_DIR"

EVENTS="cycles,instructions,cache-references,cache-misses,branch-instructions,branch-misses"

for mode in mlkem bike hybrid; do
  echo "=== perf: $mode ($SAMPLES decaps) ==="
  out="$OUT_DIR/${mode}_perf.txt"
  taskset -c "$CPU" perf stat -e "$EVENTS" -o "$out" -- \
    "$ROOT/timing_bench" \
      --mode "$mode" \
      --samples "$SAMPLES" \
      --warmup 100 \
      --cpu "$CPU" \
      --out "$OUT_DIR/${mode}_perf_samples.csv" 2>&1 | tee "$OUT_DIR/${mode}_perf_log.txt" || true
done

echo "Perf outputs written to $OUT_DIR"
