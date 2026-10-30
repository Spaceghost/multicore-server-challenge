#!/usr/bin/env python3
"""Fail the build if a runtime, allocator, process-exit path, or extra export enters."""
import pathlib
import re
import subprocess
import sys

library, generated = map(pathlib.Path, sys.argv[1:])
undefined = subprocess.check_output(["nm", "-D", "--undefined-only", str(library)], text=True)
exports = subprocess.check_output(["nm", "-D", "--defined-only", str(library)], text=True)
dynamic = subprocess.check_output(["readelf", "-d", str(library)], text=True)
sections = subprocess.check_output(["readelf", "-S", str(library)], text=True)
source = generated.read_text()

# PostgreSQL exports palloc/repalloc/pfree and owns allocation. libc allocation
# or Nelua runtime errors are forbidden in this in-process extension.
for symbol in ("malloc", "calloc", "realloc", "free", "abort", "exit", "_exit",
               "printf", "fprintf", "fwrite", "puts", "longjmp"):
    if re.search(r"\b" + re.escape(symbol) + r"(?:@\S+)?\s*$", undefined, re.M):
        raise SystemExit(f"forbidden runtime import: {symbol}")
if re.search(r"\b(?:nelua_(?:gc|panic|assert|error|abort)|lua_|GC_)", source):
    raise SystemExit("runtime code entered generated Nelua C")
for dependency in re.findall(r"Shared library: \[(.*?)\]", dynamic):
    if dependency != "libc.so.6":
        raise SystemExit(f"unexpected runtime dependency: {dependency}")
allowed = {"Pg_magic_func"}
for name in ("nc_tags", "nc_profile", "nc_article", "nc_articles", "nc_feed",
             "nc_comments", "nc_favorite", "nc_follow"):
    allowed.update((name, "pg_finfo_" + name))
actual = {line.split()[-1] for line in exports.splitlines() if line.split()}
if actual != allowed:
    raise SystemExit(f"export mismatch: missing={allowed - actual}, extra={actual - allowed}")
if re.search(r"\bmain\s*\(", source):
    raise SystemExit("unexpected entrypoint in Nelua C")
if re.search(r"\.(?:init_array|fini_array)\b", sections):
    raise SystemExit("unexpected constructor/destructor machinery")
print("audit passed: no Lua VM, GC, libc allocator, panic/exit path, or extra exports")
subprocess.run(["size", str(library)], check=True)
