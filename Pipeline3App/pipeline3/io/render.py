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


def _phase_widths(entries) -> dict:
    w = defaultdict(lambda: {"id": 0, "loc": 0, "info": [0] * len(INFO_HEADERS)})
    for e in entries:
        if e.level == "PHASE":
            continue
        ph = w[e.phase]
        ph["id"] = max(ph["id"], len(e.id))
        ph["loc"] = max(ph["loc"], len(e.location))
        for i, c in enumerate(e.info.cells()):
            ph["info"][i] = max(ph["info"][i], len(str(c)))
    return w


def banner_lines(detail: str) -> list:
    """The 3 text lines a PHASE banner renders as: a blank line, the title, its `===` underline."""
    return ["", detail, "=" * max(8, len(detail))]


def _format_line(e, w) -> tuple:
    """One finding entry -> (text, [LinkSpan]). The text is byte-identical to the legacy inline
    formatting (same fields, the `  ->  ` location2 suffix, the trailing rstrip); the spans cover the
    `location`/`location2` cell glyphs (not their right-padding), computed on the pre-rstrip line."""
    info = " | ".join(str(c).ljust(w["info"][i]) for i, c in enumerate(e.info.cells()))
    loc = e.location.ljust(w["loc"])
    line = f"[{e.level:<4}] {e.id:<{max(1, w['id'])}}  {loc}  | {info}  :: {e.detail}"
    spans = []
    if e.location:                            # primary cell: leftmost occurrence is the loc field
        s = line.index(e.location)            # (before info/detail), so the span is the cell, not padding
        spans.append(LinkSpan(s, s + len(e.location), e.doc))
    if e.location2:                           # cross-check: the matched cell in the OTHER workbook
        line += f"  ->  {e.location2}"        # sheet!cell only; the workbook (doc2) is not rendered
        s2 = len(line) - len(e.location2)
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
