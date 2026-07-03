"""The phase-100 validation report renderer - clean-room port of PL3's `io/render.py`, over PL4's
`core.finding.Finding` (with the optional `info`/`cmp`/`location2` payload) instead of PL3's `LogEntry`.

ONE source renders both reports; only the level filter differs - the complete log, and the error-only view
(banners + INFO + WARN + ERROR + FAIL, dropping PASS/SKIP/DEBUG). Columns auto-fit per (sub-)phase.

Rendered finding line (`<id>` is `<phase>-<type>`; `<location>` is `Sheet!Cell`, never the workbook name -
`doc`/`doc2` ride on the Finding for the GUI and are not rendered):
    [LEVL] <id>  <location>  |  bit | FLD | …  ::  <detail>
The info columns are laid out PER (SUB)PHASE GROUP and only the columns some line in that group
actually fills are rendered (no empty `| |` placeholders; a no-info group carries no pipes); each
group opens with a [HEAD] line carrying the column titles in the same alignment.
A cross-check (130/140) line renders its aligned `<caller> op <other>` comparisons IN the bit + FLD
columns (op = `===`/`=/=`), with MarkSpans so a viewer can style them: the whole comparison neutral
grey, the operator green (===) / red (=/=), and a =/='s differing chars background-highlighted.
A BANNER finding (severity == severity.BANNER) renders as a section header.

`render_records` is the GUI-facing twin of `render_lines`: it returns the SAME text plus, per line, the char
spans of `location`/`location2` and their workbook (`doc`/`doc2`) so a log pane can make each a clickable
link WITHOUT re-parsing. Both build their text from the ONE `_format_line`/`banner_lines` helper, so the
report text (the golden) cannot drift from the records.
"""
from __future__ import annotations

from collections import defaultdict, namedtuple

from pipeline4.core import severity
from pipeline4.core.model import InfoBlock

INFO_HEADERS = ("bit", "FLD", "desc_l1", "desc_l1b", "drawing", "type-index")
# The error-only report keeps banners/headers + INFO + WARN + ERRR + FAIL (drops PASS/SKIP/DEBG).
ERROR_REPORT_LEVELS = (severity.BANNER, severity.HEADER, "INFO", "WARN", "ERRR", "FAIL")
_EMPTY_INFO = InfoBlock()

# A clickable cell: [start, end) char offsets into the line + the workbook basename (doc/doc2).
LinkSpan = namedtuple("LinkSpan", "start end doc")
# A comparison styling span: [start, end) + style. The layered model (user-reviewed): "cmp" = the
# WHOLE comparison in a neutral grey (always, both kinds); "cmp_op_eq" / "cmp_op_ne" = the ===/=/=
# operator itself (green / red); "cmp_diff" = the chars that DIFFER across a =/= comparison,
# highlighted with a red-ish BACKGROUND (the text stays neutral). Spans NEST (op/diff inside cmp).
MarkSpan = namedtuple("MarkSpan", "start end style")
# One rendered entry: kind "banner" (text = title) or "line"; `links` = 0..2 LinkSpans (location, then
# location2); `uid` = the finding's stable hash (for a treatable line; "" for a banner / PASS);
# `marks` = the cross-check comparison MarkSpans (empty for a non-cmp line).
RenderRec = namedtuple("RenderRec", "kind level text links uid marks", defaults=("", ()))

_VS = " vs "                                  # the cross-check location separator: `<loc1> vs <loc2>`


def _is_banner(f) -> bool:
    return f.severity == severity.BANNER


def _location_text(f, loc1w: int = 0) -> str:
    """The location column: `<loc1> vs <loc2>` for a cross-check (loc1 left-padded to the per-phase
    caller-cell width so the `vs` lines up), else just `<loc1>`."""
    if f.location and f.location2:
        return f"{f.location:<{loc1w}}{_VS}{f.location2}"
    return f.location


def _cmp_cell(caller: str, other: str, eq: bool, wc: int, wo: int) -> str:
    """One side of the cross-check comparison as an info-block CELL (the comparison lives IN the bit /
    FLD columns, not duplicated in the detail): `<caller> op <other>`, aligned per-phase so the
    `===`/`=/=` operators line up."""
    return f"{caller:>{wc}} {'===' if eq else '=/='} {other:<{wo}}"


def _char_diff_runs(a: str, b: str) -> list:
    """The contiguous [start, end) char runs where `a` and `b` differ (compared left-aligned; positions
    beyond the shorter string count as different) - what the =/= underline marks on each side."""
    runs, start = [], None
    n = max(len(a), len(b))
    for i in range(n):
        differ = i >= len(a) or i >= len(b) or a[i] != b[i]
        if differ and start is None:
            start = i
        elif not differ and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, n))
    return runs


