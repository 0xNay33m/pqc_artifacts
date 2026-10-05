#ifndef SC_SHA256_H
#define SC_SHA256_H

#include <stddef.h>
#include <stdint.h>

void sc_sha256(uint8_t out[32], const uint8_t *in, size_t inlen);

#endif
