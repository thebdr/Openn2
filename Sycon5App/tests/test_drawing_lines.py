"""The controller's green line chosen from a colour scan (2026-10-30: on a laid-out project the bus is vertical, x 8..12,
and the most common green row was a device's branch - six drops there attached nothing; the probe's drop on the
vertical bus attached at once), on synthetic scans: the laid-out bus, SYCON.net's default horizontal line with short
drop lines, the drop points kept off the rows a branch crosses."""
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from sycon5 import drawing  # noqa: E402

GREEN = (80, 160, 128)


def scan(segments):
    """cols, rows, count as colour_lines gives them (step 2) for green segments ('h', y, x0, x1) / ('v', x, y0, y1)."""
    cols, rows, count = defaultdict(Counter), defaultdict(Counter), Counter()
    for kind, a, b0, b1 in segments:
        for b in range(b0 - b0 % 2, b1 + 1, 2):
            x, y = (b, a) if kind == "h" else (a, b)
            cols[GREEN][x] += 1
            rows[GREEN][y] += 1
            count[GREEN] += 1
    return cols, rows, count


def laid_out():
    """The probe's scan: the vertical bus at x 8 and 10 from y 22 to 684, branches at 208, 626, 648, 670."""
    segs = [("v", 8, 22, 684), ("v", 10, 22, 684)]
    segs += [("h", y, 8, x1) for y, x1 in ((208, 400), (626, 400), (648, 470), (670, 548))]
    return segs


def test_the_laid_out_bus_is_the_vertical_line():
    cols, rows, count = scan(laid_out())
    green = drawing.pick_green(cols, rows, count)
    assert green[0] == "v" and green[1] == 9 and green[2] == 22 and green[3] == 684, green


def test_a_default_layout_keeps_the_horizontal_line():
    segs = [("h", 300, 40, 900)] + [("v", x, 300, 330) for x in range(100, 900, 70)]     # short drop lines
    cols, rows, count = scan(segs)
    green = drawing.pick_green(cols, rows, count)
    assert green == ("h", 300, 40, 900), green
    assert drawing.slave_points(green)[0] == (210, 300), "the proven-first point of a horizontal line, unchanged"


def test_drop_points_keep_off_the_branch_rows():
    cols, rows, count = scan(laid_out() + [("h", y, 8, 300) for y in (150, 151, 152)])
    green = drawing.pick_green(cols, rows, count)
    crossings = drawing.crossing_rows(rows, count)
    assert {150, 152, 208, 670} <= crossings and 300 not in crossings
    points = drawing.slave_points(green, crossings)
    assert points and all(x == 9 for x, _y in points)
    assert all(min(abs(y - c) for c in crossings) >= 4 for _x, y in points), (points, sorted(crossings))
    assert all(22 < y < 684 for _x, y in points)


def test_nothing_green_is_none():
    cols, rows, count = scan([])
    assert drawing.pick_green(cols, rows, count) is None
