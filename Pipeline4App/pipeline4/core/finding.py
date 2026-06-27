"""A `Finding` - one diagnostic the pipeline produces - and the `validation_issues` SSOT table it persists to.

A finding is a FACT the code emits (a config error, a skipped signal, a warning). Its DEFAULT severity is
set at the emit site (`severity.LEVELS`); the operator can later RECLASSIFY the effective severity per
`uid` via the treatment registry (`core.treatments` / `error_management.csv`) - so severity is deliberately
NOT part of the uid. The `validation_issues` table records the raw findings (the facts); the registry is a
separate overlay (the decisions). They join by `uid`.

The `uid` is the stable cross-run identity: `keys.uid(phase, type, norm(location), norm(detail))` - a port
of PL3's `sha1(phase|type|location|detail)`, EXCLUDING the volatile severity/seq + the workbook identity,
so a treatment (and any FK) survives a document revision OR a severity change. `location`/`detail` are
whitespace-normalized before hashing so a cosmetic message edit doesn't silently re-key the finding.
"""
from __future__ import annotations

from dataclasses import dataclass

from pipeline4.core import keys
from pipeline4.core.table import Table


def _norm(text) -> str:
    """Collapse all whitespace + strip - the canonical form hashed into the uid (so trailing spaces / a
    newline-vs-space don't churn the identity)."""
    return " ".join(str(text if text is not None else "").split())


@dataclass(frozen=True)
class Finding:
    phase: int               # the (sub-)phase that emitted it (300, 520, 400, 510, 600, …)
    type: str                # the grep/i18n slug ("db_element_not_declared") - the CODE anchor + treatment key part
    severity: str            # the DEFAULT (code) severity: one of severity.LEVELS. NOT in the uid.
    detail: str              # the variable human message (the right-hand text)
    location: str = ""       # "Sheet!Cell" OR a logical locator ("DB <name>", "IF_<inst>/<sig>")
    source_uid: str = ""     # FK to the producing entity's uid (a signal / interface_element) - audit only
    doc: str = ""            # workbook basename for a GUI link; NOT hashed (volatile)

    @property
    def uid(self) -> str:
        return keys.uid(str(self.phase), self.type, _norm(self.location), _norm(self.detail))

    @property
    def id(self) -> str:
        """The code-traceable log-type index '<phase>-<type>' (grep the type -> the emit site)."""
        return f"{self.phase}-{self.type}" if self.type else str(self.phase)


def validation_issues_table() -> Table:
    """The SSOT record of every finding the pipeline produced (one row per finding, at its DEFAULT
    severity). The treatment overlay (effective severity) lives in error_management.csv, joined by uid -
    NOT stored here, so the table stays a pure record of facts. `uid` is supplied (not re-stamped) so it
    equals `Finding.uid` (the registry key)."""
    return Table(
        "validation_issues",
        columns=["uid", "id", "phase", "type", "severity", "location", "detail", "source_uid", "doc"],
        json_columns=[],
        key_columns=["phase", "type", "location", "detail"],
    )


def record(database, findings) -> None:
    """Append `findings` to the database's `validation_issues` table (creating it if absent), each row
    carrying the Finding's own `uid`. The caller saves the database."""
    if "validation_issues" not in database:
        database.add_table(validation_issues_table())
    table = database["validation_issues"]
    for f in findings:
        table.add(uid=f.uid, id=f.id, phase=f.phase, type=f.type, severity=f.severity,
                  location=f.location, detail=f.detail, source_uid=f.source_uid, doc=f.doc)
