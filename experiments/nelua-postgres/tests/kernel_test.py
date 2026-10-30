#!/usr/bin/env python3
"""Compare generated Nelua JSON with Python's parser, without PostgreSQL.

Usage: python3 tests/kernel_test.py build/kernel.c [--sanitize]
The optional sanitizer pass executes the same generated code in a standalone
host; LeakSanitizer is disabled because sandboxed /proc access may be restricted.
"""
import argparse
import ctypes as C
import json
import os
from pathlib import Path
import random
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


class Writer(C.Structure):
    _fields_ = [("data", C.c_char * 65536), ("length", C.c_size_t)]


class Cell(C.Structure):
    _fields_ = [("text", C.c_void_p), ("length", C.c_size_t),
                ("integer", C.c_int64), ("boolean", C.c_bool),
                ("is_null", C.c_bool)]


class Row(C.Structure):
    _fields_ = [("columns", Cell * 16)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generated_c", type=Path)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    source = args.generated_c.resolve()
    compiler = shlex.split(os.environ.get("CC", "cc"))
    shared_flags = ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I" + str(ROOT / "src")]
    sources = [str(source), str(ROOT / "tests/kernel_stub.c")]
    with tempfile.TemporaryDirectory(prefix="nc-kernel-") as tmp:
        libpath = Path(tmp) / "kernel_test.so"
        subprocess.run(compiler + shared_flags + ["-fPIC", "-shared", "-Wl,--no-undefined"] +
                       sources + ["-o", str(libpath)], check=True)
        lib = C.CDLL(str(libpath))
        lib.nc_json_string.argtypes = [C.POINTER(Writer), C.c_void_p, C.c_size_t]
        lib.nc_json_int64.argtypes = [C.POINTER(Writer), C.c_int64]
        lib.nc_json_bool.argtypes = [C.POINTER(Writer), C.c_bool]
        lib.nc_json_null.argtypes = [C.POINTER(Writer)]
        lib.nc_json_profile.argtypes = [C.POINTER(Writer), C.POINTER(Row), C.c_int]
        lib.nc_json_article.argtypes = [C.POINTER(Writer), C.POINTER(Row), C.c_bool]
        lib.nc_json_comment.argtypes = [C.POINTER(Writer), C.POINTER(Row)]
        for name in ("string", "int64", "bool", "null", "profile", "article", "comment"):
            getattr(lib, "nc_json_" + name).restype = None

        def encode(kind, *values):
            writer = Writer()
            getattr(lib, "nc_json_" + kind)(C.byref(writer), *values)
            return C.string_at(C.addressof(writer), writer.length)

        def string(value):
            data = value.encode("utf-8")
            return encode("string", data, len(data))

        samples = ["", "plain ASCII", 'quote" backslash\\ slash/',
                   "".join(chr(i) for i in range(128)), "café 雪 🌌",
                   "\u2028\u2029", "\x00before\x00after\x00"]
        rng = random.Random(2309)
        alphabet = [chr(i) for i in range(128)] + list("café 雪 🌌")
        samples += ["".join(rng.choice(alphabet) for _ in range(rng.randrange(600)))
                    for _ in range(1000)]
        for value in samples:
            assert json.loads(string(value)) == value
        # Exhaustive byte preservation, including non-UTF8 bytes: those are not
        # accepted by the SQL UTF8 boundary, but catch byte-indexing regressions.
        raw = bytes(range(256))
        encoded = encode("string", raw, len(raw))
        assert json.loads(encoded.decode("latin1")).encode("latin1") == raw
        assert encode("string", None, 0) == b'""'
        numbers = [-(1 << 63), -(1 << 63) + 1, -10, -1, 0, 1, 9, 10,
                   (1 << 63) - 2, (1 << 63) - 1]
        numbers += [rng.randrange(-(1 << 63), 1 << 63) for _ in range(10000)]
        for number in numbers:
            assert encode("int64", number) == str(number).encode("ascii")
        assert encode("bool", True) == b"true"
        assert encode("bool", False) == b"false"
        assert encode("null") == b"null"

        keepalive = []

        def row(values):
            result = Row()
            for i, value in enumerate(values):
                if value is None:
                    result.columns[i].is_null = True
                elif isinstance(value, bool):
                    result.columns[i].boolean = value
                elif isinstance(value, int):
                    result.columns[i].integer = value
                else:
                    raw = value.encode("utf8")
                    buffer = C.create_string_buffer(raw)
                    keepalive.append(buffer)
                    result.columns[i].text = C.addressof(buffer)
                    result.columns[i].length = len(raw)
            return result

        profile = {"username": 'author"雪', "bio": None,
                   "image": "https://example.test/🌌", "following": True}
        profile_values = list(profile.values())
        assert json.loads(encode("profile", C.byref(row(profile_values)), 0)) == profile
        shifted = row([None, None] + profile_values)
        assert json.loads(encode("profile", C.byref(shifted), 2)) == profile
        created = "2025-04-01T12:00:00.000Z"
        updated = "2025-04-02T12:00:00.123Z"
        article = {"slug": "hello-1", "title": 'A "title"', "description": "line\nline",
                   "body": "body\t雪", "createdAt": created, "updatedAt": updated,
                   "tagList": ["a", "z"], "favoritesCount": 123,
                   "favorited": True, "author": profile}
        full_values = [article["slug"], article["title"], article["description"],
                       article["body"], json.dumps(created), json.dumps(updated),
                       json.dumps(article["tagList"]), 123, True] + profile_values
        assert json.loads(encode("article", C.byref(row(full_values)), True)) == article
        list_values = full_values[:3] + full_values[4:]
        del article["body"]
        assert json.loads(encode("article", C.byref(row(list_values)), False)) == article
        comment = {"id": 9223372036854775807, "body": "comment\x01雪",
                   "createdAt": created, "updatedAt": updated, "author": profile}
        comment_values = [comment["id"], comment["body"], json.dumps(created),
                          json.dumps(updated)] + profile_values
        assert json.loads(encode("comment", C.byref(row(comment_values)))) == comment

        if args.sanitize:
            executable = Path(tmp) / "kernel_sanitized"
            subprocess.run(compiler + shared_flags + ["-DNC_TEST_MAIN", "-fsanitize=address,undefined"] +
                           sources + ["-o", str(executable)], check=True)
            env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0")
            subprocess.run([str(executable)], check=True, env=env)
        print("Kernel: JSON escaping, UTF8, int64 boundaries, 10,000 random integers, and serializer layouts passed.")


if __name__ == "__main__":
    main()
