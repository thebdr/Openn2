"""The pure logic behind the Findings panel (GUI M2) - testable without Tk.

A finding's FACT lives in the `validation_issues` SSOT table (one row per finding at its DEFAULT severity);
the operator's decision lives in the `error_management.csv` treatment registry (keyed by `uid`). This module
joins them (`panel_rows`) into display rows carrying the EFFECTIVE severity, and applies a one-click
treatment (`apply_treatment`) - create-or-update the registry row (more forgiving than `treatments.set_treatment`,
which only updates an existing row, so a freshly-shown finding can be treated immediately).
"""
from __future__ import annotations

from dataclasses import replace

from pipeline5.core import finding_treatments as treatments
from pipeline5.io import report_renderer as render


def panel_rows(issues, registry: dict) -> list:
    """[{uid, phase, type, severity, effective, treatment, location, location2, bit, fld, compared,
    detail, doc, doc2}] - the `validation_issues` rows joined to the treatment registry, with the
    EFFECTIVE severity computed per uid. The location2/bit/fld/compared context columns carry the same
    key details as the log line (what differed, where both sides live); an old-schema issues file
    simply leaves them empty. Input order preserved."""
    out = []
    for r in issues or []:
        uid = str(r.get("uid", ""))
        default = str(r.get("severity", ""))
        tr = registry.get(uid)
        treatment = tr.treatment if tr else ""
        out.append({
            "uid": uid,
            "phase": str(r.get("phase", "")),
            "type": str(r.get("type", "")),
            "severity": default,
            "effective": treatments.effective_severity(default, treatment),
            "treatment": treatment,
            "location": str(r.get("location", "")),
            "location2": str(r.get("location2", "")),
            "bit": str(r.get("bit", "")),
            "fld": str(r.get("fld", "")),
            "compared": str(r.get("compared", "")),
            "detail": str(r.get("detail", "")),
            "doc": str(r.get("doc", "")),
            "doc2": str(r.get("doc2", "")),
        })
    return out


def filter_rows(rows, phase: str = "", severity: str = "") -> list:
    """Filter display rows by phase (exact, "" = any) and EFFECTIVE severity ("" = any)."""
    out = []
    for r in rows:
        if phase and str(r["phase"]) != str(phase):
            continue
        if severity and r["effective"] != severity:
            continue
        out.append(r)
    return out


def apply_and_records(findings, path: str | None = None) -> tuple:
    """Apply the treatment registry to `findings` (reconcile + write), then render the EFFECTIVE-severity
    findings to structured records for the log. Returns `(applied, records)` - `applied` is the
    `[(finding, effective_severity)]` (so the caller can check `treatments.should_halt`), `records` is the
    `io.render.render_records` list (banners + clickable link spans). Used by the GUI's gate/render seam."""
    applied = treatments.apply_and_reconcile(findings, path)
    effective = [replace(finding, severity=eff) for finding, eff in applied]
    return applied, render.render_records(effective)


def apply_treatment(uid: str, level: str, finding_row: dict, path: str | None = None) -> None:
    """Create-or-update the registry row for `uid` with `level` (one of treatments.TREATMENTS, or '' to
    clear), carrying the finding's context, and write the CSV. `finding_row` is a `validation_issues` row
    (or a panel row) used for the row context when the uid is new to the registry."""
    apply_treatments([finding_row | {"uid": uid}], level, path)


def apply_treatments(finding_rows, level: str, path: str | None = None) -> None:
    """The multi-select treat: set `level` on EVERY row's uid (one registry load + one write - not one
    file round-trip per row). Each row is a `validation_issues`/panel row carrying its own `uid`."""
    path = path or treatments.registry_path()
    registry = treatments.load(path)
    for row in finding_rows:
        uid = str(row.get("uid", ""))
        if not uid:
            continue
        registry[uid] = treatments.Treatment(
            uid=uid, treatment=(level or "").strip().lower(), status="",
            id=str(row.get("id", "") or f"{row.get('phase', '')}-{row.get('type', '')}"),
            phase=str(row.get("phase", "")), type=str(row.get("type", "")),
            location=str(row.get("location", "")), message=str(row.get("detail", "")))
    treatments.write(path, registry)
