/*
 * Chosen-ciphertext wall-clock timing test (dudect-style fixed-vs-random class).
 *
 * Motivation: the thesis harness timed decapsulation of *valid* ciphertexts.
 * The exploitable timing channel in FO-KEMs, if any, lives on the
 * implicit-rejection path: a ciphertext that DECODES/RE-ENCRYPTS incorrectly.
 * This harness compares two ciphertext classes against a single fixed key:
 *
 *   class 0 : a valid ciphertext (decaps succeeds)
 *   class 1 : a corrupted ciphertext (decode/re-encryption fails -> implicit
 *             rejection returns a pseudorandom shared secret)
 *
 * Measurements are interleaved (random class per trial, dudect-style) to cancel
 * slow drift. We report Welch's t statistic on percentile-cropped cycle counts.
 * dudect's decision rule: |t| > 4.5  =>  timing leakage detected.
 *
 * Usage: cct_dudect <ALG> <num_measurements>
 */
#include <oqs/oqs.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>
#include <time.h>

static inline uint64_t rdtscp_now(void)
{
    unsigned aux;
    return __builtin_ia32_rdtscp(&aux);
}

typedef struct { double mean, m2; uint64_t n; } welch_acc;
static void acc_push(welch_acc *a, double x) {
    a->n++;
    double d = x - a->mean;
    a->mean += d / (double)a->n;
    a->m2 += d * (x - a->mean);
}
static double acc_var(const welch_acc *a){ return a->n > 1 ? a->m2/(double)(a->n-1) : 0.0; }

static int cmp_u64(const void *p, const void *q){
    uint64_t a=*(const uint64_t*)p, b=*(const uint64_t*)q;
    return (a>b)-(a<b);
}

