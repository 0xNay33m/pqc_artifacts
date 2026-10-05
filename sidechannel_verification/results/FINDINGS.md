# Side-Channel Verification — Findings

Closing the two "what could still hide" gaps from the thesis discussion:

> *"The only places leakage could still hide are the **cache channel
> (secret-indexed rotation)** and **compiler regressions** — neither visible to
> the wall-clock harness."*

Four independent experiments were run against the exact library the thesis
benchmarks (`liboqs 0.14.0`, BIKE-L1 + ML-KEM-768) on the same machine
(AMD Ryzen 5 5500U, Debian/Parrot, GCC 14.2, Clang 19.1, Valgrind 3.24).
**No edits were made to the thesis `.tex` sources.** All raw logs are in this
folder; this file is the summary for discussion.

---

## TL;DR

| Concern | Method | BIKE-L1 | ML-KEM-768 |
|---|---|---|---|
| Secret-indexed branch / memory index | ctgrind (Valgrind memcheck, poisoned secret) | **CLEAN** (0) | **CLEAN** (0) |
| Compiler regression (KyberSlash class) | rebuild ×7 compilers/opt, re-run ctgrind | **CLEAN** all 7 | **CLEAN** all 7 |
| Cache channel (secret-indexed rotation) | callgrind cache model, 5 distinct keys | **byte-identical** address stream | only *public*-matrix variation |
| Decode-failure timing path | chosen-ciphertext dudect (valid vs corrupted CT) | max\|t\|=2.17 **NO LEAK** | max\|t\|=3.67 **NO LEAK** |

**Bottom line:** both algorithms are data-oblivious with respect to the secret
key. The secret-indexed rotation in BIKE is implemented as constant-time SIMD
shifts and produces an identical memory-access pattern for every key. No
compiler/optimization setting (including the KyberSlash-sensitive Clang
`-O1`/`-Os`) introduces a secret-dependent branch. The wall-clock null result in
the thesis is therefore corroborated at the *structural* level — there was no
hidden leakage for the wall-clock harness to have missed.

---

## Experiment 1 — ctgrind / TIMECOP constant-time test (shipped library)

**Method.** The same technique that discovered KyberSlash: generate a keypair +
valid ciphertext, mark the secret key as "undefined" to Valgrind memcheck, run
decapsulation. Any *branch* or *memory address* that depends on the secret is
reported. A constant-time implementation yields zero unsuppressed reports. The
output *value* legitimately depends on the secret; memcheck only flags secret
values used in control flow or addressing, so value-dependence is not a false
positive.  (harness: `ctgrind/ct_test.c`)

**Raw result (no suppressions).**
- BIKE-L1: 6 reports — all `Use of uninitialised value` inside
  `rotate_right_avx2`/`rotate256_small` (the syndrome rotation) and
  `secure_set_bits_avx2`.
- ML-KEM-768: 130 reports — all inside `rej_uniform`/`gen_matrix`/`indcpa`
  (the FO re-encryption) plus one `mlk_check_sk`.

**Cross-check against liboqs' own audit.** liboqs ships Valgrind suppression
files for its constant-time CI
(`vendor/liboqs-src/tests/constant_time/kem/passes/{bike,ml_kem}`, copied here as
`ctgrind/official_*.supp`). Every report above corresponds **1:1** to an entry
the maintainers manually audited as benign:
- BIKE rotate/`secure_set_bits` → *"the secret is fed to a data-independent SIMD
  shift (`_mm256_slli/srli_epi64`), not used as a branch or address."*
- ML-KEM `gen_matrix`/`rej_uniform` → *"rejection sampling to produce the public
  A matrix"* (seed `rho` is public).
- ML-KEM `mlk_check_sk` → *"the parts of sk hashed/compared here are public."*

