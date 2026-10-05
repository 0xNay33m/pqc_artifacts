#!/usr/bin/env bash
# Intel Platform B — single entry point for all thesis timing experiments.
#
# Default (priority): varying-key decaps n=50,000 under performance governor
#   ./RUN_INTEL.sh
#
# Full battery (steps 1–8, ~1–2 h):
#   ./RUN_INTEL.sh --full
#
# Varying-key + dudect verification (~2 h):
#   ./RUN_INTEL.sh --with-dudect
#
# Preflight only (no benchmarks):
#   ./RUN_INTEL.sh --check-only
#
# Options:
#   CPU=1 ./RUN_INTEL.sh
#   DUDECT_SAMPLES=50000 ./RUN_INTEL.sh --with-dudect
#   SKIP_SETUP_CPU=1 ./RUN_INTEL.sh          # not recommended
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
HARNESS="$ROOT/sc_harness"
OUT="$ROOT/results_sc_timing_intel"
STAB="$OUT/stability"
LOG="$OUT/run.log"
REPORT="$OUT/RUN_REPORT.txt"
CPU="${CPU:-2}"
DUDECT_SAMPLES="${DUDECT_SAMPLES:-500000}"
VARYING_KEY_SAMPLES="${VARYING_KEY_SAMPLES:-50000}"
MODES=(mlkem bike hybrid)

MODE="varying-key"
CHECK_ONLY=0

mkdir -p "$OUT" "$STAB"

log()  { local msg="[$(date -Iseconds)] $*"; echo "$msg" | tee -a "$LOG"; }
ok()   { log "OK   $*"; }
warn() { log "WARN $*"; }
die()  { log "FAIL $*"; echo ""; echo "See log: $LOG"; exit 1; }

on_err() {
  local line="$1"
  log "ERROR: command failed at line $line (exit $?)"
  echo "Run aborted. Partial results may be in $OUT"
  exit 1
}
trap 'on_err $LINENO' ERR
trap 'log "Interrupted by user"; exit 130' INT TERM

usage() {
  cat <<'EOF'
Usage: ./RUN_INTEL.sh [OPTIONS]

  (no flags)       Varying-key decaps 50k × 3 modes + analysis + tarball  [~30–45 min]
  --full           Complete battery: fixed, encaps, varying-ct/key, dudect, legs  [~1–2 h]
  --with-dudect    Varying-key 50k then dudect re-run under performance      [~2 h]
  --check-only     Setup + preflight tests only (no benchmarks)
  -h, --help       Show this help

Environment:
  CPU=2                 Pin benchmark core (default 2)
  DUDECT_SAMPLES=500000 Samples per dudect class (default 500000)
  SKIP_SETUP_CPU=1      Skip governor pinning (not recommended)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --full)       MODE="full" ;;
    --with-dudect) MODE="with-dudect" ;;
    --check-only) CHECK_ONLY=1 ;;
    -h|--help)    usage; exit 0 ;;
    *) die "Unknown option: $1 (try --help)" ;;
  esac
  shift
done

: >"$LOG"
log "=== RUN_INTEL.sh start (mode=$MODE check_only=$CHECK_ONLY) ==="
log "Bundle: $ROOT"

export LD_LIBRARY_PATH="$ROOT/vendor/liboqs-install/lib:${LD_LIBRARY_PATH:-}"

step() { log ""; log "── $* ──"; }

verify_governor() {
  local gov
  gov="$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo unknown)"
  if [[ "$gov" != "performance" ]]; then
    if [[ "${SKIP_SETUP_CPU:-0}" == "1" ]]; then
      warn "Governor is '$gov' (SKIP_SETUP_CPU=1)"
    else
      die "Governor is '$gov', expected 'performance'. Run: sudo $HARNESS/setup_cpu.sh"
    fi
  else
    ok "Governor: performance"
  fi
}

verify_csv() {
  local file="$1" min_rows="$2" label="$3"
  [[ -f "$file" ]] || die "Missing output: $file ($label)"
  local rows
  rows=$(wc -l <"$file")
  if [[ "$rows" -lt "$min_rows" ]]; then
    die "$label: $file has $rows lines, expected >= $min_rows"
  fi
  ok "$label: $file ($rows lines)"
}

