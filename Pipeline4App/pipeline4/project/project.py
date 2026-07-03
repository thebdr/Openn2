"""Folder-based projects for PL4 (GUI M6) - pure functions, no tkinter (the GUI wires these).

A PL4 project is a self-contained ROOT folder:

    <root>/
        config_project/      the project's OWN config (project_params.yaml + the CSVs + user_input/)
        Database/            the SSOT tables (one CSV-with-JSON-cells per table)
        Output/              the BuilderData + ProjectDocumentation tree

`config.use_project(root)` points the loaders, the Database folder, and the Output tree at <root>;
`use_builtin()` reverts to the app's bundled `config_project/` + `Shared/`. A project is identified by
`<root>/config_project/project_params.yaml` (the run params). New-project SCAFFOLDS the layout by copying
the builtin config_project (the operator then re-points the I/O List / C&E doc paths via the Files tab /
externally). Simpler than PL3's project.yaml-at-root model because PL4 keeps project_params.yaml inside
config_project/ and auto-saves its Database — there's no separate save step.
"""
from __future__ import annotations

import datetime
import os
import re
import shutil
import zipfile

from pipeline4.core import config
from pipeline4.project import state

CONFIG_DIRNAME = "config_project"
_PARAMS_REL = os.path.join(CONFIG_DIRNAME, "project_params.yaml")

# The creatable project types: (id, display label, available). The greyed RTX ones are declared for
# the roadmap - the dialog shows them disabled until their pipelines exist.
PROJECT_TYPES = (
    ("siemens_plc_safety", "Siemens PLC: Safety", True),
    ("rtx_cpci_sorter", "RTX cPCI: Sorter", False),
    ("rtx_cpci_induction", "RTX cPCI: Induction", False),
    ("rtx_cpci_plant", "RTX cPCI: Plant", False),
)
BACKUPS_KEPT_MAX = 20
BACKUPS_KEPT_DEFAULT = 5
DOCS_DIRNAME = "input_documents"          # where Import-documents copies the source docs (current/previous)

_NAME_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def validate_name(name: str) -> str:
    """'' when `name` is a usable project (folder) name, else the problem (for the dialog)."""
    text = str(name or "").strip()
    if not text:
        return "empty name"
    if _NAME_BAD.search(text):
        return 'a project name cannot contain  < > : " / \\ | ? *'
    if text.endswith(".") or text != text.strip():
        return "a project name cannot end with a dot or space"
    return ""


class ProjectConfigError(Exception):
    """A project's `config_project/` is INCOMPLETE vs the builtin canonical config set (it is missing files
    the app ships with). This is a DEVELOPMENT-phase code error - e.g. new-project scaffolding drift, or a
    project created before a config file was added - and must surface as a hard FAIL-AND-STOP, never be
    silently defaulted around (a shipped app would otherwise run on wrong/empty config). Carries the list
    of missing relative paths."""

    def __init__(self, root: str, missing: list):
        self.root, self.missing = root, list(missing)
        super().__init__(f"project config incomplete ({project_name(root)}): missing {', '.join(self.missing)}")


def is_project(root: str) -> bool:
    """True when `root` is a PL4 project folder (it carries config_project/project_params.yaml)."""
    return bool(root) and os.path.isfile(os.path.join(root, _PARAMS_REL))


def _config_file_set(config_dir: str) -> set:
    """Every file under a `config_project/` dir, as relative '/'-joined paths."""
    out = set()
    for dirpath, _dirs, files in os.walk(config_dir):
        for name in files:
            out.add(os.path.relpath(os.path.join(dirpath, name), config_dir).replace(os.sep, "/"))
    return out


def config_gaps(root: str) -> list:
    """The canonical config files (present in the BUILTIN config_project) that are MISSING from
    `<root>/config_project`. Empty -> complete. The bundled builtin is the single source of truth - there
    is NO baked manifest. Project-specific extra files are fine; only missing canonical files are gaps."""
    builtin = _config_file_set(config.builtin_config_project_dir())
    have = _config_file_set(os.path.join(root, CONFIG_DIRNAME))
    return sorted(builtin - have)


