"""error_management.py - an error registry + per-error treatment between validation runs.

Some validation errors are acceptable for a given project and the user wants the pipeline to go
forward anyway. `validate(..., out_dir=...)` calls `run(log, out_dir)`, which:

  1. tags every entry with its phase id (0A/0B/1/2/3),
  2. writes a COMPLETE registry of every FAIL to `<out_dir>/error_management.csv` - columns
     `id, phase, type, treatment, location, message` (one row per distinct error), and
  3. applies the `treatment` the user set in that CSV on a PREVIOUS run (matched by string):
        warn       -> this error becomes a WARNING,
        skip       -> this error is dropped to SKIP (so the pipeline goes forward),
        skip_type  -> EVERY error of the same (phase, type) is dropped to SKIP.

`id` is a stable per-instance hash; `type` is a normalised signature of the message (variable
parts removed) so `skip_type` catches every occurrence of the same check. Treatments already set
are preserved across runs (merge by id). The GUIs link the `[FAIL]` tag to this CSV.
"""
from __future__ import annotations
import csv
import hashlib
import os
import re

from . import config

CSV_NAME = "error_management.csv"
HEADER = ["id", "phase", "type", "treatment", "location", "message"]
TREATMENTS = {"warn", "skip", "skip_type"}

_PHASE_RE = re.compile(r"(?:PHASE|FASE)\s+(\S+)", re.I)   # EN "PHASE 0A", IT "FASE 0A"
# strip the variable parts of a message to get a stable per-check "type" signature
_VAR_SUBS = [
    re.compile(r"\[[^\]]*\]"),          # [sheet '...' - cell 'X1'] / [cell U281] / [<L>1]
    re.compile(r"'[^']*'"),             # 'quoted values'
    re.compile(r"\b\d+(?:\.\d+)+\b"),   # IPs / dotted addresses
    re.compile(r"\b\d+\b"),             # bare numbers
]


def assign_phases(log) -> None:
    """Tag each entry with the phase id of the banner above it (0A/0B/1/2/3)."""
    cur = ""
    for e in log:
        if e.level == "PHASE":
            m = _PHASE_RE.search(e.message or "")
            cur = m.group(1) if m else cur
        elif not getattr(e, "phase", ""):
            e.phase = cur


def error_type(message: str) -> str:
    """A stable signature for the KIND of error (variable parts removed); drives skip_type."""
    s = message or ""
    for rx in _VAR_SUBS:
        s = rx.sub("", s)
    return " ".join(s.split())


def error_id(entry) -> str:
    """A deterministic id for THIS error instance (stable across runs while the data is)."""
    raw = "|".join((getattr(entry, "phase", "") or "", entry.location or "",
                    entry.key or "", entry.address or "", entry.message or ""))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def load_rules(path: str):
    """(by_id: {id: treatment}, skip_types: set[(phase, type)]) from an existing CSV."""
    by_id: dict[str, str] = {}
    skip_types: set = set()
    if not os.path.exists(path):
        return by_id, skip_types
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                t = (r.get("treatment") or "").strip().lower()
                if t not in TREATMENTS:
                    continue
                rid = (r.get("id") or "").strip()
                if rid:
                    by_id[rid] = t
                if t == "skip_type":
                    skip_types.add(((r.get("phase") or "").strip(), (r.get("type") or "").strip()))
    except OSError:
        pass
    return by_id, skip_types


def write_csv(path: str, fails: list, by_id: dict) -> None:
    """Write the complete error registry (one row per distinct FAIL), carrying treatments by id."""
    seen, rows = set(), []
    for e in fails:
        rid = error_id(e)
        if rid in seen:
            continue
        seen.add(rid)
        rows.append({"id": rid, "phase": getattr(e, "phase", "") or "",
                     "type": error_type(e.message), "treatment": by_id.get(rid, ""),
                     "location": e.location or "", "message": e.message or ""})
    rows.sort(key=lambda r: (r["phase"], r["type"], r["location"]))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(rows)


def apply_rules(log, by_id: dict, skip_types: set) -> None:
    """Mutate FAIL entries per the user's treatments (warn -> WARN, skip/skip_type -> SKIP)."""
    for e in log:
        if e.level != "FAIL":
            continue
        t = by_id.get(error_id(e), "")
        if t in ("skip", "skip_type") or (getattr(e, "phase", ""), error_type(e.message)) in skip_types:
            e.level = "SKIP"
            e.message = (e.message or "") + "  [skipped by error_management]"
        elif t == "warn":
            e.level = "WARN"
            e.message = (e.message or "") + "  [downgraded by error_management]"


def run(log, out_dir: str | None = None) -> str:
    """Tag phases, write the registry CSV, apply the user's treatments. Returns the CSV path.
    `out_dir` defaults to user_input/ (treatments persist between runs, edited by the user)."""
    assign_phases(log)
    path = os.path.join(out_dir or config.USER_INPUT, CSV_NAME)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    by_id, skip_types = load_rules(path)
    write_csv(path, [e for e in log if e.level == "FAIL"], by_id)   # registry from the ORIGINAL fails
    apply_rules(log, by_id, skip_types)
    return path
