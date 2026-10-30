#!/usr/bin/env python3
"""Inspect an ELF locally. This deliberately performs no kernel verification/load."""
from pathlib import Path
import re
import struct
import sys

elf = Path(sys.argv[1]).read_bytes()
source = Path(sys.argv[2]).read_text()
if elf[:6] != b"\x7fELF\x02\x01":
    raise SystemExit("expected little-endian ELF64")
if struct.unpack_from("<H", elf, 18)[0] != 247:
    raise SystemExit("expected EM_BPF machine")
offset = struct.unpack_from("<Q", elf, 40)[0]
entry_size, count, names_index = struct.unpack_from("<HHH", elf, 58)
headers = [struct.unpack_from("<IIQQQQIIQQ", elf, offset + i * entry_size)
           for i in range(count)]
names_header = headers[names_index]
names = elf[names_header[4]:names_header[4] + names_header[5]]


def string(table, cursor):
    return table[cursor:table.index(b"\0", cursor)].decode()


sections = {string(names, h[0]): h for h in headers}
for section in ("xdp", ".maps", ".BTF", "license"):
    if section not in sections:
        raise SystemExit("missing ELF section: " + section)
if sections.get(".text", (0, 0, 0, 0, 0, 0))[5]:
    raise SystemExit("unexpected out-of-line helper code; parser should inline into XDP entry")
if re.search(r"\b(?:malloc|calloc|realloc|free|abort|exit|lua_|nelua_(?:gc|panic|error))\b", source):
    raise SystemExit("unexpected runtime operation in generated code")
undefined = []
for h in headers:
    if h[1] != 2:  # SHT_SYMTAB
        continue
    strings_header = headers[h[6]]
    strings = elf[strings_header[4]:strings_header[4] + strings_header[5]]
    for cursor in range(h[4], h[4] + h[5], h[9]):
        name, info, other, index, value, size = struct.unpack_from("<IBBHQQ", elf, cursor)
        if index == 0 and name:
            undefined.append(string(strings, name))
if undefined:
    raise SystemExit(f"unexpected unresolved symbols: {undefined}")
program = sections["xdp"]
code = elf[program[4]:program[4] + program[5]]
if len(code) % 8:
    raise SystemExit("bad BPF instruction size")
helpers = []
for i in range(0, len(code), 8):
    opcode, registers, branch, immediate = struct.unpack_from("<BBhi", code, i)
    if opcode == 0x85 and registers >> 4 == 0:
        helpers.append(immediate)
if any(helper != 51 for helper in helpers):
    raise SystemExit(f"unexpected helper calls: {helpers}")
print(f"PASS: BPF ELF audit; {len(code)//8} XDP instructions, helpers={helpers}, {len(elf)} ELF bytes")
print("Compilation and ELF inspection are not a kernel verifier acceptance test.")
