"""Where does a catalog drop attach on a project whose canvas `canvas.apply_layout` laid out (2026-10-30: the resume of
the repaired sorter copy dropped 'PN/PN Coupler X2' six times on the longest horizontal green line - a device's branch,
y 670 x 8..548 - and no node appeared)? On a COPY of PROD_Sorter_Lower_repair (never saved): the green lines the colour
scan sees, a screenshot of the window, then the coupler dropped on the vertical bus (x 8..12) and on the controller's
stub line until a node appears. Usage (from Sycon5App, the repo venv):  python -I scripts\\probe_drop_laid_out.py"""
import os
import shutil
import sys

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
sys.path.insert(0, os.path.join(APP, "scripts"))

from sycon5 import SyconDriver, catalog                    # noqa: E402
from sycon5.drawing import colour_lines, drawing_pane      # noqa: E402
from sycon5.session import log                             # noqa: E402
from ui_recorder import png_of_window                      # noqa: E402

SCRATCH = r"C:\Source\Repos\_Openn5\Sycon5App\spike\scratch"
SRC = os.path.join(SCRATCH, "PROD_Sorter_Lower_repair", "HilscherIOCard1")
DST = os.path.join(SCRATCH, "_probe_drop")
ITEM, GSDML = "PN/PN Coupler X2 [DAP X2 V4.2]", "GSDML-V2.35-Siemens-PNPNIOC-20200924.xml"

shutil.rmtree(DST, ignore_errors=True)
os.makedirs(DST)
shutil.copy2(os.path.join(SRC, "HilscherPnCard_1.spj"), DST)
shutil.copytree(os.path.join(SRC, "HilscherPnCard_1"), os.path.join(DST, "HilscherPnCard_1"))
spj = os.path.join(DST, "HilscherPnCard_1.spj")

d = SyconDriver()
try:
    d.open(spj)
    s = d.session
    s.close_menus()
    s.bring_front()
    r = drawing_pane(s.main()).rectangle()
    log("drawing pane:", (r.left, r.top, r.right, r.bottom), "size", (r.width(), r.height()))
    png_of_window(s.main().handle, os.path.join(DST, "window.png"))
    cols, rows, count, _grey = colour_lines(r)
    for key, n in count.most_common(8):
        R, G, B = key
        if not (G > R + 40 and G > B):
            continue
        top_rows = rows[key].most_common(4)
        top_cols = cols[key].most_common(4)
        log("green %s n=%d rows %s cols %s" % (key, n, top_rows, top_cols))
        col = top_cols[0][0]
        ys = sorted(y for y, c in rows[key].items() if cols[key][col])
        ys_in_col = sorted(y for y in rows[key] if y)  # the rows this colour fills (any column)
        log("   column %d: the colour's rows span %s..%s" % (col, ys_in_col[0] if ys_in_col else None, ys_in_col[-1] if ys_in_col else None))
    # candidate points: the vertical bus (x 8..12) at several heights, then the controller's stub (y 72..76, x 8..34)
    points = [(10, 150), (10, 300), (10, 120), (10, 450), (20, 74), (11, 200)]
    before = len(s.nodes())
    for dx, dy in points:
        item = catalog.catalog_item(s, "slave", ITEM, GSDML)
        label = catalog.drop(s, item, dx, dy)
        log("drop at %s -> %r" % ((dx, dy), label))
        if label:
            png_of_window(s.main().handle, os.path.join(DST, "after_drop.png"))
            break
    log("nodes before %d after %d" % (before, len(s.nodes())))
finally:
    log("close (nothing saved):", d.close())
