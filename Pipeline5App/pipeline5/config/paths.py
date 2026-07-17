"""WHERE everything lives: the app/Shared roots, the active-project state, and every directory helper.

The single owner of the `_PROJECT_ROOT` state: `use_project()` points the whole app (config loaders,
the SSOT `Database/` folder, the `Output/` tree) at a project - or back at the builtin `Shared/`.
Delivery-tree dirs (the TIA `BuilderData/` surfaces) are TRANSITIONAL here: they move to the Siemens
system's `output_layout` at migration step 4 (PL5 plan, coupling #3); the neutral dirs
(ProjectDocumentation/Reports) stay kernel.
"""
from __future__ import annotations

import os
import sys

# APP_ROOT = the Pipeline5App dir (dev: 3 levels above this file; frozen: the bundle dir).
if getattr(sys, "frozen", False):
    APP_ROOT = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
else:
    # pipeline5/config/paths.py -> config -> pipeline5 -> Pipeline5App
    APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SHARED = os.path.normpath(os.path.join(APP_ROOT, os.pardir, "Shared"))
TEMPLATES_DIR = os.path.join(SHARED, "Templates")
INTERFACE_TEMPLATE = os.path.join(TEMPLATES_DIR, "MachineInterfaces", "TEMPLATE_INTERFACES_v0.0.xlsx")
BLOCK_TEMPLATES_DIR = os.path.join(TEMPLATES_DIR, "Tia Portal Software Blocks")   # ph800 block .xml templates
DIAG_SCL_TEMPLATE = os.path.join(BLOCK_TEMPLATES_DIR, "TEMPLATE--v1.0--06_Diagnostic for OPC.scl")
_BUILTIN_CONFIG_PROJECT = os.path.join(APP_ROOT, "config_project")
_BUILTIN_DATABASE = os.path.join(SHARED, "Database")        # the SSOT folder (DESIGN 10.3)
_BUILTIN_OUTPUT = os.path.join(SHARED, "OutputTree")        # the OPn BuilderData export surface
DEVICE_TYPES_DB_DEFAULT = os.path.join(SHARED, "HardwareConfigBuilderData", "DeviceTypesDatabase.csv")  # ph700 DTD

# The ACTIVE project root (None = the builtin app config + Shared/). Project open/close calls
# use_project() so the config loaders, the Database folder, and the Output tree all follow the project.
_PROJECT_ROOT: str | None = None

# The ACTIVE system (id, builtin config_root) - the resolver's system tiers. Set by use_system()
# alongside use_project(); None = no system tier (kernel-only flows, some tests).
_ACTIVE_SYSTEM: tuple | None = None


def use_system(system) -> None:
    """Point the config resolver's SYSTEM tiers at `system` (a System descriptor); None clears them.
    Refreshes the injected address notation (truth.addresses) - the tiers just changed."""
    global _ACTIVE_SYSTEM
    _ACTIVE_SYSTEM = None if system is None else (system.id, system.config_root or "")
    _refresh_address_format()


def active_system() -> tuple | None:
    return _ACTIVE_SYSTEM


def builtin_shared_config_dir() -> str:
    """The app's builtin SHARED config tier (tier 4): config_project/shared."""
    return os.path.join(_BUILTIN_CONFIG_PROJECT, "shared")


def use_project(root: str | None) -> None:
    """Point the config loaders + the Database + the Output tree at <root>/...; None reverts to builtin.
    Refreshes the injected address notation (truth.addresses) - the tiers just changed."""
    global _PROJECT_ROOT
    _PROJECT_ROOT = root or None
    _refresh_address_format()


def _refresh_address_format() -> None:
    """Resolve `address_format.yaml` through the 4-tier walk and inject it into truth.addresses
    (P-010). No tier shipping one -> the TIA default. Lazy imports: paths sits below resolver."""
    from pipeline5.config.resolver import find
    from pipeline5.truth.addresses import configure_address_format
    path = find("address_format.yaml")
    if not path:
        configure_address_format(None, None)
        return
    from pipeline5.config.params import _read_yaml
    data = _read_yaml(path) or {}
    configure_address_format(data.get("pattern"), data.get("direction_tokens"))


def use_builtin() -> None:
    use_project(None)


def active_project() -> str | None:
    return _PROJECT_ROOT


def config_project_dir() -> str:
    return os.path.join(_PROJECT_ROOT, "config_project") if _PROJECT_ROOT else _BUILTIN_CONFIG_PROJECT


def builtin_config_project_dir() -> str:
    """The app's BUNDLED canonical config_project (always, regardless of the active project). It is the
    completeness reference a project's config_project is verified against (project/assert_config_complete)."""
    return _BUILTIN_CONFIG_PROJECT


