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

from pipeline5 import config
from pipeline5.project import app_state as state

CONFIG_DIRNAME = "config_project"
_PARAMS_REL = os.path.join(CONFIG_DIRNAME, "shared", "project_params.yaml")

# The creatable project types now DERIVE from the systems registry (pipeline5.systems.catalog -
# availability = membership, C-021); PL4's hardcoded PROJECT_TYPES tuple is retired. Project meta
# written from here on carries the TAXONOMY ids (siemens_s7_safety, intervalzero_rtx_*).
BACKUPS_KEPT_MAX = 20
BACKUPS_KEPT_DEFAULT = 5
DOCS_DIRNAME = "input_documents"          # where Import-documents copies the source docs (current/previous)
SCHEMA_VERSION = 1                        # the project meta/layout format (bumped on breaking changes)

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


class UnknownSystemError(Exception):
    """A project's meta declares a system type the registry doesn't know - either a PL4-era id (this
    is a PL4 project; open it with Pipeline4) or a typo'd/future id. Opening STOPS: running a project
    against the wrong system's config/handlers would silently build wrong output."""

    def __init__(self, root: str, sid: str):
        from pipeline5.systems import catalog
        self.root, self.sid = root, str(sid)
        self.is_pl4 = self.sid in catalog.PL4_LEGACY_IDS
        detail = ("this is a PIPELINE4 project - PL5 does not migrate it; open it with Pipeline4App"
                  if self.is_pl4 else "no REGISTERED system carries this id (a planned-but-unbuilt "
                                      "type cannot open)")
        super().__init__(f"unknown system type {self.sid!r} in {project_name(root)}: {detail}")


def project_systems(root: str) -> list:
    """The System objects a project's meta declares (meta `types`, registry-resolved, order kept).
    Raises UnknownSystemError on an id the catalog can't resolve (incl. the pointed PL4-legacy case).
    A pre-meta/typeless project returns [] - the GUI falls back to its default system."""
    from pipeline5.systems import catalog
    systems = []
    for sid in load_project_meta(root).get("types") or []:
        system = catalog.by_id(sid)
        if system is None:
            raise UnknownSystemError(root, sid)
        systems.append(system)
    return systems


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
    """The canonical config files MISSING from the project, per TIER (the step-4 regroup): the app's
    builtin SHARED tier vs `<root>/config_project/shared`, plus - for each system the project declares
    in its meta - that system's builtin config_root vs `<root>/config_project/systems/<sid>`. Empty ->
    complete. The bundled builtins are the single source of truth - there is NO baked manifest.
    Project-specific extra files are fine; only missing canonical files are gaps."""
    gaps = []
    builtin_shared = _config_file_set(config.builtin_shared_config_dir())
    have_shared = _config_file_set(os.path.join(root, CONFIG_DIRNAME, "shared"))
    gaps += [os.path.join("shared", g) for g in sorted(builtin_shared - have_shared)]
    from pipeline5.systems import catalog
    for sid in (load_project_meta(root) or {}).get("types") or []:
        system = catalog.by_id(sid)
        if system is None or not system.config_root:
            continue
        want = _config_file_set(system.config_root)
        have = _config_file_set(os.path.join(root, CONFIG_DIRNAME, "systems", sid))
        gaps += [os.path.join("systems", sid, g) for g in sorted(want - have)]
    return gaps


def assert_config_complete(root: str) -> None:
    """Raise `ProjectConfigError` when `<root>/config_project` is missing any canonical config file - the
    fail-loud guard so a scaffolding/drift bug is caught in development, not shipped."""
    missing = config_gaps(root)
    if missing:
        raise ProjectConfigError(root, missing)


def project_name(root: str) -> str:
    return os.path.basename(os.path.abspath(root)) if root else ""


def open_project(root: str) -> str:
    """Make `root` the active project: validate it (folder shape, meta types vs the registry, config
    completeness), point `config` at it - including the multi-system Database/Output routing when the
    meta declares >1 type - and record it recent/last-opened. Returns the absolute root. Raises
    FileNotFoundError when `root` isn't a project folder, UnknownSystemError on an unresolvable meta
    type (pointed message for PL4-era ids), ProjectConfigError on missing canonical config."""
    root = os.path.abspath(root)
    if not is_project(root):
        raise FileNotFoundError(os.path.join(root, _PARAMS_REL))
    systems = project_systems(root)         # meta types -> System objects; unknown id -> pointed raise
    assert_config_complete(root)            # fail loud + stop if the project's config is incomplete
    config.use_project(root)
    config.set_multi_system(len(systems) > 1)
    state.push_recent(root)
    return root


def close_project() -> None:
    """Revert to the builtin app config + Shared/ (no project open) and forget the auto-reopen target."""
    config.use_builtin()
    config.set_multi_system(False)
    state.clear_last_opened()


