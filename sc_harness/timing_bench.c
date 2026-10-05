#define _GNU_SOURCE
#include "hybrid_kem.h"
#include "timing_util.h"

#include <errno.h>
#include <inttypes.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* 8 MiB touch buffer to disturb LLC/TLB between setup and timed decaps. */
#define COOL_BYTES (8u * 1024u * 1024u)

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

static kem_mode_t parse_mode(const char *s) {
    if (strcmp(s, "mlkem") == 0) return MODE_MLKEM;
    if (strcmp(s, "bike") == 0) return MODE_BIKE;
    if (strcmp(s, "hybrid") == 0) return MODE_HYBRID;
    fprintf(stderr, "unknown mode: %s\n", s);
    exit(2);
}

static void cool_cache(uint8_t *buf, size_t n) {
    size_t i;
    volatile uint8_t sink = 0;
    for (i = 0; i < n; i += 64) {
        buf[i] = (uint8_t)(buf[i] + 1);
        sink ^= buf[i];
    }
    (void)sink;
}

static void usage(const char *argv0) {
    fprintf(stderr,
            "Usage: %s --mode mlkem|bike|hybrid --samples N --out file.csv\n"
            "       [--cpu N] [--warmup N]\n"
            "       [--input fixed|varying-ct|varying-key|varying-key-legacy|varying-key-cool]\n"
            "       [--op decaps|encaps]\n"
            "\n"
            "varying-key:         keygen+encaps outside timer, then timed decaps (corrected)\n"
            "varying-key-legacy:  keygen only outside timer (thesis path; CT may mismatch)\n"
            "varying-key-cool:    keygen+encaps+8MiB walk, then timed decaps\n",
            argv0);
}

static int is_varying_key_family(const char *input_mode) {
    return strcmp(input_mode, "varying-key") == 0
        || strcmp(input_mode, "varying-key-legacy") == 0
        || strcmp(input_mode, "varying-key-cool") == 0;
}

