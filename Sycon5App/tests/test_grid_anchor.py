"""The IP Address Table's resync anchor (2026-10-30: a resume wrote rows 1-6, its next targets were rows 48 and 61, and
after a half-view scroll the anchor - the last row written, row 6 - was out of view: "scroll lost"). The anchor is the
lowest row in view, which a half-view scroll keeps in view; `bottom_row` finds it."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from sycon5 import controller  # noqa: E402
from sycon5.controller import ROW_H, ROW_Y0, bottom_row  # noqa: E402


def centre(abs_row, scrolled):
    return ROW_Y0 + ROW_H * abs_row - scrolled


def test_the_lowest_row_in_view():
    height, margin = 700, 10
    for scrolled in (0, 16, 100, 448, 1000):
        a, y = bottom_row(scrolled, height, margin)
        assert y == centre(a, scrolled) and y <= height - margin < y + ROW_H, (scrolled, a, y)


def test_a_half_view_scroll_keeps_the_anchor_in_view_and_loses_the_top_row():
    height, margin = 700, 10
    visible = (height - ROW_Y0) // ROW_H
    a, _y = bottom_row(0, height, margin)
    shift = (visible // 2) * ROW_H
    assert ROW_Y0 - 4 <= centre(a, shift) <= height - 4, "the bottom anchor is still in view after the scroll"
    assert centre(6, shift) < ROW_Y0 - 4, "row 6, the old anchor, has left the view - the failure of 2026-10-30"


def test_no_row_in_a_too_small_grid():
    a, _y = bottom_row(0, ROW_Y0 + 5, 10)
    assert a < 0
    assert controller.bottom_row is bottom_row
