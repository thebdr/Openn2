"""The netDevice drawing (pane auto id 3000) is custom-drawn: its bus lines are located by colour from one BitBlt
capture. The grey root line (a Master is dropped on it) and a controller's green network line (a Slave is dropped
on it) move with the layout, so they are located before every drop.
"""
from collections import Counter, defaultdict

import win32con
import win32gui
import win32ui

DRAWING_PANE_ID = "3000"


def capture(rect):
    """BitBlt a screen rectangle; returns (bits, stride, bytes per pixel, width, height)."""
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
    mem.DeleteDC()
    src.DeleteDC()
    win32gui.ReleaseDC(hdesk, hdc)
    win32gui.DeleteObject(bmp.GetHandle())
    return bits, info["bmWidthBytes"], info["bmBitsPixel"] // 8, w, h


def colour_lines(rect, step=2):
    """Per saturated colour (quantised to 16): the columns and rows it fills; plus the grey rows."""
    bits, stride, bpp, w, h = capture(rect)
    cols, rows, count = defaultdict(Counter), defaultdict(Counter), Counter()
    grey_rows = Counter()
    for y in range(0, h, step):
        row = bits[y * stride:(y + 1) * stride]
        for x in range(0, w, step):
            b, g, r = row[x * bpp], row[x * bpp + 1], row[x * bpp + 2]
            mx, mn = max(r, g, b), min(r, g, b)
            if mx - mn > 40:
                key = (r // 16 * 16, g // 16 * 16, b // 16 * 16)
                cols[key][x] += 1
                rows[key][y] += 1
                count[key] += 1
            elif 90 < mx < 200:
                grey_rows[y] += 1
    return cols, rows, count, grey_rows


def drawing_pane(main):
    panes = [p for p in main.descendants(control_type="Pane") if p.element_info.automation_id == DRAWING_PANE_ID]
    if not panes:
        raise RuntimeError("netDevice drawing pane not found")
    return panes[0]


def locate_lines(main, step=2):
    """Returns (pane rect, grey root line dy or None, green line or None).
    green = ('h', dy, x0, x1) for a horizontal line, ('v', dx, y0, y1) for a vertical one (pane-relative)."""
    r = drawing_pane(main).rectangle()
    cols, rows, count, grey = colour_lines(r, step)
    h = r.height()
    cand = [(hits, dy) for dy, hits in grey.items() if 10 < dy < h - 30 and hits * step > r.width() // 4]
    grey_dy = max(cand)[1] if cand else None
    green = None
    for key, n in count.most_common(10):
        R, G, B = key
        if G > R + 40 and G > B and n > 50:
            rw, c = rows[key], cols[key]
            dy, hits = rw.most_common(1)[0]
            if hits * step > 100:
                xs = sorted(c)
                green = ("h", dy, xs[0], xs[-1])
                break
            dx, hits = c.most_common(1)[0]
            if hits * step > 100:
                ys = sorted(rw)
                green = ("v", dx, ys[0], ys[-1])
                break
    return r, grey_dy, green


def master_points(grey_dy):
    """Candidate drop points (pane-relative) on the root line for a Master."""
    return [(400, grey_dy), (300, grey_dy), (500, grey_dy), (400, grey_dy - 1), (400, grey_dy + 1)]


def slave_points(green):
    """Candidate drop points (pane-relative) on a controller's green line for a Slave, proven-first."""
    if green[0] == "h":
        x0, x1, dy = green[2], green[3], green[1]
        return [(x0 + 170, dy), ((x0 + x1) // 2, dy), (x0 + 100, dy), (x1 - 120, dy), (x0 + 170, dy - 1), (x0 + 170, dy + 1)]
    dx, y0, y1 = green[1], green[2], green[3]
    return [(dx, (y0 + y1) // 2), (dx, y0 + 150), (dx, y1 - 150)]


def text_bands(rect, band, threshold=600, x0=40):
    """Dark-pixel count per horizontal band of a captured rectangle (to find the text rows of a custom grid)."""
    bits, stride, bpp, w, h = capture(rect)
    out = []
    for y0 in range(0, h - band + 1, band):
        n = 0
        for y in range(y0, y0 + band):
            row = bits[y * stride:(y + 1) * stride]
            n += sum(1 for x in range(x0, w) if (row[x * bpp] + row[x * bpp + 1] + row[x * bpp + 2]) < threshold)
        out.append((y0, n))
    return out
