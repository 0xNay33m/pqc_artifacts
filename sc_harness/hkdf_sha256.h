#ifndef HKDF_SHA256_H
#define HKDF_SHA256_H

#include <stddef.h>
#include <stdint.h>

int hkdf_sha256(uint8_t *out, size_t out_len,
                const uint8_t *salt, size_t salt_len,
                const uint8_t *ikm, size_t ikm_len,
                const uint8_t *info, size_t info_len);

#endif