def _cmp_marks(caller: str, other: str, eq: bool, wc: int, cell_start: int) -> list:
    """The MarkSpans for one comparison cell at line offset `cell_start` (the caller right-aligns
    into its `wc` field, the operator sits at wc+1..wc+4, the other side starts at wc+5): the WHOLE
    `<caller> op <other>` goes neutral ('cmp'), the operator green/red ('cmp_op_eq'/'cmp_op_ne'),
    and a =/= comparison additionally background-highlights the DIFFERING chars on both sides."""
    marks = [MarkSpan(cell_start, cell_start + wc + 5 + len(other), "cmp"),
             MarkSpan(cell_start + wc + 1, cell_start + wc + 4,
                      "cmp_op_eq" if eq else "cmp_op_ne")]
    if eq:
        return marks
    caller_at = cell_start + (wc - len(caller))
    other_at = cell_start + wc + 5                    # after the caller field + " op "
    for start, end in _char_diff_runs(caller, other):
        if start < len(caller):
            marks.append(MarkSpan(caller_at + start, caller_at + min(end, len(caller)), "cmp_diff"))
        if start < len(other):
            marks.append(MarkSpan(other_at + start, other_at + min(end, len(other)), "cmp_diff"))
    return marks


def _phase_widths(entries) -> dict:
    """Per-(sub)phase column layout: the field maxima AND `used` - the ordered indices of the info
    columns that at least one line in THAT group actually fills (a plain non-empty cell, or the
    bit/FLD slots of a cmp line). Unused columns are DROPPED from the group's layout entirely - no
    empty `| |` placeholders; a group whose lines carry no info renders with no pipes at all. The
    [HEAD] titles participate in the widths so the header always fits its column."""
    w = defaultdict(lambda: {"id": len("type"), "loc": len("location"), "loc1": 0,
                             "info": [0] * len(INFO_HEADERS), "used": [],
                             "ca": 0, "oa": 0, "cf": 0, "of": 0})
    for f in entries:                         # pass 1: per-field maxima (incl. the caller-cell width)
        if _is_banner(f):
            continue
        ph = w[f.phase]
        ph["id"] = max(ph["id"], len(f.id))
        if f.location and f.location2:        # a cross-check's caller cell -> the `vs`-alignment width
            ph["loc1"] = max(ph["loc1"], len(f.location))
        for i, c in enumerate((f.info or _EMPTY_INFO).cells()):
            if f.cmp is not None and i in (0, 1):   # a cmp line renders the COMPARISON in bit/FLD instead
                continue
            if str(c):
                ph["info"][i] = max(ph["info"][i], len(str(c)))
                if i not in ph["used"]:
                    ph["used"].append(i)
        if f.cmp is not None:
            for i in (0, 1):                  # a comparison occupies the bit + FLD columns
                if i not in ph["used"]:
                    ph["used"].append(i)
            ph["ca"], ph["oa"] = max(ph["ca"], len(f.cmp.caller_addr)), max(ph["oa"], len(f.cmp.other_addr))
            ph["cf"], ph["of"] = max(ph["cf"], len(f.cmp.caller_fld)), max(ph["of"], len(f.cmp.other_fld))
    for ph in w.values():
        ph["used"].sort()
        if ph["ca"] or ph["oa"]:              # fold the composite `<caller> op <other>` cell widths in
            ph["info"][0] = max(ph["info"][0], ph["ca"] + ph["oa"] + 5)
            ph["info"][1] = max(ph["info"][1], ph["cf"] + ph["of"] + 5)
        for i in ph["used"]:                  # the [HEAD] titles fit their columns
            ph["info"][i] = max(ph["info"][i], len(INFO_HEADERS[i]))
    for f in entries:                         # pass 2: the combined-location width (needs loc1 from pass 1)
        if _is_banner(f):
            continue
        ph = w[f.phase]
        ph["loc"] = max(ph["loc"], len(_location_text(f, ph["loc1"])))
    return w


def banner_lines(detail: str) -> list:
    """The 3 text lines a banner renders as: a blank line, the title, its `===` underline."""
    return ["", detail, "=" * max(8, len(detail))]


