"""The phase-100 validation report renderer - clean-room port of PL3's `io/render.py`, over PL4's
`core.finding.Finding` (with the optional `info`/`cmp`/`location2` payload) instead of PL3's `LogEntry`.

ONE source renders both reports; only the level filter differs - the complete log, and the error-only view
(banners + INFO + WARN + ERROR + FAIL, dropping PASS/SKIP/DEBUG). Columns auto-fit per (sub-)phase.

Rendered finding line (`<id>` is `<phase>-<type>`; `<location>` is `Sheet!Cell`, never the workbook name -
`doc`/`doc2` ride on the Finding for the GUI and are not rendered):
    [LEVEL] <id>  <location>  |  bit | FLD | desc_l1 | desc_l1b | drawing | type-index  ::  <detail>
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
# One rendered entry: kind "banner" (text = title) or "line"; `links` = 0..2 LinkSpans (location, then
# location2); `uid` = the finding's stable hash (for a treatable line; "" for a banner / PASS).
RenderRec = namedtuple("RenderRec", "kind level text links uid", defaults=("",))

_VS = " vs "                                  # the cross-check location separator: `<loc1> vs <loc2>`


def _is_banner(f) -> bool:
    return f.severity == severity.BANNER


def _location_text(f, loc1w: int = 0) -> str:
    """The location column: `<loc1> vs <loc2>` for a cross-check (loc1 left-padded to the per-phase
    caller-cell width so the `vs` lines up), else just `<loc1>`."""
    if f.location and f.location2:
        return f"{f.location:<{loc1w}}{_VS}{f.location2}"
    return f.location


def _cmp_text(c, w) -> str:
    """The cross-check comparison, columns aligned per-phase so the `===`/`=/=` operators line up:
    `<caller_addr> op <other_addr> | <caller_fld> op <other_fld>`."""
    op_a = "===" if c.addr_eq else "=/="
    op_f = "===" if c.fld_eq else "=/="
    return (f"{c.caller_addr:>{w['ca']}} {op_a} {c.other_addr:<{w['oa']}} | "
            f"{c.caller_fld:>{w['cf']}} {op_f} {c.other_fld:<{w['of']}}")


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
            ph["info"][i] = max(ph["info"][i], len(str(c)))
        if f.cmp is not None:
            ph["ca"], ph["oa"] = max(ph["ca"], len(f.cmp.caller_addr)), max(ph["oa"], len(f.cmp.other_addr))
            ph["cf"], ph["of"] = max(ph["cf"], len(f.cmp.caller_fld)), max(ph["of"], len(f.cmp.other_fld))
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
    """One finding -> (text, [LinkSpan]). The location column is `<loc1> vs <loc2>` for a cross-check
    (both clickable); a cross-check mismatch prepends its aligned comparison body to the detail. Spans
    cover the cell glyphs (not padding), computed on the pre-rstrip line."""
    info = " | ".join(str(c).ljust(w["info"][i]) for i, c in enumerate((f.info or _EMPTY_INFO).cells()))
    loc = _location_text(f, w["loc1"]).ljust(w["loc"])
    detail = f"{_cmp_text(f.cmp, w)} :: {f.detail}" if f.cmp is not None else f.detail
    line = f"[{f.severity:<4}] {f.id:<{max(1, w['id'])}}  {loc}  | {info}  :: {detail}"
    spans = []
    if f.location:                            # loc1: leftmost occurrence is the location field
        s = line.index(f.location)
        spans.append(LinkSpan(s, s + len(f.location), f.doc))
        if f.location2:                       # loc2 sits after the per-phase-padded loc1 + " vs "
            s2 = s + w["loc1"] + len(_VS)
            spans.append(LinkSpan(s2, s2 + len(f.location2), f.doc2))
    return line.rstrip(), spans               # rstrip drops only trailing space; spans stay valid


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
        text, spans = _format_line(f, widths[f.phase])
        uid = f.uid if f.severity not in ("PASS", "SKIP") else ""
        recs.append(RenderRec("line", f.severity, text, tuple(spans), uid))
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
"""

_LEVEL_CLASS = {"FAIL": "fail", "ERROR": "fail", "WARN": "warn", "PASS": "pass",
                "SKIP": "skip", "INFO": "info", "DEBUG": "info"}


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _line_html(rec) -> str:
    """A finding line -> escaped HTML, with its location link-spans wrapped in <span class="loc">."""
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
