#!/usr/bin/env bash
# Pin CPU frequency governor to performance before timing experiments.
# Requires root for sysfs writes. isolcpus needs a kernel boot parameter.
set -euo pipefail

CPU="${CPU:-2}"
GOV="${GOV:-performance}"

log() { echo "[setup_cpu] $*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  log "Re-executing with sudo..."
  exec sudo -E "$0" "$@"
fi

log "Setting scaling_governor=$GOV on all CPUs"
for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
  if [[ -w "$g" ]] || [[ -w "$(dirname "$g")" ]]; then
    echo "$GOV" >"$g" 2>/dev/null || true
  fi
done

# Lock min frequency to max available when sysfs nodes exist (reduces P-state drift).
for cpu_dir in /sys/devices/system/cpu/cpu[0-9]*; do
  freq_dir="${cpu_dir}/cpufreq"
  [[ -d "$freq_dir" ]] || continue
  if [[ -r "${freq_dir}/scaling_max_freq" ]]; then
    max_f="$(cat "${freq_dir}/scaling_max_freq")"
    if [[ -w "${freq_dir}/scaling_min_freq" ]]; then
      echo "$max_f" >"${freq_dir}/scaling_min_freq" 2>/dev/null || true
    fi
  fi
done

log "Governor sample (cpu0): $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo n/a)"
if [[ -r /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq ]]; then
  log "Current freq (cpu0): $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq) kHz"
fi

if ! grep -q isolcpus /proc/cmdline 2>/dev/null; then
  log "warn: isolcpus not in kernel cmdline — CPU $CPU affinity via sched_setaffinity only"
fi

log "Done. Run benchmarks with CPU=$CPU"
