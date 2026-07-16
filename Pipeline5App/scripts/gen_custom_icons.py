"""Generate the CUSTOM phase-bar icons (the ones with no real emoji equivalent) into `assets/icons/`.

The four customs - db-write (300), io-arrows (500), pcb-board (700), code-file (800) - are drawn in
Twemoji's flat style + palette on the same 36-unit grid Twemoji uses, supersampled x8 and downscaled to
the official 72x72 PNG size, so they sit next to the official assets seamlessly.

DEV-TIME tool, run once when an icon changes (the PNGs are committed; the app never imports this):
    py -m pip install pillow   (or point PYTHONPATH at any dir holding Pillow)
    py scripts/gen_custom_icons.py
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONS_DIR = os.path.join(APP_ROOT, "assets", "icons")
GRID = 36          # the Twemoji design grid
OUT = 72           # the shipped size (matches the official 72x72 assets)
SS = 8             # supersample factor (draw at 288, LANCZOS down to 72)


def _canvas():
    img = Image.new("RGBA", (GRID * SS, GRID * SS), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _s(*coords):
    """Scale 36-grid coordinates to the supersampled canvas."""
    return [c * SS for c in coords]


def _save(img, name):
    img = img.resize((OUT, OUT), Image.LANCZOS)
    path = os.path.join(ICONS_DIR, name)
    img.save(path)
    print(f"wrote {path}")


def _polyline(d, pts, fill, width):
    """A round-capped, round-jointed polyline (PIL lines are butt-capped - cap the ends manually)."""
    w = width * SS
    scaled = [(x * SS, y * SS) for x, y in pts]
    d.line(scaled, fill=fill, width=int(w), joint="curve")
    r = w / 2
    for x, y in (scaled[0], scaled[-1]):
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def db_write():
    """300 Documents Staging - a database cylinder with a green arrow dropping in."""
    img, d = _canvas()
    body, top, band, green = "#5DADEC", "#8CCAF7", "#4A94D4", "#78B159"
    d.ellipse(_s(7, 22.4, 29, 31.6), fill=body)                      # cylinder bottom cap
    d.rectangle(_s(7, 17, 29, 27), fill=body)                        # cylinder body
    d.arc(_s(7, 15.9, 29, 25.1), start=0, end=180, fill=band, width=int(1.4 * SS))
    d.ellipse(_s(7, 12.4, 29, 21.6), fill=top)                       # cylinder top (lighter)
    d.rounded_rectangle(_s(15.4, 1, 20.6, 8.2), radius=1.6 * SS, fill=green)
    d.polygon(_s(10.4, 7.6) + _s(25.6, 7.6) + _s(18, 16.6), fill=green)
    _save(img, "db-write.png")


def io_arrows():
    """500 Signals Mapping - electrical I/O: green up-arrow block (input) + red down-arrow block (output)."""
    img, d = _canvas()
    d.rounded_rectangle(_s(1, 10, 17, 26), radius=4 * SS, fill="#78B159")
    d.rounded_rectangle(_s(19, 10, 35, 26), radius=4 * SS, fill="#DD2E44")
    up = [(9, 12.6), (13.6, 17.6), (10.6, 17.6), (10.6, 23.4), (7.4, 23.4), (7.4, 17.6), (4.4, 17.6)]
    dn = [(27, 23.4), (31.6, 18.4), (28.6, 18.4), (28.6, 12.6), (25.4, 12.6), (25.4, 18.4), (22.4, 18.4)]
    d.polygon([(x * SS, y * SS) for x, y in up], fill="#FFFFFF")
    d.polygon([(x * SS, y * SS) for x, y in dn], fill="#FFFFFF")
    _save(img, "io-arrows.png")


def pcb_board():
    """700 Hardware Generation - a PCB: green board, gold traces + pads, black IC with a pin-1 dot."""
    img, d = _canvas()
    d.rounded_rectangle(_s(2, 4, 34, 32), radius=4 * SS, fill="#77B255",
                        outline="#5C913B", width=int(1.6 * SS))
    gold, pad = "#FFCC4D", "#FFD983"
    for pts in ([(7, 10), (12.5, 10), (12.5, 14.4)], [(29, 10), (23.5, 10), (23.5, 14.4)],
                [(7, 26), (12.5, 26), (12.5, 21.6)], [(29, 26), (23.5, 26), (23.5, 21.6)],
                [(18, 8), (18, 13)], [(18, 28), (18, 23)]):
        _polyline(d, pts, gold, 1.7)
    for cx, cy in ((7, 10), (29, 10), (7, 26), (29, 26)):
        d.ellipse(_s(cx - 2, cy - 2, cx + 2, cy + 2), fill=pad)
    d.rounded_rectangle(_s(11.5, 13, 24.5, 23), radius=1.6 * SS, fill="#292F33")
    d.ellipse(_s(13, 14.4, 15, 16.4), fill="#F5F8FA")
    _save(img, "pcb-board.png")


def code_file():
    """800 Software Generation - a source-code file: Twemoji page, folded corner, blue `</>`."""
    img, d = _canvas()
    d.rounded_rectangle(_s(6, 2, 30, 34), radius=2.5 * SS, fill="#E1E8ED")
    # punch the folded corner out of the page (transparent above the fold diagonal)
    mask = Image.new("L", img.size, 255)
    ImageDraw.Draw(mask).polygon(_s(21, 1.5) + _s(30.5, 1.5) + _s(30.5, 11), fill=0)
    alpha = img.getchannel("A").point(lambda a: a)  # copy
    img.putalpha(Image.composite(alpha, Image.new("L", img.size, 0), mask))
    d = ImageDraw.Draw(img)
    d.polygon(_s(21, 2) + _s(30, 11) + _s(23.5, 11) + _s(21, 8.5), fill="#CCD6DD")
    _polyline(d, [(13.2, 16.6), (8.8, 21.5), (13.2, 26.4)], "#5DADEC", 2.4)
    _polyline(d, [(22.8, 16.6), (27.2, 21.5), (22.8, 26.4)], "#5DADEC", 2.4)
    _polyline(d, [(19.6, 14.8), (16.4, 27.2)], "#55ACEE", 2.2)
    _save(img, "code-file.png")


if __name__ == "__main__":
    os.makedirs(ICONS_DIR, exist_ok=True)
    db_write()
    io_arrows()
    pcb_board()
    code_file()