def database_dir() -> str:
    """The top-level Database/ folder - the SSOT (one CSV-with-JSON-cells per table)."""
    return os.path.join(_PROJECT_ROOT, "Database") if _PROJECT_ROOT else _BUILTIN_DATABASE


def user_input_dir() -> str:
    """The USER-LOCAL inputs (the treatment registry finding_treatments.csv) - the SHARED tier's
    user_input/, per project when one is open, else the builtin's. Co-located with the active config
    so each project owns its treatments."""
    return os.path.join(config_project_dir(), "shared", "user_input")


def output_root() -> str:
    """The BuilderData/ export root - what OPn imports."""
    return os.path.join(_PROJECT_ROOT, "Output") if _PROJECT_ROOT else _BUILTIN_OUTPUT


def blocks_import_dir() -> str:
    """The phase-520 GlobalDB-XML BuilderData surface (`<DB>.xml`), under the output root - what OP4
    imports. Byte-stable to PL3's `ImportReady/` (the 02_COM.xml there is phase-800-owned)."""
    return os.path.join(output_root(), "TiaPortalProjectInterface", "BuilderData", "SoftwareBlocks", "ImportReady")


def interfaces_dir() -> str:
    """The phase-400 `IF_*.xlsx` output - DOCUMENTATION/intermediate under ProjectDocumentation, NOT a
    BuilderData import surface (510 reads the IF_ sheets inserted into the I/O List, not these files)."""
    return os.path.join(output_root(), "ProjectDocumentation", "InformationDatabase", "Interfaces")


def io_tags_dir() -> str:
    """The phase-510 I/O Tags BuilderData surface (`PLCTags.xlsx`), under the output root - what OP4
    imports. The leaf is `PlcTags` to match PL3's OUTPUT_PATHS['io_tags_dir'] (the OP-import contract path)."""
    return os.path.join(output_root(), "TiaPortalProjectInterface", "BuilderData", "PlcTags")


def diaglist_dir() -> str:
    """The phase-610 DiagList output (`DiagList_IO.csv` + `DiagList_Logic.csv`) - DOCUMENTATION under
    ProjectDocumentation (NOT a BuilderData import surface; matches PL3's DiagnosisData path)."""
    return os.path.join(output_root(), "ProjectDocumentation", "InformationDatabase", "DiagnosisData")


def hardware_dir() -> str:
    """The phase-700 Hardware BuilderData surface (`Stations.csv` + `Modules.csv`), under the output root
    - what OP4 imports. Matches PL3's OUTPUT_PATHS['hardware_dir'] (the OP-import contract path)."""
    return os.path.join(output_root(), "TiaPortalProjectInterface", "BuilderData", "HardwareConfiguration")


def blocks_creation_dir() -> str:
    """The phase-800 Software CreationInfo BuilderData surface (the `$/#/%/@` template-fill CSVs +
    `InstanceDBs.csv`), under the output root - what OP4 imports. Matches PL3's `blocks_creation_dir`."""
    return os.path.join(output_root(), "TiaPortalProjectInterface", "BuilderData", "SoftwareBlocks", "CreationInfo")


def coverage_dir() -> str:
    """The phase-900 coverage report output (`io_project_coverage_report.{csv,txt}`) - DOCUMENTATION under
    ProjectDocumentation/Reports, NOT a BuilderData import surface (matches PL3's `Reports/` placement)."""
    return os.path.join(output_root(), "ProjectDocumentation", "Reports")


COVERAGE_REPORT_STEM = "io_project_coverage_report"   # the phase-900 report base name (+ .csv / .txt)


def validation_report_dir() -> str:
    """The phase-100 validation reports (`documents_validation_report`/`_errors`.{txt,html}) - DOCUMENTATION
    under ProjectDocumentation/Reports (same tree as the coverage report; NOT a BuilderData surface)."""
    return os.path.join(output_root(), "ProjectDocumentation", "Reports")


VALIDATION_REPORT_STEM = "documents_validation_report"   # phase-100 complete report (+ .txt / .html)
VALIDATION_ERRORS_STEM = "documents_validation_errors"   # phase-100 errors-only report (+ .txt / .html)


def gui_log_dir() -> str:
    """Where the GUI's optional 'log to file' tee writes (`pl5_log_<stamp>.txt`) - a Logs/ subfolder of the
    reports tree."""
    return os.path.join(validation_report_dir(), "Logs")


def changes_report_dir() -> str:
    """The ph100 before/after quality report (`io_documents_quality_report.html` + `.csv`) - DOCUMENTATION
    under ProjectDocumentation/Reports (same tree as the validation/coverage reports; NOT a BuilderData
    surface). The report is a STANDALONE analysis (not part of the pipeline)."""
    return os.path.join(output_root(), "ProjectDocumentation", "Reports")


CHANGES_REPORT_STEM = "io_documents_quality_report"      # the ph100 before/after report base (+ .html / .csv)



