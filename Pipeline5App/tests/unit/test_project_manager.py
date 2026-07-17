"""The Project Manager (project/project.py + project/state.py): is_project / open / close / new /
auto_reopen + the persisted recent/last-opened state (LOCALAPPDATA redirected to a temp dir)."""
import os
import shutil
import tempfile

from _harness import run, eq, ok
from pipeline5.project import project_manager as project
from pipeline5.project import app_state as state
from pipeline5 import config


def _make_project(root):
    """A MINIMAL project stub (only project_params.yaml) - `is_project` true, but config INCOMPLETE."""
    cp = os.path.join(root, "config_project", "shared")
    os.makedirs(cp, exist_ok=True)
    open(os.path.join(cp, "project_params.yaml"), "w").close()


def _make_complete_project(root):
    """A COMPLETE project: the builtin canonical config_project copied in (passes assert_config_complete)."""
    shutil.copytree(config.builtin_config_project_dir(), os.path.join(root, "config_project"))


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
        root = os.path.join(d, "Proj"); _make_complete_project(root)
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
        ok(os.path.isfile(os.path.join(root, "config_project", "shared", "project_params.yaml")), "config copied")
        ok(os.path.isdir(os.path.join(root, "Database")), "Database/ made")
        ok(os.path.isdir(os.path.join(root, "Output")), "Output/ made")
        eq(config.active_project(), os.path.abspath(root), "new_project opens it")
        eq(project.config_gaps(root), [], "a fresh project is COMPLETE vs the builtin (no missing files)")
    _with_temp_localappdata(body)


def test_incomplete_project_fails_loud():
    """A project missing a canonical config file must fail loud (assert + open) - the dev-phase guard so a
    scaffolding/drift bug is never silently defaulted around."""
    def body(d):
        config.use_builtin()
        root = os.path.join(d, "Drifted"); _make_complete_project(root)
        eq(project.config_gaps(root), [], "complete to start")
        os.remove(os.path.join(root, "config_project", "shared", "documents", "change_report_weights.csv"))
        eq(project.config_gaps(root), [os.path.join("shared", "documents/change_report_weights.csv")],
           "the removed file is reported missing")
        try:
            project.assert_config_complete(root)
            ok(False, "assert_config_complete must raise on an incomplete project")
        except project.ProjectConfigError as error:
            ok(os.path.join("shared", "documents/change_report_weights.csv") in error.missing,
               "the error carries the missing path")
        try:
            project.open_project(root)
            ok(False, "open_project must fail loud on an incomplete project")
        except project.ProjectConfigError:
            ok(True, "open_project raises ProjectConfigError - fail and stop")
        eq(config.active_project(), None, "config was NOT switched to the incomplete project")
        state.push_recent(root)                 # pretend it was the last-opened project
        config.use_builtin()
        eq(project.auto_reopen(), None, "auto_reopen SKIPS an incomplete project (no crash at launch)")
        eq(config.active_project(), None, "and stays on builtin")
    _with_temp_localappdata(body)


def test_auto_reopen():
    def body(d):
        config.use_builtin()
        eq(project.auto_reopen(), None, "no last_opened -> None (builtin stays)")
        root = os.path.join(d, "Proj"); _make_complete_project(root)
        state.push_recent(root)                 # records last_opened
        config.use_builtin()                    # simulate a fresh launch
        eq(project.auto_reopen(), os.path.abspath(root), "auto_reopen returns the last project")
        eq(config.active_project(), os.path.abspath(root), "and points config at it")
    _with_temp_localappdata(body)


def test_validate_name():
    eq(project.validate_name("Good Name-01"), "", "a normal name passes")
    ok(project.validate_name(""), "empty rejected")
    ok(project.validate_name("bad/name"), "path separator rejected")
    ok(project.validate_name('bad:"name'), "reserved characters rejected")
    ok(project.validate_name("trailing."), "trailing dot rejected")


