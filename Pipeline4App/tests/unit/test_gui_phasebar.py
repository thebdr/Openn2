"""GUI M4 - the phase bar's pure word-wrap helper (the chevron dropdown + the 2-row grid layout are a
manual `python launch_gui.py` check). Importing `phasebar` headless is safe: tkinter is imported but no
`Tk()` is created, so no display is needed."""
from _harness import run, eq, ok
from pipeline4.gui import phasebar


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


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_phasebar", [
        ("wrap_short_text_one_line", test_wrap_short_text_one_line),
        ("wrap_breaks_on_width", test_wrap_breaks_on_width),
        ("wrap_long_word_gets_its_own_line", test_wrap_long_word_gets_its_own_line),
    ]))