def assert_config_complete(root: str) -> None:
    """Raise `ProjectConfigError` when `<root>/config_project` is missing any canonical config file - the
    fail-loud guard so a scaffolding/drift bug is caught in development, not shipped."""
    missing = config_gaps(root)
    if missing:
        raise ProjectConfigError(root, missing)


def project_name(root: str) -> str:
    return os.path.basename(os.path.abspath(root)) if root else ""


def open_project(root: str) -> str:
    """Make `root` the active project: validate it, point `config` at it, record it recent/last-opened.
    Returns the absolute root. Raises FileNotFoundError when `root` isn't a project folder."""
    root = os.path.abspath(root)
    if not is_project(root):
        raise FileNotFoundError(os.path.join(root, _PARAMS_REL))
    assert_config_complete(root)            # fail loud + stop if the project's config is incomplete
    config.use_project(root)
    state.push_recent(root)
    return root


def close_project() -> None:
    """Revert to the builtin app config + Shared/ (no project open) and forget the auto-reopen target."""
    config.use_builtin()
    state.clear_last_opened()


def new_project(parent: str, name: str) -> str:
    """Scaffold a project at <parent>/<name>/ (its own config_project copied from the builtin + empty
    Database/ and Output/), open it, and return the root. Raises FileExistsError if it already exists."""
    root = os.path.abspath(os.path.join(parent, name))
    if os.path.exists(root):
        raise FileExistsError(root)
    os.makedirs(root)
    shutil.copytree(config.builtin_config_project_dir(), os.path.join(root, CONFIG_DIRNAME))
    for sub in ("Database", "Output"):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    assert_config_complete(root)            # the scaffold MUST be complete vs the builtin - fail loud if not
    return open_project(root)


def write_project_meta(root: str, name: str, types, multi_system: bool, backups_kept: int) -> None:
    """Insert/replace the `project:` section of `<root>/config_project/project_params.yaml`
    (round-tripping the template's comments). `backups_kept` is the € user-editable knob - each phase
    run backs the FULL project up (timestamped zip beside the project), pruned to this count."""
    from ruamel.yaml import YAML
    yaml = YAML()
    path = os.path.join(root, _PARAMS_REL)
    with open(path, encoding="utf-8") as handle:
        data = yaml.load(handle) or {}
    data["project"] = {
        "name": str(name),
        "types": [str(t) for t in types],
        "multi_system": bool(multi_system),
        "backups_kept": max(0, min(BACKUPS_KEPT_MAX, int(backups_kept))),
    }
    with open(path, "w", encoding="utf-8") as handle:
        yaml.dump(data, handle)


def load_project_meta(root: str) -> dict:
    """The `project:` section of a project's params ({} when absent - a pre-meta project still opens)."""
    try:
        params = config.load_params(os.path.join(root, _PARAMS_REL))
    except Exception:  # noqa: BLE001
        return {}
    meta = params.get("project")
    return dict(meta) if isinstance(meta, dict) else {}


def create_project(base_folder: str, name: str, types, multi_system: bool, backups_kept: int) -> str:
    """The New-project dialog's create: scaffold at `<base_folder>/<name>/<name>` (the DOUBLE nesting
    is deliberate - the outer folder is the project's own root where the timestamped backups live
    beside the live copy), write the `project:` meta, open it, return the root."""
    problem = validate_name(name)
    if problem:
        raise ValueError(problem)
    name = str(name).strip()
    root = new_project(os.path.join(base_folder, name), name)
    write_project_meta(root, name, types, multi_system, backups_kept)
    return root