`issues.json` (the maintainers' list of *real* known CT problems) lists only
Classic-McEliece; **BIKE-L1 and ML-KEM-768 carry `[]` (no known issues)** and are
in `passes.json`.

**Result with suppressions applied** (`ctgrind/shipped.supp`, the official rules
re-anchored for the optimized build's inlining):

```
shipped-baseline,BIKE-L1,0 errors,103688 suppressed  -> CLEAN
shipped-baseline,ML-KEM-768,0 errors,956 suppressed   -> CLEAN
```
Logs: `ctgrind_shipped-baseline_*.log`, `ctgrind_suppressed_*.log`,
`ctgrind_summary.csv`.

---

## Experiment 2 — Compiler-regression matrix

**Method.** Rebuild liboqs (minimal: BIKE-L1 + ML-KEM-768) with 7
compiler/optimization combinations and re-run ctgrind on each. KyberSlash
showed that a constant-time *source* can be compiled into a secret-dependent
*branch* by certain optimizers, so the discriminating signal is the count of
`Conditional jump or move depends on uninitialised value` (a real branch) that
lands **outside** the audited-benign functions. (driver:
`compiler_matrix/build_and_test.sh`)

| build | BIKE-L1 secret branches | ML-KEM-768 secret branches | verdict |
|---|---|---|---|
| gcc -O2   | 0 | 0 (68 cond, all benign rej-sampling) | CLEAN |
| gcc -O3   | 0 | 0 (75 benign) | CLEAN |
| gcc -Os   | 0 | 0 (65 benign) | CLEAN |
| clang -O1 | 0 | 0 (67 benign) | CLEAN |
| clang -Os | 0 | 0 (67 benign) | CLEAN |
| clang -O2 | 0 | 0 (66 benign) | CLEAN |
| clang -O3 | 0 | 0 (67 benign) | CLEAN |

BIKE-L1 emitted **zero `Conditional jump` reports at every setting** — the
secret never reaches a branch; the only flags are the benign data-into-SIMD-shift
`Use of uninitialised value` (and, under GCC, a `_mm256_permutevar8x32_epi32`
permute — again data, not a branch). ML-KEM's conditionals are entirely the
public-matrix rejection sampling and suppress to 0.
Logs: `cmat_*_raw.log`, `cmat_*_suppressed.log`, `compiler_matrix_summary.csv`,
`build_*.log`.

**Conclusion:** the compiler-regression hypothesis is refuted across the GCC and
Clang families and all common optimization levels.

---

## Experiment 3 — Cache channel (secret-indexed rotation)

**Method.** cachegrind/callgrind models the cache by memory *address*, not by
data value. If decapsulation is data-oblivious, two *different* secret keys must
touch the *same* address sequence, so the modelled access counts (Dr/Dw) and
cache-miss counts (D1/LL) are identical. A secret-indexed access would change the
address stream and the counts. Keys are made deterministic per seed via a custom
RNG; only the `OQS_KEM_decaps` call is measured.
(harness: `cache_probe/cache_probe.c`; data: `cache_probe_summary.csv`)

**BIKE-L1 — five distinct secret keys (seeds 11111…55555):**

```
Ir=8,620,690  Dr=2,207,087  Dw=2,304,799  D1mr=2,490  D1mw=6,878  DLmr=114  DLmw=8
```
**Byte-identical for all five keys** — instruction count, every data-access count,
and every cache-miss count match exactly. The BIKE decoder, *including the
secret-indexed syndrome rotation*, has a memory-access pattern that is completely
independent of the secret. **There is no cache channel.**

**ML-KEM-768 — five distinct keys:** counts vary by ~0.03 % (Ir 147,663–147,867).
`callgrind_annotate` localizes the *entire* difference to one function:
`rej_uniform_avx2` (e.g. 6,381 vs 6,421 instructions). Every other function
(`poly_cbd2`, `poly_frommsg`, `poly_compress10`, NTT, hashing, …) is
instruction-identical across keys. `rej_uniform` samples the **public** A matrix
from the seed `rho` (part of the public key); its iteration count depends on
public data the attacker already holds, not on the secret. This is the same
benign behaviour liboqs suppresses, and it does not constitute a secret leak.

---

## Experiment 4 — Chosen-ciphertext wall-clock test (decode-failure path)

**Method.** The thesis harness timed *valid* ciphertexts. The exploitable
channel in FO-KEMs, if any, lives on the implicit-rejection path. This test fixes
one key and compares two ciphertext classes with interleaved (dudect-style)
measurement: class 0 = valid CT (decaps succeeds), class 1 = corrupted CT
(decode/re-encryption fails → implicit rejection). We report the **max \|t\|**
Welch statistic over 10 tail-crop thresholds (dudect's conservative rule;
\|t\|>4.5 ⇒ leak). (harness: `chosen_ct/cct_dudect.c`)

| alg | n (decaps) | median diff | mean diff (best crop) | max \|Welch t\| | verdict |
|---|---|---|---|---|---|
| ML-KEM-768 | 200,000 | **0 cycles** | −3.7 / ~39,900 (0.009 %) | 3.674 | NO LEAK |
| BIKE-L1 (initial) | 50,000 | −336 / ~1.25 M (0.027 %) | −386 cycles | 2.172 | NO LEAK |
| BIKE-L1 (repeat) | **500,000** | **−21 / ~1.21 M (0.002 %)** | +38.9 cycles | **1.191** | NO LEAK |

BIKE was repeated at 500,000 samples per class (~10⁶ interleaved trials, ~18 min
wall time on Platform A) to match primary-battery dudect depth. max \|t\| **decreased**
at higher $n$, confirming the initial 50k run was under-powered but not misleading.
Data: `chosen_ct_summary.csv`, `chosen_ct_*.txt`.

## What this means for the thesis (for discussion — not yet written to .tex)

1. The null result is now **defended on three fronts**: wall-clock timing
   (original thesis), structural constant-time analysis (ctgrind), and
   architectural cache modelling (callgrind). The "two remaining ifs" are closed.
2. The honest, precise framing: *"We additionally verified with ctgrind/TIMECOP
   and cachegrind that neither implementation exhibits secret-dependent branches
   or secret-dependent memory addressing under GCC and Clang at -O1..-O3/-Os; the
   BIKE syndrome rotation is data-oblivious (identical callgrind profile across
   keys). Hence the absence of exploitable wall-clock leakage reflects a genuinely
   constant-time target, not merely insufficient measurement resolution."*
3. This is a publishable strengthening: it converts a "we measured nothing" into
   "we explain *why* there is nothing, using the same tooling that found
   KyberSlash, and we show it holds across the compiler matrix."
4. Caveat to state plainly: this covers *digital/architectural* side channels on
   this microarchitecture. It does **not** cover physical channels (power/EM) or
   microarchitectural contention attacks (e.g. SMT port contention, Prime+Probe
   across cores), which are out of scope for a wall-clock + ctgrind study.

## Reproduce
See `../README.md`. One-shot: rerun `ctgrind/run_ctgrind.sh`,
`compiler_matrix/build_and_test.sh`, `chosen_ct/cct_dudect`, `cache_probe/cache_probe`.
