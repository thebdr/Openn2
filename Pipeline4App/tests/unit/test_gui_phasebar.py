"""GUI M4 - the phase bar's pure helpers: the sub-button word-wrap + the narrow-font pick + the hover
shade (the chevron dropdown + the composite-button grid are a manual `python launch_gui.py` check).
Importing `phasebar` headless is safe: tkinter is imported but no `Tk()` is created."""
from _harness import run, eq, ok
from pipeline4.gui import phasebar, theme


def test_wrap_short_text_one_line():
    eq(phasebar._wrap("Run", 14), "Run", "text within width stays on one line")
    eq(phasebar._wrap("", 14), "", "empty text -> empty string")


def test_wrap_breaks_on_width():
    # "300  Documents Staging" word-wraps to <=14-char lines (greedy, whole words).
    wrapped = phasebar._wrap("300 Documents Staging", 14)
    lines = wrapped.split("\n")
    ok(all(len(line) <= 14 for line in lines), f"every line <= 14 chars: {lines!r}")
    eq(" ".join(lines), "300 Documents Staging", "no words lost or reordered")
    ok(len(lines) >= 2, "a long label spans multiple lines")


def test_wrap_long_word_gets_its_own_line():
    # A single word longer than the width still gets its own line (never split mid-word).
    eq(phasebar._wrap("Supercalifragilistic", 8), "Supercalifragilistic", "an over-long word is one line")
    eq(phasebar._wrap("a Supercalifragilistic b", 8).split("\n"),
       ["a", "Supercalifragilistic", "b"], "the long word breaks before + after itself")


def test_pick_narrow_prefers_semicondensed():
    fams = {"Arial", "Bahnschrift SemiCondensed", "Bahnschrift", "Segoe UI"}
    eq(theme.pick_narrow(fams), "Bahnschrift SemiCondensed", "the narrowest candidate wins")


def test_pick_narrow_falls_through_case_insensitive():
    eq(theme.pick_narrow({"arial narrow", "Segoe UI"}), "Arial Narrow", "matches case-insensitively")
    eq(theme.pick_narrow({"Comic Sans MS"}), "Segoe UI", "last-resort fallback is always returned")


def test_shade_darkens_hex():
    eq(phasebar._shade("#ffffff", 0.5), "#7f7f7f", "50% shade of white")
    eq(phasebar._shade("#000000"), "#000000", "black stays black")
    ok(phasebar._shade("#e84393") != "#e84393", "the hover shade differs from the fill")


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_phasebar", [
        ("wrap_short_text_one_line", test_wrap_short_text_one_line),
        ("wrap_breaks_on_width", test_wrap_breaks_on_width),
        ("wrap_long_word_gets_its_own_line", test_wrap_long_word_gets_its_own_line),
        ("pick_narrow_prefers_semicondensed", test_pick_narrow_prefers_semicondensed),
        ("pick_narrow_falls_through_case_insensitive", test_pick_narrow_falls_through_case_insensitive),
        ("shade_darkens_hex", test_shade_darkens_hex),
    ]))
