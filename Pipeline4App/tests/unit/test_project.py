"""The Project Manager (project/project.py + project/state.py): is_project / open / close / new /
auto_reopen + the persisted recent/last-opened state (LOCALAPPDATA redirected to a temp dir)."""
import os
import tempfile

from _harness import run, eq, ok
from pipeline4.core import config
from pipeline4.project import project, state


def _make_project(root):
    cp = os.path.join(root, "config_project")
    os.makedirs(cp, exist_ok=True)
    open(os.path.join(cp, "project_params.yaml"), "w").close()


def _with_temp_localappdata(fn):
    """Run fn(d) with LOCALAPPDATA pointed at a temp dir + config reset to builtin after."""
    with tempfile.TemporaryDirectory() as d:
        old = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = d
        try:
            fn(d)
        finally:
            config.use_builtin()
            if old is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = old


def test_is_project_and_name():
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "MyProj")
        eq(project.is_project(root), False, "no config_project/project_params.yaml -> not a project")
        _make_project(root)
        ok(project.is_project(root), "scaffolded folder is a project")
        eq(project.project_name(root), "MyProj", "name = folder basename")


def test_state_roundtrip():
    def body(d):
        eq(state.recent_projects(), [], "fresh state -> no recents")
        eq(state.last_opened(), None, "fresh -> no last")
        p1 = os.path.join(d, "p1"); os.makedirs(p1)
        p2 = os.path.join(d, "p2"); os.makedirs(p2)
        state.push_recent(p1); state.push_recent(p2)
        eq([os.path.basename(r) for r in state.recent_projects()], ["p2", "p1"], "most-recent first")
        eq(os.path.basename(state.last_opened()), "p2", "last_opened = most recent")
        state.push_recent(p1)
        eq([os.path.basename(r) for r in state.recent_projects()], ["p1", "p2"], "re-push dedups + reorders")
        state.clear_last_opened()
        eq(state.last_opened(), None, "cleared")
        eq(len(state.recent_projects()), 2, "clear_last_opened keeps recents")
        state.set_projects_root(p1)
        eq(state.projects_root(), os.path.abspath(p1), "projects_root persisted")
    _with_temp_localappdata(body)


def test_open_close_routes_config():
    def body(d):
        root = os.path.join(d, "Proj"); _make_project(root)
        project.open_project(root)
        eq(config.active_project(), os.path.abspath(root), "open -> config points at the project")
        ok(os.path.abspath(root) in [os.path.abspath(r) for r in state.recent_projects()], "recorded recent")
        project.close_project()
        eq(config.active_project(), None, "close -> builtin")
        eq(state.last_opened(), None, "close clears last_opened")
    _with_temp_localappdata(body)


def test_open_nonproject_raises():
    with tempfile.TemporaryDirectory() as d:
        try:
            project.open_project(os.path.join(d, "nope"))
            ok(False, "opening a non-project should raise")
        except FileNotFoundError:
            ok(True, "opening a non-project raises FileNotFoundError")
        finally:
            config.use_builtin()


def test_new_project_scaffolds():
    def body(d):
        config.use_builtin()
        root = project.new_project(d, "Fresh")
        ok(os.path.isfile(os.path.join(root, "config_project", "project_params.yaml")), "config copied")
        ok(os.path.isdir(os.path.join(root, "Database")), "Database/ made")
        ok(os.path.isdir(os.path.join(root, "Output")), "Output/ made")
        eq(config.active_project(), os.path.abspath(root), "new_project opens it")
    _with_temp_localappdata(body)


def test_auto_reopen():
    def body(d):
        config.use_builtin()
        eq(project.auto_reopen(), None, "no last_opened -> None (builtin stays)")
        root = os.path.join(d, "Proj"); _make_project(root)
        state.push_recent(root)                 # records last_opened
        config.use_builtin()                    # simulate a fresh launch
        eq(project.auto_reopen(), os.path.abspath(root), "auto_reopen returns the last project")
        eq(config.active_project(), os.path.abspath(root), "and points config at it")
    _with_temp_localappdata(body)


if __name__ == "__main__":
    import sys
    sys.exit(run("project", [
        ("is_project_and_name", test_is_project_and_name),
        ("state_roundtrip", test_state_roundtrip),
        ("open_close_routes_config", test_open_close_routes_config),
        ("open_nonproject_raises", test_open_nonproject_raises),
        ("new_project_scaffolds", test_new_project_scaffolds),
        ("auto_reopen", test_auto_reopen),
    ]))
