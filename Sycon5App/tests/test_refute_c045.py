"""C-045 refute round 1 (2026-10-26): the workspace scan attacked with odd card folders and broken files, the GUI's
runner with steps that cannot start or write nothing, a stop while idle, a workspace that vanished. What broke and
was fixed: `HilscherIOCard1` and `HilscherIOCard01` gave two cards numbered 1 (the table's second row would have
collided - one card now, the other folder a reported problem); a lowercase card folder was ignored while
`busfield.py` accepted it (case-insensitive now, like the folder system); a report whose first line is not a
verdict, or that cannot be read, showed as "built, not verified" (a status of its own now, red); a `.spj` whose
project folder lacks the saved XML showed as built and let Verify run into a crash (its own status, Verify disabled).
What held: a step that cannot start leaves no banner, no queue and no open log file; a step that writes nothing
leaves an empty log and its exit code; a stop while idle does nothing; a workspace folder gone after it was opened
empties the table with a warning."""
import os
import shutil
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
from sycon5 import workspace as ws  # noqa: E402
from test_workspace import fake_production, write  # noqa: E402

tk = pytest.importorskip("tkinter")
from sycon5 import gui  # noqa: E402


def test_odd_card_folders(tmp_path):
    root = fake_production(str(tmp_path))
    os.makedirs(os.path.join(root, "HilscherIOCard01"))
    os.makedirs(os.path.join(root, "hilscheriocard3", "SyconNetProjectInterface"))
    os.makedirs(os.path.join(root, "HilscherIOCard5x"))
    write(os.path.join(root, "HilscherIOCardX", "note.txt"), "x")
    w = ws.scan(root)
    assert [c.number for c in w.cards] == [1, 2, 3, 7]
    assert w.card(1).folder.endswith("HilscherIOCard1") and w.card(3).folder.endswith("hilscheriocard3")
    assert "two folders for card 1: HilscherIOCard1 and HilscherIOCard01 - HilscherIOCard01 ignored" in w.problems, w.problems
    assert "folder HilscherIOCard5x ignored: not HilscherIOCard<n>" in w.problems and "folder HilscherIOCardX ignored: not HilscherIOCard<n>" in w.problems


def test_a_report_that_is_not_a_verdict_or_cannot_be_read(tmp_path):
    root = fake_production(str(tmp_path))
    report = os.path.join(root, "HilscherIOCard1", "_PL_Logs", "HilscherPnCard_1.verification.txt")
    write(report, "Traceback (most recent call last):\n  boom\n")
    c = ws.scan(root).card(1)
    assert c.report and not c.report_ok and c.passed == -1 and c.status() == "verification report unreadable"
    os.remove(report)
    os.makedirs(report)                                             # a folder where the report should be
    c = ws.scan(root).card(1)
    assert not c.report_ok and c.status() == "verification report unreadable"


def test_a_project_file_without_its_folder(tmp_path):
    root = fake_production(str(tmp_path))
    shutil.rmtree(os.path.join(root, "HilscherIOCard1", "HilscherPnCard_1"))
    c = ws.scan(root).card(1)
    assert c.project and not c.project_dir_ok and c.status().startswith("project folder missing")
    assert ws.scan(root).card(2).project_dir_ok, "a card not built is not accused of a missing folder"


@pytest.fixture
def app(tmp_path):
    root = None
    for attempt in range(3):
        try:
            root = tk.Tk()
            break
        except tk.TclError as ex:
            if attempt == 2:
                pytest.skip("no display: %s" % ex)
            time.sleep(0.5)
    root.withdraw()
    a = gui.App(root, fake_production(str(tmp_path / "PRODUCTION")), settings_path=str(tmp_path / "gui.json"))
    yield a
    root.destroy()


def enabled(button):
    return "disabled" not in button.state()


def test_a_step_that_cannot_start_leaves_nothing_behind(app, tmp_path):
    c1 = app.workspace.card(1)
    cmd = ws.Command("ghost", [str(tmp_path / "no-such-program.exe")], str(tmp_path), os.path.join(c1.logs_dir, "ghost.log"))
    assert app.run(cmd, then=[cmd]) is False
    app.root.update()
    assert not app.runner.running and app.pending == [] and app.banner.winfo_manager() == ""
    assert "could not start" in app.text.get("1.0", "end-1c")
    assert enabled(app.b_build) and not enabled(app.b_stop)
    os.remove(cmd.log)                                              # the log file is closed, not held open


def test_a_step_that_writes_nothing_and_a_stop_while_idle(app, tmp_path):
    app.stop()                                                      # nothing running: a no-op
    assert app.pending == [] and not app.runner.running
    c1 = app.workspace.card(1)
    cmd = ws.Command("silent", [sys.executable, "-c", "pass"], str(tmp_path), os.path.join(c1.logs_dir, "silent.log"))
    assert app.run(cmd)
    t0 = time.time()
    while app.runner.running and time.time() - t0 < 30:
        app.root.update()
        time.sleep(0.05)
    app.root.update()
    assert open(cmd.log, encoding="utf-8").read() == "" and "silent: exit 0" in app.text.get("1.0", "end-1c")
    app.stop()
    assert not app.runner.stopped, "a stop after the end marks nothing"


def test_a_workspace_that_vanished(app, tmp_path):
    shutil.rmtree(app.workspace.root)
    app.reload()
    app.root.update()
    assert app.tree.get_children() == () and app.workspace.cards == []
    assert "not a folder" in app.text.get("1.0", "end-1c")
    assert not enabled(app.b_build) and not enabled(app.b_all) and enabled(app.b_open)


def test_a_row_with_a_broken_report_is_red(app, tmp_path):
    root = app.workspace.root
    write(os.path.join(root, "HilscherIOCard1", "_PL_Logs", "HilscherPnCard_1.verification.txt"), "garbage\n")
    app.reload()
    app.root.update()
    item = app.tree.item("1")
    assert item["tags"] == ["bad"] and item["values"][10] == "verification report unreadable"
    app.tree.selection_set("1")
    app.root.update()
    assert enabled(app.b_verify), "a re-verification is the way out"
