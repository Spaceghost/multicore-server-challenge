#!/usr/bin/env python3
"""Repeat saved feed SQL parity/plans, optionally its component timings."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--libpq')
p.add_argument('--benchmark',action='store_true')
p.add_argument('--seconds',type=float,default=1)
a=p.parse_args()
if not 0<a.seconds<=10:p.error('seconds must be in (0,10]')
here=Path(__file__).resolve().parent
a.output.mkdir(parents=True,exist_ok=True)
if any(a.output.iterdir()):p.error('output must be new or empty')
for name in ['baseline.sql','candidate.sql','floor-only.sql']:shutil.copyfile(here/name,a.output/name)
s=(here/'prototype.py').read_text()
s=s.replace("pq=C.CDLL(str(root/'pg18/lib/libpq.so'))", "import ctypes.util\npq=C.CDLL(os.environ.get('LIBPQ') or ctypes.util.find_library('pq'))")
script=a.output/'prototype.py';script.write_text(s)
env=dict(os.environ)
if a.libpq:env['LIBPQ']=a.libpq
cmd=[sys.executable,str(script),'--seconds',str(a.seconds)]
if a.benchmark:cmd.append('--benchmark')
raise SystemExit(subprocess.run(cmd,env=env).returncode)