def test_create_project_double_nested_with_meta():
    def body(d):
        config.use_builtin()
        root = project.create_project(d, "Nest", ["siemens_s7_safety"], False, 99)
        eq(root, os.path.abspath(os.path.join(d, "Nest", "Nest")),
           "the <base>/<name>/<name> DOUBLE-NESTED layout (backups live in the outer root)")
        meta = project.load_project_meta(root)
        eq(meta.get("name"), "Nest")
        eq(meta.get("types"), ["siemens_s7_safety"])
        eq(meta.get("multi_system"), False)
        eq(meta.get("backups_kept"), project.BACKUPS_KEPT_MAX, "backups_kept clamps to the 20 limit")
        eq(meta.get("schema_version"), project.SCHEMA_VERSION, "the meta format is stamped")
        ok(meta.get("created") and meta.get("app_version"), "created + app_version stamps present")
        eq(meta.get("notes"), "", "the € notes field starts empty")
        eq(config.active_project(), root, "created + opened")
        try:
            project.create_project(d, "bad/name", ["siemens_s7_safety"], False, 5)
            ok(False, "a bad name must raise")
        except ValueError:
            ok(True, "ValueError on a bad name")
    _with_temp_localappdata(body)


def test_backup_rotation_and_zip():
    def body(d):
        config.use_builtin()
        root = project.create_project(d, "Bk", ["siemens_s7_safety"], False, 5)
        open(os.path.join(root, "Database", "~$lock.xlsx"), "w").close()   # must be skipped
        first = project.make_backup(root, "300", keep=2)
        ok(first.endswith(".zip") and os.path.isfile(first), "the timestamped zip exists")
        eq(os.path.dirname(first), project.backups_dir(root), "backups live BESIDE the project")
        import zipfile
        with zipfile.ZipFile(first) as bundle:
            names = bundle.namelist()
        ok(all(n.startswith("Bk/") for n in names), "arcnames rooted at the project name")
        ok(not any("~$" in n for n in names), "Excel lock files skipped")
        project.make_backup(root, "400", keep=2)
        third = project.make_backup(root, "500", keep=2)
        left = sorted(os.listdir(project.backups_dir(root)))
        eq(len(left), 2, "pruned to keep=2")
        ok(os.path.basename(first) not in left and os.path.basename(third) in left,
           "the OLDEST backup is the one pruned")
        eq(project.make_backup(root, "x", keep=0), "", "keep=0 -> backups off")
    _with_temp_localappdata(body)


def test_archive_and_import_documents():
    def body(d):
        config.use_builtin()
        root = project.create_project(d, "Self", ["siemens_s7_safety"], False, 5)
        src_a = os.path.join(d, "docs_a"); os.makedirs(src_a)
        src_b = os.path.join(d, "docs_b"); os.makedirs(src_b)
        cur = os.path.join(src_a, "io.xlsx")
        prev = os.path.join(src_b, "io.xlsx")           # SAME basename - the current/previous split
        with open(cur, "wb") as h:
            h.write(b"CUR")
        with open(prev, "wb") as h:
            h.write(b"PREV")
        config.save_document_path("iolist_path", cur)
        config.save_document_path("iolist_previous_path", prev)
        actions = {k: (a, v) for k, a, v in project.import_documents(root)}
        eq(actions["iolist_path"], ("imported", "../../input_documents/current/io.xlsx"),
           "copied + rewritten RELATIVE to config_project")
        eq(actions["iolist_previous_path"], ("imported", "../../input_documents/previous/io.xlsx"),
           "the previous revision lands in its own subfolder (no basename collision)")
        params = config.load_params()
        with open(params["iolist_path"], "rb") as h:
            eq(h.read(), b"CUR", "the relative path resolves INSIDE the project to the right file")
        with open(params["iolist_previous_path"], "rb") as h:
            eq(h.read(), b"PREV")
        actions2 = {k: (a, v) for k, a, v in project.import_documents(root)}
        eq(actions2["iolist_path"][0], "up-to-date", "a second run with an unchanged source only normalizes")
        dest = os.path.join(d, "arch.zip")
        count = project.archive_project(root, dest)
        ok(count >= 5 and os.path.isfile(dest),   # the regrouped scaffold: the shared tier + the imported docs
           "Archive Project writes one compressed zip")
        project.close_project()
        try:
            project.import_documents(root)
            ok(False, "import must refuse a non-active project")
        except ValueError:
            ok(True, "the active-project guard holds")
    _with_temp_localappdata(body)