int main(int argc, char **argv)
{
    const char *alg = (argc > 1) ? argv[1] : "BIKE-L1";
    uint64_t N = (argc > 2) ? strtoull(argv[2], NULL, 10) : 200000;

    OQS_KEM *kem = OQS_KEM_new(alg);
    if (!kem) { fprintf(stderr, "alg not enabled: %s\n", alg); return 2; }

    uint8_t *pk = malloc(kem->length_public_key);
    uint8_t *sk = malloc(kem->length_secret_key);
    uint8_t *ct_valid = malloc(kem->length_ciphertext);
    uint8_t *ct_bad   = malloc(kem->length_ciphertext);
    uint8_t *ss_enc   = malloc(kem->length_shared_secret);
    uint8_t *ss_out   = malloc(kem->length_shared_secret);

    if (OQS_KEM_keypair(kem, pk, sk) != OQS_SUCCESS) return 3;
    if (OQS_KEM_encaps(kem, ct_valid, ss_enc, pk) != OQS_SUCCESS) return 4;

    /* class 1: corrupt a copy so decode / re-encryption fails. We flip a chunk
     * of bytes in the first part of the ciphertext (the code/poly component). */
    memcpy(ct_bad, ct_valid, kem->length_ciphertext);
    for (size_t i = 0; i < kem->length_ciphertext / 4; i++) ct_bad[i] ^= 0x5A;

    /* sanity: confirm the two classes really take different decode paths */
    OQS_STATUS r0 = OQS_KEM_decaps(kem, ss_out, ct_valid, sk);
    OQS_STATUS r1 = OQS_KEM_decaps(kem, ss_out, ct_bad,   sk);
    fprintf(stderr, "INFO: %s valid_rc=%d corrupted_rc=%d (both run full decaps)\n",
            alg, (int)r0, (int)r1);

    uint64_t *t0 = malloc(N * sizeof(uint64_t));
    uint64_t *t1 = malloc(N * sizeof(uint64_t));
    uint64_t n0 = 0, n1 = 0;
    if (!t0 || !t1) { fprintf(stderr, "alloc fail\n"); return 5; }

    /* warm up */
    for (int i = 0; i < 2000; i++) OQS_KEM_decaps(kem, ss_out, ct_valid, sk);

    srand(12345);
    for (uint64_t i = 0; i < 2 * N; i++) {
        int cls = rand() & 1;
        const uint8_t *ct = cls ? ct_bad : ct_valid;
        uint64_t a = rdtscp_now();
        OQS_KEM_decaps(kem, ss_out, ct, sk);
        uint64_t b = rdtscp_now();
        uint64_t dt = b - a;
        if (cls == 0 && n0 < N) t0[n0++] = dt;
        else if (cls == 1 && n1 < N) t1[n1++] = dt;
        if (n0 >= N && n1 >= N) break;
    }

    /* dudect-faithful analysis: compute Welch t for MANY upper-crop thresholds
     * (to discard OS/IRQ tail noise) and report the MAX |t| over all crops.
     * This is the conservative statistic dudect uses; if even the worst-case
     * crop stays below 4.5 the implementation is indistinguishable. */
    uint64_t *all = malloc((n0 + n1) * sizeof(uint64_t));
    memcpy(all, t0, n0 * sizeof(uint64_t));
    memcpy(all + n0, t1, n1 * sizeof(uint64_t));
    qsort(all, n0 + n1, sizeof(uint64_t), cmp_u64);

    /* crop percentiles from 60% up to 100% */
    static const double pct[] = {0.60,0.65,0.70,0.75,0.80,0.85,0.90,0.95,0.975,1.00};
    double max_abs_t = 0.0, t_at_max = 0.0, diff_at_max = 0.0;
    double best_m0 = 0.0, best_m1 = 0.0; uint64_t best_cut = 0, best_n0=0, best_n1=0;

    for (size_t k = 0; k < sizeof(pct)/sizeof(pct[0]); k++) {
        uint64_t idx = (uint64_t)((n0 + n1 - 1) * pct[k]);
        uint64_t cutoff = all[idx];
        welch_acc a0 = {0}, a1 = {0};
        for (uint64_t i = 0; i < n0; i++) if (t0[i] <= cutoff) acc_push(&a0, (double)t0[i]);
        for (uint64_t i = 0; i < n1; i++) if (t1[i] <= cutoff) acc_push(&a1, (double)t1[i]);
        if (a0.n < 100 || a1.n < 100) continue;
        double se = sqrt(acc_var(&a0)/(double)a0.n + acc_var(&a1)/(double)a1.n);
        double t = se > 0 ? (a0.mean - a1.mean)/se : 0.0;
        if (fabs(t) > max_abs_t) {
            max_abs_t = fabs(t); t_at_max = t; diff_at_max = a0.mean - a1.mean;
            best_m0 = a0.mean; best_m1 = a1.mean; best_cut = cutoff;
            best_n0 = a0.n; best_n1 = a1.n;
        }
    }

    /* robust medians (full data) */
    qsort(t0, n0, sizeof(uint64_t), cmp_u64);
    qsort(t1, n1, sizeof(uint64_t), cmp_u64);
    uint64_t med0 = t0[n0/2], med1 = t1[n1/2];

    const char *verdict = (max_abs_t > 4.5)
        ? "LEAK (max|t|>4.5): decode-failure path distinguishable by timing"
        : "NO LEAK (max|t|<=4.5): valid vs decode-failure indistinguishable";

    printf("alg=%s\n", alg);
    printf("n_valid=%llu n_corrupted=%llu\n",
           (unsigned long long)n0, (unsigned long long)n1);
    printf("best-crop: cutoff=%llu cycles (n_valid=%llu n_corrupted=%llu)\n",
           (unsigned long long)best_cut,
           (unsigned long long)best_n0, (unsigned long long)best_n1);
    printf("mean_valid=%.1f mean_corrupted=%.1f diff=%.1f cycles (at max-|t| crop)\n",
           best_m0, best_m1, diff_at_max);
    printf("median_valid=%llu median_corrupted=%llu (diff=%lld cycles)\n",
           (unsigned long long)med0, (unsigned long long)med1,
           (long long)med0 - (long long)med1);
    printf("MAX_ABS_WELCH_T=%.3f (signed %.3f) over %zu crop thresholds\n",
           max_abs_t, t_at_max, sizeof(pct)/sizeof(pct[0]));
    printf("VERDICT: %s\n", verdict);

    fprintf(stderr, "CSV,%s,%llu,%.1f,%.1f,%.1f,%lld,%.3f\n", alg,
            (unsigned long long)(n0 + n1), best_m0, best_m1, diff_at_max,
            (long long)med0 - (long long)med1, max_abs_t);

    free(pk); free(sk); free(ct_valid); free(ct_bad);
    free(ss_enc); free(ss_out); free(t0); free(t1); free(all);
    OQS_KEM_free(kem);
    return 0;
}
