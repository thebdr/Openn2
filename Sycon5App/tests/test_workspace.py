"""The GUI's workspace scan on a fake PRODUCTION folder (no GUI, no SYCON.net): the cards and their state, the
command lines of the steps, the log viewer's levels."""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from sycon5 import workspace  # noqa: E402

HEADER = "#!openn\n#! kind: %s\n#! schema: 1\n#! producer: test\n#! generated: 2026-10-25T09:57:51Z\n#! source: list.xlsx\n#!end\n"


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def fake_production(root):
    card1 = os.path.join(root, "HilscherIOCard1")
    h = os.path.join(card1, "SyconNetProjectInterface")
    write(os.path.join(h, "SyconStations.csv"), HEADER % "hw/sycon-stations" + "# Role,Station Name,Catalog Kind\n"
          "controller,n0001-ctrl,master\nslave,n0002-a,slave\nslave,n0003-b,slave\n")
    write(os.path.join(h, "SyconModules.csv"), HEADER % "hw/sycon-modules" + "# Station Name,Slot\n"
          "n0002-a,1\nn0002-a,2\nn0003-b,1\n")
    write(os.path.join(card1, "HilscherPnCard_1.spj"), "spj")
    write(os.path.join(card1, "HilscherPnCard_1", "_S129", "SYCON_net.xml"), "<xml/>")
    write(os.path.join(card1, "_PL_Logs", "HilscherPnCard_1.verification.txt"),
          "verification: 12 PASS, 1 FAIL\nPASS a\nNOTE b\nFAIL c\nNOTE d\n")
    write(os.path.join(card1, "_PL_Logs", "build.log"), "10:00:00 cloned\n")
    write(os.path.join(card1, "HilscherIO.xml"), "<x/>")
    write(os.path.join(card1, "nWid", "config.nxd"), "nxd")
    # card 2: a handoff only
    h2 = os.path.join(root, "HilscherIOCard2", "SyconNetProjectInterface")
    write(os.path.join(h2, "SyconStations.csv"), HEADER % "hw/sycon-stations" + "# Role,Station Name\ncontroller,n0001-c2\n")
    # a stray folder and an empty card folder
    os.makedirs(os.path.join(root, "IODriver"), exist_ok=True)
    os.makedirs(os.path.join(root, "HilscherIOCard7"), exist_ok=True)
    write(os.path.join(root, "IODriver", "BusField.csv"), "#!openn\n#!end\n")
    write(os.path.join(root, "_PL_Logs", "build.log"), "10:00:00 export\n")
    return root


def test_scan_reads_the_cards_in_order(tmp_path):
    w = workspace.scan(fake_production(str(tmp_path)))
    assert [c.number for c in w.cards] == [1, 2, 7]
    c1 = w.card(1)
    assert c1.name == "HilscherPnCard_1" and c1.controller == "n0001-ctrl"
    assert (c1.stations, c1.modules) == (2, 3)
    assert c1.headers["generated"] == "2026-10-25T09:57:51Z" and c1.headers["source"] == "list.xlsx"
    assert c1.project.endswith("HilscherPnCard_1.spj") and c1.project_time > 0
    assert (c1.passed, c1.failed, c1.notes) == (12, 1, 2)
    assert c1.exports_present == 2 and c1.exports["HilscherIO.xml"] > 0 and c1.exports[os.path.join("nWid", "config_nwid.nxd")] == 0
    assert [os.path.basename(p) for p in c1.logs] and all(p.endswith((".log", ".txt")) for p in c1.logs)
    assert c1.verdict == "12 PASS, 1 FAIL (2 notes)" and c1.status() == "1 FAIL, exports 2/4"
    c2 = w.card(2)
    assert c2.handoff and c2.stations == 0 and c2.status() == "not built"
    assert w.card(7).status() == "no handoff"
    assert w.busfield.endswith("BusField.csv") and w.busfield_time > 0
    assert [os.path.basename(p) for p in w.logs] == ["build.log"]
    labels = [lab for lab, _p in w.log_files()]
    assert labels[0] == "_PL_Logs/build.log" and "HilscherIOCard1/_PL_Logs/HilscherPnCard_1.verification.txt" in labels
    assert not w.problems


def test_scan_of_a_report_older_than_the_project(tmp_path):
    root = fake_production(str(tmp_path))
    old = time.time() - 3600
    report = os.path.join(root, "HilscherIOCard1", "_PL_Logs", "HilscherPnCard_1.verification.txt")
    os.utime(report, (old, old))
    c1 = workspace.scan(root).card(1)
    assert c1.status() == "1 FAIL, verified before the last save, exports 2/4"
    for rel in workspace.EXPORTS:
        write(os.path.join(root, "HilscherIOCard1", rel), "x")
    write(report, "verification: 3 PASS, 0 FAIL\n")
    assert workspace.scan(root).card(1).status() == "complete"


