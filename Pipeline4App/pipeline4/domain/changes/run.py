"""Orchestrate the ph100 before/after quality report (standalone - not part of the pipeline).

Reads the configured CURRENT documents (`iolist_path` / `matrix_path`) and their PRIOR revisions
(`iolist_previous_path` / `matrix_previous_path`), matches + classifies each, and writes a graphical
HTML dashboard + a CSV audit trail under ProjectDocumentation/Reports. When a prior revision is missing
(or identical to the current), that document degrades to a "no prior revision" notice (first-issue mode).
"""
from __future__ import annotations

import csv
import os
from datetime import datetime

from pipeline4.core import config
from pipeline4.domain.changes import reader, match, classify, report

# A document read can fail many ways on real input (missing sheet -> ValueError; open-in-Excel ->
# FileLockedError; a corrupt/non-xlsx -> openpyxl/zipfile errors). This report is a best-effort analysis
# that must NEVER crash the GUI, so the read boundary degrades on ANY exception (the reason is surfaced).
def _label(path: str) -> str:
    return os.path.basename(path) if path else ""


def _why_unavailable(before: str, after: str) -> str | None:
    """The reason a comparison can't run, or None when both revisions are present and distinct."""
    if not before:
        return "no prior revision configured"
    if not os.path.exists(before):
        return "prior revision file not found"
    if not after or not os.path.exists(after):
        return "current document not found"
    if os.path.abspath(before) == os.path.abspath(after):
        return "prior revision is the same file as the current"
    return None


def _compare_iolist(before: str, after: str, params: dict, weights: dict) -> dict:
    reason = _why_unavailable(before, after)
    if reason:
        return {"available": False, "reason": reason}
    try:
        old_rows = reader.read_iolist(before, params)
        new_rows = reader.read_iolist(after, params)
    except Exception as error:                           # noqa: BLE001 - never crash the GUI on a bad doc
        return {"available": False, "reason": f"could not read the I/O List ({type(error).__name__})"}
    if not old_rows and not new_rows:                    # a wrong sheet name reads 0 rows WITHOUT raising -
        return {"available": False,                      # do NOT show a misleading green "all clean" report
                "reason": "no I/O List rows read - check iolist_params.sheets"}
    result = classify.classify_iolist(match.match_iolist(old_rows, new_rows), weights.get("IoList", {}))
    result.update({"available": True, "before": _label(before), "after": _label(after),
                   "before_rows": len(old_rows), "after_rows": len(new_rows)})
    return result


def _compare_cematrix(before: str, after: str, params: dict, weights: dict) -> dict:
    if _why_unavailable(before, after):
        return {}
    try:
        old_rows, old_areas = reader.read_ce_matrix(before, params)
        new_rows, new_areas = reader.read_ce_matrix(after, params)
        area_old, area_new = reader.read_area_sheets(before, params), reader.read_area_sheets(after, params)
    except Exception as error:                           # noqa: BLE001 - never crash the GUI on a bad doc
        return {"cematrix": {"available": False, "reason": f"could not read the C&E Matrix ({type(error).__name__})"}}
    ce = classify.classify_ce(match.match_ce(old_rows, new_rows), old_areas, new_areas, weights.get("CE", {}))
    ce.update({"available": True, "before": _label(before), "after": _label(after),
               "before_rows": len(old_rows), "after_rows": len(new_rows),
               "old_areas": old_areas, "new_areas": new_areas})

    counts_old = {k: len(v) for k, v in area_old.items()}
    counts_new = {k: len(v) for k, v in area_new.items()}
    old_pool = [r for rows in area_old.values() for r in rows]
    new_pool = [r for rows in area_new.values() for r in rows]
    area = classify.classify_area(match.match_area(old_pool, new_pool), counts_old, counts_new,
                                  weights.get("AREA", {}))
    area["available"] = True
    return {"cematrix": ce, "area": area}


def build_report(params: dict | None = None, stamp: str | None = None) -> dict:
    """Assemble the full classified result for both documents. `stamp` is the generated-at label (defaults
    to now; injected for deterministic tests)."""
    params = params or config.load_params()
    weights = config.load_change_weights()
    iol = _compare_iolist(params.get("iolist_previous_path"), params.get("iolist_path"), params, weights)
    cem = _compare_cematrix(params.get("matrix_previous_path"), params.get("matrix_path"), params, weights)
    return {
        "meta": {"project_code": params.get("project_code", ""),
                 "generated": stamp or datetime.now().strftime("%Y-%m-%d %H:%M"),
                 "iolist_before": _label(params.get("iolist_previous_path")),
                 "iolist_after": _label(params.get("iolist_path")),
                 "matrix_before": _label(params.get("matrix_previous_path")),
                 "matrix_after": _label(params.get("matrix_path"))},
        "iolist": iol,
        "cematrix": cem.get("cematrix", {"available": False}),
        "area": cem.get("area", {"available": False}),
    }


def _audit_rows(result: dict) -> list:
    """Flatten every change (both documents) into CSV rows for the audit trail: the node-grouped
    structural changes (address/slot/pin/device) FIRST - they are the costly ones - then the itemized
    corrections + channel blocks."""
    rows = [["document", "identity", "description", "tier", "directions", "fields", "confidence"]]
    iol = result.get("iolist", {})
    for g in iol.get("grouped_changes", []):
        for old_v, new_v in g.get("changes", []):        # one row per structural change, with old->new
            rows.append(["IoList", g["node"], g["label"], g["tier"], "structural",
                         f"{old_v!r} -> {new_v!r}", ""])
    for c in iol.get("corrections", []):           # all itemized corrections (incl. channel-uncertain, flagged)
        rows.append(["IoList", c["fld"], c["desc"], c["tier"], "|".join(c["directions"]),
                     "; ".join(f"{d['field']}: {d['old']!r}->{d['new']!r}" for d in c["diffs"]),
                     c["confidence"]])
    ce = result.get("cematrix", {})
    for s in ce.get("structural", []):
        rows.append(["C&E", s["label"], f"{s['rows']} cause rows", s["tier"], "", "structural", ""])
    for c in ce.get("corrections", []):
        rows.append(["C&E", c.get("concat_id", ""), c["desc"], c["tier"], "|".join(c["directions"]),
                     "; ".join(f"{d['field']}: {d['old']!r}->{d['new']!r}" for d in c["diffs"]), ""])
    area = result.get("area", {})
    for m in area.get("moves", []):                  # safety-critical: every area reassignment, with addresses
        rows.append(["AREA", m.get("device_tag", ""), m.get("desc", ""), "critical", "moved",
                     f"area {m.get('sheet_old')!r}->{m.get('sheet_new')!r}; "
                     f"address {m.get('addr_old')!r}->{m.get('addr_new')!r}", ""])
    return rows


def run_change_report(params: dict | None = None, out_dir: str | None = None,
                      stamp: str | None = None) -> dict:
    """Build + write the report (HTML + CSV). Returns {result, paths, dir}."""
    result = build_report(params, stamp=stamp)
    out_dir = out_dir or config.changes_report_dir()
    os.makedirs(out_dir, exist_ok=True)
    html_path = os.path.join(out_dir, config.CHANGES_REPORT_STEM + ".html")
    csv_path = os.path.join(out_dir, config.CHANGES_REPORT_STEM + ".csv")
    with open(html_path, "w", encoding="utf-8") as handle:
        handle.write(report.render_html(result))
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(_audit_rows(result))
    return {"result": result, "paths": {"html": html_path, "csv": csv_path}, "dir": out_dir}
