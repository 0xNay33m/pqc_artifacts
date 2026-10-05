#!/usr/bin/env bash
# Run timing benchmarks for all three KEM modes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
OUT_DIR="${ROOT}/../results_sc_timing"
SAMPLES="${SAMPLES:-50000}"
CPU="${CPU:-2}"
WARMUP="${WARMUP:-200}"

export LD_LIBRARY_PATH="${ROOT}/../vendor/liboqs-install/lib:${LD_LIBRARY_PATH:-}"

make -C "$ROOT" clean all

mkdir -p "$OUT_DIR"

for mode in mlkem bike hybrid; do
  echo "=== timing: $mode ($SAMPLES samples) ==="
  "$ROOT/timing_bench" \
    --mode "$mode" \
    --samples "$SAMPLES" \
    --warmup "$WARMUP" \
    --cpu "$CPU" \
    --out "$OUT_DIR/${mode}_timing.csv"
done

echo "Timing CSVs written to $OUT_DIR"
