"""Project Manager - the pure project module + the persisted state. Data-independent green gate:
creates projects in a temp dir (its own config_project/ copied from the app), and round-trips
state.json under a temp LOCALAPPDATA. No real I/O List / C&E needed."""
import os
import tempfile

from _harness import run, ok, eq
from pipeline3.core import config
from pipeline3.project import project, state


def test_new_project_layout():
    with tempfile.TemporaryDirectory() as d:
        folder = os.path.join(d, "Proj1")
        path = project.new_project(folder)
        ok(os.path.exists(path), "project.yaml written")
        for sub in ("Input", "Output", "user_input", "config_project"):
            ok(os.path.isdir(os.path.join(folder, sub)), f"{sub}/ created")
        ok(os.path.isdir(os.path.join(folder, "config_project", "input_docs")),
           "project carries its OWN config CSVs (input_docs copied)")
        doc = project.load_doc(path)
        eq(str(doc.get("output_dir")), "Output", "output_dir defaults to Output (relative -> portable)")
        for key in ("io_list", "ce"):
            if key in doc and "path" in doc[key]:
                eq(str(doc[key]["path"]), "", f"{key} path blanked")


def test_copy_inputs_rewrites_path():
    with tempfile.TemporaryDirectory() as d:
        folder = os.path.join(d, "Proj2")
        project.new_project(folder)
        src = os.path.join(d, "MyIOList.xlsx")          # a fake workbook outside the project
        with open(src, "wb") as f:
            f.write(b"PK\x03\x04 fake-xlsx-bytes")
        doc = project.load_doc(project.project_yaml(folder))
        doc.setdefault("io_list", {})["path"] = src
        project.save_project(doc, project.project_yaml(folder), copy_inputs=True)
        ok(os.path.isfile(os.path.join(folder, "Input", "MyIOList.xlsx")), "workbook copied into Input/")
        eq(str(project.load_doc(project.project_yaml(folder))["io_list"]["path"]), "Input/MyIOList.xlsx",
           "path rewritten to Input/<name>")


def test_refresh_inputs_recopies_source():
    """Designer 'live source': the project remembers the original `source`; every run re-copies its
    latest bytes onto the Input/ copy while `path` (Input/<name>) is untouched."""
    with tempfile.TemporaryDirectory() as d:
        folder = os.path.join(d, "ProjLive")
        project.new_project(folder)
        src = os.path.join(d, "Live.xlsx")
        with open(src, "wb") as f:
            f.write(b"v1-original")
        doc = project.load_doc(project.project_yaml(folder))
        node = doc.setdefault("io_list", {})
        node["path"] = src
        node["source"] = src                                       # remember the live source
        project.save_project(doc, project.project_yaml(folder), copy_inputs=True)
        doc2 = project.load_doc(project.project_yaml(folder))
        eq(str(doc2["io_list"]["path"]), "Input/Live.xlsx", "path rewritten to the Input/ copy")
        eq(str(doc2["io_list"]["source"]), src, "source preserved across copy_inputs (never rewritten)")
        with open(src, "wb") as f:                                 # the user edits the live source
            f.write(b"v2-edited")
        names = project.refresh_inputs(doc2, folder)
        eq(names, ["Live.xlsx"], "refresh reports the re-copied input")
        with open(os.path.join(folder, "Input", "Live.xlsx"), "rb") as f:
            eq(f.read(), b"v2-edited", "Input/ copy now holds the latest source bytes")
        eq(str(doc2["io_list"]["path"]), "Input/Live.xlsx", "path unchanged by refresh")


def test_default_doc_bases():
    main_doc = project.default_doc()                               # main: input paths blanked
    for key in ("io_list", "ce"):
        if key in main_doc and isinstance(main_doc[key], dict) and "path" in main_doc[key]:
            eq(str(main_doc[key]["path"]), "", f"{key} path blanked for main")
    des = project.default_doc(config.DESIGNER_PARAMS_FILE, keep_inputs=True)   # designer: keep + source
    for key in ("io_list", "ce"):
        node = des.get(key)
        if isinstance(node, dict) and str(node.get("path") or "").strip():
            eq(str(node.get("source")), str(node["path"]), f"{key} source == seeded path (live source)")


def test_open_missing_raises():
    with tempfile.TemporaryDirectory() as d:
        try:
            project.open_project(os.path.join(d, "nope"))
            ok(False, "open_project should raise on a missing project")
        except FileNotFoundError:
            ok(True, "open_project raises FileNotFoundError")


def test_config_paths_resolve_under_project():
    with tempfile.TemporaryDirectory() as d:
        folder = os.path.join(d, "Proj3")
        path = project.new_project(folder)
        eq(project.config_root(path), os.path.join(folder, "config_project"))
        eq(project.user_input_root(path), os.path.join(folder, "user_input"))
        eq(project.project_name(path), "Proj3")


def test_state_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        old = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = d                  # redirect state.json to the temp dir
        try:
            eq(state.projects_root(), config.PROJECTS_DIR, "root defaults to config.PROJECTS_DIR when unset")
            root = os.path.join(d, "Projects")
            state.set_projects_root(root)
            eq(state.projects_root(), os.path.abspath(root), "persisted projects root")
            p1 = os.path.join(d, "P1", "project.yaml")
            p2 = os.path.join(d, "P2", "project.yaml")
            for p in (p1, p2):
                os.makedirs(os.path.dirname(p))
                open(p, "w").close()
            state.push_recent(p1)
            state.push_recent(p2)
            eq([os.path.basename(os.path.dirname(x)) for x in state.recent_projects()], ["P2", "P1"],
               "recent is most-recent-first")
            eq(state.last_opened(), os.path.abspath(p2), "last_opened tracks the latest push")
            state.clear_last_opened()
            eq(state.last_opened(), None, "clear_last_opened forgets the auto-reopen target")
            eq(len(state.recent_projects()), 2, "recents survive clear_last_opened")
        finally:
            if old is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = old


def test_use_project_routes_config():
    with tempfile.TemporaryDirectory() as d:
        folder = os.path.join(d, "ProjC")
        project.new_project(folder)
        try:
            config.use_project(folder)
            eq(config.config_project_dir(), os.path.join(folder, "config_project"), "config base -> project")
            eq(config.input_docs_dir(), os.path.join(folder, "config_project", "input_docs"))
            eq(config.diagnosis_dir(), os.path.join(folder, "config_project", "diagnosis"))
            eq(config.user_input_dir(), os.path.join(folder, "user_input"), "treatments -> project")
            ok(len(config.load_column_map("IoList")) > 0, "a loader now reads the project's OWN copied config")
            eq(config.active_project(), folder)
        finally:
            config.use_builtin()
        eq(config.config_project_dir(), config.CONFIG_PROJECT, "reverts to the app config")
        eq(config.user_input_dir(), config.USER_INPUT, "treatments revert to the app default")
        eq(config.active_project(), None)


if __name__ == "__main__":
    raise SystemExit(run("project", [
        ("new_project_layout", test_new_project_layout),
        ("copy_inputs_rewrites_path", test_copy_inputs_rewrites_path),
        ("refresh_inputs_recopies_source", test_refresh_inputs_recopies_source),
        ("default_doc_bases", test_default_doc_bases),
        ("open_missing_raises", test_open_missing_raises),
        ("config_paths_resolve_under_project", test_config_paths_resolve_under_project),
        ("state_roundtrip", test_state_roundtrip),
        ("use_project_routes_config", test_use_project_routes_config),
    ]))
