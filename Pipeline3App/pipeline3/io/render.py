"""The single log renderer (plan §4.1). ONE function renders both reports; only the level filter
differs - the complete log, and the error-only view (PHASE headers + INFO + WARN + FAIL, dropping
PASS/SKIP). Columns auto-fit per phase.

Rendered finding line (`<id>` is the log-type index `<phase>-<type>`; `<location>` is `sheet!cell`,
never the workbook name - the `doc`/`doc2` workbook identity rides on the LogEntry for the GUI and
is not rendered):
    [LEVEL] <id>  <location>  |  bit | FLD | desc_l1 | desc_l1b | drawing | type-index  ::  <detail>
A PHASE entry renders as a banner.

`render_records` is the GUI-facing twin of `render_lines`: it returns the SAME text plus, per line,
the character spans of `location`/`location2` and their workbook (`doc`/`doc2`) so the log pane can
make each cell a clickable Excel link WITHOUT re-parsing text. Both functions build their text from
the ONE `_format_line`/`banner_lines` helper, so the report text (the frozen golden) is provably a
single source - it cannot drift from the records.
"""
from __future__ import annotations
from collections import defaultdict, namedtuple

from pipeline3.core.model import number_entries, ERROR_REPORT_LEVELS

INFO_HEADERS = ("bit", "FLD", "desc_l1", "desc_l1b", "drawing", "type-index")

# A clickable cell in a rendered line: [start, end) char offsets into the line text + the workbook
# basename (`doc`/`doc2`) the cell lives in (resolved to a path by the GUI).
LinkSpan = namedtuple("LinkSpan", "start end doc")
# One rendered entry for the GUI: kind "banner" (text = the title) or "line" (text = the finding
# line); `links` = 0..2 LinkSpans (location, then location2).
RenderRec = namedtuple("RenderRec", "kind level text links")


_VS = " vs "                                  # the cross-check location separator: `<loc1> vs <loc2>`


def _location_text(e, loc1w: int = 0) -> str:
    """The location column: `<loc1> vs <loc2>` for a cross-check (loc1 left-padded to the per-phase
    caller-cell width `loc1w` so the `vs` lines up down the column; loc2 = the matched cell, or the
    other-workbook label on a miss), else just `<loc1>`."""
    if e.location and e.location2:
        return f"{e.location:<{loc1w}}{_VS}{e.location2}"
    return e.location


def _cmp_text(c, w) -> str:
    """The cross-check comparison, columns aligned per-phase so the `===`/`=/=` operators line up:
    `<caller_addr> op <other_addr> | <caller_fld> op <other_fld>` (left elements right-justified, right
    elements left-justified, so each element hugs its operator)."""
    op_a = "===" if c.addr_eq else "=/="
    op_f = "===" if c.fld_eq else "=/="
    return (f"{c.caller_addr:>{w['ca']}} {op_a} {c.other_addr:<{w['oa']}} | "
            f"{c.caller_fld:>{w['cf']}} {op_f} {c.other_fld:<{w['of']}}")


def _phase_widths(entries) -> dict:
    w = defaultdict(lambda: {"id": 0, "loc": 0, "loc1": 0, "info": [0] * len(INFO_HEADERS),
                             "ca": 0, "oa": 0, "cf": 0, "of": 0})
    for e in entries:                         # pass 1: per-field maxima (incl. the caller-cell width)
        if e.level == "PHASE":
            continue
        ph = w[e.phase]
        ph["id"] = max(ph["id"], len(e.id))
        if e.location and e.location2:        # a cross-check's caller cell -> the `vs`-alignment width
            ph["loc1"] = max(ph["loc1"], len(e.location))
        for i, c in enumerate(e.info.cells()):
            ph["info"][i] = max(ph["info"][i], len(str(c)))
        if e.cmp is not None:
            ph["ca"], ph["oa"] = max(ph["ca"], len(e.cmp.caller_addr)), max(ph["oa"], len(e.cmp.other_addr))
            ph["cf"], ph["of"] = max(ph["cf"], len(e.cmp.caller_fld)), max(ph["of"], len(e.cmp.other_fld))
    for e in entries:                         # pass 2: the combined-location width (needs loc1 from pass 1)
        if e.level == "PHASE":
            continue
        ph = w[e.phase]
        ph["loc"] = max(ph["loc"], len(_location_text(e, ph["loc1"])))
    return w


def banner_lines(detail: str) -> list:
    """The 3 text lines a PHASE banner renders as: a blank line, the title, its `===` underline."""
    return ["", detail, "=" * max(8, len(detail))]


def _format_line(e, w) -> tuple:
    """One finding entry -> (text, [LinkSpan]). The location column is `<loc1> vs <loc2>` for a
    cross-check (both cells/labels clickable); a cross-check mismatch prepends its aligned comparison
    body to the detail. Spans cover the cell/label glyphs (not padding), computed on the pre-rstrip line."""
    info = " | ".join(str(c).ljust(w["info"][i]) for i, c in enumerate(e.info.cells()))
    loc = _location_text(e, w["loc1"]).ljust(w["loc"])
    detail = f"{_cmp_text(e.cmp, w)} :: {e.detail}" if e.cmp is not None else e.detail
    line = f"[{e.level:<4}] {e.id:<{max(1, w['id'])}}  {loc}  | {info}  :: {detail}"
    spans = []
    if e.location:                            # loc1: leftmost occurrence is the location field
        s = line.index(e.location)
        spans.append(LinkSpan(s, s + len(e.location), e.doc))
        if e.location2:                       # loc2 sits after the per-phase-padded loc1 + " vs "
            s2 = s + w["loc1"] + len(_VS)
            spans.append(LinkSpan(s2, s2 + len(e.location2), e.doc2))
    return line.rstrip(), spans               # rstrip drops only trailing space; spans stay valid


