"""Locate the bus lines of the netDevice drawing by colour (the drawing is custom-drawn, not UIA-readable):
one BitBlt capture of the pane, then per-colour line detection - every saturated colour is reported with the
columns (vertical lines) and rows (horizontal lines) it fills. Read-only.

Usage:  python -I scripts/find_buslines.py [step]
Prints lines as pane-relative coordinates (dx / dy usable with probe_add_device.py) and screen coordinates.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collections import Counter, defaultdict
import win32gui, win32ui, win32con
from _probe_lib import sycon_main

STEP = int(sys.argv[1]) if len(sys.argv) > 1 else 2


def capture(rect):
    w, h = rect.width(), rect.height()
    hdesk = win32gui.GetDesktopWindow()
    hdc = win32gui.GetWindowDC(hdesk)
    src = win32ui.CreateDCFromHandle(hdc)
    mem = src.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(src, w, h)
    mem.SelectObject(bmp)
    mem.BitBlt((0, 0), (w, h), src, (rect.left, rect.top), win32con.SRCCOPY)
    info = bmp.GetInfo()
    bits = bmp.GetBitmapBits(True)
    mem.DeleteDC(); src.DeleteDC(); win32gui.ReleaseDC(hdesk, hdc); win32gui.DeleteObject(bmp.GetHandle())
    return bits, info["bmWidthBytes"], info["bmBitsPixel"] // 8, w, h


def lines(rect, step=STEP):
    """Returns {colour: (Counter(columns), Counter(rows), n)} for saturated colours, plus the grey rows."""
    bits, stride, bpp, w, h = capture(rect)
    cols, rows, n = defaultdict(Counter), defaultdict(Counter), Counter()
    grey_rows = Counter()
    for y in range(0, h, step):
        row = bits[y * stride:(y + 1) * stride]
        for x in range(0, w, step):
            b, g, r = row[x * bpp], row[x * bpp + 1], row[x * bpp + 2]
            mx, mn = max(r, g, b), min(r, g, b)
            if mx - mn > 40:
                key = (r // 16 * 16, g // 16 * 16, b // 16 * 16)
                cols[key][x] += 1; rows[key][y] += 1; n[key] += 1
            elif mx < 200 and mx > 90:
                grey_rows[y] += 1
    return cols, rows, n, grey_rows


if __name__ == "__main__":
    main = sycon_main()
    pane = [p for p in main.descendants(control_type="Pane") if p.element_info.automation_id == "3000"][0]
    r = pane.rectangle()
    cols, rows, n, grey_rows = lines(r)
    print("pane rect:", r, "step", STEP)
    print("grey rows (dy: hits):", grey_rows.most_common(4))
    for key, cnt in n.most_common(8):
        c, rw = cols[key], rows[key]
        ys = sorted(rw)
        print(f"colour RGB~{key}: {cnt} samples | columns {c.most_common(4)} | rows {rw.most_common(3)} | dy range {ys[0]}..{ys[-1]}")
        dx, hits = c.most_common(1)[0]
        if hits * STEP > 100:
            print(f"   -> VERTICAL LINE at dx={dx} (screen x={r.left + dx}), dy {ys[0]}..{ys[-1]}: drop at dx={dx} dy={(ys[0] + ys[-1]) // 2}")
