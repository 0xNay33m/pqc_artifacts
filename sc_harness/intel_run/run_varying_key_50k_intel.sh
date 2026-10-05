#!/usr/bin/env bash
# Platform B (Intel): varying-key decaps at n=50,000 under performance governor.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$ROOT/.." && pwd)"
OUT="${BUNDLE}/results_sc_timing_intel"
CPU="${CPU:-2}"
export LD_LIBRARY_PATH="${BUNDLE}/vendor/liboqs-install/lib:${LD_LIBRARY_PATH:-}"

mkdir -p "$OUT"

if [[ "${SKIP_SETUP_CPU:-0}" != "1" ]] && [[ -x "$ROOT/setup_cpu.sh" ]]; then
  sudo "$ROOT/setup_cpu.sh"
else
  echo "[info] SKIP_SETUP_CPU=1 — governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo unknown)"
fi

make -C "$ROOT" timing_bench

BACKUP="$OUT/varying_key_10k_backup"
if ls "$OUT"/*_varying_key*.csv >/dev/null 2>&1; then
  mkdir -p "$BACKUP"
  cp -a "$OUT"/*_varying_key*.csv "$BACKUP/" 2>/dev/null || true
  echo "[info] Backed up prior varying-key CSVs to $BACKUP"
fi

echo "=== Varying-key decaps (50k per mode, Intel / performance) ==="
for mode in mlkem bike hybrid; do
  echo "--- $mode ($(date -Iseconds)) ---"
  "$ROOT/timing_bench" --mode "$mode" --op decaps --input varying-key \
    --samples 50000 --warmup 200 --cpu "$CPU" \
    --out "$OUT/${mode}_varying_key_50k.csv"
  cp "$OUT/${mode}_varying_key_50k.csv" "$OUT/${mode}_varying_key_perf.csv"
done

echo "=== Analyse ==="
python3 "$ROOT/analyze_intel_results.py"
python3 "$ROOT/analyze_intel.py" 2>/dev/null || true
echo "Done $(date -Iseconds)"