def new_project(parent: str, name: str) -> str:
    """Scaffold a project at <parent>/<name>/ (its own config_project copied from the builtin + empty
    Database/ and Output/), open it, and return the root. Raises FileExistsError if it already exists."""
    root = os.path.abspath(os.path.join(parent, name))
    if os.path.exists(root):
        raise FileExistsError(root)
    os.makedirs(root)
    shutil.copytree(config.builtin_shared_config_dir(), os.path.join(root, CONFIG_DIRNAME, "shared"))
    for folder in ("Database", "Output"):
        os.makedirs(os.path.join(root, folder), exist_ok=True)
    # NOTE: the per-system tier (`config_project/systems/<sid>/`) is scaffolded by create_project
    # AFTER the meta records the selected types (scaffold_system_tiers) - new_project alone is
    # type-agnostic. assert_config_complete checks per the meta, so a bare new_project passes.
    assert_config_complete(root)            # the scaffold MUST be complete vs the builtin - fail loud if not
    return open_project(root)


def _update_meta(root: str, updates: dict) -> None:
    """Merge `updates` into the `project:` section of `<root>/config_project/project_params.yaml`
    (ruamel round-trip - the template's comments survive; the other sections are untouched)."""
    from ruamel.yaml import YAML
    yaml = YAML()
    path = os.path.join(root, _PARAMS_REL)
    with open(path, encoding="utf-8") as handle:
        data = yaml.load(handle) or {}
    section = data.get("project")
    if not isinstance(section, dict):
        section = {}
    section.update(updates)
    data["project"] = section
    with open(path, "w", encoding="utf-8") as handle:
        yaml.dump(data, handle)


def write_project_meta(root: str, name: str, types, multi_system: bool, backups_kept: int) -> None:
    """Write the full `project:` meta at creation. `backups_kept` + `notes` are the € user-editable
    knobs (each user button press backs the FULL project up, pruned to `backups_kept`); the
    `schema_version`/`created`/`app_version` stamps identify what made the project (migration safety)."""
    from pipeline5 import __version__
    _update_meta(root, {
        "name": str(name),
        "types": [str(t) for t in types],
        "multi_system": bool(multi_system),
        "backups_kept": max(0, min(BACKUPS_KEPT_MAX, int(backups_kept))),
        "schema_version": SCHEMA_VERSION,
        "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "app_version": __version__,
        "notes": "",
    })


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
    scaffold_system_tiers(root)             # copy each selected system's builtin config tier
    assert_config_complete(root)            # now WITH the system tiers - fail loud on scaffold drift
    return root


def scaffold_system_tiers(root: str) -> None:
    """Copy each meta-declared system's builtin config_root to `<root>/config_project/systems/<sid>`
    (skipping systems already scaffolded - reopening/upgrading a project only ADDS)."""
    from pipeline5.systems import catalog
    for sid in (load_project_meta(root) or {}).get("types") or []:
        system = catalog.by_id(sid)
        if system is None or not system.config_root:
            continue
        dest = os.path.join(root, CONFIG_DIRNAME, "systems", sid)
        if not os.path.isdir(dest):
            shutil.copytree(system.config_root, dest)


def save_as(root: str, base_folder: str, new_name: str) -> str:
    """'Save Project As': COPY the whole current project to `<base_folder>/<new_name>/<new_name>` (the
    same double-nested layout; the backup zips stay with the ORIGINAL - the copy starts a fresh history),
    restamp the meta name, open the copy, and return its root. The rename/migrate helper."""
    problem = validate_name(new_name)
    if problem:
        raise ValueError(problem)
    new_name = str(new_name).strip()
    new_root = os.path.abspath(os.path.join(base_folder, new_name, new_name))
    if os.path.exists(new_root):
        raise FileExistsError(new_root)
    shutil.copytree(os.path.abspath(root), new_root, ignore=shutil.ignore_patterns("~$*"))
    _update_meta(new_root, {"name": new_name})
    return open_project(new_root)


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


def restore_backup(root: str, zip_path: str) -> str:
    """Extract a backup zip into a NEW sibling folder (`<outer>/restored_<zip stem>/`) - the live
    project is NEVER overwritten - and return the restored project ROOT (the zip's top-level folder
    is the project name). Raises FileExistsError when that restore folder already exists."""
    outer = os.path.dirname(os.path.abspath(root))
    stem = os.path.splitext(os.path.basename(zip_path))[0]
    dest_parent = os.path.abspath(os.path.join(outer, f"restored_{stem}"))
    if os.path.exists(dest_parent):
        raise FileExistsError(dest_parent)
    with zipfile.ZipFile(zip_path) as bundle:
        tops = set()
        for member in bundle.namelist():
            target = os.path.abspath(os.path.join(dest_parent, member))
            if target != dest_parent and not target.startswith(dest_parent + os.sep):  # zip-slip guard
                raise ValueError(f"unsafe path in backup zip: {member}")
            tops.add(member.replace("\\", "/").split("/", 1)[0])
        bundle.extractall(dest_parent)
    inner = sorted(t for t in tops if t)
    return os.path.join(dest_parent, inner[0]) if inner else dest_parent


