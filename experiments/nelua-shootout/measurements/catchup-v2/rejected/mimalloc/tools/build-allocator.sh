#!/usr/bin/env bash
# Isolated experiment: compile the same generated application with either heap.
set -euo pipefail
cd "$(dirname "$0")/.."
mode="${1:-mimalloc}"
case "$mode" in mimalloc|glibc) ;; *) exit 2 ;; esac
mkdir -p build bin .deps
mi_checksum=6a45a52f43e1c16f667ccfe4dd8c85b7f7c204fd5e3bf46c5b0db9a5c3c0b8e9
mi_archive="${MIMALLOC_ARCHIVE:-$PWD/.deps/libmimalloc-sys-0.1.49.crate}"
mi_root="$PWD/.deps/libmimalloc-sys-0.1.49/c_src/mimalloc/v3"
pg_config="${PG_CONFIG:-pg_config}"
compiler="${CC:-gcc}"
extra=()
if [ "$mode" = mimalloc ]; then
  if [ ! -f "$mi_archive" ]; then
    python3 - "$mi_archive" <<'PY'
import sys
import urllib.request
urllib.request.urlretrieve(
    'https://static.crates.io/crates/libmimalloc-sys/libmimalloc-sys-0.1.49.crate', sys.argv[1])
PY
  fi
  printf '%s  %s\n' "$mi_checksum" "$mi_archive" | sha256sum -c -
  tar -xzf "$mi_archive" -C .deps
  "$compiler" -std=gnu11 -O3 -DNDEBUG -DMI_DEBUG=0 -DMI_BUILD_RELEASE \
    -ffunction-sections -fdata-sections -ftls-model=initial-exec \
    -I"$mi_root/include" -I"$mi_root/src" -pthread \
    -c "$mi_root/src/static.c" -o build/mimalloc.o
  extra=(-I"$mi_root/include" -include tools/allocator-host.h)
fi
"$compiler" -std=gnu11 -O3 -flto -fno-semantic-interposition \
  -ffunction-sections -fdata-sections -fstack-protector-strong \
  ${NATIVE_FLAGS--march=native} -Wall -Wextra -Werror \
  -Isrc -I"$("$pg_config" --includedir)" "${extra[@]}" \
  -c src/transport.c src/request.c src/bcrypt.c src/db.c build/app.c
objects=(transport.o request.o bcrypt.o db.o app.o)
if [ "$mode" = mimalloc ]; then objects+=(build/mimalloc.o); fi
"$compiler" -O3 -flto -fno-semantic-interposition -Wl,--gc-sections \
  "${objects[@]}" -L"$("$pg_config" --libdir)" -Wl,-rpath,"$("$pg_config" --libdir)" \
  -pthread -lpq -lcrypto -lcrypt -o "bin/conduit-$mode"
rm -f transport.o request.o bcrypt.o db.o app.o
# Defining these symbols would accidentally replace shared libraries' heaps.
if nm --defined-only "bin/conduit-$mode" | awk '{print $3}' | \
    rg -x 'malloc|calloc|realloc|free'; then
  echo 'unexpected global allocator override' >&2; exit 1
fi
strip --strip-unneeded "bin/conduit-$mode"
