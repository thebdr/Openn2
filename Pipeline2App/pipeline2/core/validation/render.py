"""Rendering: the aligned caller-vs-other table (one renderer, every sink) + the .txt/.html log."""
from __future__ import annotations
import os
from collections import namedtuple

from .. import config
from .model import _caller_info, _row_info_parts


# --------------------------------------------------------------------------- #
# rendering: the aligned caller-vs-other table (one renderer, every sink)      #
# --------------------------------------------------------------------------- #
RenderRec = namedtuple("RenderRec", "kind level location body link1 link2 title")
#  kind 'phase' -> a banner (title set); 'line' -> a normal/cmp line.
#  location = the leading "Sheet!Cell" (clickable via link1); body = everything after it;
#  link2 = the other-workbook cell (only on a not-PASS partial match), else None.


def _op(eq: bool) -> str:
    """The 3-char comparison operator: '===' (match) / '=/=' (differ); the '/' centers under '='."""
    return "===" if eq else "=/="


def _cmp_body(cmp, widths=None) -> str:
    """The two comparison cells, address first then device: `<caller> <op> <other> | <caller> <op>
    <other>`. The caller value is on the left, the other document's on the right (no sigils -
    the leading 'vs <other_doc>' + the position say which side is which). `widths` = (caller_addr,
    other_addr, caller_fld, other_fld) column widths for per-phase alignment; None = natural widths."""
    ca, oa, cf, of = cmp.caller_addr, cmp.other_addr, cmp.caller_fld, cmp.other_fld
    if widths:
        wca, woa, wcf, wof = widths
        # caller (left) is right-justified so it sits flush against the operator; the other
        # (right) is left-justified so the trailing ` | ` aligns across the phase.
        ca, oa, cf, of = ca.rjust(wca), oa.ljust(woa), cf.rjust(wcf), of.ljust(wof)
    return f"{ca} {_op(cmp.addr_eq)} {oa} | {cf} {_op(cmp.fld_eq)} {of}"


def _cell_link(location: str, path: str, ce_path: str):
    """A {path, sheet, cell} link dict from a raw 'Sheet!Cell' location, or None."""
    if not location or "!" not in location:
        return None
    sheet, cell = location.split("!", 1)
    return {"path": path or ce_path, "sheet": sheet, "cell": cell}


def render_lines(log: list, full_print: bool = True, ce_path: str = "") -> list:
    """Turn a validation log into render records (one per displayed entry), columns auto-fit PER
    PHASE (segmented by the PHASE banners, not e.phase, which is unset without out_dir). Two
    aligned groups share the phase's location column: the cross-check (Phase 1/2) lines render the
    caller-vs-other comparison table, and the plain info-block lines (SKIP, diagnosis) align their
    `bit | desc | FLD | drawing | st-index` columns. Lines with neither (banners, summaries,
    params.yaml) stay simple. Filter: FAIL/WARN always; params.yaml as INFO; PASS/SKIP/INFO only
    when full_print."""
    grey = {"PASS", "SKIP", "INFO"}
    seg_of, cur = [], -1
    for e in log:
        if e.level == "PHASE":
            cur += 1
        seg_of.append(cur)

    def disp_level(e):
        """The level to display, or None to drop (mirrors the full_print/grey filter)."""
        if e.level in ("FAIL", "WARN"):
            return e.level
        if e.location == "params.yaml":
            return "INFO"
        if full_print and e.level in grey:
            return e.level
        return None

    # pass 1: pick displayed entries + per-phase column widths (cmp cols, info cols, shared loc)
    shown, W = [], {}
    for e, s in zip(log, seg_of):
        if e.level == "PHASE":
            shown.append((e, s, "PHASE"))
            continue
        lvl = disp_level(e)
        if lvl is None:
            continue
        parts = None if e.cmp is not None else _row_info_parts(e.row)
        shown.append((e, s, lvl))
        if e.cmp is None and parts is None:
            continue                                    # a simple summary line - not column-aligned
        w = W.setdefault(s, {"loc": 0, "ca": 0, "oa": 0, "cf": 0, "of": 0, "caller": 0,
                             "bit": 0, "fld": 0, "desc": 0, "desc1b": 0, "dwg": 0, "sti": 0})
        w["loc"] = max(w["loc"], len(e.location or ""))
        if e.cmp is not None:
            c = e.cmp
            w["ca"], w["oa"] = max(w["ca"], len(c.caller_addr)), max(w["oa"], len(c.other_addr))
            w["cf"], w["of"] = max(w["cf"], len(c.caller_fld)), max(w["of"], len(c.other_fld))
            w["caller"] = max(w["caller"], len(_caller_info(e.row)))
        else:
            for k, v in zip(("bit", "fld", "desc", "desc1b", "dwg", "sti"), parts):  # parts = display order
                w[k] = max(w[k], len(v))

    # pass 2: render
    recs = []
    for e, s, lvl in shown:
        if lvl == "PHASE":
            recs.append(RenderRec("phase", "PHASE", "", "", None, None, e.message))
            continue
        w = W.get(s, {})
        loc = e.location or ""
        pad = " " * (w.get("loc", 0) - len(loc)) if w else ""   # pad the (variable) cell, shared left edge
        link1 = _cell_link(e.location, e.path, ce_path)
        link2 = _cell_link(e.location2, e.path2, ce_path) if (lvl != "PASS" and e.location2) else None
        if e.cmp is not None:
            table = _cmp_body(e.cmp, (w["ca"], w["oa"], w["cf"], w["of"]) if w else None)
            caller = _caller_info(e.row).ljust(w.get("caller", 0))
            body = f"{pad}vs {e.cmp.other_doc} | {table} | {caller} : {e.message}".rstrip()
        else:
            parts = _row_info_parts(e.row)
            if parts and w:
                b, f, d, d2, g, t = parts               # bit, FLD, desc_l1, desc_l1b, drawing, st-index
                info = (f"{b.ljust(w['bit'])} | {f.ljust(w['fld'])} | {d.ljust(w['desc'])} | "
                        f"{d2.ljust(w['desc1b'])} | {g.ljust(w['dwg'])} | {t.ljust(w['sti'])}")
                tail = f" : {e.message}" if e.message else ""
                body = f"{pad}| {info}{tail}".rstrip()  # location becomes the first | column
            else:                                       # simple summary line (no info block)
                body = e.message or ""
        recs.append(RenderRec("line", lvl, loc, body, link1, link2, ""))
    return recs