# ── Phase 1: platform record ──────────────────────────────────────────────────
step "Phase 1 — Platform info"
{
  echo "run_date: $(date -Iseconds)"
  echo "mode: $MODE"
  echo "cpu_affinity: $CPU"
  echo "varying_key_samples: $VARYING_KEY_SAMPLES"
  echo "dudect_samples_per_class: $DUDECT_SAMPLES"
  echo "governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo unknown)"
  lscpu | head -24
  uname -a
} | tee "$OUT/platform_info.txt" >>"$LOG"
ok "Wrote $OUT/platform_info.txt"

# ── Phase 2: dependencies ─────────────────────────────────────────────────────
step "Phase 2 — Dependencies"
for cmd in gcc make python3; do
  command -v "$cmd" >/dev/null || die "Missing: $cmd (sudo apt-get install build-essential python3)"
  ok "$cmd -> $(command -v "$cmd")"
done

[[ -f "$ROOT/vendor/liboqs-install/lib/liboqs.so.0.14.0" ]] \
  || die "Missing liboqs — vendor/liboqs-install not found"

if ! python3 -c "import numpy, scipy" 2>/dev/null; then
  log "Installing Python packages..."
  if command -v apt-get >/dev/null; then
    sudo apt-get update -qq || warn "apt-get update failed"
    sudo apt-get install -y build-essential python3 python3-pip \
      || die "apt-get install failed"
    python3 -m pip install --user numpy scipy matplotlib \
      || sudo apt-get install -y python3-numpy python3-scipy python3-matplotlib \
      || die "Could not install numpy/scipy"
  else
    die "numpy/scipy missing and apt-get unavailable"
  fi
fi
python3 -c "import numpy, scipy" || die "numpy/scipy still not importable"
ok "numpy/scipy available"

free_mb=$(df -Pm "$OUT" | awk 'NR==2 {print $4}')
if [[ "${free_mb:-0}" -lt 200 ]]; then
  warn "Low disk space: ${free_mb}MB free in $OUT (recommend >= 250MB for dudect)"
else
  ok "Disk space: ${free_mb}MB free"
fi

# ── Phase 3: build ────────────────────────────────────────────────────────────
step "Phase 3 — Build sc_harness"
chmod +x "$HARNESS/setup_cpu.sh" 2>/dev/null || true
make -C "$HARNESS" clean all >>"$LOG" 2>&1
[[ -x "$HARNESS/timing_bench" ]] || die "Build failed: timing_bench not found"
ok "Built timing_bench"

if [[ "$MODE" == "full" || "$MODE" == "with-dudect" ]]; then
  for bin in dudect_bench noise_bench leg_bench; do
    [[ -x "$HARNESS/$bin" ]] || die "Build failed: $bin not found"
  done
  ok "Built dudect_bench, noise_bench, leg_bench"
fi

# ── Phase 4: smoke tests ──────────────────────────────────────────────────────
step "Phase 4 — Smoke tests"
SMOKE="/tmp/intel_run_intel_smoke_$$.csv"
"$HARNESS/timing_bench" --mode mlkem --op decaps --input fixed \
  --samples 5 --warmup 1 --cpu "$CPU" --out "$SMOKE" >>"$LOG" 2>&1
verify_csv "$SMOKE" 6 "smoke test (mlkem fixed)"
rm -f "$SMOKE"

SMOKE_VK="/tmp/intel_run_intel_vk_smoke_$$.csv"
"$HARNESS/timing_bench" --mode hybrid --op decaps --input varying-key \
  --samples 3 --warmup 1 --cpu "$CPU" --out "$SMOKE_VK" >>"$LOG" 2>&1
verify_csv "$SMOKE_VK" 4 "smoke test (hybrid varying-key)"
rm -f "$SMOKE_VK"

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  step "Check-only complete"
  ok "All preflight tests passed. Run without --check-only to execute benchmarks."
  exit 0
fi

# ── Phase 5: CPU governor ───────────────────────────────────────────────────────
step "Phase 5 — CPU governor (performance)"
if [[ "${SKIP_SETUP_CPU:-0}" == "1" ]]; then
  warn "SKIP_SETUP_CPU=1 — not pinning governor"
else
  sudo "$HARNESS/setup_cpu.sh" >>"$LOG" 2>&1 \
    || die "setup_cpu.sh failed (need sudo for performance governor)"
fi
verify_governor

