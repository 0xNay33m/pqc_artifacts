# sc_harness — Side-channel measurement harness

Native C harness for comparative timing and cache-proxy evaluation of:
- **mlkem** — ML-KEM-768 decaps only
- **bike** — BIKE-L1 decaps only  
- **hybrid** — both legs + HKDF-SHA256 combiner

## Build

```bash
export LD_LIBRARY_PATH=../vendor/liboqs-install/lib:$LD_LIBRARY_PATH
make clean all
```

## Run

```bash
./run_timing.sh          # 50k warm samples × 3 modes
./run_cache_proxy.sh     # 10k warm + 10k cold × 3 modes
python3 analyze_results.py
```

## Binaries

| Binary | Purpose |
|--------|---------|
| `timing_bench` | High-volume warm-cache timing CSV |
| `cache_bench` | Warm vs LLC-cold eviction timing |
