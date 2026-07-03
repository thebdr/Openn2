"""Phase 100a - the validation reporting spine: the address-format helper + the rich report renderer
(banners, the aligned line, the InfoBlock middle, the cross-check Cmp + dual-workbook links, the
errors-only filter, the HTML). Pure + data-independent."""
from _harness import run, eq, ok
from pipeline4.core.finding import Finding
from pipeline4.core.model import Cmp, InfoBlock
from pipeline4.domain.validation import address
from pipeline4.io import render


def _banner(phase, title):
    return Finding(phase=phase, type="", severity="PHASE", detail=f"{phase} {title}")


# --- address ----------------------------------------------------------------------------------- #
def test_address_format_and_kind():
    ok(address.format_ok("I20.0") and address.format_ok("Q0.1"), "valid 2-part dotted")
    ok(address.format_ok("I0.1.2.3"), "valid 4-part")
    ok(not address.format_ok("I:0.0"), "Rockwell colon rejected")
    ok(not address.format_ok("X1.0"), "bad leading letter")
    ok(not address.format_ok("I1.2.3"), "3-part dot-count rejected")
    ok(address.format_ok("") and address.format_ok("ABC") and address.format_ok("2.0"),
       "empty / non-dotted / bare-number are not address attempts")
    ok(address.is_input("I3.0") and address.is_output("Q1.0") and address.is_output("O5.2"))
    eq((address.kind("i7.0"), address.norm("  q 0.1 ")), ("I", "Q0.1"))


# --- the renderer ------------------------------------------------------------------------------ #
def test_banner_lines_and_render():
    findings = [_banner(110, "Validate I/O List"),
                Finding(phase=110, type="x", severity="WARN", detail="hi", location="IO!A1")]
    lines = render.render_lines(findings)
    eq(lines[:3], ["", "110 Validate I/O List", "=" * 21], "a banner -> blank, title, === underline")
    ok(lines[3].startswith("[HEAD] type") and "location" in lines[3] and lines[3].endswith(":: detail"),
       "each group opens with the [HEAD] column-header line")
    ok("|" not in lines[3], "a no-info group's header carries no pipes")
    ok(lines[4].startswith("[WARN] 110-x") and "IO!A1" in lines[4] and lines[4].endswith(":: hi"))
    ok("|" not in lines[4], "a no-info group's data lines carry no empty | | placeholders")


def test_info_block_columns():
    f = Finding(phase=110, type="addr_format", severity="FAIL", detail="bad address", location="IO!G5",
                info=InfoBlock(bit="I0.0", fld="S1", desc_l1="DOOR"))
    head, line = render.render_lines([f])
    ok("| bit" in head and "| FLD" in head and "| desc_l1" in head, "the header titles the used columns")
    ok("desc_l1b" not in head and "drawing" not in head and "type-index" not in head,
       "the UNUSED columns are dropped from the group's layout entirely")
    ok("| I0.0 | S1" in line and "| DOOR" in line, "the used InfoBlock cells render between |s")
    ok(line.startswith("[FAIL] 110-addr_format"))
    eq(line.count("|"), 3, "exactly the 3 used columns - no empty trailing placeholders")