def test_stale_import_detection_and_refresh():
    """The stale-import cycle: import records {source, mtime}; editing the ORIGINAL flags the key in
    stale_imports (the GUI open-time WARN); the next Import REFRESHES the project copy from it."""
    def body(d):
        config.use_builtin()
        root = project.create_project(d, "Stale", ["siemens_s7_safety"], False, 5)
        src = os.path.join(d, "ext"); os.makedirs(src)
        doc = os.path.join(src, "io.xlsx")
        with open(doc, "wb") as h:
            h.write(b"V1")
        config.save_document_path("iolist_path", doc)
        actions = {k: a for k, a, _v in project.import_documents(root)}
        eq(actions["iolist_path"], "imported", "first run copies the external doc")
        rec = project.load_project_meta(root).get("imported", {}).get("iolist_path", {})
        eq(rec.get("source"), os.path.abspath(doc), "the import remembers WHERE the copy came from")
        eq(project.stale_imports(root), [], "an untouched source is not stale")
        with open(doc, "wb") as h:
            h.write(b"V2-NEWER")
        newer = os.path.getmtime(doc) + 10
        os.utime(doc, (newer, newer))               # simulate the original edited AFTER the import
        eq(project.stale_imports(root), [("iolist_path", os.path.abspath(doc))],
           "an edited original is flagged stale")
        actions2 = {k: a for k, a, _v in project.import_documents(root)}
        eq(actions2["iolist_path"], "refreshed", "the next import refreshes the copy from the source")
        with open(config.load_params()["iolist_path"], "rb") as h:
            eq(h.read(), b"V2-NEWER", "the project copy now carries the new content")
        eq(project.stale_imports(root), [], "refreshed -> no longer stale")
    _with_temp_localappdata(body)


def test_open_rejects_unknown_and_pl4_system_ids():
    """Step 5: open_project CONSUMES the meta types - an id the registry can't resolve refuses the
    open with a pointed error, and the PL4-era ids get the 'this is a PL4 project' message. auto_reopen
    skips such a project instead of crashing the launch."""
    def body(d):
        config.use_builtin()
        root = project.create_project(d, "Meta", ["siemens_s7_safety"], False, 5)
        project.close_project()
        project._update_meta(root, {"types": ["no_such_system"]})
        try:
            project.open_project(root)
            ok(False, "an unknown system id must refuse the open")
        except project.UnknownSystemError as error:
            eq(error.sid, "no_such_system", "the error names the offending id")
            eq(error.is_pl4, False, "a typo'd id is not flagged as PL4")
        eq(config.active_project(), None, "config was NOT switched")
        project._update_meta(root, {"types": ["siemens_plc_safety"]})
        try:
            project.open_project(root)
            ok(False, "a PL4-era id must refuse the open")
        except project.UnknownSystemError as error:
            ok(error.is_pl4, "the PL4-era id is recognized")
            ok("PIPELINE4" in str(error), "the message says it is a PL4 project")
        state.push_recent(root)                 # pretend it was the last-opened project
        config.use_builtin()
        eq(project.auto_reopen(), None, "auto_reopen SKIPS a project with an unknown system id")
        project._update_meta(root, {"types": ["siemens_s7_safety"]})
        ok(project.open_project(root), "the fixed meta opens again")
        eq([s.id for s in project.project_systems(root)], ["siemens_s7_safety"],
           "project_systems resolves the meta types to System objects")
    _with_temp_localappdata(body)


