#!/usr/bin/env bash
# Build the ctgrind harness against a given liboqs install and run it under
# Valgrind memcheck for BIKE-L1 and ML-KEM-768. Captures full logs + a summary.
#
# Usage: run_ctgrind.sh <OQS_ROOT> <CC> <CFLAGS_LABEL> <CFLAGS...> 
#   OQS_ROOT       path to a liboqs install prefix (lib/ + include/)
#   CC             compiler for the harness (gcc|clang)
#   CFLAGS_LABEL   label for output files (e.g. shipped-gcc-O2, clang-O1)
# Remaining args are passed as CFLAGS for the harness build.
set -u

OQS_ROOT="${1:?need OQS_ROOT}"
CC="${2:?need CC}"
LABEL="${3:?need label}"
shift 3
HARNESS_CFLAGS="$*"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS="$HERE/../results"
mkdir -p "$RESULTS"

BIN="$HERE/ct_test_${LABEL}"

echo "[build] $CC $HARNESS_CFLAGS  (OQS_ROOT=$OQS_ROOT)"
$CC $HARNESS_CFLAGS -std=c11 -g -O1 \
    -I"$OQS_ROOT/include" \
    "$HERE/ct_test.c" \
    -L"$OQS_ROOT/lib" -Wl,-rpath,"$OQS_ROOT/lib" \
    -loqs -lm -o "$BIN" || { echo "BUILD FAILED"; exit 10; }

VG="valgrind --tool=memcheck --error-exitcode=99 --track-origins=yes -q"

for ALG in "BIKE-L1" "ML-KEM-768"; do
    SAFE_ALG="${ALG//[^A-Za-z0-9]/_}"
    LOG="$RESULTS/ctgrind_${LABEL}_${SAFE_ALG}.log"
    echo "[run ] $ALG poisoned-secret under memcheck -> $LOG"
    LD_LIBRARY_PATH="$OQS_ROOT/lib" $VG "$BIN" "$ALG" 1 \
        >"$LOG" 2>&1
    VG_RC=$?
    # Count secret-dependence reports
    ERRORS=$(grep -cE "depends on uninitialised|uninitialised value" "$LOG")
    if [ "$VG_RC" -eq 99 ] || [ "$ERRORS" -gt 0 ]; then
        VERDICT="LEAK (secret-dependent branch/index found: $ERRORS reports)"
    else
        VERDICT="CLEAN (no secret-dependent branch/index)"
    fi
    echo "    => $VERDICT"
    echo "${LABEL},${ALG},${ERRORS},${VG_RC},${VERDICT}" \
        >> "$RESULTS/ctgrind_summary.csv"
done
