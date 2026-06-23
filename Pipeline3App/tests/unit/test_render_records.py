"""The GUI link path: `render_records` carries the SAME text as `render_lines` PLUS, per line, the
char spans of the `location`/`location2` cells and their workbook (`doc`/`doc2`) - so the log pane
can make each cell a clickable Excel link without re-parsing text. Data-independent (synthetic
LogEntries); the text-identity case also locks the golden single-source property."""
from _harness import run, ok, eq
from pipeline3.core.model import LogEntry, InfoBlock, banner
from pipeline3.io import render


def _log():
    return [
        banner(100, "PHASE 100 - Documents Validation"),
        LogEntry(level="PASS", phase=110, type="hdr_ok", detail="header ok", info=InfoBlock(bit="I0.0", fld="+MS1")),
        LogEntry(level="SKIP", phase=110, type="row_skip", detail="skipped row", info=InfoBlock(fld="+MS2")),
        LogEntry(level="INFO", phase=110, type="ctx", detail="for context"),
        LogEntry(level="FAIL", phase=110, type="ip_missing", detail="IP missing",
                 location="NET SAFETY 50!V5", doc="IOList.xlsx", info=InfoBlock(fld="+MS0")),
        # two 130 lines so the WARN's shorter location gets right-padded -> exercises padding-stripping
        LogEntry(level="WARN", phase=130, type="xc_warn", detail="A1 vs IOList | I0.0 =/= I0.1",
                 location="AREA 1!F5", doc="CEMatrix.xlsx",
                 location2="NET SAFETY 50!O30", doc2="IOList.xlsx", info=InfoBlock(fld="+MS3")),
        LogEntry(level="FAIL", phase=130, type="xc_long", detail="dangling ref",
                 location="CAUSE&EFFECT MATRIX!AB12", doc="CEMatrix.xlsx", info=InfoBlock(fld="+MS5")),
        LogEntry(level="FAIL", phase=130, type="xc_fail", detail="missing in C&E", info=InfoBlock(fld="+MS4")),
    ]


def _lines_from_records(recs):
    out = []
    for r in recs:
        if r.kind == "banner":
            out.extend(render.banner_lines(r.text))
        else:
            out.append(r.text)
    return out


def _line_recs(log, errors_only=False):
    return [r for r in render.render_records(log, errors_only=errors_only) if r.kind == "line"]


def test_text_identity_with_render_lines():
    """The records' reconstructed text == render_lines exactly: ONE source, golden cannot drift."""
    log = _log()
    eq(_lines_from_records(render.render_records(log)), render.render_lines(log))


def test_errors_only_parity():
    log = _log()
    eq(_lines_from_records(render.render_records(log, errors_only=True)),
       render.render_lines(log, errors_only=True))
    levels = [r.level for r in _line_recs(log, errors_only=True)]
    ok("PASS" not in levels and "SKIP" not in levels, "errors_only drops PASS/SKIP")


def test_primary_span_is_cell_and_doc():
    warn = next(r for r in _line_recs(_log()) if r.level == "WARN")
    eq(len(warn.links), 2, "WARN carries location + location2 spans")
    sp = warn.links[0]
    eq(warn.text[sp.start:sp.end], "AREA 1!F5", "primary span is the location cell")
    eq(sp.doc, "CEMatrix.xlsx", "primary span carries the location's workbook")


def test_secondary_span_is_location2_and_doc2():
    warn = next(r for r in _line_recs(_log()) if r.level == "WARN")
    sp2 = warn.links[1]
    eq(warn.text[sp2.start:sp2.end], "NET SAFETY 50!O30", "secondary span is the location2 cell")
    eq(sp2.doc, "IOList.xlsx", "secondary span carries the OTHER workbook (doc2)")


def test_single_link_for_plain_fail():
    fail = next(r for r in _line_recs(_log()) if "NET SAFETY 50!V5" in r.text)
    eq(len(fail.links), 1, "a non-cross-check FAIL has just the primary cell link")
    eq(fail.links[0].doc, "IOList.xlsx")


def test_no_span_without_location():
    recs = _line_recs(_log())
    for marker in ("header ok", "skipped row", "for context", "missing in C&E"):   # the no-location lines
        r = next(rr for rr in recs if rr.text.rstrip().endswith(marker))
        eq(r.links, (), f"line ending {marker!r} (no location) has no link span")


def test_span_covers_cell_not_padding():
    for r in _line_recs(_log()):
        for sp in r.links:
            cell = r.text[sp.start:sp.end]
            ok(cell and cell == cell.strip() and "!" in cell, f"span is the bare cell: {cell!r}")


if __name__ == "__main__":
    raise SystemExit(run("render_records", [
        ("text_identity_with_render_lines", test_text_identity_with_render_lines),
        ("errors_only_parity", test_errors_only_parity),
        ("primary_span_is_cell_and_doc", test_primary_span_is_cell_and_doc),
        ("secondary_span_is_location2_and_doc2", test_secondary_span_is_location2_and_doc2),
        ("single_link_for_plain_fail", test_single_link_for_plain_fail),
        ("no_span_without_location", test_no_span_without_location),
        ("span_covers_cell_not_padding", test_span_covers_cell_not_padding),
    ]))
