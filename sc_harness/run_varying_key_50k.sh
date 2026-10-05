#!/usr/bin/env bash
# Platform A: varying-key decaps at n=50,000 (parity with fixed-input battery).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
OUT="${ROOT}/../results_sc_timing"
CPU="${CPU:-2}"
export LD_LIBRARY_PATH="${ROOT}/../vendor/liboqs-install/lib:${LD_LIBRARY_PATH:-}"

if [[ "${SKIP_SETUP_CPU:-0}" != "1" ]] && [[ -x "$ROOT/setup_cpu.sh" ]]; then
  chmod +x "$ROOT/setup_cpu.sh"
  "$ROOT/setup_cpu.sh"
else
  echo "[info] SKIP_SETUP_CPU=1 — governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo unknown)"
fi

make -C "$ROOT" timing_bench
mkdir -p "$OUT"

echo "=== Varying-key decaps (50k per mode, Platform A) ==="
for mode in mlkem bike hybrid; do
  echo "--- $mode ($(date -Iseconds)) ---"
  "$ROOT/timing_bench" --mode "$mode" --op decaps --input varying-key \
    --samples 50000 --warmup 200 --cpu "$CPU" \
    --out "$OUT/${mode}_varying_key.csv"
done

echo "=== Analyse ==="
python3 "$ROOT/analyze_results.py"
echo "Done $(date -Iseconds)"
