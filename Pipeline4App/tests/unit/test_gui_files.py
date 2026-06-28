"""The Files tab logic (gui/files_view + gui/extedit) - the Tk-free scan/dispatch/read helpers."""
import os
import tempfile

from openpyxl import Workbook

from _harness import run, eq, ok
from pipeline4.gui import extedit, files_view


def test_allowed_filters():
    for name in ("signals.csv", "PLCTags.xlsx", "app_config.yaml", "x.json", "a.xml", "d.scl", "n.txt"):
        ok(files_view.allowed(name), f"{name} is shown")
    for name in ("~$io.xlsx", "signals.bak_20260101.csv", "mod.pyc", "pic.png", "tool.exe"):
        eq(files_view.allowed(name), False, f"{name} is hidden")


def test_viewer_kind():
    eq(files_view.viewer_kind("signals.csv"), "csv")
    eq(files_view.viewer_kind("PLCTags.xlsx"), "xlsx")
    eq(files_view.viewer_kind("MACRO.xlsm"), "xlsx")
    for name in ("app_config.yaml", "x.json", "a.xml", "d.scl", "n.txt", "r.md"):
        eq(files_view.viewer_kind(name), "text", f"{name} -> text")
    eq(files_view.viewer_kind("pic.png"), None, "an unsupported ext -> None")


def test_sniff_delim():
    eq(files_view.sniff_delim("a,b,c\n1,2,3"), ",", "more commas -> comma")
    eq(files_view.sniff_delim("a;b;c\n1;2;3"), ";", "more semicolons -> semicolon")
    eq(files_view.sniff_delim("\n\na,b;c,d\n"), ",", "skips blank lines; commas win the tie-break")


def test_read_csv_rows():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.csv")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("uid,name\n1,alpha\n2,beta\n")
        rows = files_view.read_csv_rows(p)
        eq(rows[0], ["uid", "name"], "header row")
        eq(len(rows), 3, "header + 2 data rows")
        eq(rows[2], ["2", "beta"], "the second data row")


def test_populate_prunes_and_skips():
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "a.csv"), "w").close()
        open(os.path.join(d, "mod.pyc"), "w").close()          # disallowed ext
        open(os.path.join(d, "~$lock.xlsx"), "w").close()      # lock file
        os.mkdir(os.path.join(d, "sub")); open(os.path.join(d, "sub", "b.yaml"), "w").close()
        os.mkdir(os.path.join(d, "empty"))                     # no shown files -> pruned
        nodes = files_view.populate(d)
        names = [n["name"] for n in nodes]
        eq(names, ["sub/", "a.csv"], "dirs-first sorted; .pyc + ~$ skipped; empty/ pruned")
        sub = nodes[0]
        ok(sub["is_dir"] and [c["name"] for c in sub["children"]] == ["b.yaml"], "sub/ holds b.yaml")
        eq(nodes[1]["is_dir"], False, "a.csv is a file node")


def test_read_xlsx():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.xlsx")
        wb = Workbook()
        wb.active.title = "One"
        wb.active["A1"] = "h1"; wb.active["B1"] = "h2"; wb.active["A2"] = "v1"; wb.active["B2"] = 7
        wb.create_sheet("Two")["A1"] = "only"
        wb.save(p)
        names, rows = files_view.read_xlsx(p)
        eq(names, ["One", "Two"], "both sheet names")
        eq(rows[0], ["h1", "h2"], "first sheet header")
        eq(rows[1], ["v1", "7"], "cells stringified")
        _n, rows2 = files_view.read_xlsx(p, "Two")
        eq(rows2[0], ["only"], "the named second sheet")


def test_extedit_missing_path():
    ok_, msg = extedit.open_external(os.path.join(tempfile.gettempdir(), "no_such_file_xyz.csv"))
    eq(ok_, False, "a missing file -> (False, ...)")
    ok("not found" in msg, "the message says not found")
    ok2, _m = extedit.reveal("")
    eq(ok2, False, "reveal of an empty path -> False")


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_files", [
        ("allowed_filters", test_allowed_filters),
        ("viewer_kind", test_viewer_kind),
        ("sniff_delim", test_sniff_delim),
        ("read_csv_rows", test_read_csv_rows),
        ("populate_prunes_and_skips", test_populate_prunes_and_skips),
        ("read_xlsx", test_read_xlsx),
        ("extedit_missing_path", test_extedit_missing_path),
    ]))
