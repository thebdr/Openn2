"""The phase RUN gate - the one seam that applies the treatment registry, renders each finding at its
EFFECTIVE severity, and decides whether a phase may proceed (halt iff any effective severity halts).

PL4 has no engine yet (the GUI runs phases inline), so this is a small free function the handlers call -
the same seam a future engine will reuse, testable headless (pass a list sink as `log_append`). Findings
are produced by the phases (`build`/`project` return `list[Finding]` + record them to the
`validation_issues` table); this gate is the report + halt layer on top.
"""
from __future__ import annotations

from pipeline4.core import severity, treatments


def _render(applied, log_append) -> None:
    """Render each (finding, effective_severity) pair via `log_append(level, message)`, noting a treatment
    that changed the level (`(was FAIL)`)."""
    for finding, effective in applied:
        suffix = "" if effective == finding.severity else f"  (was {finding.severity})"
        loc = f"  {finding.location}" if finding.location else ""
        log_append(effective, f"  {finding.id}{loc}  ::  {finding.detail}{suffix}")


def gate(findings, log_append, *, label: str, registry_path: str | None = None) -> bool:
    """Apply the treatment registry to `findings`, render each via `log_append(level, message)` at its
    EFFECTIVE severity, and return whether to CONTINUE. Returns False (HALT) iff any effective severity is
    in `severity.HALTING`. `log_append` is `(level:str, message:str) -> None` (the GUI passes
    `self.log.append`; tests pass a list's append). Use `gate` for a halt-capable phase (one whose write is
    GUARDED by the outcome); use `render` for a WARN-only projection whose output is already written."""
    applied = treatments.apply_and_reconcile(findings, registry_path)
    _render(applied, log_append)
    if treatments.should_halt(applied):
        log_append("FAIL", f"  {label} halted on a blocking finding - nothing written")
        return False
    return True


def render(findings, log_append, *, registry_path: str | None = None) -> None:
    """Apply the registry + render each finding at its EFFECTIVE severity + reconcile (so the findings stay
    treatable) - but NEVER halt. For a WARN-only PROJECTION phase (400/510/…) whose BuilderData is written
    BEFORE this call: an escalated WARN is shown at its effective level, but we don't print a misleading
    `nothing written` halt line (the output already exists). Halt-capable phases use `gate`."""
    _render(treatments.apply_and_reconcile(findings, registry_path), log_append)


def has_blocking(findings) -> bool:
    """True iff any finding's RAW (pre-treatment) severity halts - the build-side guard so a phase never
    WRITES its BuilderData output on a raw FAIL (a buggy registry can't trick it into writing)."""
    return any(f.severity in severity.HALTING for f in findings)
