#!/usr/bin/env bash
# Keygen-isolation battery (Platform A): corrected varying-key vs cooled vs legacy.
# Writes under results_sc_timing/keygen_isolation/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
OUT="${ROOT}/../results_sc_timing/keygen_isolation"
CPU="${CPU:-2}"
SAMPLES="${SAMPLES:-50000}"
export LD_LIBRARY_PATH="${ROOT}/../vendor/liboqs-install/lib:${LD_LIBRARY_PATH:-}"

if [[ "${SKIP_SETUP_CPU:-0}" != "1" ]] && [[ -x "$ROOT/setup_cpu.sh" ]]; then
  chmod +x "$ROOT/setup_cpu.sh"
  "$ROOT/setup_cpu.sh"
else
  echo "[info] SKIP_SETUP_CPU=1 — governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo unknown)"
fi

make -C "$ROOT" timing_bench
mkdir -p "$OUT"

echo "=== Keygen isolation (n=$SAMPLES) governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo unknown) ==="

# Protocols: corrected, cooled, and a short legacy check (10k) for continuity.
for proto in varying-key varying-key-cool; do
  for mode in mlkem bike hybrid; do
    echo "--- $proto / $mode ($(date -Iseconds)) ---"
    "$ROOT/timing_bench" --mode "$mode" --op decaps --input "$proto" \
      --samples "$SAMPLES" --warmup 200 --cpu "$CPU" \
      --out "$OUT/${mode}_${proto//-/_}.csv"
  done
done

LEGACY_N="${LEGACY_N:-50000}"
echo "=== Legacy thesis path (n=$LEGACY_N) for comparison ==="
for mode in mlkem bike hybrid; do
  echo "--- varying-key-legacy / $mode ($(date -Iseconds)) ---"
  "$ROOT/timing_bench" --mode "$mode" --op decaps --input varying-key-legacy \
    --samples "$LEGACY_N" --warmup 200 --cpu "$CPU" \
    --out "$OUT/${mode}_varying_key_legacy.csv"
done

echo "=== Analyse ==="
python3 "$ROOT/analyze_keygen_isolation.py" --dir "$OUT"
echo "Done $(date -Iseconds)"
