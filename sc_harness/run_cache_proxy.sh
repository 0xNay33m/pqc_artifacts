#!/usr/bin/env bash
# Cache sensitivity: warm vs LLC-cold decaps timing per mode.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="${ROOT}/../results_sc_cache"
SAMPLES="${CACHE_SAMPLES:-10000}"
CPU="${CPU:-2}"

export LD_LIBRARY_PATH="${ROOT}/../vendor/liboqs-install/lib:${LD_LIBRARY_PATH:-}"
make -C "$ROOT" cache_bench
mkdir -p "$OUT_DIR"

for mode in mlkem bike hybrid; do
  for cond in warm cold; do
    echo "=== cache proxy: $mode / $cond ==="
    "$ROOT/cache_bench" \
      --mode "$mode" \
      --condition "$cond" \
      --samples "$SAMPLES" \
      --warmup 100 \
      --cpu "$CPU" \
      --out "$OUT_DIR/${mode}_${cond}_cache.csv"
  done
done

echo "Cache-proxy CSVs written to $OUT_DIR"