def _format_line(f, w) -> tuple:
    """One finding -> (text, [LinkSpan], [MarkSpan]). The location column is `<loc1> vs <loc2>` for a
    cross-check (both clickable); a cross-check's aligned `<caller> op <other>` comparisons render IN
    the bit + FLD info columns (the layered marks style them). Only the group's USED columns render
    (w['used']); a group with none carries no pipes. Spans cover the cell glyphs (not padding),
    computed on the pre-rstrip line."""
    cells = [str(c) for c in (f.info or _EMPTY_INFO).cells()]
    marks = []
    loc = _location_text(f, w["loc1"]).ljust(w["loc"])
    prefix = f"[{f.severity:<4}] {f.id:<{max(1, w['id'])}}  {loc}"
    if f.cmp is not None:
        c = f.cmp
        cells[0] = _cmp_cell(c.caller_addr, c.other_addr, c.addr_eq, w["ca"], w["oa"])
        cells[1] = _cmp_cell(c.caller_fld, c.other_fld, c.fld_eq, w["cf"], w["of"])
    parts, cell_at = [], len(prefix) + 4      # each cell begins after "  | " / " | "
    for i in w["used"]:
        if f.cmp is not None and i == 0:
            marks += _cmp_marks(c.caller_addr, c.other_addr, c.addr_eq, w["ca"], cell_at)
        elif f.cmp is not None and i == 1:
            marks += _cmp_marks(c.caller_fld, c.other_fld, c.fld_eq, w["cf"], cell_at)
        parts.append(cells[i].ljust(w["info"][i]))
        cell_at += w["info"][i] + 3           # + " | "
    info = ("  | " + " | ".join(parts)) if parts else ""
    line = f"{prefix}{info}  :: {f.detail}"
    spans = []
    if f.location:                            # loc1: leftmost occurrence is the location field
        s = line.index(f.location)
        spans.append(LinkSpan(s, s + len(f.location), f.doc))
        if f.location2:                       # loc2 sits after the per-phase-padded loc1 + " vs "
            s2 = s + w["loc1"] + len(_VS)
            spans.append(LinkSpan(s2, s2 + len(f.location2), f.doc2))
    return line.rstrip(), spans, marks        # rstrip drops only trailing space; spans stay valid


def _head_line(w) -> str:
    """The [HEAD] column-header line for one (sub)phase group, aligned to the SAME layout its data
    lines use: `[HEAD] type  location  | <used titles> ::  detail`."""
    parts = [INFO_HEADERS[i].ljust(w["info"][i]) for i in w["used"]]
    info = ("  | " + " | ".join(parts)) if parts else ""
    return f"[{severity.HEADER:<4}] {'type':<{max(1, w['id'])}}  {'location'.ljust(w['loc'])}{info}  :: detail".rstrip()


def render_records(findings, errors_only: bool = False) -> list:
    """Render `findings` (banner findings interleaved, in order) to structured records. Each
    (sub)phase group gets a [HEAD] column-header record before its FIRST data line (emitted after
    the level filter, so a fully-filtered group carries no orphan header). `errors_only` keeps
    banners/headers + INFO/WARN/ERRR/FAIL."""
    entries = [f for f in findings if (not errors_only or f.severity in ERROR_REPORT_LEVELS)]
    widths = _phase_widths(entries)
    recs = []
    headed = set()                            # the phases whose [HEAD] is already out
    for f in entries:
        if _is_banner(f):
            recs.append(RenderRec("banner", severity.BANNER, f.detail, ()))
            continue
        if f.phase not in headed:
            headed.add(f.phase)
            recs.append(RenderRec("line", severity.HEADER, _head_line(widths[f.phase]), ()))
        text, spans, marks = _format_line(f, widths[f.phase])
        uid = f.uid if f.severity not in ("PASS", "SKIP") else ""
        recs.append(RenderRec("line", f.severity, text, tuple(spans), uid, tuple(marks)))
    return recs


def render_lines(findings, errors_only: bool = False) -> list:
    """Render `findings` to text lines (banner -> its 3 banner_lines)."""
    lines = []
    for r in render_records(findings, errors_only=errors_only):
        if r.kind == "banner":
            lines.extend(banner_lines(r.text))
        else:
            lines.append(r.text)
    return lines


def render_text(findings, errors_only: bool = False) -> str:
    return "\n".join(render_lines(findings, errors_only=errors_only))


def reports(findings) -> dict:
    """Both report bodies: {'complete': <full>, 'errors': <errors-only view>}."""
    return {"complete": render_text(findings, errors_only=False),
            "errors": render_text(findings, errors_only=True)}


