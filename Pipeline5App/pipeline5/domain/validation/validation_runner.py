"""Phase 100 orchestrator - runs the four validators (110 I/O List, 120 C&E, 130/140 cross-checks),
records the treatable facts into `validation_issues`, and writes the two operator reports (complete +
errors-only) as txt + html. Clean-room analog of PL3's `phases/p100_validation.py` (PL4 has no `phases/`
package - phases run inline from the GUI - so this is a plain `run_validation` the GUI/parity calls).

`run_validation` itself never raises/halts - the 4 validators always complete and the reports are always
written. The SEVERITY CONTRACT (production-test decision) is enforced by the GUI seam: a FAIL finding then
HALTS THE PIPELINE (the run state / the Run-all chain) - reports written, generation blocked. The report
shows EFFECTIVE severity (the treatment registry applied). 150 (diagnosis-slot) + the `accept` treatment are
out of scope. `run_validation` is READ-ONLY w.r.t. the treatment registry (the GUI's `run.render` reconciles
+ writes it); so a headless/parity call doesn't mutate `user_input/`.
"""
from __future__ import annotations

import os
from dataclasses import replace

from pipeline5.core import config
from pipeline5.core import i18n
from pipeline5.core import severity
from pipeline5.core import finding_treatments as treatments
from pipeline5.core.finding import Finding, record
from pipeline5.io import report_renderer as render
from pipeline5.domain import iolist_staging as staging
from pipeline5.domain.validation import crosscheck
from pipeline5.domain.validation import diagcheck
from pipeline5.domain.validation import iolist_checks as iolist
from pipeline5.domain.validation import cematrix_checks as matrix
from pipeline5.domain.validation import messages

# the sub-phase banner label KEYS (the registry's pb_* keys; resolved per language at render time)
_BANNER_KEYS = {110: "pb_validate_iolist", 120: "pb_validate_ce",
                130: "pb_xcheck_cem_iol", 140: "pb_xcheck_iol_cem",
                150: "pb_validate_diag"}
_TREATABLE = ("FAIL", "ERRR", "WARN")


def _banner(num: int, lang: str = "en") -> Finding:
    return Finding(phase=num, type="", severity=severity.BANNER,
                   detail=f"{num} {i18n.tr(_BANNER_KEYS[num], lang)}")


def run_validation(database=None, params: dict | None = None, out_dir: str | None = None,
                   lang: str = "en") -> dict:
    """Run phase 100 over the configured documents. `database` (the staged `signals`, for 130/140) is staged
    when None; 110/120 read the raw workbooks from `params`. The finding detail + the banners + the report
    chrome are built in `lang` (the operator's language - this IS the point of i18n; default `en` keeps the
    parity oracle English). Records the treatable findings + saves, writes the 4 reports. Returns
    {'findings','applied','items','paths','counts','dir'} - `items` is the banner-interleaved
    effective-severity sequence the reports render (the GUI log renders the SAME items)."""
    params = params or config.load_params()
    if database is None:
        database, _staging_findings = staging.stage(params)

    with messages.active_lang(lang):                                # findings build their detail in `lang`
        findings = []                                              # the 4-step workflow (user spec):
        findings += iolist.run_iolist(params)                      # 1. doc 1 (110, raw I/O List)
        findings += matrix.run_ce_matrix(params)                   # 2. doc 2 if present (120, raw C&E)
        findings += crosscheck.run_xcheck_cem_iol(database, params)  # 3. cross-checks (130 CEM -> IOL)
        findings += crosscheck.run_xcheck_iol_cem(database, params)  #    + 140 (IOL -> CEM)
        findings += diagcheck.run_diag_checks(database, params)    # 4. diagnosis (150; SKIPs on a virgin doc)

    # record only the ISSUES (FAIL/ERROR/WARN) into validation_issues - PASS/INFO/SKIP are report-only noise.
    record(database, [f for f in findings if f.severity in _TREATABLE])
    database.save(config.database_dir())

    # apply the treatment registry (read-only) -> the EFFECTIVE severity the report shows.
    applied = treatments.apply(findings, treatments.load())

    # the interleaved report items: a banner per (sub)phase, then its findings at effective severity.
    items, last = [], None
    for f, eff in applied:
        if f.phase != last:
            items.append(_banner(f.phase, lang))
            last = f.phase
        items.append(replace(f, severity=eff))

    out_dir = out_dir or config.validation_report_dir()
    os.makedirs(out_dir, exist_ok=True)
    txt, html = render.reports(items), render.html_reports(items, lang)
    paths = {}
    for kind, stem in (("complete", config.VALIDATION_REPORT_STEM), ("errors", config.VALIDATION_ERRORS_STEM)):
        for ext, body in ((".txt", txt[kind]), (".html", html[kind])):
            path = os.path.join(out_dir, stem + ext)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(body)
            paths[stem + ext] = path

    counts: dict = {}
    for _f, eff in applied:
        counts[eff] = counts.get(eff, 0) + 1
    return {"findings": findings, "applied": applied, "items": items, "paths": paths,
            "counts": counts, "dir": out_dir}
