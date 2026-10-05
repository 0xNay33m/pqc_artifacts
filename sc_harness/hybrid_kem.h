#ifndef HYBRID_KEM_H
#define HYBRID_KEM_H

#include <oqs/oqs.h>
#include <stddef.h>
#include <stdint.h>

typedef enum {
    MODE_MLKEM = 0,
    MODE_BIKE = 1,
    MODE_HYBRID = 2
} kem_mode_t;

typedef struct {
    kem_mode_t mode;
    OQS_KEM *kem_mlkem;
    OQS_KEM *kem_bike;
    uint8_t *pk_mlkem;
    uint8_t *sk_mlkem;
    uint8_t *pk_bike;
    uint8_t *sk_bike;
    uint8_t *ct_mlkem;
    uint8_t *ct_bike;
    uint8_t *ss_mlkem;
    uint8_t *ss_bike;
    uint8_t master[32];
} hybrid_ctx_t;

typedef struct {
    uint64_t mlkem_ns;
    uint64_t bike_ns;
    uint64_t hkdf_ns;
    uint64_t total_ns;
} decaps_timing_t;

int hybrid_ctx_init(hybrid_ctx_t *ctx, kem_mode_t mode);
void hybrid_ctx_free(hybrid_ctx_t *ctx);
int hybrid_keygen(hybrid_ctx_t *ctx);
int hybrid_encaps(hybrid_ctx_t *ctx);
int hybrid_decaps(hybrid_ctx_t *ctx);
int hybrid_decaps_timed(hybrid_ctx_t *ctx, decaps_timing_t *timing);
const char *hybrid_mode_label(kem_mode_t mode);

#endif
