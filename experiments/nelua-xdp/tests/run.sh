#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash build.sh
"${CC:-cc}" -std=c11 -O1 -g -Wall -Wextra -Werror -Isrc \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  build/program.c tests/sanitize.c -o build/packet_sanitized
ASAN_OPTIONS=detect_leaks=0 build/packet_sanitized