def render_records(log, errors_only: bool = False) -> list:
    """Render `log` to structured records (text + per-line link spans). The GUI consumes these;
    `render_lines` derives its text from the same helpers. `errors_only` keeps PHASE/INFO/WARN/FAIL."""
    number_entries(log)
    entries = [e for e in log if (not errors_only or e.level in ERROR_REPORT_LEVELS)]
    widths = _phase_widths(entries)
    recs = []
    for e in entries:
        if e.level == "PHASE":
            recs.append(RenderRec("banner", "PHASE", e.detail, ()))
            continue
        text, spans = _format_line(e, widths[e.phase])
        recs.append(RenderRec("line", e.level, text, tuple(spans)))
    return recs


def render_lines(log, errors_only: bool = False) -> list:
    """Render `log` to a list of text lines. `errors_only` keeps PHASE/INFO/WARN/FAIL only.
    Derived from `render_records` so the report text and the GUI records share one source."""
    lines = []
    for r in render_records(log, errors_only=errors_only):
        if r.kind == "banner":
            lines.extend(banner_lines(r.text))
        else:
            lines.append(r.text)
    return lines


def render_text(log, errors_only: bool = False) -> str:
    return "\n".join(render_lines(log, errors_only=errors_only))


def reports(log) -> dict:
    """Both report bodies: {'complete': <full log>, 'errors': <errors-only view>}."""
    return {"complete": render_text(log, errors_only=False),
            "errors": render_text(log, errors_only=True)}


# --- HTML report: the GUI log-viewer look as a standalone file; lines do NOT wrap ----------------- #
# Colours mirror gui/theme.log_tags(dark) + the dark log_bg/fg/accent so the report matches the in-app
# log pane. The ONE difference from a wrapping report is `white-space:pre` (+ horizontal scroll), which
# is exactly what the log pane already does (its Text is wrap="none").
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
  .line.ok{color:#3fb950;font-weight:bold;}
  .line.info{color:#e6e6e6;}
  .loc{color:#4ea1ff;text-decoration:underline;}            /* the viewer's clickable-cell styling */
"""

_LEVEL_CLASS = {"FAIL": "fail", "ERROR": "fail", "HALT": "fail", "WARN": "warn", "WARNING": "warn",
                "PASS": "pass", "SKIP": "skip", "OK": "ok", "INFO": "info"}


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _line_html(rec) -> str:
    """A finding line -> escaped HTML, with its location link-spans wrapped in <span class="loc"> (the
    viewer's clickable-cell styling; cells aren't live links in a standalone file)."""
    text = rec.text
    if not rec.links:
        return _esc(text)
    out, prev = [], 0
    for span in sorted(rec.links, key=lambda s: s.start):
        if span.start < prev:                  # defensive: ignore any overlap
            continue
        out.append(_esc(text[prev:span.start]))
        out.append(f'<span class="loc">{_esc(text[span.start:span.end])}</span>')
        prev = span.end
    out.append(_esc(text[prev:]))
    return "".join(out)


def render_html(log, errors_only: bool = False, *, title: str = "Documents Validation") -> str:
    """The validation log as a standalone HTML document that REPLICATES the in-app log viewer
    (gui/logview): the same per-phase-aligned text (from render_records), the dark log palette and
    level colours. The ONE difference is that lines do NOT wrap (`white-space:pre` + horizontal scroll,
    matching the pane's wrap="none"). PHASE banners render as their 3 banner_lines; location cells
    carry the viewer's link styling. `errors_only` keeps PHASE/INFO/WARN/FAIL."""
    recs = render_records(log, errors_only=errors_only)
    c = {lv: sum(1 for e in log if e.level == lv) for lv in ("PASS", "FAIL", "WARN", "SKIP")}
    summary = f"{c['PASS']} passed, {c['FAIL']} failed, {c['WARN']} warning(s), {c['SKIP']} skipped"
    body = []
    for r in recs:
        if r.kind == "banner":
            for bl in banner_lines(r.text):
                body.append(f'<div class="line section">{_esc(bl)}</div>')
        else:
            body.append(f'<div class="line {_LEVEL_CLASS.get(r.level, "info")}">{_line_html(r)}</div>')
    head = _esc(title) + (" - errors only" if errors_only else "")
    return ("<!DOCTYPE html>\n<html lang='en'><head><meta charset='utf-8'>"
            f"<title>{_esc(title)}</title><style>{_HTML_CSS}</style></head><body>"
            f"<h1>{head}</h1><p class='summary'>{_esc(summary)}</p>\n"
            "<div class='log'>\n" + "\n".join(body) + "\n</div></body></html>\n")


def html_reports(log) -> dict:
    """Both HTML report bodies (the GUI-viewer look, no-wrap): {'complete': …, 'errors': …}."""
    return {"complete": render_html(log, errors_only=False),
            "errors": render_html(log, errors_only=True)}
