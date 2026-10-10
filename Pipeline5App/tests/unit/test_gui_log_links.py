"""The log pane's clickable spans (workbench/log_view.py): one shared `link` / `errlink` tag and a per-line lookup
- a click reaches the span under the mouse, the tag count never grows with the log, and a validation-sized log
(thousands of linked findings) appends and scrolls in chunks without the stalls a tag per link caused (user
2026-10-10: "the animation during the running phases lags"). Tk, no dialogs; the window stays withdrawn."""
import time
import tkinter as tk

from _harness import run, eq, ok
from pipeline5.findings.report_renderer import LinkSpan, RenderRec
from pipeline5.workbench.log_view import LogView


def _view(**callbacks):
    root = tk.Tk()
    root.withdraw()
    return root, LogView(root, **callbacks)


def _line(level, uid, text, *cells):
    """A finding line whose `cells` (`Sheet!Cell` tokens, each with its doc) are links at their positions."""
    spans = tuple(LinkSpan(text.index(cell), text.index(cell) + len(cell), doc) for cell, doc in cells)
    return RenderRec("line", level, text, spans, uid)


def test_a_click_reaches_the_span_under_the_mouse():
    """Left-click a `Sheet!Cell` span -> on_link(doc, sheet, cell) of THAT span (two on one line kept apart, the
    gap between them nothing); left-click a treatable line's `[LEVEL]` -> on_errjump(uid), right-click -> the
    treat menu for that uid; a PASS line has no errlink; clear() forgets every span."""
    links, jumps, menus = [], [], []
    root, view = _view(on_link=lambda d, s, c: links.append((d, s, c)), on_errjump=jumps.append,
                       on_errtreat=lambda uid, level: None)
    view._err_menu = lambda _event, uid: menus.append(uid)
    try:
        view.append("PHASE", "100 Documents Validation")
        view.append_records([
            _line("FAIL", "u1", "[FAIL]  NET!O12  bad", ("NET!O12", "io.xlsx")),
            _line("WARN", "u2", "[WARN]  NET!O20 vs CE!B7  differ", ("NET!O20", "io.xlsx"), ("CE!B7", "ce.xlsx")),
            _line("PASS", "", "[PASS]  NET!O30  ok", ("NET!O30", "io.xlsx"))])
        first = int(view.text.index("end-1c").split(".")[0]) - 3        # the FAIL line's number
        click = lambda handler, line, col: (setattr(view, "_at", lambda _e: (line, col)), handler(None))
        click(view._click_link, first, 10)
        click(view._click_link, first + 1, 9)
        click(view._click_link, first + 1, 21)
        click(view._click_link, first + 1, 17)                          # " vs " between the two links
        click(view._click_link, first + 2, 9)
        eq(links, [("io.xlsx", "NET", "O12"), ("io.xlsx", "NET", "O20"), ("ce.xlsx", "CE", "B7"),
                   ("io.xlsx", "NET", "O30")], "each click reaches its own span")
        click(view._click_err, first, 2)
        click(view._click_err, first + 1, 2)
        click(view._click_err, first + 2, 2)
        click(view._click_err_menu, first + 1, 2)
        eq((jumps, menus), (["u1", "u2"], ["u2"]), "the [LEVEL] of a treatable line; a PASS line none")
        eq([str(i) for i in view.text.tag_ranges("link")][:2], [f"{first}.8", f"{first}.15"], "the span tagged")
        view.clear()
        click(view._click_link, first, 10)
        click(view._click_err, first, 2)
        eq((len(links), len(jumps)), (4, 2), "cleared: nothing left to click")
    finally:
        root.destroy()


def test_the_tag_count_never_grows_with_the_log():
    """A tag per link / per error line made thousands of tags on a validation run; now the set is fixed."""
    root, view = _view(on_link=lambda *a: None, on_errjump=lambda u: None)
    try:
        view.append_records([_line("FAIL", "u0", "[FAIL]  NET!O1  x", ("NET!O1", "io.xlsx"))])
        before = set(view.text.tag_names())
        view.append_records([_line("FAIL", f"u{n}", f"[FAIL]  NET!O{n}  x", (f"NET!O{n}", "io.xlsx"))
                             for n in range(2, 600)])
        eq(set(view.text.tag_names()), before, "the same tags after 600 linked findings")
    finally:
        root.destroy()


def test_a_validation_sized_log_appends_and_scrolls_without_stalls():
    """4400 linked, treatable findings appended in chunks of 150 with a scroll after each (the drain's rhythm) - the
    old tag-per-link pane took tens of seconds (one `see` 52 s on FVT); now it stays well under the bound."""
    root, view = _view(on_link=lambda *a: None, on_errjump=lambda u: None)
    try:
        records = [_line("FAIL" if n % 3 else "WARN", f"u{n}", f"[FAIL]  NET SAFETY!O{n}  vs CE!B{n} detail {n}",
                         (f"NET SAFETY!O{n}", "io.xlsx"), (f"CE!B{n}", "ce.xlsx")) for n in range(4400)]
        start, worst = time.perf_counter(), 0.0
        for at in range(0, len(records), 150):
            t = time.perf_counter()
            view.append_records(records[at:at + 150], scroll=False)
            view.scroll_end()
            root.update()
            worst = max(worst, time.perf_counter() - t)
        total = time.perf_counter() - start
        ok(total < 10.0 and worst < 2.0, f"total {total:.2f} s, worst chunk {worst:.2f} s")
    finally:
        root.destroy()


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_log_links", [
        ("a_click_reaches_the_span_under_the_mouse", test_a_click_reaches_the_span_under_the_mouse),
        ("the_tag_count_never_grows_with_the_log", test_the_tag_count_never_grows_with_the_log),
        ("a_validation_sized_log_appends_and_scrolls_without_stalls",
         test_a_validation_sized_log_appends_and_scrolls_without_stalls),
    ]))