int main(int argc, char **argv) {
    const char *mode_str = NULL;
    const char *out_path = NULL;
    const char *input_mode = "fixed";
    const char *op = "decaps";
    size_t samples = 50000;
    size_t warmup = 200;
    int cpu = 2;
    kem_mode_t mode;
    hybrid_ctx_t ctx;
    FILE *out;
    size_t i;
    volatile uint8_t sink = 0;
    uint8_t *cool_buf = NULL;

    for (i = 1; i < (size_t)argc; i++) {
        if (strcmp(argv[i], "--mode") == 0 && i + 1 < (size_t)argc) mode_str = argv[++i];
        else if (strcmp(argv[i], "--samples") == 0 && i + 1 < (size_t)argc) samples = (size_t)strtoull(argv[++i], NULL, 10);
        else if (strcmp(argv[i], "--out") == 0 && i + 1 < (size_t)argc) out_path = argv[++i];
        else if (strcmp(argv[i], "--cpu") == 0 && i + 1 < (size_t)argc) cpu = atoi(argv[++i]);
        else if (strcmp(argv[i], "--warmup") == 0 && i + 1 < (size_t)argc) warmup = (size_t)strtoull(argv[++i], NULL, 10);
        else if (strcmp(argv[i], "--input") == 0 && i + 1 < (size_t)argc) input_mode = argv[++i];
        else if (strcmp(argv[i], "--op") == 0 && i + 1 < (size_t)argc) op = argv[++i];
        else if (strcmp(argv[i], "--help") == 0) { usage(argv[0]); return 0; }
        else { usage(argv[0]); return 2; }
    }

    if (!mode_str || !out_path) { usage(argv[0]); return 2; }
    if (strcmp(op, "decaps") != 0 && strcmp(op, "encaps") != 0) {
        fprintf(stderr, "unknown --op: %s\n", op);
        return 2;
    }
    if (strcmp(op, "encaps") == 0 && strcmp(input_mode, "varying-ct") == 0) {
        fprintf(stderr, "encaps mode does not support varying-ct; use fixed or varying-key\n");
        return 2;
    }
    if (strcmp(op, "encaps") == 0 && (strcmp(input_mode, "varying-key-cool") == 0
            || strcmp(input_mode, "varying-key-legacy") == 0)) {
        fprintf(stderr, "encaps mode: use --input fixed or varying-key\n");
        return 2;
    }

    mode = parse_mode(mode_str);
    pin_cpu(cpu);
    OQS_init();

    if (strcmp(input_mode, "varying-key-cool") == 0) {
        cool_buf = (uint8_t *)malloc(COOL_BYTES);
        if (!cool_buf) {
            fprintf(stderr, "cool buffer alloc failed\n");
            OQS_destroy();
            return 1;
        }
        memset(cool_buf, 0, COOL_BYTES);
    }

    if (hybrid_ctx_init(&ctx, mode) != 0) {
        fprintf(stderr, "hybrid_ctx_init failed\n");
        free(cool_buf);
        OQS_destroy();
        return 1;
    }

    if (!is_varying_key_family(input_mode)) {
        if (hybrid_keygen(&ctx) != 0) {
            fprintf(stderr, "setup failed\n");
            hybrid_ctx_free(&ctx);
            free(cool_buf);
            OQS_destroy();
            return 1;
        }
        if (strcmp(op, "decaps") == 0 && hybrid_encaps(&ctx) != 0) {
            fprintf(stderr, "setup failed\n");
            hybrid_ctx_free(&ctx);
            free(cool_buf);
            OQS_destroy();
            return 1;
        }
    }

    for (i = 0; i < warmup; i++) {
        if (is_varying_key_family(input_mode)) {
            if (hybrid_keygen(&ctx) != 0) {
                fprintf(stderr, "warmup failed\n");
                return 1;
            }
            /* Always encaps in warmup so legacy path starts from a defined state. */
            if (strcmp(op, "decaps") == 0 && hybrid_encaps(&ctx) != 0) {
                fprintf(stderr, "warmup failed\n");
                return 1;
            }
        }
        if (strcmp(op, "encaps") == 0) {
            if (hybrid_encaps(&ctx) != 0) {
                fprintf(stderr, "warmup failed\n");
                return 1;
            }
        } else if (strcmp(input_mode, "varying-ct") == 0) {
            if (hybrid_encaps(&ctx) != 0 || hybrid_decaps(&ctx) != 0) {
                fprintf(stderr, "warmup failed\n");
                return 1;
            }
        } else if (hybrid_decaps(&ctx) != 0) {
            fprintf(stderr, "warmup failed\n");
            return 1;
        }
        sink ^= ctx.master[0];
    }

    out = fopen(out_path, "w");
    if (!out) {
        fprintf(stderr, "fopen failed\n");
        return 1;
    }

    fprintf(out, "iteration,mode,input,op,elapsed_ns\n");
    for (i = 0; i < samples; i++) {
        uint64_t t0, t1;

        if (is_varying_key_family(input_mode)) {
            if (hybrid_keygen(&ctx) != 0) {
                fprintf(stderr, "keygen failed at %zu\n", i);
                return 1;
            }
            if (strcmp(op, "decaps") == 0) {
                if (strcmp(input_mode, "varying-key-legacy") == 0) {
                    /* Thesis path: no re-encaps; CT may not match new SK. */
                } else {
                    if (hybrid_encaps(&ctx) != 0) {
                        fprintf(stderr, "encaps failed at %zu\n", i);
                        return 1;
                    }
                    if (strcmp(input_mode, "varying-key-cool") == 0) {
                        cool_cache(cool_buf, COOL_BYTES);
                    }
                }
            }
        } else if (strcmp(op, "decaps") == 0 && strcmp(input_mode, "varying-ct") == 0) {
            if (hybrid_encaps(&ctx) != 0) {
                fprintf(stderr, "encaps failed at %zu\n", i);
                return 1;
            }
        }

        t0 = timing_nsec_now();
        if (strcmp(op, "encaps") == 0) {
            if (hybrid_encaps(&ctx) != 0) {
                fprintf(stderr, "encaps failed at %zu\n", i);
                return 1;
            }
        } else if (hybrid_decaps(&ctx) != 0) {
            fprintf(stderr, "decaps failed at %zu\n", i);
            return 1;
        }
        t1 = timing_nsec_now();
        sink ^= ctx.master[0];
        fprintf(out, "%zu,%s,%s,%s,%" PRIu64 "\n", i + 1, hybrid_mode_label(mode), input_mode, op, t1 - t0);
    }

    fclose(out);
    hybrid_ctx_free(&ctx);
    free(cool_buf);
    OQS_destroy();
    (void)sink;
    return 0;
}
