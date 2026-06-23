"""The phase-100 treatment registry (M6b).

A finding's stable identity is `LogEntry.uid` (a per-FAIL hash of phase+type+location+detail,
independent of the workbook and the volatile level/seq - so a treatment keeps matching across runs
and document revisions). `user_input/error_management.csv` records, per uid, a treatment applied on
the NEXT run:

  warn   -> the finding is logged as WARNING (downgraded)
  skip   -> the finding is logged as SKIP (acknowledged; proceed past it)
  accept -> ONLY the "address matches, device (FLD) mismatches" cross-check (iol_cem_addr_only):
            write the C&E-side FLD into the I/O List row description (documenting the intentional
            alias) and resolve the finding to SKIP. The one document-mutating treatment (idempotent).

The philosophy: reach a clean validation by RECORDING decisions for findings you knowingly ignore,
not by faking the documents.

Reconciliation each run (mark-stale policy): every current FAIL is (re)written; an UNTREATED row whose
uid no longer appears is pruned (noise); a TREATED row that no longer appears is KEPT and marked
`stale` (never hard-deleted, so the decision survives a transient disappearance / doc re-edit).

The designer (validation-only) build reads a SEPARATE uid-keyed CSV, `designer_suppressions.csv`, that
only suppresses lines locally - kept distinct from the operator's error_management.csv.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, replace

from pipeline3.core import config
from pipeline3.io import csv_tables, workbook as wbk
from pipeline3.io.workbook import FileLockedError

FIELDS = ["uid", "id", "phase", "type", "treatment", "status", "location", "message"]
TREATMENTS = ("warn", "skip", "accept")
ACCEPT_TYPES = ("iol_cem_addr_only",)          # address matches, device (FLD) differs

def _err_mgmt_csv() -> str:
    """The operator treatment registry, under the ACTIVE config (a project's user_input/, or the
    app's when no project is open) - so each project owns its own treatments."""
    return os.path.join(config.user_input_dir(), "error_management.csv")


def _designer_suppress_csv() -> str:
    return os.path.join(config.user_input_dir(), "designer_suppressions.csv")


@dataclass
class Treatment:
    uid: str
    treatment: str = ""
    status: str = ""
    id: str = ""
    phase: str = ""
    type: str = ""
    location: str = ""
    message: str = ""


def load(path: str) -> dict:
    """uid -> Treatment, from a CSV (a missing file -> {})."""
    if not path or not os.path.exists(path):
        return {}
    out = {}
    for r in csv_tables.read_rows(path):
        uid = (r.get("uid") or "").strip()
        if uid:
            out[uid] = Treatment(uid=uid, treatment=(r.get("treatment") or "").strip().lower(),
                                 status=(r.get("status") or "").strip().lower(),
                                 id=(r.get("id") or "").strip(), phase=(r.get("phase") or "").strip(),
                                 type=(r.get("type") or "").strip(), location=(r.get("location") or "").strip(),
                                 message=(r.get("message") or "").strip())
    return out


def _level_for(treatment: str):
    return {"warn": "WARN", "skip": "SKIP", "accept": "SKIP"}.get(treatment)


def apply_and_reconcile(ctx, log, path: str | None = None) -> str:
    """Operator/main path: apply the recorded treatments to FAIL lines (mutating `log`), then
    reconcile the registry (refresh current findings, prune untreated-gone, mark treated-gone stale)
    and write it back. Returns the CSV path."""
    path = path or _err_mgmt_csv()
    treatments = load(path)
    seen: dict = {}
    for e in log:
        if e.level != "FAIL":
            continue
        seen.setdefault(e.uid, e)
        t = treatments.get(e.uid)
        if not t or not t.treatment:
            continue
        if t.treatment == "accept":
            if e.type in ACCEPT_TYPES and apply_accept(ctx, e):
                e.level = "SKIP"
            continue                            # wrong type / couldn't apply -> leave as FAIL
        lvl = _level_for(t.treatment)
        if lvl:
            e.level = lvl
    return _write(path, _reconcile(seen, treatments))


def _reconcile(seen: dict, treatments: dict) -> dict:
    merged: dict = {}
    for uid, e in seen.items():                 # every current FAIL -> active row (treatment preserved)
        old = treatments.get(uid)
        merged[uid] = Treatment(uid=uid, treatment=(old.treatment if old else ""), status="",
                                id=e.id, phase=str(e.phase), type=e.type,
                                location=e.location, message=e.detail)
    for uid, old in treatments.items():
        if uid in seen:
            continue
        if old.treatment:                       # treated but gone -> keep, mark stale
            merged[uid] = replace(old, status="stale")
        # untreated + gone -> pruned (dropped)
    return merged


def _write(path: str, merged: dict) -> str:
    rows = [{"uid": t.uid, "id": t.id, "phase": t.phase, "type": t.type, "treatment": t.treatment,
             "status": t.status, "location": t.location, "message": t.message}
            for t in merged.values()]
    return csv_tables.write_rows(path, FIELDS, rows)


def apply_suppressions(log, path: str | None = None) -> int:
    """Designer build: SKIP any FAIL/WARN line whose uid is listed in designer_suppressions.csv.
    Returns the number suppressed. Read-only (never writes the registry)."""
    sup = load(path or _designer_suppress_csv())
    n = 0
    for e in log:
        if e.level in ("FAIL", "WARN") and e.uid in sup:
            e.level = "SKIP"
            n += 1
    return n


def apply_accept(ctx, entry) -> bool:
    """Document-mutating accept (idempotent): append the C&E-side FLD to the I/O List row's variable
    description, documenting the intentional address alias. Returns True when applied or already
    present; False when it can't be applied (no matching row, no C&E FLD, or the file is locked)."""
    row = next((r for r in (ctx.rows or []) if r.get("source_cell") == entry.location), None)
    if row is None:
        return False
    ce = " ".join(x for x in (row.get("ce_functional_unit"), row.get("ce_location"),
                              row.get("ce_device")) if x).strip()
    sheet, srow = row.get("_source_sheet"), row.get("_source_row")
    if not ce or not sheet or not srow:
        return False
    note = f"[C&E: {ce}]"
    col = {m["canonical"]: m["column"] for m in config.load_column_map("IoList")}.get("desc_l1b", "L")
    io_path = ctx.io_list_path()
    try:
        w = wbk.load_for_write(io_path)
    except FileLockedError:
        return False
    try:
        cell = w[sheet][f"{col}{srow}"]
        cur = "" if cell.value is None else str(cell.value)
        if note in cur:
            return True                         # already documented -> idempotent
        cell.value = (cur + " " + note).strip()
        cell.data_type = "s"
        w.save(io_path)
    finally:
        w.close()
    return True
