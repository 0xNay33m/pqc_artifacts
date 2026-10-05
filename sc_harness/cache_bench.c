#define _GNU_SOURCE
#include "hybrid_kem.h"
#include "timing_util.h"

#include <errno.h>
#include <inttypes.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define EVICT_BYTES (8u * 1024u * 1024u)

static uint8_t *evict_buf;
static size_t evict_len;

static uint64_t nsec_now(void) {
    return timing_nsec_now();
}

static int pin_cpu(int cpu) {
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    if (sched_setaffinity(0, sizeof(set), &set) != 0) {
        fprintf(stderr, "warn: sched_setaffinity(cpu=%d): %s\n", cpu, strerror(errno));
        return -1;
    }
    return 0;
}

static void touch_evict_buffer(void) {
    volatile uint8_t sink = 0;
    size_t i;
    for (i = 0; i < evict_len; i += 64) {
        sink ^= evict_buf[i];
    }
    (void)sink;
}

static kem_mode_t parse_mode(const char *s) {
    if (strcmp(s, "mlkem") == 0) return MODE_MLKEM;
    if (strcmp(s, "bike") == 0) return MODE_BIKE;
    if (strcmp(s, "hybrid") == 0) return MODE_HYBRID;
    fprintf(stderr, "unknown mode: %s\n", s);
    exit(2);
}

static void usage(const char *argv0) {
    fprintf(stderr,
            "Usage: %s --mode mlkem|bike|hybrid --samples N --out file.csv "
            "[--cpu N] [--warmup N] [--condition warm|cold]\n",
            argv0);
}

int main(int argc, char **argv) {
    const char *mode_str = NULL;
    const char *out_path = NULL;
    const char *condition = "warm";
    size_t samples = 10000;
    size_t warmup = 100;
    int cpu = 2;
    kem_mode_t mode;
    hybrid_ctx_t ctx;
    FILE *out;
    size_t i;
    volatile uint8_t sink = 0;

    for (i = 1; i < (size_t)argc; i++) {
        if (strcmp(argv[i], "--mode") == 0 && i + 1 < (size_t)argc) mode_str = argv[++i];
        else if (strcmp(argv[i], "--samples") == 0 && i + 1 < (size_t)argc) samples = (size_t)strtoull(argv[++i], NULL, 10);
        else if (strcmp(argv[i], "--out") == 0 && i + 1 < (size_t)argc) out_path = argv[++i];
        else if (strcmp(argv[i], "--cpu") == 0 && i + 1 < (size_t)argc) cpu = atoi(argv[++i]);
        else if (strcmp(argv[i], "--warmup") == 0 && i + 1 < (size_t)argc) warmup = (size_t)strtoull(argv[++i], NULL, 10);
        else if (strcmp(argv[i], "--condition") == 0 && i + 1 < (size_t)argc) condition = argv[++i];
        else if (strcmp(argv[i], "--help") == 0) { usage(argv[0]); return 0; }
        else { usage(argv[0]); return 2; }
    }

    if (!mode_str || !out_path) { usage(argv[0]); return 2; }

    evict_len = EVICT_BYTES;
    evict_buf = aligned_alloc(64, evict_len);
    if (!evict_buf) {
        fprintf(stderr, "evict buffer alloc failed\n");
        return 1;
    }
    memset(evict_buf, 1, evict_len);

    mode = parse_mode(mode_str);
    pin_cpu(cpu);
    OQS_init();

    if (hybrid_ctx_init(&ctx, mode) != 0 || hybrid_keygen(&ctx) != 0 || hybrid_encaps(&ctx) != 0) {
        fprintf(stderr, "setup failed\n");
        return 1;
    }

    for (i = 0; i < warmup; i++) {
        if (strcmp(condition, "cold") == 0) touch_evict_buffer();
        hybrid_decaps(&ctx);
    }

    out = fopen(out_path, "w");
    if (!out) {
        fprintf(stderr, "fopen failed\n");
        return 1;
    }

    fprintf(out, "iteration,mode,condition,elapsed_ns\n");
    for (i = 0; i < samples; i++) {
        if (strcmp(condition, "cold") == 0) touch_evict_buffer();
        uint64_t t0 = nsec_now();
        if (hybrid_decaps(&ctx) != 0) {
            fprintf(stderr, "decaps failed\n");
            return 1;
        }
        uint64_t t1 = nsec_now();
        sink ^= ctx.master[0];
        fprintf(out, "%zu,%s,%s,%" PRIu64 "\n", i + 1, hybrid_mode_label(mode), condition, t1 - t0);
    }

    fclose(out);
    hybrid_ctx_free(&ctx);
    OQS_destroy();
    free(evict_buf);
    (void)sink;
    return 0;
}
