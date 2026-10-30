#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Spaceghost's fork is the compiler; its bundled Lua runs only at build time.
NELUA_REV=3c29419776dfdca194fa7e9c572498264fe5c654
NELUA_ROOT="${NELUA_ROOT:-$PWD/.deps/nelua}"
PG_CONFIG="${PG_CONFIG:-pg_config}"
case "$("$PG_CONFIG" --version)" in
  'PostgreSQL 18.'*) ;;
  *) echo 'This experiment targets PostgreSQL 18. Set PG_CONFIG to its pg_config.' >&2; exit 1 ;;
esac
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
make -j"${JOBS:-2}" PG_CONFIG="$PG_CONFIG" NELUA_ROOT="$NELUA_ROOT" all audit
