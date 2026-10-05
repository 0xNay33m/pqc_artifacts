#include "hybrid_kem.h"
#include "hkdf_sha256.h"
#include "timing_util.h"

#include <sc_sha256.h>
#include <stdlib.h>
#include <string.h>

static const uint8_t KEM_INFO[] = "thesis/hybrid-kem/v1";

static int derive_master(hybrid_ctx_t *ctx) {
    uint8_t salt_material[4096];
    size_t salt_len = 0;
    uint8_t salt[32];
    uint8_t ikm[64];
    size_t ikm_len = 0;

    if (ctx->mode == MODE_MLKEM || ctx->mode == MODE_HYBRID) {
        memcpy(salt_material + salt_len, ctx->pk_mlkem, ctx->kem_mlkem->length_public_key);
        salt_len += (size_t)ctx->kem_mlkem->length_public_key;
    }
    if (ctx->mode == MODE_BIKE || ctx->mode == MODE_HYBRID) {
        memcpy(salt_material + salt_len, ctx->pk_bike, ctx->kem_bike->length_public_key);
        salt_len += (size_t)ctx->kem_bike->length_public_key;
    }

    sc_sha256(salt, salt_material, salt_len);

    if (ctx->mode == MODE_MLKEM || ctx->mode == MODE_HYBRID) {
        memcpy(ikm + ikm_len, ctx->ss_mlkem, (size_t)ctx->kem_mlkem->length_shared_secret);
        ikm_len += (size_t)ctx->kem_mlkem->length_shared_secret;
    }
    if (ctx->mode == MODE_BIKE || ctx->mode == MODE_HYBRID) {
        memcpy(ikm + ikm_len, ctx->ss_bike, (size_t)ctx->kem_bike->length_shared_secret);
        ikm_len += (size_t)ctx->kem_bike->length_shared_secret;
    }

    return hkdf_sha256(ctx->master, sizeof(ctx->master),
                       salt, sizeof(salt), ikm, ikm_len,
                       KEM_INFO, sizeof(KEM_INFO) - 1);
}

const char *hybrid_mode_label(kem_mode_t mode) {
    switch (mode) {
    case MODE_MLKEM: return "mlkem";
    case MODE_BIKE: return "bike";
    case MODE_HYBRID: return "hybrid";
    default: return "unknown";
    }
}

int hybrid_ctx_init(hybrid_ctx_t *ctx, kem_mode_t mode) {
    memset(ctx, 0, sizeof(*ctx));
    ctx->mode = mode;

    if (mode == MODE_MLKEM || mode == MODE_HYBRID) {
        ctx->kem_mlkem = OQS_KEM_new(OQS_KEM_alg_ml_kem_768);
        if (!ctx->kem_mlkem) {
            return -1;
        }
        ctx->pk_mlkem = malloc((size_t)ctx->kem_mlkem->length_public_key);
        ctx->sk_mlkem = malloc((size_t)ctx->kem_mlkem->length_secret_key);
        ctx->ct_mlkem = malloc((size_t)ctx->kem_mlkem->length_ciphertext);
        ctx->ss_mlkem = malloc((size_t)ctx->kem_mlkem->length_shared_secret);
        if (!ctx->pk_mlkem || !ctx->sk_mlkem || !ctx->ct_mlkem || !ctx->ss_mlkem) {
            return -1;
        }
    }

    if (mode == MODE_BIKE || mode == MODE_HYBRID) {
        ctx->kem_bike = OQS_KEM_new(OQS_KEM_alg_bike_l1);
        if (!ctx->kem_bike) {
            return -1;
        }
        ctx->pk_bike = malloc((size_t)ctx->kem_bike->length_public_key);
        ctx->sk_bike = malloc((size_t)ctx->kem_bike->length_secret_key);
        ctx->ct_bike = malloc((size_t)ctx->kem_bike->length_ciphertext);
        ctx->ss_bike = malloc((size_t)ctx->kem_bike->length_shared_secret);
        if (!ctx->pk_bike || !ctx->sk_bike || !ctx->ct_bike || !ctx->ss_bike) {
            return -1;
        }
    }

    return 0;
}

