EXTENSION = nelua_conduit
MODULE_big = nelua_conduit
OBJS = build/extension.o build/kernel.o
DATA = sql/nelua_conduit--0.1.0.sql

PG_CONFIG ?= pg_config
NELUA_ROOT ?= $(CURDIR)/.deps/nelua
NELUA = $(NELUA_ROOT)/nelua

# O3/LTO optimize across the PostgreSQL bridge and generated Nelua C.
# Keep PostgreSQL's stack/overflow protection flags. Native CPU tuning is opt-in.
PG_CPPFLAGS = -I$(CURDIR)/src
PG_CFLAGS = -O3 -flto -fno-semantic-interposition -ffunction-sections -fdata-sections $(NATIVE_FLAGS)
# There are no C/Nelua constructors: PostgreSQL calls the exported ABI directly.
PG_LDFLAGS = -flto -nostartfiles
SHLIB_LINK = -Wl,--gc-sections -Wl,--version-script=$(CURDIR)/src/exports.map

PGXS := $(shell $(PG_CONFIG) --pgxs)
include $(PGXS)

# PGXS must come first so its default goal remains 'all'.
nelua_conduit.so: src/exports.map Makefile

build/extension.o: src/extension.c src/bridge.h src/kernel.h src/queries.h Makefile | build
	$(CC) $(CFLAGS) $(CPPFLAGS) -fPIC -c $< -o $@

build/kernel.c: src/kernel.nelua src/bridge.h src/kernel.h build.sh | build
	$(NELUA) --release --print-code $< > $@.tmp
	mv $@.tmp $@

build/kernel.o: build/kernel.c src/bridge.h src/kernel.h Makefile
	$(CC) $(CFLAGS) -Wno-declaration-after-statement $(CPPFLAGS) -fPIC -c $< -o $@

# PGXS also generates LLVM bitcode on distribution builds with LLVM enabled.
build/extension.bc: src/extension.c src/bridge.h src/kernel.h src/queries.h | build
	$(COMPILE.c.bc) -o $@ $<

build/kernel.bc: build/kernel.c src/bridge.h src/kernel.h
	$(COMPILE.c.bc) -o $@ $<

build:
	mkdir -p $@

.PHONY: audit kernel-test integration-test
audit: all
	python3 tools/audit.py nelua_conduit.so build/kernel.c

kernel-test: build/kernel.c
	python3 tests/kernel_test.py build/kernel.c --sanitize

integration-test: all
	python3 tests/integration.py

EXTRA_CLEAN = build
