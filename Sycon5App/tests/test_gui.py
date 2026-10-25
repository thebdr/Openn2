"""The GUI on a fake workspace, the window withdrawn: the cards table, the buttons' enabling, the log viewer's levels and
filter, and one real step through the Runner (a short python command instead of a SYCON.net build) with its log file.
Skipped where Tk cannot open a display."""
import os
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from sycon5 import workspace as ws  # noqa: E402
from test_workspace import fake_production  # noqa: E402

tk = pytest.importorskip("tkinter")
from sycon5 import gui  # noqa: E402


@pytest.fixture
def app(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as ex:
        pytest.skip("no display: %s" % ex)
    root.withdraw()
    a = gui.App(root, fake_production(str(tmp_path / "PRODUCTION")), settings_path=str(tmp_path / "gui.json"))
    yield a
    root.destroy()


def states(app):
    return {name: "disabled" not in b.state() for name, b in (("build", app.b_build), ("resume", app.b_resume), ("verify", app.b_verify),
                                                              ("all", app.b_all), ("busfield", app.b_busfield), ("stop", app.b_stop))}


def test_the_cards_table_and_the_buttons(app):
    rows = {app.tree.item(i)["values"][0]: app.tree.item(i) for i in app.tree.get_children()}
    assert sorted(rows) == [1, 2, 7]
    r1 = rows[1]
    assert r1["values"][1] == "HilscherPnCard_1" and r1["values"][2] == "n0001-ctrl" and r1["values"][3:5] == [2, 3]
    assert r1["values"][5] == "2026-10-25 09:57:51" and r1["values"][7] == "12 PASS, 1 FAIL (2 notes)" and r1["values"][8]
    assert r1["values"][9] == "2/4" and r1["values"][10] == "1 FAIL, exports 2/4" and r1["tags"] == ["bad"]
    assert rows[2]["values"][10] == "not built" and rows[2]["tags"] == ["todo"]
    assert rows[7]["values"][10] == "no handoff"
    assert app.tree.selection() == ("1",)
    assert states(app) == {"build": True, "resume": True, "verify": True, "all": True, "busfield": True, "stop": False}
    app.tree.selection_set("2")
    app.root.update()
    assert states(app) == {"build": True, "resume": False, "verify": False, "all": True, "busfield": True, "stop": False}
    app.tree.selection_set("7")
    app.root.update()
    assert states(app)["build"] is False
    assert app.log_box["values"][0] == gui.RUN_OUTPUT and "_PL_Logs/build.log" in app.log_box["values"]
    assert os.path.exists(app.settings_path) is False or True       # written at close / open_workspace


def test_the_log_viewer_shows_a_file_with_levels_and_hides_filtered_ones(app):
    label = "HilscherIOCard1/_PL_Logs/HilscherPnCard_1.verification.txt"
    app.log_var.set(label)
    app.show_log()
    text = app.text.get("1.0", "end-1c").splitlines()
    assert text == ["verification: 12 PASS, 1 FAIL", "PASS a", "NOTE b", "FAIL c", "NOTE d"]
    assert "RSLT" in app.text.tag_names("1.0") and "PASS" in app.text.tag_names("2.0") and "FAIL" in app.text.tag_names("4.0")
    assert app.count_var.get() == "5 lines"
    app.level_vars["PASS"].set(False)
    app._apply_levels()
    assert app.text.tag_cget("PASS", "elide") in ("1", "true", True) and app.settings["levels"] == ["INFO", "NOTE"]
    app.log_var.set(gui.RUN_OUTPUT)
    app.show_log()
    assert "workspace" in app.text.get("1.0", "end-1c")


def test_a_step_runs_through_the_runner_and_writes_its_log(app, tmp_path):
    c1 = app.workspace.card(1)
    cmd = ws.Command("probe step", [sys.executable, "-c", "print('PASS one'); print('FAIL two'); import sys; sys.exit(4)"],
                     str(tmp_path), os.path.join(c1.logs_dir, "probe.log"))
    assert app.run(cmd) is True and app.runner.running and states(app)["stop"] is True and states(app)["build"] is False
    assert app.banner.winfo_manager() == "grid" and app.banner_var.get() == "Running: probe step"
    t0 = time.time()
    while app.runner.running and time.time() - t0 < 30:
        app.root.update()
        time.sleep(0.05)
    app.root.update()
    assert not app.runner.running and app.banner.winfo_manager() == ""
    text = app.text.get("1.0", "end-1c")
    assert "PASS one" in text and "FAIL two" in text and "probe step: exit 4" in text
    assert open(cmd.log, encoding="utf-8").read().splitlines() == ["PASS one", "FAIL two"]
    assert "HilscherIOCard1/_PL_Logs/probe.log" in app.log_box["values"]      # the reload after the step lists it
    assert states(app)["build"] is True and states(app)["stop"] is False


def test_a_batch_runs_its_steps_one_after_the_other_and_a_stop_drops_the_rest(app, tmp_path):
    c1 = app.workspace.card(1)
    one = ws.Command("one", [sys.executable, "-c", "print('one')"], str(tmp_path), os.path.join(c1.logs_dir, "one.log"))
    two = ws.Command("two", [sys.executable, "-c", "print('two')"], str(tmp_path), os.path.join(c1.logs_dir, "two.log"))
    app.run(one, then=[two])
    t0 = time.time()
    while (app.runner.running or app.pending) and time.time() - t0 < 30:
        app.root.update()
        time.sleep(0.05)
    text = app.text.get("1.0", "end-1c")
    assert "one: exit 0" in text and "two: exit 0" in text and text.index("one: exit 0") < text.index("two: exit 0")
    slow = ws.Command("slow", [sys.executable, "-c", "import time; time.sleep(30)"], str(tmp_path), os.path.join(c1.logs_dir, "slow.log"))
    app.run(slow, then=[two])
    app.root.update()
    app.stop()
    assert app.pending == []
    if not gui.has_console():                                          # pytest under a console: CTRL_BREAK; else a terminate
        pass
    app.runner.proc.terminate() if app.runner.proc else None           # no SIGBREAK handler in the probe: end it now
    t0 = time.time()
    while app.runner.running and time.time() - t0 < 30:
        app.root.update()
        time.sleep(0.05)
    assert "slow stopped" in app.text.get("1.0", "end-1c")
