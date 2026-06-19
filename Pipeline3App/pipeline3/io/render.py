"""The single log renderer (plan §4.1). ONE function renders both reports; only the level filter
differs - the complete log, and the error-only view (PHASE headers + INFO + WARN + FAIL, dropping
PASS/SKIP). Columns auto-fit per phase.

Rendered finding line:
    [LEVEL] <id>  <location>  |  bit | FLD | desc_l1 | desc_l1b | drawing | type-index  ::  <detail>
A PHASE entry renders as a banner.
"""
from __future__ import annotations
from collections import defaultdict

from pipeline3.core.model import number_entries, ERROR_REPORT_LEVELS

INFO_HEADERS = ("bit", "FLD", "desc_l1", "desc_l1b", "drawing", "type-index")


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


def render_lines(log, errors_only: bool = False) -> list:
    """Render `log` to a list of text lines. `errors_only` keeps PHASE/INFO/WARN/FAIL only."""
    number_entries(log)
    entries = [e for e in log if (not errors_only or e.level in ERROR_REPORT_LEVELS)]
    widths = _phase_widths(entries)
    lines = []
    for e in entries:
        if e.level == "PHASE":
            lines.append("")
            lines.append(e.detail)
            lines.append("=" * max(8, len(e.detail)))
            continue
        w = widths[e.phase]
        info = " | ".join(str(c).ljust(w["info"][i]) for i, c in enumerate(e.info.cells()))
        loc = e.location.ljust(w["loc"])
        line = f"[{e.level:<4}] {e.id:<{max(1, w['id'])}}  {loc}  | {info}  :: {e.detail}"
        lines.append(line.rstrip())
    return lines


def render_text(log, errors_only: bool = False) -> str:
    return "\n".join(render_lines(log, errors_only=errors_only))


def reports(log) -> dict:
    """Both report bodies: {'complete': <full log>, 'errors': <errors-only view>}."""
    return {"complete": render_text(log, errors_only=False),
            "errors": render_text(log, errors_only=True)}
