/*
 * Cache-channel probe for the secret-indexed syndrome rotation in BIKE
 * (and, as a control, ML-KEM).
 *
 * Idea: cachegrind/callgrind model the cache by memory ADDRESS, not by data
 * value. If decapsulation is data-oblivious (constant-time), then two DIFFERENT
 * secret keys exercise the *same* sequence of memory addresses, so the modelled
 * data-access counts (Dr/Dw) and cache-miss counts (D1/LL) are IDENTICAL across
 * keys. If the rotation (or anything) indexed memory by a secret value, the
 * address stream -- and thus the miss counts -- would differ between keys.
 *
 * We make keygen/encaps/decaps fully deterministic per <seed> via a custom RNG,
 * and use CALLGRIND_TOGGLE_COLLECT so ONLY the decaps call is measured.
 * Run under: valgrind --tool=callgrind --cache-sim=yes --collect-atstart=no
 *
 * Usage: cache_probe <ALG> <seed>
 */
#include <oqs/oqs.h>
#include <valgrind/callgrind.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

/* deterministic splitmix64 RNG, seeded from argv */
static uint64_t g_state;
static void det_rng(uint8_t *out, size_t n) {
    size_t i = 0;
    while (i < n) {
        g_state += 0x9E3779B97F4A7C15ULL;
        uint64_t z = g_state;
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
        z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
        z = z ^ (z >> 31);
        size_t chunk = (n - i < 8) ? (n - i) : 8;
        memcpy(out + i, &z, chunk);
        i += chunk;
    }
}

int main(int argc, char **argv)
{
    const char *alg = (argc > 1) ? argv[1] : "BIKE-L1";
    uint64_t seed = (argc > 2) ? strtoull(argv[2], NULL, 10) : 1;
    g_state = seed;

    OQS_randombytes_custom_algorithm(det_rng);

    OQS_KEM *kem = OQS_KEM_new(alg);
    if (!kem) { fprintf(stderr, "alg not enabled: %s\n", alg); return 2; }

    uint8_t *pk = malloc(kem->length_public_key);
    uint8_t *sk = malloc(kem->length_secret_key);
    uint8_t *ct = malloc(kem->length_ciphertext);
    uint8_t *ss = malloc(kem->length_shared_secret);
    uint8_t *ssd = malloc(kem->length_shared_secret);

    if (OQS_KEM_keypair(kem, pk, sk) != OQS_SUCCESS) return 3;
    if (OQS_KEM_encaps(kem, ct, ss, pk) != OQS_SUCCESS) return 4;

    /* Measure ONLY decaps: toggle collection on around the call and let the
     * single termination dump report exactly the decaps event counts. Run with
     * --collect-atstart=no (no --toggle-collect / no explicit DUMP_STATS). */
    CALLGRIND_TOGGLE_COLLECT;
    OQS_STATUS rc = OQS_KEM_decaps(kem, ssd, ct, sk);
    CALLGRIND_TOGGLE_COLLECT;

    fprintf(stderr, "INFO: alg=%s seed=%llu decaps_rc=%d sk_byte0=%02x\n",
            alg, (unsigned long long)seed, (int)rc, sk[0]);

    free(pk); free(sk); free(ct); free(ss); free(ssd);
    OQS_KEM_free(kem);
    return 0;
}
