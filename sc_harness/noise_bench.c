#define _GNU_SOURCE
#include "timing_util.h"

#include <errno.h>
#include <inttypes.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Noise floor: hybrid ciphertext bundle = ML-KEM-768 ct (1088 B) + BIKE-L1 ct (1573 B) = 2661 B. */
#define NOISE_BYTES 2661

static int pin_cpu(int cpu) {
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    return sched_setaffinity(0, sizeof(set), &set);
}

int main(int argc, char **argv) {
    size_t samples = 50000;
    size_t warmup = 200;
    int cpu = 2;
    const char *out_path = NULL;
    uint8_t *src;
    uint8_t *dst;
    FILE *out;
    size_t i;

    for (i = 1; i < (size_t)argc; i++) {
        if (strcmp(argv[i], "--samples") == 0 && i + 1 < (size_t)argc) samples = (size_t)strtoull(argv[++i], NULL, 10);
        else if (strcmp(argv[i], "--out") == 0 && i + 1 < (size_t)argc) out_path = argv[++i];
        else if (strcmp(argv[i], "--cpu") == 0 && i + 1 < (size_t)argc) cpu = atoi(argv[++i]);
        else if (strcmp(argv[i], "--warmup") == 0 && i + 1 < (size_t)argc) warmup = (size_t)strtoull(argv[++i], NULL, 10);
    }

    if (!out_path) {
        fprintf(stderr, "Usage: noise_bench --samples N --out file.csv [--cpu N]\n");
        return 2;
    }

    src = aligned_alloc(64, NOISE_BYTES);
    dst = aligned_alloc(64, NOISE_BYTES);
    if (!src || !dst) return 1;
    memset(src, 0xA5, NOISE_BYTES);

    pin_cpu(cpu);
    for (i = 0; i < warmup; i++) {
        memcpy(dst, src, NOISE_BYTES);
    }

    out = fopen(out_path, "w");
    if (!out) return 1;
    fprintf(out, "iteration,mode,input,elapsed_ns\n");

    for (i = 0; i < samples; i++) {
        uint64_t t0 = timing_nsec_now();
        memcpy(dst, src, NOISE_BYTES);
        uint64_t t1 = timing_nsec_now();
        fprintf(out, "%zu,noise,fixed,%" PRIu64 "\n", i + 1, t1 - t0);
    }

    fclose(out);
    free(src);
    free(dst);
    return 0;
}
