#!/usr/bin/env bash
# Fetch and build the liboqs release used in the paper into vendor/liboqs-install.
# Configuration matches vendor/oqsconfig.reference.h (the oqsconfig.h of the measured build).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAG=0.14.0
COMMIT=94b421ebb82405c843dba4e9aa521a56ee5a333d

cd "$HERE"
if [ ! -d liboqs-src ]; then
    git clone --branch "$TAG" --depth 1 https://github.com/open-quantum-safe/liboqs.git liboqs-src
fi
test "$(git -C liboqs-src rev-parse HEAD)" = "$COMMIT" || { echo "liboqs-src is not at $COMMIT"; exit 1; }

cmake -S liboqs-src -B liboqs-src/build -GNinja \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED_LIBS=ON \
    -DOQS_USE_OPENSSL=OFF \
    -DOQS_DIST_BUILD=ON \
    -DCMAKE_INSTALL_PREFIX="$HERE/liboqs-install"
ninja -C liboqs-src/build install

diff <(grep -E '^#define OQS_(USE|DIST|OPT|ENABLE_KEM_(bike_l1|ml_kem_768))' liboqs-install/include/oqs/oqsconfig.h) \
     <(grep -E '^#define OQS_(USE|DIST|OPT|ENABLE_KEM_(bike_l1|ml_kem_768))' oqsconfig.reference.h) \
    && echo "liboqs $TAG installed; configuration matches the measured build."
