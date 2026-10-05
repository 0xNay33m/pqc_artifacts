#include "hkdf_sha256.h"

#include "sc_sha256.h"
#include <string.h>

#define SHA256_LEN 32
#define BLOCK_LEN 64

static void hmac_sha256(uint8_t out[SHA256_LEN],
                        const uint8_t *key, size_t key_len,
                        const uint8_t *msg, size_t msg_len) {
    uint8_t k[BLOCK_LEN];
    uint8_t inner[BLOCK_LEN + 256];
    uint8_t inner_hash[SHA256_LEN];
    size_t i;

    memset(k, 0, sizeof(k));
    if (key_len > BLOCK_LEN) {
        sc_sha256(k, key, key_len);
    } else if (key_len > 0) {
        memcpy(k, key, key_len);
    }

    for (i = 0; i < BLOCK_LEN; i++) {
        inner[i] = (uint8_t)(k[i] ^ 0x36u);
    }
    memcpy(inner + BLOCK_LEN, msg, msg_len);
    sc_sha256(inner_hash, inner, BLOCK_LEN + msg_len);

    for (i = 0; i < BLOCK_LEN; i++) {
        k[i] = (uint8_t)(k[i] ^ 0x36u ^ 0x5cu);
    }
    {
        uint8_t outer[BLOCK_LEN + SHA256_LEN];
        memcpy(outer, k, BLOCK_LEN);
        memcpy(outer + BLOCK_LEN, inner_hash, SHA256_LEN);
        sc_sha256(out, outer, BLOCK_LEN + SHA256_LEN);
    }
}

static int hkdf_expand(uint8_t *out, size_t out_len,
                       const uint8_t *prk, size_t prk_len,
                       const uint8_t *info, size_t info_len) {
    uint8_t t[SHA256_LEN];
    size_t t_len = 0;
    size_t pos = 0;
    uint8_t counter = 1;
    uint8_t buf[256 + 1];

    while (pos < out_len) {
        size_t msg_len = 0;
        if (t_len > 0) {
            memcpy(buf, t, t_len);
            msg_len = t_len;
        }
        if (info_len > 0) {
            memcpy(buf + msg_len, info, info_len);
            msg_len += info_len;
        }
        buf[msg_len++] = counter;
        hmac_sha256(t, prk, prk_len, buf, msg_len);
        t_len = SHA256_LEN;
        {
            size_t copy = out_len - pos;
            if (copy > SHA256_LEN) {
                copy = SHA256_LEN;
            }
            memcpy(out + pos, t, copy);
            pos += copy;
        }
        counter++;
    }
    return 0;
}

int hkdf_sha256(uint8_t *out, size_t out_len,
                const uint8_t *salt, size_t salt_len,
                const uint8_t *ikm, size_t ikm_len,
                const uint8_t *info, size_t info_len) {
    uint8_t prk[SHA256_LEN];
    uint8_t zero_salt[SHA256_LEN];
    const uint8_t *use_salt = salt;
    size_t use_salt_len = salt_len;

    if (salt_len == 0) {
        memset(zero_salt, 0, sizeof(zero_salt));
        use_salt = zero_salt;
        use_salt_len = SHA256_LEN;
    }

    hmac_sha256(prk, use_salt, use_salt_len, ikm, ikm_len);
    return hkdf_expand(out, out_len, prk, SHA256_LEN, info, info_len);
}