def test_multi_system_projects_namespace_database_and_output():
    """Step 5: a project declaring MORE than one system routes Database/<sid> + Output/<sid> per the
    ACTIVE system; a single-system project keeps the FLAT layout (the OP4 path contract)."""
    def body(d):
        from pipeline5.systems import catalog
        from pipeline5.systems.system_contract import System
        config.use_builtin()
        root = project.create_project(d, "Multi", ["siemens_s7_safety"], True, 5)
        eq(os.path.basename(config.database_dir()), "Database",
           "ONE declared type -> flat Database/ even with the multi_system dialog flag on")
        siemens = catalog.by_id("siemens_s7_safety")
        stub = System(id="stub_second_system", name_key="sys_stub", taxonomy=("T",))
        original_all = catalog.ALL_SYSTEMS
        catalog.ALL_SYSTEMS = original_all + (stub,)
        try:
            project._update_meta(root, {"types": ["siemens_s7_safety", "stub_second_system"]})
            project.open_project(root)
            config.use_system(siemens)
            eq(config.database_dir(), os.path.join(root, "Database", "siemens_s7_safety"),
               ">1 type -> Database/<active sid>")
            ok(config.output_root().endswith(os.path.join("Output", "siemens_s7_safety")),
               ">1 type -> Output/<active sid>")
            config.use_system(stub)
            eq(os.path.basename(config.database_dir()), "stub_second_system",
               "switching the active system switches the tree")
        finally:
            catalog.ALL_SYSTEMS = original_all
            project.close_project()
            config.use_system(siemens)
        eq(os.path.basename(config.database_dir()), "Database",
           "close resets to the FLAT builtin Database/ (the /<sid> level is gone)")
    _with_temp_localappdata(body)


def test_restore_backup_and_save_as():
    def body(d):
        config.use_builtin()
        root = project.create_project(d, "Rst", ["siemens_s7_safety"], False, 5)
        marker = os.path.join(root, "Database", "marker.txt")
        with open(marker, "w") as h:
            h.write("SNAPSHOT")
        zip_path = project.make_backup(root, "300", keep=5)
        with open(marker, "w") as h:
            h.write("CHANGED-AFTER-BACKUP")
        restored = project.restore_backup(root, zip_path)
        ok(os.path.abspath(restored) != os.path.abspath(root), "restore NEVER lands on the live project")
        eq(os.path.dirname(os.path.dirname(restored)), os.path.dirname(root),
           "the restore folder is a SIBLING inside the outer root")
        ok(project.is_project(restored), "the restored folder is a full project")
        with open(os.path.join(restored, "Database", "marker.txt")) as h:
            eq(h.read(), "SNAPSHOT", "the restored copy carries the BACKED-UP state")
        with open(marker) as h:
            eq(h.read(), "CHANGED-AFTER-BACKUP", "the live project is untouched")
        try:
            project.restore_backup(root, zip_path)
            ok(False, "a second restore of the same zip must not clobber the first")
        except FileExistsError:
            ok(True, "an existing restore folder raises FileExistsError")
        copy = project.save_as(root, d, "RstCopy")
        eq(copy, os.path.abspath(os.path.join(d, "RstCopy", "RstCopy")),
           "save-as lands at the double-nested <base>/<name>/<name>")
        eq(project.load_project_meta(copy).get("name"), "RstCopy", "the meta name is restamped")
        eq(project.load_project_meta(copy).get("backups_kept"), 5, "the other meta knobs survive the copy")
        eq(config.active_project(), copy, "save-as switches to the copy")
        ok(not os.path.isdir(project.backups_dir(copy)), "the backup zips stay with the ORIGINAL")
    _with_temp_localappdata(body)


if __name__ == "__main__":
    import sys
    sys.exit(run("project", [
        ("is_project_and_name", test_is_project_and_name),
        ("state_roundtrip", test_state_roundtrip),
        ("open_close_routes_config", test_open_close_routes_config),
        ("open_nonproject_raises", test_open_nonproject_raises),
        ("new_project_scaffolds", test_new_project_scaffolds),
        ("incomplete_project_fails_loud", test_incomplete_project_fails_loud),
        ("auto_reopen", test_auto_reopen),
        ("validate_name", test_validate_name),
        ("create_project_double_nested_with_meta", test_create_project_double_nested_with_meta),
        ("backup_rotation_and_zip", test_backup_rotation_and_zip),
        ("archive_and_import_documents", test_archive_and_import_documents),
        ("stale_import_detection_and_refresh", test_stale_import_detection_and_refresh),
        ("open_rejects_unknown_and_pl4_system_ids", test_open_rejects_unknown_and_pl4_system_ids),
        ("multi_system_projects_namespace_database_and_output", test_multi_system_projects_namespace_database_and_output),
        ("restore_backup_and_save_as", test_restore_backup_and_save_as),
    ]))
