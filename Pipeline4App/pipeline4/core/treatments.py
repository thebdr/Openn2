"""The TREATMENT registry - the operator overlay that RECLASSIFIES a finding's effective severity per uid.

`user_input/error_management.csv` records, per finding `uid`, a `treatment` the operator chose. Unlike PL3
(whose treatments were a fixed warn/skip/accept -> a fixed level), a PL4 treatment NAMES the target level
directly, so it can DOWNGRADE *or* ESCALATE:
  fail   -> FAIL  (escalate: this finding now HALTS the run)
  error  -> ERROR
  warn   -> WARN  (downgrade a FAIL so the run proceeds)
  skip   -> SKIP  (acknowledge)
  ignore -> SKIP  (acknowledge + hide from the operator view)
A blank/unknown treatment leaves the code DEFAULT severity. The pipeline halts iff any finding's EFFECTIVE
severity is in `severity.HALTING` (currently {FAIL}). (`accept` - the document-mutating phase-100 treatment
- is out of scope until phase 100 ports.)

Reconciliation each run (PL3's mark-stale policy): every CURRENT finding is (re)written with refreshed
context; an UNTREATED row whose uid is gone is PRUNED (noise); a TREATED row that is gone is KEPT and marked
`stale` (so the decision survives a transient disappearance / a doc re-edit). Clean-room generalization of
PL3 `core/errors.py`.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, replace

from pipeline4.core import config, severity

FIELDS = ["uid", "id", "phase", "type", "treatment", "status", "location", "message"]
TREATMENTS = ("fail", "error", "warn", "skip", "ignore")   # + "accept" (doc-mutating) lands with phase 100
# findings the operator can treat (the actionable ones get a registry row; PASS/INFO/SKIP/DEBUG don't).
_TREATABLE = frozenset({"FAIL", "ERRR", "WARN"})


@dataclass
class Treatment:
    uid: str
    treatment: str = ""
    status: str = ""             # "" (current) | "stale" (treated-but-gone)
    id: str = ""
    phase: str = ""
    type: str = ""
    location: str = ""
    message: str = ""


def registry_path() -> str:
    return os.path.join(config.user_input_dir(), "error_management.csv")


def load(path: str | None = None) -> dict:
    """uid -> Treatment, from the CSV (a missing file -> {})."""
    path = path or registry_path()
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            uid = (row.get("uid") or "").strip()
            if not uid:
                continue
            out[uid] = Treatment(uid=uid, treatment=(row.get("treatment") or "").strip().lower(),
                                 status=(row.get("status") or "").strip().lower(),
                                 id=(row.get("id") or ""), phase=(row.get("phase") or ""),
                                 type=(row.get("type") or ""), location=(row.get("location") or ""),
                                 message=(row.get("message") or ""))
    return out


def effective_severity(default_severity: str, treatment: str) -> str:
    """The effective level: the treatment NAMES the target (first-char-addressable like severity.resolve);
    'ignore' -> SKIP; a blank/unknown treatment -> the code default."""
    t = (treatment or "").strip().lower()
    if not t:
        return default_severity
    if t == "ignore":
        return "SKIP"
    return severity.resolve(t) or default_severity


def apply(findings, treatments: dict) -> list:
    """[(finding, effective_severity)] in input order - the effective == default unless a treatment matches
    the finding's uid. Does NOT mutate the (frozen) Finding."""
    out = []
    for f in findings:
        tr = treatments.get(f.uid)
        out.append((f, effective_severity(f.severity, tr.treatment if tr else "")))
    return out


def should_halt(applied) -> bool:
    """True iff any effective severity is in severity.HALTING (currently {FAIL})."""
    return any(eff in severity.HALTING for _f, eff in applied)


def reconcile(findings, treatments: dict) -> dict:
    """The merged {uid: Treatment} to write: every CURRENT treatable finding refreshed (treatment kept,
    status cleared, context rewritten); an UNTREATED gone uid pruned; a TREATED gone uid kept + marked
    'stale'."""
    current = {f.uid: f for f in findings if f.severity in _TREATABLE}
    merged = {}
    for uid, f in current.items():
        tr = treatments.get(uid)
        merged[uid] = Treatment(uid=uid, treatment=(tr.treatment if tr else ""), status="",
                                id=f.id, phase=str(f.phase), type=f.type, location=f.location, message=f.detail)
    for uid, tr in treatments.items():
        if uid in current:
            continue
        if tr.treatment:                         # treated-but-gone -> keep, mark stale
            merged[uid] = replace(tr, status="stale")
        # untreated-but-gone -> pruned (dropped)
    return merged


def write(path: str, merged: dict) -> str:
    """Write {uid: Treatment} to the CSV (the 8 FIELDS). Creates the dir."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for tr in merged.values():
            writer.writerow({"uid": tr.uid, "id": tr.id, "phase": tr.phase, "type": tr.type,
                             "treatment": tr.treatment, "status": tr.status,
                             "location": tr.location, "message": tr.message})
    return path


def apply_and_reconcile(findings, path: str | None = None) -> list:
    """The one entry the run-helper calls: load -> apply -> reconcile -> write -> return the applied pairs."""
    path = path or registry_path()
    treatments = load(path)
    applied = apply(findings, treatments)
    write(path, reconcile(findings, treatments))
    return applied


def set_treatment(uid: str, treatment: str, path: str | None = None) -> bool:
    """The GUI quick-treat: set/clear one uid's treatment in the CSV (True if the uid row existed)."""
    path = path or registry_path()
    treatments = load(path)
    if uid not in treatments:
        return False
    treatments[uid] = replace(treatments[uid], treatment=(treatment or "").strip().lower(), status="")
    write(path, treatments)
    return True