def test_scan_of_an_empty_or_missing_folder(tmp_path):
    w = workspace.scan(str(tmp_path))
    assert w.cards == [] and w.problems == ["no HilscherIOCard<n> folder in %s" % tmp_path]
    w = workspace.scan(str(tmp_path / "nope"))
    assert w.problems[0].startswith("not a folder")


def test_scan_flags_a_bad_handoff(tmp_path):
    h = os.path.join(str(tmp_path), "HilscherIOCard1", "SyconNetProjectInterface")
    write(os.path.join(h, "SyconStations.csv"), HEADER % "hw/sycon-modules" + "# Role\nslave,a\n")
    c = workspace.scan(str(tmp_path)).card(1)
    assert c.problems == ["SyconStations.csv is not hw/sycon-stations", "0 controller rows"]
    assert c.status() == "handoff: SyconStations.csv is not hw/sycon-stations"


def test_the_commands_of_the_steps(tmp_path):
    root = fake_production(str(tmp_path))
    w = workspace.scan(root)
    c1 = w.card(1)
    b = workspace.build_command(c1)
    assert b.argv[0] == (workspace.VENV_PYTHON if os.path.exists(workspace.VENV_PYTHON) else sys.executable)
    assert b.drives_sycon and b.cwd == workspace.APP and b.argv[1] == "-I" and b.argv[2].endswith("build_from_handoff.py")
    assert b.argv[b.argv.index("--handoff") + 1] == c1.handoff and b.argv[b.argv.index("--out") + 1] == c1.project_path
    assert b.argv[b.argv.index("--report") + 1] == c1.report_path and "--resume" not in b.argv
    assert b.log == os.path.join(c1.logs_dir, "build.log") and b.label == "build card 1"
    r = workspace.build_command(c1, resume=True)
    assert r.argv[-1] == "--resume" and r.log.endswith("build_resume.log") and "(resume)" in r.label
    v = workspace.verify_command(c1)
    assert not v.drives_sycon and v.argv[2].endswith("verify_saved.py") and v.log.endswith(os.path.join("_PL_Logs", "verify.log"))
    f = workspace.busfield_command(root)
    assert f.argv[2].endswith("busfield.py") and f.argv[-1] == root and f.log == os.path.join(root, "_PL_Logs", "busfield.log")
    e = workspace.export_command(r"Z:\list.xlsx", root)
    assert e.cwd == workspace.PL5 and "-m" in e.argv and e.argv[-1] == root and e.log.endswith("export.log")
    assert e.label == "export the handoff of list.xlsx"
    workspace.note_summary(root, "card 1: exit 0")
    lines = open(os.path.join(root, "_PL_Logs", "build.log"), encoding="utf-8").read().splitlines()
    assert lines[-1].endswith(" card 1: exit 0") and len(lines[-1].split(" ", 1)[0]) == 8


def test_the_levels_of_the_log_lines():
    assert workspace.level_of("PASS station x exists") == "PASS"
    assert workspace.level_of("FAIL station x: 3 modules") == "FAIL"
    assert workspace.level_of("NOTE station x: order number pattern") == "NOTE"
    assert workspace.level_of("verification: 823 PASS, 0 FAIL") == "RSLT"
    assert workspace.level_of("11:55:18 card 1: exit 0 - verification: 823 PASS, 0 FAIL") == "RSLT"
    assert workspace.level_of("SYCON handoff card 1 (HilscherPnCard_1): 63 stations") == "RSLT"
    assert workspace.level_of("Traceback (most recent call last):") == "ERRR"
    assert workspace.level_of("sycon5.session.SyconError: SYCON.net is already running") == "ERRR"
    assert workspace.level_of("10:00:00 Warning dialog answered Yes") == "WARN"
    assert workspace.level_of("10:00:00 cloned 4 x n0002") == "INFO"
    assert set(workspace.LEVELS) >= {"PASS", "FAIL", "NOTE", "RSLT", "ERRR", "WARN", "INFO"}


if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        test_scan_reads_the_cards_in_order(Path(d) / "a")
        test_scan_of_a_report_older_than_the_project(Path(d) / "b")
        test_scan_of_an_empty_or_missing_folder(Path(d) / "c")
        test_scan_flags_a_bad_handoff(Path(d) / "d")
        test_the_commands_of_the_steps(Path(d) / "e")
    test_the_levels_of_the_log_lines()
    print("ok")