# ── Phase 6: benchmarks ─────────────────────────────────────────────────────────
run_varying_key_50k() {
  step "Phase 6 — Varying-key decaps (${VARYING_KEY_SAMPLES}/mode)"
  local backup="$OUT/varying_key_backup_$(date +%Y%m%d_%H%M%S)"
  if ls "$OUT"/*_varying_key*.csv >/dev/null 2>&1; then
    mkdir -p "$backup"
    cp -a "$OUT"/*_varying_key*.csv "$backup/" 2>/dev/null || true
    ok "Backed up prior varying-key CSVs to $backup"
  fi

  local min_rows=$((VARYING_KEY_SAMPLES + 1))
  for mode in "${MODES[@]}"; do
    log "  -> $mode varying-key (started $(date -Iseconds))"
    "$HARNESS/timing_bench" --mode "$mode" --op decaps --input varying-key \
      --samples "$VARYING_KEY_SAMPLES" --warmup 200 --cpu "$CPU" \
      --out "$OUT/${mode}_varying_key_50k.csv" >>"$LOG" 2>&1
    verify_csv "$OUT/${mode}_varying_key_50k.csv" "$min_rows" "$mode varying-key 50k"
    cp "$OUT/${mode}_varying_key_50k.csv" "$OUT/${mode}_varying_key_perf.csv"
    cp "$OUT/${mode}_varying_key_50k.csv" "$OUT/${mode}_varying_key.csv"
  done
}

run_dudect() {
  step "Phase 6b — Dudect two-class (${DUDECT_SAMPLES}/class)"
  verify_governor
  for mode in "${MODES[@]}"; do
    log "  -> dudect $mode (started $(date -Iseconds))"
    "$HARNESS/dudect_bench" --mode "$mode" --samples-per-class "$DUDECT_SAMPLES" \
      --warmup 200 --cpu "$CPU" --out "$OUT/${mode}_dudect.csv" >>"$LOG" 2>&1
    [[ -s "$OUT/${mode}_dudect.csv" ]] || die "dudect output empty: ${mode}_dudect.csv"
    ok "dudect $mode -> ${mode}_dudect.csv"
  done
  # annotate governor for dudect in platform info
  echo "dudect_governor_at_run: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)" \
    >>"$OUT/platform_info.txt"
}

run_full_battery() {
  step "Phase 6 — Full battery (steps 1–8)"

  for mode in "${MODES[@]}"; do
    log "  -> fixed decaps $mode"
    "$HARNESS/timing_bench" --mode "$mode" --op decaps --input fixed \
      --samples 50000 --warmup 200 --cpu "$CPU" --out "$OUT/${mode}_fixed.csv" >>"$LOG" 2>&1
    cp "$OUT/${mode}_fixed.csv" "$OUT/${mode}_fixed_perf.csv"
    verify_csv "$OUT/${mode}_fixed.csv" 50001 "$mode fixed decaps"
  done

  for mode in "${MODES[@]}"; do
    log "  -> fixed encaps $mode"
    "$HARNESS/timing_bench" --mode "$mode" --op encaps --input fixed \
      --samples 50000 --warmup 200 --cpu "$CPU" --out "$OUT/${mode}_encaps_fixed.csv" >>"$LOG" 2>&1
    cp "$OUT/${mode}_encaps_fixed.csv" "$OUT/${mode}_encaps_fixed_perf.csv"
    verify_csv "$OUT/${mode}_encaps_fixed.csv" 50001 "$mode fixed encaps"
  done

  for mode in "${MODES[@]}"; do
    log "  -> varying-ct $mode"
    "$HARNESS/timing_bench" --mode "$mode" --op decaps --input varying-ct \
      --samples 10000 --warmup 100 --cpu "$CPU" --out "$OUT/${mode}_varying_ct.csv" >>"$LOG" 2>&1
    cp "$OUT/${mode}_varying_ct.csv" "$OUT/${mode}_varying_ct_perf.csv"
    verify_csv "$OUT/${mode}_varying_ct.csv" 10001 "$mode varying-ct"
  done

  run_varying_key_50k

  run_dudect

  log "  -> noise floor"
  "$HARNESS/noise_bench" --samples 50000 --warmup 200 --cpu "$CPU" \
    --out "$OUT/noise_floor.csv" >>"$LOG" 2>&1
  verify_csv "$OUT/noise_floor.csv" 50001 "noise floor"

  log "  -> hybrid legs"
  "$HARNESS/leg_bench" --samples 10000 --warmup 100 --cpu "$CPU" \
    --out "$OUT/hybrid_legs.csv" >>"$LOG" 2>&1
  verify_csv "$OUT/hybrid_legs.csv" 10001 "hybrid legs"

  for run in 1 2 3 4 5; do
    for mode in "${MODES[@]}"; do
      "$HARNESS/timing_bench" --mode "$mode" --op decaps --input fixed \
        --samples 10000 --warmup 100 --cpu "$CPU" \
        --out "$STAB/${mode}_run${run}.csv" >>"$LOG" 2>&1
    done
  done
  ok "Stability runs 1–5 complete"
}

case "$MODE" in
  varying-key)   run_varying_key_50k ;;
  with-dudect)   run_varying_key_50k; run_dudect ;;
  full)          run_full_battery ;;
  *)             die "Internal error: unknown MODE=$MODE" ;;
esac

# ── Phase 7: analysis + report ────────────────────────────────────────────────
step "Phase 7 — Analysis and report"
cd "$HARNESS"
python3 analyze_intel_results.py >>"$LOG" 2>&1 \
  || die "analyze_intel_results.py failed"
ok "Wrote $OUT/summary_stats.json"

python3 analyze_intel.py >>"$LOG" 2>&1 || warn "analyze_intel.py skipped (AMD paths may be absent on Intel)"

python3 - "$OUT" "$REPORT" <<'PY'
import json, sys
from pathlib import Path
out, report = Path(sys.argv[1]), Path(sys.argv[2])
stats = json.loads((out / "summary_stats.json").read_text())

def fmt_block(name):
    block = stats.get(name, {})
    if not block.get("hybrid"):
        return f"  {name}: (no data)\n"
    h, b, m = block["hybrid"], block["bike"], block["mlkem"]
    lines = [f"  [{name}] n={h.get('n','?')}"]
    for label, row in [("ML-KEM", m), ("BIKE", b), ("Hybrid", h)]:
        cv = row.get("cv", 0) * 100
        med = row.get("median_ns", 0) / 1000
        p99 = row.get("p99_ns", 0) / 1000
        lines.append(f"    {label:8s}  med={med:8.1f} µs  CV={cv:6.1f}%  P99={p99:8.1f} µs")
    if b.get("cv") and h.get("cv") and b["cv"] > 0:
        lines.append(f"    Hybrid/BIKE CV ratio: {h['cv']/b['cv']:.1f}×")
    return "\n".join(lines) + "\n"

gov = "governor: unknown"
pi = out / "platform_info.txt"
if pi.exists():
    for line in pi.read_text().splitlines():
        if "governor" in line.lower():
            gov = line
            break

lines = [
    "=" * 60,
    "INTEL RUN REPORT",
    f"Platform: {stats.get('platform', 'Intel Core i5-8350U')}",
    gov,
    "=" * 60,
    "",
    "VARYING-KEY (parity with AMD n=50,000, performance governor):",
    fmt_block("varying_key_50k"),
]
if not stats.get("varying_key_50k", {}).get("hybrid"):
    lines += ["Prior session (lower n):", fmt_block("varying_key_perf")]

d = stats.get("dudect", {}).get("hybrid", {})
lines += [
    "",
    "DUDECT hybrid:",
    (f"  |t|={abs(d.get('welch_t_raw',0)):.2f}  |t_m|={abs(d.get('welch_t_moment',0)):.2f}  "
     f"leakage_flag={d.get('leakage_flag_raw')}") if d else "  (not run this session)",
    "",
    "AMD reference (Platform A): hybrid CV≈141%  BIKE CV≈8.0%  ratio≈17×",
    "",
    "How to read Intel varying-key 50k:",
    "  Hybrid CV < 20%  → platform-specific tail; Intel does not replicate AMD magnitude",
    "  Hybrid CV ~100%+ → key-rotation tail may be broader x86 hybrid behaviour",
    "=" * 60,
    f"Full stats: {out / 'summary_stats.json'}",
    f"Run log:    {out / 'run.log'}",
]
text = "\n".join(lines) + "\n"
report.write_text(text)
print(text)
PY
ok "Wrote $REPORT"

# ── Phase 8: package ────────────────────────────────────────────────────────────
step "Phase 8 — Package results"
TARBALL="$ROOT/intel_results_for_amd.tar.gz"
tar czf "$TARBALL" -C "$ROOT" results_sc_timing_intel
ok "Created $TARBALL ($(du -h "$TARBALL" | cut -f1))"

log ""
log "=== RUN_INTEL.sh complete ==="
log "Results:  $OUT"
log "Report:   $REPORT"
log "Send back: $TARBALL"
cat "$REPORT"
