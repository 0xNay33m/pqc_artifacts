/*
 * ctgrind / TIMECOP-style constant-time test for liboqs KEM decapsulation.
 *
 * Method (Langley's ctgrind, as extended by KyberSlash):
 *   1. Generate a keypair and a *valid* ciphertext.
 *   2. Mark the SECRET KEY bytes as "undefined" (poisoned) to Valgrind memcheck.
 *   3. Run decapsulation.
 *   4. Under `valgrind --tool=memcheck`, ANY control-flow decision (branch) or
 *      memory-address computation that depends on the poisoned secret is
 *      reported as "Conditional jump or move depends on uninitialised value(s)"
 *      or "Use of uninitialised value...". A constant-time implementation
 *      produces ZERO such reports.
 *
 * This detects BOTH:
 *   - secret-dependent branches (the KyberSlash / Clang-regression class), and
 *   - secret-indexed memory access (the BIKE rotate-by-secret-position concern).
 *
 * The output VALUE legitimately depends on the secret; memcheck only flags
 * undefined values used in branches or as addresses, so value-dependence does
 * not cause false positives.
 *
 * Usage: ct_test <ALG> <poison:0|1>
 */
#include <oqs/oqs.h>
#include <valgrind/memcheck.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

int main(int argc, char **argv)
{
    const char *alg = (argc > 1) ? argv[1] : "BIKE-L1";
    int poison = (argc > 2) ? atoi(argv[2]) : 1;

    OQS_KEM *kem = OQS_KEM_new(alg);
    if (!kem) {
        fprintf(stderr, "ERROR: algorithm not enabled: %s\n", alg);
        return 2;
    }

    uint8_t *pk = malloc(kem->length_public_key);
    uint8_t *sk = malloc(kem->length_secret_key);
    uint8_t *ct = malloc(kem->length_ciphertext);
    uint8_t *ss_enc = malloc(kem->length_shared_secret);
    uint8_t *ss_dec = malloc(kem->length_shared_secret);
    if (!pk || !sk || !ct || !ss_enc || !ss_dec) {
        fprintf(stderr, "ERROR: malloc failed\n");
        return 2;
    }

    if (OQS_KEM_keypair(kem, pk, sk) != OQS_SUCCESS) {
        fprintf(stderr, "ERROR: keypair failed\n");
        return 3;
    }
    if (OQS_KEM_encaps(kem, ct, ss_enc, pk) != OQS_SUCCESS) {
        fprintf(stderr, "ERROR: encaps failed\n");
        return 4;
    }

    if (poison) {
        /* Secret-dependence detector: poison the secret key. */
        VALGRIND_MAKE_MEM_UNDEFINED(sk, kem->length_secret_key);
    }

    OQS_STATUS rc = OQS_KEM_decaps(kem, ss_dec, ct, sk);

    /* Re-define outputs so consuming them does not create spurious reports. */
    VALGRIND_MAKE_MEM_DEFINED(ss_dec, kem->length_shared_secret);
    VALGRIND_MAKE_MEM_DEFINED(&rc, sizeof(rc));

    volatile uint8_t sink = 0;
    for (size_t i = 0; i < kem->length_shared_secret; i++) sink ^= ss_dec[i];
    (void)sink;

    fprintf(stderr, "INFO: alg=%s poison=%d decaps_rc=%d\n",
            alg, poison, (int)rc);

    free(pk); free(sk); free(ct); free(ss_enc); free(ss_dec);
    OQS_KEM_free(kem);
    return 0;
}
