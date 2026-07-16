"""The Files tab logic (gui/files_view + gui/extedit) - the Tk-free scan/filter/dispatch/read helpers,
including the config-driven visibility (files_tab: regex include/exclude + ${placeholder} roots)."""
import os
import tempfile

from openpyxl import Workbook

from _harness import run, eq, ok
from pipeline5.gui import external_editor as extedit
from pipeline5.gui import files_view

# the shipped default excludes (mirrors app_config.yaml files_tab)
_EXCLUDES = ["~\\$.*", ".*\\.pyc$", ".*\\.bak_.*", "__pycache__"]


def test_compile_filters_and_matches():
    exclude, warns = files_view.compile_filters(_EXCLUDES)
    eq(warns, [], "the shipped patterns all compile")
    include, _ = files_view.compile_filters([".*"])
    for rel in ("signals.csv", "sub/PLCTags.xlsx", "Reports/report.html", "tool.exe"):
        ok(files_view.matches(rel, include, exclude), f"{rel} shows (no extension whitelist anymore)")
    for rel in ("~$io.xlsx", "signals.bak_20260101.csv", "mod.pyc", "sub/~$lock.xlsx"):
        eq(files_view.matches(rel, include, exclude), False, f"{rel} excluded")
    only_html, _ = files_view.compile_filters([r".*\.html$"])
    ok(files_view.matches("Reports/a.html", only_html, []), "a scoped include matches")
    eq(files_view.matches("Reports/a.csv", only_html, []), False, "outside the include -> hidden")
    _c, bad = files_view.compile_filters(["[unclosed"])
    eq(len(bad), 1, "a bad regex becomes one warning")
    ok("unclosed" in bad[0], "the warning names the pattern")


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


def test_populate_prunes_and_filters():
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "a.csv"), "w").close()
        open(os.path.join(d, "mod.pyc"), "w").close()          # excluded by the shipped regexes
        open(os.path.join(d, "~$lock.xlsx"), "w").close()      # lock file, excluded
        os.mkdir(os.path.join(d, "sub")); open(os.path.join(d, "sub", "b.yaml"), "w").close()
        os.mkdir(os.path.join(d, "empty"))                     # no shown files -> pruned
        include, _ = files_view.compile_filters([".*"])
        exclude, _ = files_view.compile_filters(_EXCLUDES)
        nodes = files_view.populate(d, include, exclude)
        names = [n["name"] for n in nodes]
        eq(names, ["sub/", "a.csv"], "dirs-first sorted; .pyc + ~$ excluded; empty/ pruned")
        sub = nodes[0]
        ok(sub["is_dir"] and [c["name"] for c in sub["children"]] == ["b.yaml"], "sub/ holds b.yaml")
        eq(nodes[1]["is_dir"], False, "a.csv is a file node")
        # relative-path scoping: an include anchored to the subfolder shows ONLY its files
        scoped, _ = files_view.compile_filters([r"^sub/"])
        only_sub = files_view.populate(d, scoped, [])
        eq([n["name"] for n in only_sub], ["sub/"], "a ^sub/ include hides the top-level files")
        # no filters at all -> everything shows (visibility is config's job now)
        eq(len(files_view.populate(d)), 4, "unfiltered: sub/ + a.csv + mod.pyc + ~$lock all show")


def test_sections_from_config():
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "doc.xlsx"), "w").close()
        specs = [
            {"title": "Docs", "roots": [d, "${iolist}", "${nope}"], "include": [".*"], "exclude": []},
            {"title": "Bad",  "roots": [d], "include": ["[broken"]},
            "not-a-mapping",
        ]
        sections, warnings = files_view.sections_from_config(specs, {"iolist_path": ""})
        eq(len(sections), 2, "the two mapping entries compile; the junk entry is a warning")
        eq(sections[0]["title"], "Docs")
        eq(sections[0]["roots"], [d], "a literal root passes; empty ${iolist} skips silently; ${nope} warns")
        ok(any("unknown placeholder ${nope}" in w for w in warnings), "the unknown placeholder is named")
        ok(any("Bad: bad regex" in w for w in warnings), "the bad include regex is attributed to its section")
        ok(any("not-a-mapping" in w for w in warnings), "the junk entry is reported")
        mapping = files_view.placeholder_map({"iolist_path": "X.xlsx"})
        eq(mapping["iolist"], "X.xlsx", "the iolist placeholder resolves from params")
        ok(mapping["config_project"], "the config_project placeholder always resolves")


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


