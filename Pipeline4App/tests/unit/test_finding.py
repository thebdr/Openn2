"""The Finding model + the validation_issues table (core.finding): the uid scheme (stable across a
severity change, churns on a detail change, whitespace-normalized), id, frozenness, and record()."""
from _harness import run, eq, ok, raises
from pipeline4.core import keys
from pipeline4.core.database import Database
from pipeline4.core.finding import Finding, record, validation_issues_table


def test_uid_excludes_severity_includes_content():
    a = Finding(phase=520, type="db_x", severity="FAIL", detail="boom", location="DB Foo")
    b = Finding(phase=520, type="db_x", severity="WARN", detail="boom", location="DB Foo")  # diff severity
    eq(a.uid, b.uid, "a severity change keeps the uid (a treatment must keep matching)")
    eq(a.uid, keys.uid("520", "db_x", "DB Foo", "boom"), "uid = keys.uid(phase, type, norm(location), norm(detail))")
    c = Finding(phase=520, type="db_x", severity="FAIL", detail="boom!", location="DB Foo")  # diff detail
    ok(a.uid != c.uid, "a detail change re-keys the finding")
    d = Finding(phase=520, type="db_x", severity="FAIL", detail="  boom ", location="DB   Foo")
    eq(a.uid, d.uid, "whitespace in location/detail is normalized before hashing")


def test_id_and_frozen():
    f = Finding(phase=600, type="diag_scl_template_missing", severity="WARN", detail="x")
    eq(f.id, "600-diag_scl_template_missing", "id = <phase>-<type>")
    eq(Finding(phase=700, type="", severity="INFO", detail="x").id, "700", "no type -> just the phase")
    raises(Exception, lambda: setattr(f, "severity", "FAIL"))   # frozen dataclass


def test_validation_issues_table_shape():
    t = validation_issues_table()
    eq(t.name, "validation_issues")
    for c in ("uid", "id", "phase", "type", "severity", "location", "detail", "source_uid", "doc",
              "location2", "doc2", "bit", "fld", "compared"):
        ok(c in t.columns, f"{c} column present")
    ok("treatment" not in t.columns and "effective_severity" not in t.columns,
       "the table records FACTS only; treatments live in error_management.csv")


def test_record_uses_finding_uid():
    db = Database([])
    fs = [Finding(phase=520, type="db_dup", severity="WARN", detail="dropped", location="DB A"),
          Finding(phase=520, type="db_bad", severity="FAIL", detail="undeclared", location="DB B")]
    record(db, fs)
    ok("validation_issues" in db, "the table is created on first record")
    rows = list(db["validation_issues"])
    eq(len(rows), 2)
    eq({r["uid"] for r in rows}, {f.uid for f in fs}, "each row carries the Finding's own uid (== the registry key)")
    eq(rows[1]["severity"], "FAIL", "the default severity is recorded")
    record(db, [Finding(phase=300, type="x", severity="INFO", detail="more")])
    eq(len(list(db["validation_issues"])), 3, "a second record appends")


def test_record_persists_report_context():
    """The phase-100 context (location2, bit/FLD, the flattened comparison) lands in the table so the
    Findings panel shows the SAME key details as the log line; other phases leave the tail empty."""
    from pipeline4.core.finding import compared_text
    from pipeline4.core.model import Cmp, InfoBlock
    cmp = Cmp("I110.0", "I110.0", True, "=S1 -S80001", "=S1 -X80101", False)
    eq(compared_text(cmp), "I110.0 === I110.0 | =S1 -S80001 =/= =S1 -X80101",
       "the Cmp flattens to the one-cell comparison")
    eq(compared_text(None), "", "no cmp -> empty cell")
    db = Database([])
    record(db, [Finding(phase=130, type="cem_addr_fld", severity="FAIL", detail="different FLD",
                        location="CE!F102", doc="ce.xlsx", location2="IO!O195", doc2="io.xlsx",
                        info=InfoBlock(bit="I110.0", fld="=S1 -S80001"), cmp=cmp),
                Finding(phase=520, type="db_dup", severity="WARN", detail="dropped", location="DB A")])
    rich, plain = list(db["validation_issues"])
    eq((rich["location2"], rich["doc2"]), ("IO!O195", "io.xlsx"), "the other-side link is persisted")
    eq((rich["bit"], rich["fld"]), ("I110.0", "=S1 -S80001"), "the signal identity is persisted")
    eq(rich["compared"], compared_text(cmp), "the comparison is persisted")
    eq((plain["location2"], plain["bit"], plain["compared"]), ("", "", ""),
       "a non-100 finding leaves the context columns empty")


def test_record_standalone_appends_only_issues():
    """The doc-only-phase seam (ph200): records straight to <dir>/validation_issues.csv, APPENDS to
    what a previous save left there, and touches NO other SSOT file."""
    import os
    import tempfile
    from pipeline4.core.finding import record_standalone
    with tempfile.TemporaryDirectory() as d:
        first = Finding(phase=300, type="stg_x", severity="WARN", detail="earlier", location="IO!A1")
        eq(record_standalone([first], d), 1, "creates the file on first record")
        second = Finding(phase=200, type="fill_unresolved", severity="FAIL", detail="fill it",
                         location="NET SAFETY 50!AD179", doc="io.xlsx")
        eq(record_standalone([second], d), 1)
        eq(record_standalone([], d), 0, "an empty batch writes nothing")
        with open(os.path.join(d, "validation_issues.csv"), encoding="utf-8") as h:
            body = h.read()
        ok(first.uid in body and second.uid in body, "the second record APPENDED (no clobber)")
        eq(os.listdir(d), ["validation_issues.csv"], "no other SSOT table is created or touched")


if __name__ == "__main__":
    import sys
    sys.exit(run("finding", [
        ("uid_excludes_severity_includes_content", test_uid_excludes_severity_includes_content),
        ("id_and_frozen", test_id_and_frozen),
        ("validation_issues_table_shape", test_validation_issues_table_shape),
        ("record_uses_finding_uid", test_record_uses_finding_uid),
        ("record_persists_report_context", test_record_persists_report_context),
        ("record_standalone_appends_only_issues", test_record_standalone_appends_only_issues),
    ]))