# --- HTML report: the GUI log-viewer look as a standalone file; lines do NOT wrap ----------------- #
_HTML_CSS = """
  :root{color-scheme:dark;}
  body{background:#1c1c1c;color:#e6e6e6;margin:0;padding:16px;
       font:13px/1.5 'Monaspace Neon','Cascadia Mono',Consolas,'Courier New',monospace;}
  h1{color:#e6e6e6;font-size:17px;margin:0 0 4px;}
  .summary{color:#9ad67d;font-weight:bold;margin:0 0 12px;}
  .log{overflow-x:auto;}
  .line{white-space:pre;width:max-content;min-width:100%;}   /* NO WRAP - horizontal scroll */
  .line.section{color:#4ea1ff;font-weight:bold;}
  .line.head{color:#8f9ba2;font-weight:bold;}
  .line.fail{color:#ff6b6b;font-weight:bold;}
  .line.warn{color:#e0a458;}
  .line.pass{color:#9ad67d;}
  .line.skip{color:#a8a8a8;}
  .line.info{color:#e6e6e6;}
  .loc{color:#4ea1ff;text-decoration:underline;}            /* the viewer's clickable-cell styling */
  .cmp{color:#a8a8a8;}                                      /* the whole comparison: neutral grey */
  .cmpopeq{color:#9ad67d;font-weight:bold;}                 /* the === operator: green */
  .cmpopne{color:#ff6b6b;font-weight:bold;}                 /* the =/= operator: red */
  .cmpdiff{background:#5b2b2b;}                             /* differing chars: red-ish highlight */
"""

_LEVEL_CLASS = {"FAIL": "fail", "ERRR": "fail", "WARN": "warn", "PASS": "pass",
                "SKIP": "skip", "INFO": "info", "DEBG": "info", "HEAD": "head"}


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_MARK_CLASS = {"cmp": "cmp", "cmp_op_eq": "cmpopeq", "cmp_op_ne": "cmpopne", "cmp_diff": "cmpdiff"}


def _line_html(rec) -> str:
    """A finding line -> escaped HTML. The comparison marks NEST (op/diff spans sit inside the
    neutral whole-comparison span), so styling is composed PER CHARACTER: each char collects its
    classes and consecutive same-class runs wrap in one <span> (classes sorted for determinism)."""
    text = rec.text
    classes = [None] * len(text)                   # None = plain; else a set of class names

    def paint(start, end, cls):
        for i in range(max(0, start), min(len(text), end)):
            if classes[i] is None:
                classes[i] = set()
            classes[i].add(cls)

    for span in rec.links:
        paint(span.start, span.end, "loc")
    for mark in getattr(rec, "marks", ()):
        cls = _MARK_CLASS.get(mark.style)
        if cls:
            paint(mark.start, mark.end, cls)
    if not any(classes):
        return _esc(text)
    out, i = [], 0
    while i < len(text):
        j = i
        while j < len(text) and classes[j] == classes[i]:
            j += 1
        chunk = _esc(text[i:j])
        if classes[i]:
            out.append(f'<span class="{" ".join(sorted(classes[i]))}">{chunk}</span>')
        else:
            out.append(chunk)
        i = j
    return "".join(out)


def render_html(findings, errors_only: bool = False, *, title: str | None = None, lang: str = "en") -> str:
    """The validation log as a standalone HTML document replicating the in-app log viewer: per-phase-aligned
    text (from render_records), the dark palette + level colours, lines that do NOT wrap (`white-space:pre`
    + horizontal scroll). Banners render as their 3 banner_lines; location cells carry the link styling. The
    finding LINES are already localized (built in the active language); only the title + summary chrome here
    is resolved in `lang`."""
    from pipeline4.core import i18n
    title = title if title is not None else i18n.tr("ph_validation", lang)
    recs = render_records(findings, errors_only=errors_only)
    c = {lv: sum(1 for f in findings if f.severity == lv) for lv in ("PASS", "FAIL", "WARN", "SKIP")}
    summary = i18n.tr("rpt_summary", lang, p=c["PASS"], f=c["FAIL"], w=c["WARN"], s=c["SKIP"])
    body = []
    for r in recs:
        if r.kind == "banner":
            for bl in banner_lines(r.text):
                body.append(f'<div class="line section">{_esc(bl)}</div>')
        else:
            body.append(f'<div class="line {_LEVEL_CLASS.get(r.level, "info")}">{_line_html(r)}</div>')
    head = _esc(title) + (f" - {i18n.tr('rpt_errors_only', lang)}" if errors_only else "")
    return (f"<!DOCTYPE html>\n<html lang='{i18n.normalize(lang)}'><head><meta charset='utf-8'>"
            f"<title>{_esc(title)}</title><style>{_HTML_CSS}</style></head><body>"
            f"<h1>{head}</h1><p class='summary'>{_esc(summary)}</p>\n"
            "<div class='log'>\n" + "\n".join(body) + "\n</div></body></html>\n")


def html_reports(findings, lang: str = "en") -> dict:
    """Both HTML report bodies (the GUI-viewer look, no-wrap): {'complete': …, 'errors': …}."""
    return {"complete": render_html(findings, errors_only=False, lang=lang),
            "errors": render_html(findings, errors_only=True, lang=lang)}