def test_text_file_round_trip_preserves_style():
    with tempfile.TemporaryDirectory() as d:
        # CRLF + BOM file
        p1 = os.path.join(d, "a.yaml")
        with open(p1, "wb") as h:
            h.write(b"\xef\xbb\xbfkey: 1\r\nother: 2\r\n")
        info = files_view.read_text_file(p1)
        eq(info["text"], "key: 1\nother: 2\n", "the editor sees \\n-normalized text")
        eq((info["bom"], info["crlf"], info["truncated"]), (True, True, False))
        files_view.write_text_file(p1, info["text"].replace("1", "9"), info["bom"], info["crlf"])
        raw = open(p1, "rb").read()
        eq(raw, b"\xef\xbb\xbfkey: 9\r\nother: 2\r\n", "BOM + CRLF style survive the save")
        # plain LF, no BOM
        p2 = os.path.join(d, "b.txt")
        with open(p2, "wb") as h:
            h.write(b"one\ntwo\n")
        info2 = files_view.read_text_file(p2)
        eq((info2["bom"], info2["crlf"]), (False, False))
        files_view.write_text_file(p2, info2["text"] + "three\n", info2["bom"], info2["crlf"])
        eq(open(p2, "rb").read(), b"one\ntwo\nthree\n", "LF/no-BOM style survives")


def test_csv_edit_round_trip_keeps_dialect():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.csv")
        with open(p, "w", encoding="utf-8", newline="") as h:
            h.write("a;b\r\n1;x\r\n2;y\r\n")                    # semicolon dialect
        rows, delim = files_view.read_csv_rows_delim(p)
        eq(delim, ";", "the dialect is sniffed")
        eq(rows, [["a", "b"], ["1", "x"], ["2", "y"]])
        rows[1][1] = 'j,"son'                                    # needs quoting in the save
        files_view.write_csv_rows(p, rows, delim)
        raw = open(p, "rb").read()
        eq(raw, b'a;b\r\n1;"j,""son"\r\n2;y\r\n', "same delimiter + CRLF + proper re-quoting")
        rows2, delim2 = files_view.read_csv_rows_delim(p)
        eq((rows2[1][1], delim2), ('j,"son', ";"), "the edited cell reads back exactly")


def test_text_file_truncation_flag():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "big.log")
        with open(p, "wb") as h:
            h.write(b"x" * 100)
        eq(files_view.read_text_file(p, cap=99)["truncated"], True, "over the cap -> truncated")
        eq(files_view.read_text_file(p, cap=100)["truncated"], False, "exactly the cap -> whole")


def test_extedit_missing_path():
    ok_, msg = extedit.open_external(os.path.join(tempfile.gettempdir(), "no_such_file_xyz.csv"))
    eq(ok_, False, "a missing file -> (False, ...)")
    ok("not found" in msg, "the message says not found")
    ok2, _m = extedit.reveal("")
    eq(ok2, False, "reveal of an empty path -> False")


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_files", [
        ("compile_filters_and_matches", test_compile_filters_and_matches),
        ("viewer_kind", test_viewer_kind),
        ("sniff_delim", test_sniff_delim),
        ("read_csv_rows", test_read_csv_rows),
        ("populate_prunes_and_filters", test_populate_prunes_and_filters),
        ("sections_from_config", test_sections_from_config),
        ("read_xlsx", test_read_xlsx),
        ("text_file_round_trip_preserves_style", test_text_file_round_trip_preserves_style),
        ("csv_edit_round_trip_keeps_dialect", test_csv_edit_round_trip_keeps_dialect),
        ("text_file_truncation_flag", test_text_file_truncation_flag),
        ("extedit_missing_path", test_extedit_missing_path),
    ]))
