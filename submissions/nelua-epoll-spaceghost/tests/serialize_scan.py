#!/usr/bin/env python3
"""Compile the generated Nelua serializer against an independent scalar oracle."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--generated-c', type=Path, default=ROOT / 'build/app.c')
    parser.add_argument('--benchmark', type=int, default=0)
    args = parser.parse_args()
    config = shlex.split(os.environ.get('PG_CONFIG', 'pg_config'))
    include = subprocess.check_output(config + ['--includedir'], text=True).strip()
    flags = ['-std=gnu11', '-O1' if args.sanitize else '-O3', '-g', '-Wall', '-Wextra', '-Werror',
             '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
             '-I' + str(ROOT / 'src'), '-I' + include]
    if args.sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    with tempfile.TemporaryDirectory(prefix='nc-serialize-') as directory:
        binary = Path(directory) / 'test'
        sources = [ 'src/request.c', 'src/bcrypt.c', 'src/db.c', 'tests/serialize_scan.c']
        subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + flags +
                       [str(args.generated_c)] + [str(ROOT / p) for p in sources] +
                       ['-pthread', '-lpq', '-lcrypto', '-lcrypt', '-o', str(binary)], check=True)
        subprocess.run([str(binary)] + ([str(args.benchmark)] if args.benchmark else []), check=True, timeout=120,
                       env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})


if __name__ == '__main__':
    main()
