#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
NELUA_REV=a58450563e2d2ec49bff499865c8b5cfdf6ff81a
NELUA_ROOT="${NELUA_ROOT:-$PWD/.deps/nelua}"
if [ ! -e "$NELUA_ROOT/.git" ]; then
  mkdir -p "$(dirname "$NELUA_ROOT")"
  git clone --no-checkout https://github.com/edubart/nelua-lang.git "$NELUA_ROOT"
  git -C "$NELUA_ROOT" checkout --detach "$NELUA_REV"
fi
if [ "$(git -C "$NELUA_ROOT" rev-parse HEAD)" != "$NELUA_REV" ] ||
   ! git -C "$NELUA_ROOT" diff --quiet HEAD --; then
  echo "Expected unmodified official Nelua at $NELUA_REV" >&2; exit 1
fi
make -C "$NELUA_ROOT" -j"${JOBS:-2}"
mkdir -p build bin
# Generate C afresh and link companions explicitly; no compiler binary cache is used.
(cd src && "$NELUA_ROOT/nelua" --cache-dir "$PWD/../build/nelua-cache" --no-cache --release --print-code main.nelua) > build/app.c.tmp
mv build/app.c.tmp build/app.c
PG_CONFIG="${PG_CONFIG:-pg_config}"
"${CC:-gcc}" -std=gnu11 -O3 -flto -fno-semantic-interposition \
  -ffunction-sections -fdata-sections -fstack-protector-strong \
  ${NATIVE_FLAGS--march=native} -Wall -Wextra -Werror \
  -Isrc -I"$("$PG_CONFIG" --includedir)" \
  src/transport.c src/request.c src/bcrypt.c src/db.c build/app.c \
  -L"$("$PG_CONFIG" --libdir)" -Wl,-rpath,"$("$PG_CONFIG" --libdir)" \
  -Wl,--gc-sections -pthread -lpq -lcrypto -lcrypt -o bin/conduit
strip --strip-unneeded bin/conduit
python3 tools/audit.py