# A dark log page (so the pastel PASS/INFO read well, mirroring the dark GUI log viewer):
# font colour per level, FAIL/WARN bold, SKIP/INFO italic.
_HTML_CSS = """
  body{background:#1e1e1e;color:#d4d4d4;font:13px/1.55 Consolas,'Courier New',monospace;padding:18px;}
  h1{color:#e6e6e6;font-size:18px;margin:0 0 4px;}
  .summary{color:#e6e6e6;font-weight:bold;margin:0 0 10px;}
  h2.phase{color:#4ea1ff;font-size:15px;border-top:1px solid #3c3c3c;padding-top:14px;margin:22px 0 8px;}
  .entry{white-space:pre-wrap;margin:1px 0;}
  .FAIL{color:#ff6b6b;font-weight:bold;}
  .WARN{color:#e0a458;font-weight:bold;}
  .PASS{color:#D7FFAF;}
  .SKIP{color:#a8a8a8;font-style:italic;}
  .INFO{color:#FFE697;font-style:italic;}
"""


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _rec_text(rec) -> str:
    """The plain-text line for a render record (the leading cell, the body, the trailing link)."""
    line = f"[{rec.level:4}] {rec.location} {rec.body}".rstrip()
    if rec.link2:
        line += f"   [open {rec.link2['sheet']}!{rec.link2['cell']}]"
    return line


def _html_rec(rec) -> str:
    """One HTML log line from a render record: a phase -> a <h2> header; every other entry a
    colour-coded <div> (CSS class = the level). `white-space:pre-wrap` keeps the column layout."""
    if rec.kind == "phase":
        return f'<h2 class="phase">{_html_escape(rec.title)}</h2>'
    cls = rec.level if rec.level in ("FAIL", "WARN", "PASS", "SKIP", "INFO") else "INFO"
    return f'<div class="entry {cls}">{_html_escape(_rec_text(rec))}</div>'


def write_log(log: list, out_dir: str) -> tuple[int, int, int]:
    base = config.out_path(out_dir, "validation_report")   # <out>/Reports/documents_validation_report
    os.makedirs(os.path.dirname(base), exist_ok=True)
    passed = sum(1 for e in log if e.level == "PASS")
    failed = sum(1 for e in log if e.level == "FAIL")
    warned = sum(1 for e in log if e.level == "WARN")
    skipped = sum(1 for e in log if e.level == "SKIP")
    summary = f"{passed} passed, {failed} failed, {warned} warning(s), {skipped} skipped"
    recs = render_lines(log, full_print=True)            # the file always holds the FULL record
    with open(base + ".txt", "w", encoding="utf-8") as f:
        for rec in recs:
            f.write((f"\n{'=' * 78}\n{rec.title}\n{'=' * 78}" if rec.kind == "phase"
                     else _rec_text(rec)) + "\n")
        f.write(f"\nSUMMARY: {summary}\n")
    # an HTML twin that keeps the coloured log-viewer layout (dark page, phases as headers,
    # severity colours per line) - renders in any browser.
    html = ["<!DOCTYPE html>",
            "<html><head><meta charset='utf-8'><title>Validation log</title>",
            "<style>", _HTML_CSS, "</style></head><body>",
            "<h1>Validation log</h1>", f'<p class="summary">{_html_escape(summary)}</p>']
    html += [_html_rec(rec) for rec in recs]
    html.append("</body></html>")
    with open(base + ".html", "w", encoding="utf-8") as f:
        f.write("\n".join(html) + "\n")
    return passed, failed, warned