void hybrid_ctx_free(hybrid_ctx_t *ctx) {
    if (!ctx) {
        return;
    }
    if (ctx->kem_mlkem) {
        OQS_KEM_free(ctx->kem_mlkem);
    }
    if (ctx->kem_bike) {
        OQS_KEM_free(ctx->kem_bike);
    }
    free(ctx->pk_mlkem);
    free(ctx->sk_mlkem);
    free(ctx->ct_mlkem);
    free(ctx->ss_mlkem);
    free(ctx->pk_bike);
    free(ctx->sk_bike);
    free(ctx->ct_bike);
    free(ctx->ss_bike);
    memset(ctx, 0, sizeof(*ctx));
}

int hybrid_keygen(hybrid_ctx_t *ctx) {
    if (ctx->mode == MODE_MLKEM || ctx->mode == MODE_HYBRID) {
        if (OQS_KEM_keypair(ctx->kem_mlkem, ctx->pk_mlkem, ctx->sk_mlkem) != OQS_SUCCESS) {
            return -1;
        }
    }
    if (ctx->mode == MODE_BIKE || ctx->mode == MODE_HYBRID) {
        if (OQS_KEM_keypair(ctx->kem_bike, ctx->pk_bike, ctx->sk_bike) != OQS_SUCCESS) {
            return -1;
        }
    }
    return 0;
}

int hybrid_encaps(hybrid_ctx_t *ctx) {
    if (ctx->mode == MODE_MLKEM || ctx->mode == MODE_HYBRID) {
        if (OQS_KEM_encaps(ctx->kem_mlkem, ctx->ct_mlkem, ctx->ss_mlkem, ctx->pk_mlkem) != OQS_SUCCESS) {
            return -1;
        }
    }
    if (ctx->mode == MODE_BIKE || ctx->mode == MODE_HYBRID) {
        if (OQS_KEM_encaps(ctx->kem_bike, ctx->ct_bike, ctx->ss_bike, ctx->pk_bike) != OQS_SUCCESS) {
            return -1;
        }
    }
    return derive_master(ctx);
}

int hybrid_decaps(hybrid_ctx_t *ctx) {
    decaps_timing_t ignored;
    return hybrid_decaps_timed(ctx, &ignored);
}

int hybrid_decaps_timed(hybrid_ctx_t *ctx, decaps_timing_t *timing) {
    uint64_t t0, t1, t_mlkem = 0, t_bike = 0, t_hkdf = 0;

    if (!timing) {
        return -1;
    }
    timing->mlkem_ns = 0;
    timing->bike_ns = 0;
    timing->hkdf_ns = 0;

    t0 = timing_nsec_now();

    if (ctx->mode == MODE_MLKEM || ctx->mode == MODE_HYBRID) {
        if (OQS_KEM_decaps(ctx->kem_mlkem, ctx->ss_mlkem, ctx->ct_mlkem, ctx->sk_mlkem) != OQS_SUCCESS) {
            return -1;
        }
        t1 = timing_nsec_now();
        t_mlkem = t1 - t0;
        t0 = t1;
    }

    if (ctx->mode == MODE_BIKE || ctx->mode == MODE_HYBRID) {
        if (OQS_KEM_decaps(ctx->kem_bike, ctx->ss_bike, ctx->ct_bike, ctx->sk_bike) != OQS_SUCCESS) {
            return -1;
        }
        t1 = timing_nsec_now();
        t_bike = t1 - t0;
        t0 = t1;
    }

    if (derive_master(ctx) != 0) {
        return -1;
    }
    t1 = timing_nsec_now();
    t_hkdf = t1 - t0;

    timing->mlkem_ns = t_mlkem;
    timing->bike_ns = t_bike;
    timing->hkdf_ns = t_hkdf;
    timing->total_ns = t_mlkem + t_bike + t_hkdf;
    return 0;
}