def test_crosscheck_cmp_and_dual_link():
    f = Finding(phase=130, type="cem_addr_fld", severity="FAIL", detail="device mismatch",
                location="CE!F5", doc="ce.xlsx", location2="IO!G9", doc2="io.xlsx",
                cmp=Cmp("I0.0", "I0.0", True, "S1", "S2", False))
    recs = render.render_records([f])
    eq(recs[0].level, "HEAD", "the group opens with its header line")
    ok("| bit" in recs[0].text and "| FLD" in recs[0].text, "a cmp group uses the bit + FLD columns")
    rec = recs[1]
    ok("CE!F5 vs IO!G9" in rec.text, "the dual location column")
    # the comparisons render IN the bit + FLD info columns (not duplicated before the detail)
    ok("| I0.0 === I0.0 | S1 =/= S2" in rec.text, "the aligned comparisons live in the info columns")
    ok(rec.text.endswith(":: device mismatch"), "the detail carries no duplicated Cmp body")
    eq(len(rec.links), 2, "two clickable link spans (loc1, loc2)")
    eq([(rec.text[s.start:s.end], s.doc) for s in sorted(rec.links, key=lambda s: s.start)],
       [("CE!F5", "ce.xlsx"), ("IO!G9", "io.xlsx")], "each span covers its cell + carries its workbook")
    eq(rec.uid, f.uid, "a FAIL line carries the finding uid")
    # the layered marks (user-reviewed styling): BOTH comparisons get a whole-cell neutral span;
    # the operators get their own green/red span; the =/='s differing chars get the highlight span
    whole = [m for m in rec.marks if m.style == "cmp"]
    eq([rec.text[m.start:m.end] for m in whole], ["I0.0 === I0.0", "S1 =/= S2"],
       "both comparisons carry the whole-cell neutral span")
    ops = [(rec.text[m.start:m.end], m.style) for m in rec.marks
           if m.style in ("cmp_op_eq", "cmp_op_ne")]
    eq(ops, [("===", "cmp_op_eq"), ("=/=", "cmp_op_ne")], "the operators are marked green/red")
    diffs = [m for m in rec.marks if m.style == "cmp_diff"]
    eq([rec.text[m.start:m.end] for m in diffs], ["1", "2"],
       "the =/= highlight marks exactly the differing chars")
    html = render.render_html([f])
    ok('<span class="cmp cmpopeq">===</span>' in html, "the === operator composes cmp+green in HTML")
    ok('<span class="cmp cmpopne">=/=</span>' in html, "the =/= operator composes cmp+red in HTML")
    ok('<span class="cmp cmpdiff">1</span>' in html and '<span class="cmp cmpdiff">2</span>' in html,
       "the diff chars compose the neutral colour + the background highlight")
    ok(".cmpdiff{background:" in html, "the diff style is a BACKGROUND, not an underline")


def test_cmp_diff_runs():
    eq(render._char_diff_runs("ABC", "ABC"), [], "identical -> no runs")
    eq(render._char_diff_runs("ABCD", "AXCY"), [(1, 2), (3, 4)], "two isolated diffs -> two runs")
    eq(render._char_diff_runs("AB", "ABCD"), [(2, 4)], "the longer tail counts as different")


def test_errors_only_filter():
    findings = [_banner(110, "T"),
                Finding(phase=110, type="ok", severity="PASS", detail="p"),
                Finding(phase=110, type="sk", severity="SKIP", detail="s"),
                Finding(phase=110, type="w", severity="WARN", detail="w"),
                Finding(phase=110, type="f", severity="FAIL", detail="f")]
    kept = [r.level for r in render.render_records(findings, errors_only=True)]
    eq(kept, ["PHASE", "HEAD", "WARN", "FAIL"], "errors-only drops PASS/SKIP, keeps banner+head+WARN+FAIL")
    full = [r.level for r in render.render_records(findings, errors_only=False)]
    eq(full, ["PHASE", "HEAD", "PASS", "SKIP", "WARN", "FAIL"], "complete keeps everything")


def test_reports_and_html():
    findings = [_banner(110, "Validate I/O List"),
                Finding(phase=110, type="f", severity="FAIL", detail="boom", location="IO!A1", doc="io.xlsx")]
    rep = render.reports(findings)
    ok("complete" in rep and "errors" in rep and "110 Validate I/O List" in rep["complete"])
    html = render.html_reports(findings)["complete"]
    ok(html.startswith("<!DOCTYPE html>") and "white-space:pre" in html, "standalone no-wrap HTML")
    ok('<div class="line fail">' in html, "the FAIL level class")
    ok('<span class="loc">IO!A1</span>' in html, "the location cell carries the link styling")
    ok("1 failed" in html, "the summary counts")


if __name__ == "__main__":
    import sys
    sys.exit(run("validation_render", [
        ("address_format_and_kind", test_address_format_and_kind),
        ("banner_lines_and_render", test_banner_lines_and_render),
        ("info_block_columns", test_info_block_columns),
        ("crosscheck_cmp_and_dual_link", test_crosscheck_cmp_and_dual_link),
        ("cmp_diff_runs", test_cmp_diff_runs),
        ("errors_only_filter", test_errors_only_filter),
        ("reports_and_html", test_reports_and_html),
    ]))
