"""The phase-100 validation report renderer - clean-room port of PL3's `io/render.py`, over PL4's
`core.finding.Finding` (with the optional `info`/`cmp`/`location2` payload) instead of PL3's `LogEntry`.

ONE source renders both reports; only the level filter differs - the complete log, and the error-only view
(banners + INFO + WARN + ERROR + FAIL, dropping PASS/SKIP/DEBUG). Columns auto-fit per (sub-)phase.

Rendered finding line (`<id>` is `<phase>-<type>`; `<location>` is `Sheet!Cell`, never the workbook name -
`doc`/`doc2` ride on the Finding for the GUI and are not rendered):
    [LEVEL] <id>  <location>  |  bit | FLD | desc_l1 | desc_l1b | drawing | type-index  ::  <detail>
A cross-check (130/140) line renders its aligned `<caller> op <other>` comparisons IN the bit + FLD
columns (op = `===`/`=/=`), with MarkSpans so a viewer can style them (=== neutral, =/= diff-underlined).
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
# The error-only report keeps banners + INFO + WARN + ERROR + FAIL (drops PASS/SKIP/DEBUG).
ERROR_REPORT_LEVELS = (severity.BANNER, "INFO", "WARN", "ERROR", "FAIL")
_EMPTY_INFO = InfoBlock()

# A clickable cell: [start, end) char offsets into the line + the workbook basename (doc/doc2).
LinkSpan = namedtuple("LinkSpan", "start end doc")
# A comparison styling span: [start, end) + style "cmp_eq" (an === comparison, rendered neutral) or
# "cmp_diff" (the chars that DIFFER across a =/= comparison, rendered underlined).
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
    """The MarkSpans for one comparison cell at line offset `cell_start`: an === comparison marks the
    whole `<caller> op <other>` neutrally; a =/= comparison underlines the DIFFERING chars on both sides
    (the caller is right-aligned into its `wc` field; the other starts after `<field> op `)."""
    if eq:
        return [MarkSpan(cell_start, cell_start + wc + 5 + len(other), "cmp_eq")]
    caller_at = cell_start + (wc - len(caller))
    other_at = cell_start + wc + 5                    # after the caller field + " op "
    marks = []
    for start, end in _char_diff_runs(caller, other):
        if start < len(caller):
            marks.append(MarkSpan(caller_at + start, caller_at + min(end, len(caller)), "cmp_diff"))
        if start < len(other):
            marks.append(MarkSpan(other_at + start, other_at + min(end, len(other)), "cmp_diff"))
    return marks


def _phase_widths(entries) -> dict:
    w = defaultdict(lambda: {"id": 0, "loc": 0, "loc1": 0, "info": [0] * len(INFO_HEADERS),
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
            ph["info"][i] = max(ph["info"][i], len(str(c)))
        if f.cmp is not None:
            ph["ca"], ph["oa"] = max(ph["ca"], len(f.cmp.caller_addr)), max(ph["oa"], len(f.cmp.other_addr))
            ph["cf"], ph["of"] = max(ph["cf"], len(f.cmp.caller_fld)), max(ph["of"], len(f.cmp.other_fld))
    for ph in w.values():                     # fold the composite `<caller> op <other>` cell widths in
        if ph["ca"] or ph["oa"]:
            ph["info"][0] = max(ph["info"][0], ph["ca"] + ph["oa"] + 5)
            ph["info"][1] = max(ph["info"][1], ph["cf"] + ph["of"] + 5)
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
    the bit + FLD info columns (the marks style them: === neutral, =/= diff-chars underlined). Spans
    cover the cell glyphs (not padding), computed on the pre-rstrip line."""
    cells = [str(c) for c in (f.info or _EMPTY_INFO).cells()]
    marks = []
    loc = _location_text(f, w["loc1"]).ljust(w["loc"])
    prefix = f"[{f.severity:<4}] {f.id:<{max(1, w['id'])}}  {loc}  | "
    if f.cmp is not None:
        c = f.cmp
        cells[0] = _cmp_cell(c.caller_addr, c.other_addr, c.addr_eq, w["ca"], w["oa"])
        cells[1] = _cmp_cell(c.caller_fld, c.other_fld, c.fld_eq, w["cf"], w["of"])
        cell_at = len(prefix)                 # the bit cell starts right after the prefix
        marks += _cmp_marks(c.caller_addr, c.other_addr, c.addr_eq, w["ca"], cell_at)
        cell_at += max(w["info"][0], len(cells[0])) + 3          # + " | "
        marks += _cmp_marks(c.caller_fld, c.other_fld, c.fld_eq, w["cf"], cell_at)
    info = " | ".join(cell.ljust(w["info"][i]) for i, cell in enumerate(cells))
    line = f"{prefix}{info}  :: {f.detail}"
    spans = []
    if f.location:                            # loc1: leftmost occurrence is the location field
        s = line.index(f.location)
        spans.append(LinkSpan(s, s + len(f.location), f.doc))
        if f.location2:                       # loc2 sits after the per-phase-padded loc1 + " vs "
            s2 = s + w["loc1"] + len(_VS)
            spans.append(LinkSpan(s2, s2 + len(f.location2), f.doc2))
    return line.rstrip(), spans, marks        # rstrip drops only trailing space; spans stay valid


def render_records(findings, errors_only: bool = False) -> list:
    """Render `findings` (banner findings interleaved, in order) to structured records. `errors_only`
    keeps banners + INFO/WARN/ERROR/FAIL."""
    entries = [f for f in findings if (not errors_only or f.severity in ERROR_REPORT_LEVELS)]
    widths = _phase_widths(entries)
    recs = []
    for f in entries:
        if _is_banner(f):
            recs.append(RenderRec("banner", severity.BANNER, f.detail, ()))
            continue
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
  .line.fail{color:#ff6b6b;font-weight:bold;}
  .line.warn{color:#e0a458;}
  .line.pass{color:#9ad67d;}
  .line.skip{color:#a8a8a8;}
  .line.info{color:#e6e6e6;}
  .loc{color:#4ea1ff;text-decoration:underline;}            /* the viewer's clickable-cell styling */
  .cmpeq{color:#a8a8a8;}                                    /* an === comparison: neutral */
  .cmpdiff{text-decoration:underline;}                      /* the differing chars of a =/= comparison */
"""

_LEVEL_CLASS = {"FAIL": "fail", "ERROR": "fail", "WARN": "warn", "PASS": "pass",
                "SKIP": "skip", "INFO": "info", "DEBUG": "info"}


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _line_html(rec) -> str:
    """A finding line -> escaped HTML: the location link-spans wrap in <span class="loc">, the
    comparison marks in <span class="cmpeq"> / <span class="cmpdiff"> (links live in the location area,
    marks in the info area - they never overlap)."""
    text = rec.text
    styled = [(s.start, s.end, "loc") for s in rec.links]
    styled += [(m.start, m.end, "cmpeq" if m.style == "cmp_eq" else "cmpdiff")
               for m in getattr(rec, "marks", ())]
    if not styled:
        return _esc(text)
    out, prev = [], 0
    for start, end, cls in sorted(styled):
        if start < prev:                       # defensive: ignore any overlap
            continue
        out.append(_esc(text[prev:start]))
        out.append(f'<span class="{cls}">{_esc(text[start:min(end, len(text))])}</span>')
        prev = end
    out.append(_esc(text[prev:]))
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
