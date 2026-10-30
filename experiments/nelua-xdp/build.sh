#!/usr/bin/env bash
# Build and test only. This script never loads BPF or changes networking.
set -euo pipefail
cd "$(dirname "$0")"
NELUA_REV=3c29419776dfdca194fa7e9c572498264fe5c654
NELUA_ROOT="${NELUA_ROOT:-$PWD/.deps/nelua}"
if [ ! -d "$NELUA_ROOT/.git" ]; then
  mkdir -p "$(dirname "$NELUA_ROOT")"
  git clone --no-checkout https://github.com/Spaceghost/nelua-lang.git "$NELUA_ROOT"
  git -C "$NELUA_ROOT" checkout --detach "$NELUA_REV"
fi
if [ "$(git -C "$NELUA_ROOT" rev-parse HEAD)" != "$NELUA_REV" ] ||
   ! git -C "$NELUA_ROOT" diff --quiet HEAD --; then
  echo "NELUA_ROOT must be an unmodified checkout of $NELUA_REV" >&2
  exit 1
fi
make -C "$NELUA_ROOT" -j"${JOBS:-2}"
mkdir -p build
"$NELUA_ROOT/nelua" --release --print-code src/steer.nelua > build/steer.c.tmp
cat build/steer.c.tmp src/entry.c > build/program.c
mv build/steer.c.tmp build/steer.c
"${CC:-cc}" -std=c11 -O2 -Wall -Wextra -Werror -fPIC -shared -Isrc \
  build/program.c -o build/offline.so
python3 tests/packets.py build/offline.so

CLANG="${CLANG:-clang}"
if ! command -v "$CLANG" >/dev/null 2>&1; then
  echo 'Native packet tests passed. Set CLANG to a Clang binary with the BPF backend to build the ELF.'
  exit 0
fi
NC_PORT="${NC_PORT:-0}"
case "$NC_PORT" in ''|*[!0-9]*) echo 'NC_PORT must be an integer in 0..65535' >&2; exit 1 ;; esac
if [ "$NC_PORT" -gt 65535 ]; then echo 'NC_PORT must be in 0..65535' >&2; exit 1; fi
"$CLANG" -target bpfel -mcpu=v3 -std=c11 -O2 -g -ffreestanding -fno-stack-protector \
  -Wall -Wextra -Werror -Wno-ignored-attributes -nostdinc -Iinclude -Isrc \
  -DNC_BPF=1 -DNC_PORT="$NC_PORT" -c build/program.c -o build/nelua_xdp.o
python3 tools/audit.py build/nelua_xdp.o build/program.c
printf 'Built build/nelua_xdp.o for TCP port %s. No program was loaded or attached.\n' "$NC_PORT"