# --- import the source documents INTO the project (self-contained projects) ----------------------- #
def record_imports(root: str, records: dict) -> None:
    """Remember where the imported documents CAME from: `{key: {source, mtime}}` merged into the
    `project.imported` meta - the stale-import check compares the original's current mtime against
    the recorded one, so a source someone keeps editing is flagged instead of silently diverging."""
    if not records:
        return
    merged = dict(load_project_meta(root).get("imported") or {})
    merged.update(records)
    _update_meta(root, {"imported": merged})


def _remembered_source(record: dict) -> tuple:
    """(source_path, recorded_mtime) out of one `project.imported` record ('' / 0 when unusable)."""
    source = str((record or {}).get("source") or "")
    try:
        recorded = int((record or {}).get("mtime") or 0)
    except (TypeError, ValueError):
        recorded = 0
    return source, recorded


def stale_imports(root: str) -> list:
    """The imported documents whose ORIGINAL source file changed AFTER the import: [(key, source)].
    The GUI warns on open; the next Import-documents run refreshes the project copy from the source.
    (A >1s mtime margin absorbs filesystem timestamp granularity.)"""
    out = []
    for key, record in (load_project_meta(root).get("imported") or {}).items():
        source, recorded = _remembered_source(record)
        if source and os.path.isfile(source) and int(os.path.getmtime(source)) > recorded + 1:
            out.append((key, source))
    return out


def import_documents(root: str) -> list:
    """Copy every configured input document that lives OUTSIDE the project into
    `<root>/input_documents/current|previous/` and rewrite its path in project_params.yaml RELATIVE
    to config_project (so the whole project moves as one folder). A path already inside the project
    is normalized to relative; when its remembered SOURCE (a prior import) is newer than the copy,
    the copy is REFRESHED from it. Each copy records `{source, mtime}` into the `project.imported`
    meta (the stale-import check). Returns [(key, action, new_value)] for the status line - action
    in imported | refreshed | up-to-date | missing. `root` must be the ACTIVE project
    (save_document_path writes the active params file)."""
    active = config.active_project()
    if not active or os.path.abspath(active) != os.path.abspath(root):
        raise ValueError("import_documents requires the target to be the ACTIVE project")
    params = config.load_params(os.path.join(root, _PARAMS_REL))
    # relative doc paths are stored AGAINST THE PARAMS FILE's dir (load_params resolves there) -
    # since the regroup that is the shared tier, one level deeper than config_project/.
    config_dir = os.path.dirname(os.path.join(os.path.abspath(root), _PARAMS_REL))
    remembered = load_project_meta(root).get("imported") or {}
    records: dict = {}
    actions = []
    for key in config.DOCUMENT_KEYS:
        configured = str(params.get(key) or "").strip()
        if not configured:
            continue
        configured = os.path.abspath(configured)
        inside = os.path.commonpath([os.path.abspath(root)]) == \
            os.path.commonpath([os.path.abspath(root), configured])
        if inside:
            target = configured
            action = "up-to-date"
            source, recorded = _remembered_source(remembered.get(key))
            if source and os.path.isfile(source) and int(os.path.getmtime(source)) > recorded + 1:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(source, target)      # the original moved on since the import - refresh
                records[key] = {"source": source, "mtime": int(os.path.getmtime(source))}
                action = "refreshed"
            if not os.path.isfile(target):
                actions.append((key, "missing", configured))
                continue
        else:
            if not os.path.isfile(configured):
                actions.append((key, "missing", configured))
                continue
            sub = "previous" if key.endswith("_previous_path") else "current"
            target = os.path.join(root, DOCS_DIRNAME, sub, os.path.basename(configured))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(configured, target)
            records[key] = {"source": configured, "mtime": int(os.path.getmtime(configured))}
            action = "imported"
        relative = os.path.relpath(target, config_dir).replace(os.sep, "/")
        config.save_document_path(key, relative)
        actions.append((key, action, relative))
    record_imports(root, records)
    return actions


def auto_reopen() -> str | None:
    """Re-point `config` at the last-opened project (launch-time). Returns the root, or None when there's
    no valid last project (then the builtin config stays active). Does NOT re-push recents. A project
    with an unknown meta type or incomplete config is NOT auto-reopened (open it explicitly to see the
    pointed error)."""
    root = state.last_opened()
    if not (root and is_project(root)):
        return None
    try:
        systems = project_systems(root)
    except UnknownSystemError:
        return None
    if config_gaps(root):
        return None
    config.use_project(os.path.abspath(root))
    config.set_multi_system(len(systems) > 1)
    return os.path.abspath(root)
