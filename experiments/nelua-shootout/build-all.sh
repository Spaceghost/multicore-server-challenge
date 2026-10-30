#!/usr/bin/env bash
# Build the unchanged entry scripts. Install only toolchains/development packages.
# Runtime benchmarks never run as root and never change sysctls, affinity or NICs.
set -uo pipefail
cd "$(dirname "$0")/../.."
report="${1:?usage: build-all.sh LOG_DIRECTORY}"
mkdir -p "$report"
printf 'name\tinstall_exit\tbuild_exit\n' > "$report/build-status.tsv"
cases=(nelua-epoll-spaceghost rust-epoll-theCatWisel zig-iouring-nick-potts
       rust-epoll-WorriedArrow asm-epoll-nickita-khylkouski csharp-epoll-aot-gichamba)
for name in "${cases[@]}"; do
  echo "Building $name"
  install_exit=0
  build_exit=0
  if [ "${SHOOTOUT_SKIP_INSTALL:-0}" != 1 ]; then
    sudo bash "submissions/$name/install.sh" > "$report/$name-install.log" 2>&1 || install_exit=$?
  fi
  if [ "$install_exit" = 0 ]; then
    bash "submissions/$name/build.sh" > "$report/$name-build.log" 2>&1 || build_exit=$?
  else
    build_exit=125
  fi
  printf '%s\t%s\t%s\n' "$name" "$install_exit" "$build_exit" >> "$report/build-status.tsv"
done
# Do not hide partial builds or stop the remaining comparators on first failure.
cat "$report/build-status.tsv"
