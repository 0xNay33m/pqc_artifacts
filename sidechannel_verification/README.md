# sidechannel_verification

Follow-up experiments that close the two leakage gaps left open by the wall-clock
thesis harness: the **cache channel (secret-indexed rotation)** and **compiler
regressions**. Self-contained; does **not** modify the thesis `.tex` sources.
Read `results/FINDINGS.md` for the write-up.

Target: `liboqs 0.14.0`, BIKE-L1 + ML-KEM-768 (the thesis's own vendored build at
`../vendor/liboqs-install`, source at `../vendor/liboqs-src`).

## Layout
```
ctgrind/          ctgrind/TIMECOP constant-time test (poison secret, run memcheck)
  ct_test.c           harness
  run_ctgrind.sh      build + run vs a given liboqs install
  shipped.supp        suppressions for the optimized build (re-anchored official rules)
  official_*.supp     copies of liboqs' own CT suppression files (provenance)
compiler_matrix/  rebuild liboqs under GCC/Clang × -O1/-Os/-O2/-O3, re-run ctgrind
                    (build trees are not shipped; see "Compiler matrix" below)
chosen_ct/        chosen-ciphertext wall-clock dudect (valid vs decode-failure CT)
  cct_dudect.c
cache_probe/      callgrind cache-model probe across distinct keys (data-obliviousness)
  cache_probe.c
results/          all logs, CSVs, callgrind dumps, and FINDINGS.md
```

## Dependencies
`valgrind` (>=3.24), `cmake`, `ninja`, `gcc`, `clang`. Install:
`sudo apt-get install -y valgrind cmake`.

## Reproduce
```bash
cd sidechannel_verification
OQS=../vendor/liboqs-install

# 1. constant-time test on shipped library
./ctgrind/run_ctgrind.sh $OQS gcc shipped-baseline
#    then apply suppressions (see results/ctgrind_summary.csv)

# 2. compiler matrix: see "Compiler matrix" below

# 3. chosen-ciphertext wall-clock (governor=performance recommended)
gcc -O2 -I$OQS/include chosen_ct/cct_dudect.c -L$OQS/lib -Wl,-rpath,$OQS/lib -loqs -lm -o chosen_ct/cct_dudect
LD_LIBRARY_PATH=$OQS/lib taskset -c 2 ./chosen_ct/cct_dudect ML-KEM-768 200000
LD_LIBRARY_PATH=$OQS/lib taskset -c 2 ./chosen_ct/cct_dudect BIKE-L1 500000

# 4. cache probe (data-obliviousness across keys)
gcc -O2 -I$OQS/include cache_probe/cache_probe.c -L$OQS/lib -Wl,-rpath,$OQS/lib -loqs -lm -o cache_probe/cache_probe
for seed in 11111 22222 33333; do
  LD_LIBRARY_PATH=$OQS/lib valgrind --tool=callgrind --cache-sim=yes --collect-atstart=no \
    --callgrind-out-file=results/cg_$seed.out cache_probe/cache_probe BIKE-L1 $seed
  grep '^summary:' results/cg_$seed.out
done
```

## Compiler matrix

Seven liboqs builds (GCC `-O2`, `-O3`, `-Os`; Clang `-O1`, `-Os`, `-O2`, `-O3`; GCC 14.2.0, Clang 19.1.7),
each restricted to the two algorithms under test. The original driver script is not included. The
commands below are consistent with the recorded build logs (`results/build_*.log`: compiler identification
and the `KEM_bike_l1;KEM_ml_kem_768` algorithm filter). For each setting:

```bash
L=clang-O1; CCX=clang; OPT=-O1
cmake -S ../vendor/liboqs-src -B compiler_matrix/build_$L -GNinja \
  -DCMAKE_C_COMPILER=$CCX -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS_RELEASE="$OPT" \
  -DOQS_MINIMAL_BUILD="KEM_bike_l1;KEM_ml_kem_768" -DOQS_USE_OPENSSL=OFF \
  -DCMAKE_INSTALL_PREFIX=$PWD/compiler_matrix/install_$L
ninja -C compiler_matrix/build_$L install
./ctgrind/run_ctgrind.sh $PWD/compiler_matrix/install_$L $CCX $L
```

Raw and suppressed memcheck logs for every setting are in `results/cmat_*`, and the summary is in
`results/compiler_matrix_summary.csv`.

## Note on the system
The chosen-ct run temporarily set the CPU governor to `performance` for timing
stability; it was restored to `powersave` (the amd-pstate-epp default) afterward.
No system files outside this directory were modified except installing the two
dev packages above.
