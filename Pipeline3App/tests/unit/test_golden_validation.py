"""Data-dependent golden parity for Phase 100 (review-then-freeze, plan §7).

Regenerates the two validation reports from the REAL documents and compares them to the frozen
goldens under tests/golden/. Skips cleanly when the goldens or the real input documents are absent
(the data-independent suite stays the always-green gate). Re-freeze intentionally with:

    python tests/unit/test_golden_validation.py --freeze
"""
import os
import sys
from _harness import run, eq

GOLD = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "golden"))
REPORTS = (("validation_report", "documents_validation_report.txt"),
           ("validation_errors", "documents_validation_errors.txt"))


def _norm(s):
    return "\n".join(ln.rstrip() for ln in s.replace("\r\n", "\n").split("\n")).strip()


def _docs_present():
    from pipeline3.core import config
    io = (config.load_params().get("io_list") or {}).get("path")
    return bool(io and os.path.exists(io))


def _generate():
    """Validate the (already-filled) real document and return the written report artifact paths."""
    import pipeline3.phases  # noqa: F401  (registers the phases)
    from pipeline3 import app
    from pipeline3.context import PipelineContext
    ctx = PipelineContext.create(profile="main", emit=lambda *a, **k: None)
    ctx.completed.add(200)          # the committed source is already filled -> validate it directly
    return app.run_phase(ctx, 100).artifacts


def test_reports_match_golden():
    if not _docs_present():
        print("    (skipped: real input documents absent)"); return
    if not all(os.path.exists(os.path.join(GOLD, fn)) for _, fn in REPORTS):
        print("    (skipped: golden not frozen)"); return
    arts = _generate()
    for key, fn in REPORTS:
        with open(arts[key], encoding="utf-8") as f:
            got = f.read()
        with open(os.path.join(GOLD, fn), encoding="utf-8") as f:
            want = f.read()
        eq(_norm(got), _norm(want), f"{fn} drifted from the frozen golden (re-freeze if intended)")


def _freeze():
    import shutil
    os.makedirs(GOLD, exist_ok=True)
    arts = _generate()
    for key, fn in REPORTS:
        shutil.copyfile(arts[key], os.path.join(GOLD, fn))
        print("froze", fn)


if __name__ == "__main__":
    if "--freeze" in sys.argv:
        _freeze(); raise SystemExit(0)
    raise SystemExit(run("golden_validation", [
        ("reports_match_golden", test_reports_match_golden),
    ]))