# --- backups + archive (timestamped zips of the FULL project) ------------------------------------- #
def zip_folder(src_root: str, dest_zip: str) -> int:
    """Zip `src_root` (deflated) into `dest_zip`, arcnames rooted at the folder's basename (extracting
    yields `<name>/…`). Excel lock files (`~$*`) are skipped. Returns the file count."""
    src_root = os.path.abspath(src_root)
    base = os.path.dirname(src_root)
    count = 0
    os.makedirs(os.path.dirname(os.path.abspath(dest_zip)), exist_ok=True)
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as bundle:
        for dirpath, _dirs, files in os.walk(src_root):
            for filename in files:
                if filename.startswith("~$"):
                    continue
                full = os.path.join(dirpath, filename)
                bundle.write(full, os.path.relpath(full, base))
                count += 1
    return count


def backups_dir(root: str) -> str:
    """The backups folder: INSIDE the outer root, BESIDE the live project (the double-nested layout:
    `<outer>/<name>` is the project, `<outer>/backups` its history)."""
    return os.path.join(os.path.dirname(os.path.abspath(root)), "backups")


def make_backup(root: str, label: str, keep: int) -> str:
    """A timestamped zip of the FULL project into `backups_dir`, pruned oldest-first to `keep`.
    Returns the zip path ('' when keep<=0). The stamp sorts lexically, so pruning is by name."""
    keep = max(0, min(BACKUPS_KEPT_MAX, int(keep)))
    if keep <= 0:
        return ""
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = re.sub(r"[^\w-]+", "_", str(label or "run")).strip("_") or "run"
    dest = os.path.join(backups_dir(root), f"{project_name(root)}_{stamp}_{safe_label}.zip")
    if os.path.exists(dest):                       # two backups within one second: suffix, don't clobber
        dest = dest[:-4] + "_2.zip"
    zip_folder(root, dest)
    existing = sorted(f for f in os.listdir(backups_dir(root)) if f.lower().endswith(".zip"))
    for stale in existing[:max(0, len(existing) - keep)]:
        try:
            os.remove(os.path.join(backups_dir(root), stale))
        except OSError:
            pass
    return dest


def archive_project(root: str, dest_zip: str) -> int:
    """The Archive-project feature: one compressed zip of the current project at `dest_zip`.
    Returns the archived file count."""
    return zip_folder(root, dest_zip)


# --- import the source documents INTO the project (self-contained projects) ----------------------- #
def import_documents(root: str) -> list:
    """Copy every configured input document that lives OUTSIDE the project into
    `<root>/input_documents/current|previous/` and rewrite its path in project_params.yaml RELATIVE
    to config_project (so the whole project moves as one folder). A path already inside the project
    is only normalized to relative. Returns [(key, action, new_value)] for the status line.
    `root` must be the ACTIVE project (save_document_path writes the active params file)."""
    active = config.active_project()
    if not active or os.path.abspath(active) != os.path.abspath(root):
        raise ValueError("import_documents requires the target to be the ACTIVE project")
    params = config.load_params(os.path.join(root, _PARAMS_REL))
    config_dir = os.path.join(os.path.abspath(root), CONFIG_DIRNAME)
    actions = []
    for key in config.DOCUMENT_KEYS:
        source = str(params.get(key) or "").strip()
        if not source:
            continue
        source = os.path.abspath(source)
        if not os.path.isfile(source):
            actions.append((key, "missing", source))
            continue
        inside = os.path.commonpath([os.path.abspath(root)]) == \
            os.path.commonpath([os.path.abspath(root), source])
        if inside:
            target = source
            action = "relinked"
        else:
            sub = "previous" if key.endswith("_previous_path") else "current"
            target = os.path.join(root, DOCS_DIRNAME, sub, os.path.basename(source))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)
            action = "imported"
        relative = os.path.relpath(target, config_dir).replace(os.sep, "/")
        config.save_document_path(key, relative)
        actions.append((key, action, relative))
    return actions


def auto_reopen() -> str | None:
    """Re-point `config` at the last-opened project (launch-time). Returns the root, or None when there's
    no valid last project (then the builtin config stays active). Does NOT re-push recents."""
    root = state.last_opened()
    if root and is_project(root) and not config_gaps(root):   # an incomplete project is NOT auto-reopened
        config.use_project(os.path.abspath(root))
        return os.path.abspath(root)
    return None
