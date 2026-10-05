#define _GNU_SOURCE
#include "hybrid_kem.h"
#include "timing_util.h"

#include <errno.h>
#include <inttypes.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int pin_cpu(int cpu) {
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    return sched_setaffinity(0, sizeof(set), &set);
}

int main(int argc, char **argv) {
    size_t samples = 10000;
    size_t warmup = 100;
    int cpu = 2;
    const char *out_path = NULL;
    hybrid_ctx_t ctx;
    FILE *out;
    size_t i;
    volatile uint8_t sink = 0;

    for (i = 1; i < (size_t)argc; i++) {
        if (strcmp(argv[i], "--samples") == 0 && i + 1 < (size_t)argc) samples = (size_t)strtoull(argv[++i], NULL, 10);
        else if (strcmp(argv[i], "--out") == 0 && i + 1 < (size_t)argc) out_path = argv[++i];
        else if (strcmp(argv[i], "--cpu") == 0 && i + 1 < (size_t)argc) cpu = atoi(argv[++i]);
        else if (strcmp(argv[i], "--warmup") == 0 && i + 1 < (size_t)argc) warmup = (size_t)strtoull(argv[++i], NULL, 10);
    }

    if (!out_path) {
        fprintf(stderr, "Usage: leg_bench --samples N --out file.csv\n");
        return 2;
    }

    pin_cpu(cpu);
    OQS_init();
    if (hybrid_ctx_init(&ctx, MODE_HYBRID) != 0 ||
        hybrid_keygen(&ctx) != 0 || hybrid_encaps(&ctx) != 0) {
        return 1;
    }

    for (i = 0; i < warmup; i++) {
        decaps_timing_t t;
        hybrid_decaps_timed(&ctx, &t);
        sink ^= ctx.master[0];
    }

    out = fopen(out_path, "w");
    if (!out) return 1;
    fprintf(out, "iteration,mlkem_ns,bike_ns,hkdf_ns,total_ns\n");

    for (i = 0; i < samples; i++) {
        decaps_timing_t t;
        if (hybrid_decaps_timed(&ctx, &t) != 0) return 1;
        sink ^= ctx.master[0];
        fprintf(out, "%zu,%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "\n",
                i + 1, t.mlkem_ns, t.bike_ns, t.hkdf_ns, t.total_ns);
    }

    fclose(out);
    hybrid_ctx_free(&ctx);
    OQS_destroy();
    (void)sink;
    return 0;
}
