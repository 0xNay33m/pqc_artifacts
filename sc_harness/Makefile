OQS_ROOT ?= $(abspath ../vendor/liboqs-install)
CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -std=c11
CFLAGS += -I$(OQS_ROOT)/include -I.
LDFLAGS = -L$(OQS_ROOT)/lib -Wl,-rpath,$(OQS_ROOT)/lib
LDLIBS = -loqs -lm -lpthread

COMMON = hybrid_kem.o hkdf_sha256.o sc_sha256.o timing_util.o

.PHONY: all clean

all: timing_bench cache_bench noise_bench leg_bench dudect_bench

timing_bench: timing_bench.o $(COMMON)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS) $(LDLIBS)

cache_bench: cache_bench.o $(COMMON)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS) $(LDLIBS)

noise_bench: noise_bench.o timing_util.o
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS) $(LDLIBS)

leg_bench: leg_bench.o $(COMMON)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS) $(LDLIBS)

dudect_bench: dudect_bench.o $(COMMON)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS) $(LDLIBS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f *.o timing_bench cache_bench noise_bench leg_bench dudect_bench sha2_vendor.c
