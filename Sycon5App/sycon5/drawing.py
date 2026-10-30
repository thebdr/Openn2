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


LONG_VERTICAL_PX = 200          # a green column this long is the laid-out bus (canvas.apply_layout), never a drop line


def pick_green(cols, rows, count, step=2):
    """The controller's green line from a colour scan: ('h', dy, x0, x1) or ('v', dx, y0, y1), pane-relative; None.
    A long vertical green line wins (2026-10-30: on a project `canvas.apply_layout` laid out, the bus is vertical at x
    8..12 and the devices hang on horizontal branches - the most common green row was a device's branch, y 670 x
    8..548, and six drops there attached nothing; a drop on the vertical bus attached at once). Else, as before, the
    most common horizontal row (a SYCON.net default layout: the controller's horizontal line), else a vertical one."""
    for key, n in count.most_common(10):
        R, G, B = key
        if not (G > R + 40 and G > B and n > 50):
            continue
        rw, c = rows[key], cols[key]
        dx, vhits = c.most_common(1)[0]
        if vhits * step >= LONG_VERTICAL_PX:
            strong = sorted(x for x, k in c.items() if k >= vhits * 0.8)
            ys = sorted(rw)
            return ("v", (strong[0] + strong[-1]) // 2, ys[0], ys[-1])
        dy, hits = rw.most_common(1)[0]
        if hits * step > 100:
            xs = sorted(c)
            return ("h", dy, xs[0], xs[-1])
        if vhits * step > 100:
            ys = sorted(rw)
            return ("v", dx, ys[0], ys[-1])
    return None


def crossing_rows(rows, count, step=2, min_px=30):
    """The pane rows a horizontal green line crosses (a device's branch on a laid-out bus) - drop points avoid them."""
    out = set()
    for key, n in count.most_common(10):
        R, G, B = key
        if G > R + 40 and G > B and n > 50:
            out |= {y for y, k in rows[key].items() if k * step >= min_px}
    return out


def locate_lines(main, step=2):
    """Returns (pane rect, grey root line dy or None, green line or None, the rows branch lines cross).
    green = ('h', dy, x0, x1) for a horizontal line, ('v', dx, y0, y1) for a vertical one (pane-relative)."""
    r = drawing_pane(main).rectangle()
    cols, rows, count, grey = colour_lines(r, step)
    h = r.height()
    cand = [(hits, dy) for dy, hits in grey.items() if 10 < dy < h - 30 and hits * step > r.width() // 4]
    grey_dy = max(cand)[1] if cand else None
    return r, grey_dy, pick_green(cols, rows, count, step), crossing_rows(rows, count, step)


def master_points(grey_dy):
    """Candidate drop points (pane-relative) on the root line for a Master."""
    return [(400, grey_dy), (300, grey_dy), (500, grey_dy), (400, grey_dy - 1), (400, grey_dy + 1)]


def slave_points(green, crossings=()):
    """Candidate drop points (pane-relative) on a controller's green line for a Slave, proven-first. On a vertical line
    each point is moved down off the rows a branch crosses (`crossings`), 4 px clear - a drop on a junction could take
    the branch's device line."""
    if green[0] == "h":
        x0, x1, dy = green[2], green[3], green[1]
        return [(x0 + 170, dy), ((x0 + x1) // 2, dy), (x0 + 100, dy), (x1 - 120, dy), (x0 + 170, dy - 1), (x0 + 170, dy + 1)]
    dx, y0, y1 = green[1], green[2], green[3]
    out = []
    for y in (y0 + 128, (y0 + y1) // 2, y0 + 250, y1 - 150):
        while any(abs(y - c) < 4 for c in crossings) and y < y1:
            y += 1
        if y0 < y < y1 and (dx, y) not in out:
            out.append((dx, y))
    return out


def dark_profile(rect, threshold=600, x0=40, step=2):
    """Dark-pixel count per pixel row of a captured rectangle (a signature of the rows a custom grid shows)."""
    bits, stride, bpp, w, h = capture(rect)
    prof = []
    for y in range(h):
        row = bits[y * stride:(y + 1) * stride]
        prof.append(sum(1 for x in range(x0, w, step) if (row[x * bpp] + row[x * bpp + 1] + row[x * bpp + 2]) < threshold))
    return prof


def measure_shift(before, after, skip=18, max_shift=None):
    """The upward pixel shift of a profile between two captures (0 when nothing moved)."""
    h = len(before)
    best, best_err = 0, None
    for s in range(0, (max_shift or h - 20)):
        n = h - s - skip
        if n <= 10:
            break
        err = sum(abs(before[y + s] - after[y]) for y in range(skip, h - s)) / n
        if best_err is None or err < best_err - 1e-9:
            best, best_err = s, err
    return best


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
