"""Phase 100d - the orchestrator (run 110-140 -> record the issues -> write the 4 reports). Hermetic: the
4 validators are monkeypatched to synthetic findings; the registry/DB are pointed at a temp project."""
import os
import tempfile

from _harness import run, eq, ok
from pipeline5 import config
from pipeline5.truth.database import Database as DB
from pipeline5.findings.finding import Finding, validation_issues_table
from pipeline5.phases.validation import crosscheck
from pipeline5.phases.validation import iolist_checks as iolist
from pipeline5.phases.validation import cematrix_checks as matrix
from pipeline5.phases.validation import runner as validation


def _f(phase, type_, sev, detail="d", loc=""):
    return Finding(phase=phase, type=type_, severity=sev, detail=detail, location=loc)


def test_run_validation_orchestration():
    saved = (iolist.run_iolist, matrix.run_ce_matrix,
             crosscheck.run_xcheck_cem_iol, crosscheck.run_xcheck_iol_cem)
    with tempfile.TemporaryDirectory() as d:
        config.use_project(d)
        try:
            iolist.run_iolist = lambda p: [_f(110, "row_ok", "PASS"), _f(110, "addr_format", "FAIL", loc="IO!G5")]
            matrix.run_ce_matrix = lambda p: [_f(120, "ce_summary", "INFO")]
            crosscheck.run_xcheck_cem_iol = lambda db, p: [_f(130, "cem_addr_none", "FAIL", loc="CE!F6")]
            crosscheck.run_xcheck_iol_cem = lambda db, p: [_f(140, "iol_cem_missing_plain", "WARN", loc="IO!A2")]
            rep = os.path.join(d, "rep")
            res = validation.run_validation(database=DB([]), params={"iolist_path": "x", "matrix_path": "y"}, out_dir=rep)

            for name in ("documents_validation_report.txt", "documents_validation_report.html",
                         "documents_validation_errors.txt", "documents_validation_errors.html"):
                ok(os.path.exists(os.path.join(rep, name)), f"{name} written")
            eq(res["counts"], {"PASS": 1, "FAIL": 2, "INFO": 2, "WARN": 1}, "effective counts (+ the 150 summary INFO)")

            comp = open(res["paths"]["documents_validation_report.txt"], encoding="utf-8").read()
            ok("110 Validate I/O List" in comp and "140 Cross-Check IOL->CEM" in comp, "all sub-phase banners")
            ok("row_ok" in comp, "the complete report keeps PASS")
            err = open(res["paths"]["documents_validation_errors.txt"], encoding="utf-8").read()
            ok("row_ok" not in err and "addr_format" in err, "the errors report drops PASS, keeps FAIL")

            # only the FAIL/ERROR/WARN issues are recorded into validation_issues (PASS/INFO are report-only)
            vi = DB([validation_issues_table()]).load(config.database_dir())["validation_issues"]
            eq({(r["type"], r["severity"]) for r in vi},
               {("addr_format", "FAIL"), ("cem_addr_none", "FAIL"), ("iol_cem_missing_plain", "WARN")},
               "only the treatable findings recorded")
        finally:
            iolist.run_iolist, matrix.run_ce_matrix, crosscheck.run_xcheck_cem_iol, crosscheck.run_xcheck_iol_cem = saved
            config.use_builtin()


if __name__ == "__main__":
    import sys
    sys.exit(run("validation_phase", [
        ("run_validation_orchestration", test_run_validation_orchestration),
    ]))
