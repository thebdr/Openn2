"""Probe - the catalog entry chosen by GSDML file and the station cloning (nothing saved): launches SYCON.net on
the smoke project, lists the files every same-named `PN/PN Coupler X2` entry cites, selects the entry of each
station type of the smoke handoff by its GSDML, refuses a wrong file, then clones the AL1202 twice through the
netProject tree. SYCON.net is left running (for scripts/probe_submodules.py); close it without saving afterwards.

Usage:  ..\\.venv\\Scripts\\python -I scripts\\probe_catalog_clone.py [--project <spj>] [--handoff <folder>]
            [--source n0035-trib-sm006-k1] [--count 2]
"""
import argparse
import os
import sys
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
from sycon5 import SyconDriver  # noqa: E402
from sycon5 import catalog  # noqa: E402
from sycon5.handoff import load_handoff  # noqa: E402
from sycon5.session import SyconError, log  # noqa: E402

SMOKE_DIR = os.path.join(APP, "spike", "scratch", "FVT_LowerSorter_smoke")
SMOKE = os.path.join(SMOKE_DIR, "Smoke.spj")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--project", default=SMOKE)
    p.add_argument("--handoff", default=os.path.join(SMOKE_DIR, "SyconNetProjectInterface"))
    p.add_argument("--source", default="n0035-trib-sm006-k1")
    p.add_argument("--count", type=int, default=2)
    a = p.parse_args(argv)
    d = SyconDriver()
    d.open(a.project)
    s = d.session
    log("nodes:", s.nodes())
    # 1. every same-named entry of the coupler and the file it cites
    s.close_menus()
    s.bring_front()
    node = catalog._kind_node(s, "slave")
    entries = [i for i in s._iter_items(node) if i.window_text() == "PN/PN Coupler X2"]
    for n, e in enumerate(entries, start=1):
        _cited, _files, tokens = catalog._cites(s, e, "")
        log("PN/PN Coupler X2 entry %d of %d cites %r" % (n, len(entries), tokens))
    # 2. the entry of each station type of the handoff by its GSDML
    h = load_handoff(a.handoff)
    seen = set()
    for st in [h.controller] + h.stations:
        key = (st["catalog_kind"] or "slave", st["catalog_item"], st.get("gsdml") or "")
        if key in seen:
            continue
        seen.add(key)
        t0 = time.time()
        try:
            item = catalog.catalog_item(s, key[0], key[1], key[2] or None)
            log("chosen %r for %s in %.1f s: info cites %r" % (item.window_text(), key, time.time() - t0,
                                                               catalog.info_files(s.catalog_info())))
        except SyconError as ex:
            log("FAILED %s: %s" % (key, ex))
    # 3. a wrong file is refused
    try:
        catalog.catalog_item(s, "slave", "PN/PN Coupler X2", "GSDML-V2.35-Siemens-PNPNIOC-20190101.xml")
        log("WRONG FILE ACCEPTED")
    except SyconError as ex:
        log("wrong file refused as expected:", ex)
    # 4. the cloning
    before = s.nodes()
    t0 = time.time()
    try:
        new = d.clone_station(a.source, a.count)
        log("cloned %d in %.1f s: %r" % (len(new), time.time() - t0, [n["station"] for n in new]))
    except SyconError as ex:
        log("CLONE FAILED after %.1f s: %s" % (time.time() - t0, ex))
    log("nodes before:", before)
    log("nodes after: ", s.nodes())
    log("SYCON.net left running:", s.title())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
