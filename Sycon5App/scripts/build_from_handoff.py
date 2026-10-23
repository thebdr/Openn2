"""Build a SYCON.net project from a PL5 handoff folder and verify it by read-back.

Usage:  C:\\Source\\Repos\\_Openn5\\.venv\\Scripts\\python -I Sycon5App\\scripts\\build_from_handoff.py
            --handoff <SyconNetProjectInterface folder> --out <project.spj> [--base <base.spj>] [--resume]
Writes <project>.spj (+ its folder) and <project>.verification.txt beside it. Exit code 0 = every check passed.
"""
import argparse
import os
import sys
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
from sycon5 import consumer, SyconDriver  # noqa: E402
from sycon5.readback import describe, read_project  # noqa: E402
from sycon5.session import log  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--handoff", required=True)
p.add_argument("--out", required=True)
p.add_argument("--base", default=os.path.join(APP, "spike", "scratch", "AutomateSyconProj_BaseProj.spj"),
               help="a project to launch SYCON.net on before File > New (default: the scratch base project)")
p.add_argument("--resume", action="store_true")
a = p.parse_args()
t0 = time.time()
driver = SyconDriver()
code = 1
try:
    v, xml, plugged, driver = consumer.build(a.handoff, a.out, a.base, resume=a.resume, driver=driver)
    report = v.report() + "\n\n" + describe(read_project(xml))
    rpath = a.out[:-4] + ".verification.txt"
    with open(rpath, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print(report)
    log("report:", rpath, "| elapsed %.0f s" % (time.time() - t0))
    code = 0 if v.failed == 0 else 1
finally:
    if driver is not None:
        log("close:", driver.close())
sys.exit(code)
