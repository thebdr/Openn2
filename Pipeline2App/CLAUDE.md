# Pipeline2 — Safety-document pipeline (Python)

`Pipeline2App` is the Python half of the **`_Openn2`** monorepo. It validates the
customer's hand-authored safety documents (the **I/O List** + the **Cause & Effect
matrix**) and generates the TIA-Portal artifacts that the C# **`Open2App`** Openness tool
imports. It is a rebuild of a legacy Power Query / VBA workbook workflow (`3_Database`,
`2_HwPlc`, `1_SwPlc`) — those workbooks are **legacy and replaced**.

Pipeline: **documents → staging → validation → database / outputs**

```
I/O List + C&E matrix (customer Excel docs, authored by hand)
   → staging        canonical rows, strikethrough/skip-reason aware
   → validation     C&E + AREA cross-checks → ISSUES log (cell-addressed)
   → outputs        I/O tag tables + DBs, diagnosis lists + OPC SCL, hardware
                    Stations/Modules, interface I/O tables, software-block CSVs
```

## The `_Openn2` monorepo

`Pipeline2App` does not stand alone — it is one of three siblings under
`C:\Source\Repos\_Openn2`:

```
_Openn2/
  Pipeline2App/     <- THIS app (Python). The doc validator + TIA artifact generator.
  Open2App/         <- the C# WPF TIA-Portal Openness tool (imports what this app writes).
  Shared/           <- the handoff boundary between the two (see below).
```

`Shared/` is the contract between the two apps — this app **reads** templates + the device
DB from it and **writes** every generated artifact into its `OutputTree/`, which `Open2App`
then imports:

```
Shared/
  Templates/
    Tia Portal Software Blocks/   *.xml block exports + *.csv sidecars + InstanceOf/*.db
                                  + 06_Diagnostic for OPC.scl   (config.BLOCK_TEMPLATES_DIR)
    MachineInterfaces/            TEMPLATE_INTERFACES_v0.0.xlsx   (config.INTERFACE_TEMPLATE_DEFAULT)
  HardwareConfigBuilderData/
    DeviceTypesDatabase.csv       the global device DB (config.DEVICE_TYPES_DB_DEFAULT)
    TestData/Passing/             reference Stations/Modules + DTD for tests
  DocumentsValidationData/
    Passing/                      sample I/O List + C&E that validate clean
  OutputTree/                     <- config.OUTPUT_ROOT: every generated artifact (see "Output tree")
```

`_Openn2` is **not a git repo yet** (the reorg landed without git; init/commit on request).

## Why Python (not Power Query / VBA)

openpyxl reads cell **strikethrough** directly (the thing PQ/VBA couldn't), it runs and
tests **without Excel** (no COM, no zombie processes — that path was painful), and
everything versions cleanly as text. Prefer pure Python here; don't reach back for Power
Query or VBA.

## The `pipeline2/` package

All app code is one package, `pipeline2/`, with six subpackages. Modules use **absolute
imports** (`from pipeline2.core import config`); intra-subpackage code uses relative
(`from . import …` / `from .. import …`). Each submodule also bootstraps the app root onto
`sys.path` (`_APP_ROOT = dirname(dirname(dirname(__file__)))`), so even `python
pipeline2/gui/gui.py` works; the thin root entry scripts do the same.

### `pipeline2/core/` — the pipeline engine
- `config.py` — the single source of truth for the layout. Anchors `APP_ROOT`,
  `CONFIG_PROJECT`, `INPUT_DOCS_DIR`, `DIAGNOSIS_DIR`, `USER_INPUT`, `SHARED`,
  `TEMPLATES_DIR`, `BLOCK_TEMPLATES_DIR`, `OUTPUT_ROOT`, `PARAMS_FILE`,
  `BLOCK_TEMPLATES_JSON`, `PROJECTS_DIR` (where New/Save As create projects), `DESIGNER_PARAMS_FILE`
  (the slim designer GUI's own validation-focused base; both built-in bases skip the project output
  routing), the Shared defaults `DEVICE_TYPES_DB_DEFAULT` /
  `INTERFACE_TEMPLATE_DEFAULT`, and the **`OUTPUT_PATHS`** map + `output_root(params)` /
  `out_path(out_root, key, *extra)` (see "Output tree"). `APP_ROOT` = `sys._MEIPASS` /
  `dirname(sys.executable)` when frozen, else this file's great-grandparent (Pipeline2App).
  Loaders: `load_params(path)` (ruamel safe-load YAML, or `.json` for back-compat; resolves
  doc paths relative to the params file's folder; **defaults `device_types_db` /
  `interface_template` to the Shared copies** when the project omits them; for a project's own
  params file it defaults `output_dir` to `Output` and resolves it to `<project>/Output`),
  `load_signal_types`,
  `load_device_types_db`, `resolve_type` (pattern-aware), `parse_params_by_type`,
  `sorter_areas`, `load_iolist_columns` / `load_permanent_parts` (the ported Phase-0A
  glossaries from `input_docs/`), `resolve_sheets`/`resolve_sheet` (match the regex
  `io_list.sheet` / `ce.matrix_sheet` patterns against a workbook's sheets).
- `staging.py` — `load_io_list`: reads the I/O List by **column position** (header verified
  by prefix; the doc has duplicate "Description language" headers and newline-wrapped
  headers, so a name map is unsafe). `io_list.sheet` entries are **regex patterns**
  (`config.resolve_sheets`, case-insensitive `re.search`, literal fallback). Excludes struck
  rows and rows with a Skip Reason. Resolves each row's signal type.
  `load_diagnostic_blocks` — the I/O List diagnosis-block sheet (`{cabinet_id: {index,
  fld, template_type}}`, keyed by `ID_SWP`); accepts the sheet named **`DiagnosisBlocks`** (what
  the `iolist_diag` populator writes, and the golden) **or** the older `DiagnosticBlocks`.
- `matrix.py` — reads the C&E workbook; enriches each staged row with `matrix_areas` (see
  "the CentralDatabase" under software-block templates).
- `validation/` — **a package** (split from the old monolithic `validation.py`). Public
  names are re-exported from `validation/__init__.py`, so callers and tests just
  `from pipeline2.core import validation` and use `validation.validate` / `LogEntry` / etc.
  - `model.py` — `LogEntry`, the `Cmp` cross-check payload, and the leaf helpers
    (`_norm`/`_key`/`_addr`/`_row_info_parts`/`_levenshtein`/`_banner`/…). `LogEntry.info()`
    builds the info block; `LogEntry.format()` is the un-aligned console fallback.
  - `indexes.py` — `build_io_index`, `build_ce_index`.
  - `checks.py` — `validate(params, io_rows, phases=None, lang="en", out_dir=None)` + the
    per-phase check functions (`check_ce_matrix`, `check_area_sheets`, `check_ce_mandatory`,
    `check_diagnosis_bits`, `_check_reference`).
  - `render.py` — the single **`render_lines(log, full_print, ce_path)`** (columns auto-fit
    **per phase**) consumed by every sink, plus `write_log` (the `.txt` + dark `.html` report)
    and the HTML helpers.
  - `validate(...)` logs the effective **project_params.yaml** first (config audit, always
    shown), then the requested phases of a stable **5-phase interface** (each led by a `PHASE`
    banner; `phases` is a set of ids, default ALL; a missing document degrades gracefully):
    **0A. I/O List standalone** (`core.iolist_checks.check_iolist_standalone`, the VBA port —
    runs first), **0B. C&E Matrix standalone** (placeholder), **1. C&E in IOList** (forward:
    `check_ce_matrix` + `check_area_sheets`), **2. IOList in C&E** (reverse:
    `check_ce_mandatory`), **3. Diagnosis Coherence Check** (`check_diagnosis_bits`). The
    designer tool passes `phases={"0A","0B","1","2"}` (no diagnosis).
  - Every entry carries an **info block** `bit | FLD | desc_l1 | desc_l1b | drawing |
    script_type-index` (from the I/O row, or a C&E pseudo-row for unmatched forward refs).
    Phase 3 = `check_diagnosis_bits` (I/O List only): every in-diagnosis signal must carry a
    numeric Diag Cabinet (AE) + Diag Bit (AF), and (cabinet, bit) must be unique within its
    alarm/warning family (col R 'Type' ending 'W' = warning) — missing/invalid or colliding
    slots are FAILs. Phase 2 `check_ce_mandatory` (runs when the C&E doc exists): an I/O signal
    that must be in the C&E but isn't is flagged, matched by BOTH device key (FLD) and address
    — a typed row by its type's `ce_mandatory` (`yes`→FAIL, `warn`→WARN, `no`/blank→skip); an
    untyped/unknown row when it carries a device designation (FLD) — or, device-less, a
    non-empty `desc_l1`/`desc_l1b` — plus an address, FAIL when its description names a safety
    concept (params `ce_mandatory_words`) else WARN. A **partial** match (only the FLD or only
    the address differs) is logged at the same severity; the entry carries a **second cell
    link** (`LogEntry.location2`/`path2`) so a non-PASS partial links **both workbooks** (the
    C&E cell *and* the I/O List row). Fuzzy word match uses params `ce_fuzzy_chars`
    (Levenshtein tolerance; `0` disables). Untyped rows whose description matches
    `ce_excluded_words` are skipped — but a `ce_mandatory_words` match wins, and typed rows are
    never excluded; `ce_full_check` (default `false`) ignores the exclusion list.
    `ce_always_excluded_words` (**substring only — no fuzzy**) ALWAYS skips a row, overriding
    everything incl. `ce_full_check`. Every PASS/SKIP is logged (with its reason);
    `ce_full_print` controls only whether the **live display** shows passing/skipped rows.
  - **Cross-check (Phase 1/2) lines** read from the **caller** workbook's perspective —
    `<caller cell> vs <OtherDoc> | <addr> <op> <addr> | <device> <op> <device> | <caller> :
    <msg>` — caller value on the left (so the left side flips per phase: `vs IOList` / `vs
    CEMatrix`), operator `===` (match) / `=/=` (differ), the looked-up side set-joined, an
    absent side `(none)`; the `Cmp` payload holds the values. **Info-block lines** (Phase 0A,
    SKIP, diagnosis) column-align `<cell> | bit | FLD | desc_l1 | desc_l1b | drawing | st-index
    : <msg>` and share the location column. Messages are short bilingual **i18n** keys
    (`xc_p1_*`/`xc_p2_*`); severity is carried by the `[LEVEL]` tag. `write_log` returns
    `(passed, failed, warned)`.
- `iolist_checks.py` — **Phase 0A**: a faithful port of the external `IOList check_v18.xlsm`
  VBA. `check_iolist_standalone(params, log, lang)` re-opens the I/O List read-only and checks
  each safety sheet on its own (column headers vs the glossary, addresses, Profinet
  nodes/IPs/names, the "permanent part", T.S. refs, duplicate IPs/devices, node counts) →
  `LogEntry`s via `i18n`.
- `i18n.py` — hard-coded EN/IT string table + `tr(key, lang, **fmt)` (GUI chrome, Phase 0A
  messages, the Phase 1/2 cross-check messages `xc_p1_*`/`xc_p2_*`).
- `error_management.py` — error registry + per-error treatment between runs. `validate(...)`
  calls `run(log, out_dir)`: tags each entry with its phase, writes a complete
  **`user_input/error_management.csv`** (`id, phase, type, treatment, location, message` — one
  row per distinct FAIL; `id` = stable per-instance hash), and applies the `treatment` the user
  set on a prior run: **warn** → WARNING, **skip** → SKIP (pipeline goes forward),
  **skip_type** → SKIP every error of that (phase, type). Treatments persist across runs (merge
  by id). The GUIs link the **`[FAIL]` tag** to this CSV.
- `outputs.py` — I/O tags, DBs, diagnosis lists (config-driven columns +
  `plc_binding`/`ml_value`); `write_dbs` writes the `.db` files into the `ImportReady/` slot.
- `hardware.py` — `extract`: format-2 Stations + Modules.

### `pipeline2/blocks/` — software-block tooling (not the pipeline)
- `block_templates.py` — `keys` scans the block templates for `!!key$$` placeholders →
  `config_project/block_templates.json` (merge-preserving) **and `sync_builders` regenerates
  `block_builders.py`** from it; `staged` exports the CentralDatabase to the
  `io_database` output (`IODatabase.csv`).
- `block_builders.py` — **you edit**: one `build_*(db)` per template returning instances.
- `softwareblocks.py` — the engine that writes the `<NN_Name>.csv` + `InstanceDBs.csv` into
  the `blocks_creation_dir` (`SoftwareBlocks/CreationInfo/`).
- `blockshells.py` — the per-template **shell workbook** `SoftwareBlocks.xlsm` (one sheet per
  template, with a `$ <mode>` directive `keep`/`fill`/`override` in B2; additive). Path via
  `blockshells.shell_path(params)` (under `CreationInfo/`).

### `pipeline2/diagnosis/`
- `diagnostic_opc.py` + `diagnosis_rules.py` — the diagnosis SCL generator + the
  rule-generated `>List_Logic`. Writes `DiagList_IO.csv` / `DiagList_Logic.csv` (diagnosis
  dir) and **`Diagnostic_for_OPC.scl`** (the `ImportReady/` slot).

### `pipeline2/iolist_diag/` — the I/O-List diagnosis populator (runs **before** staging)
Turns a *fresh* Emergency I/O List (empty `script_type`/`index`/`diag_cabinet`/`diag_bit`, no
`DiagnosisBlocks` sheet) into the populated workbook staging consumes. **Idempotent +
non-destructive**: every column is written **only into an empty cell**; a pre-filled cell is
preserved and audit-logged. `run.py` runs it first and **halts before staging** if anything is
unresolved (`<input required>`). `populate(params)` is the entry; it copies the input (never mutates
it in place — the copy keeps COVER, the suggested-type array formula, the `_TRO_TRAILING` LAMBDA and
all formatting), reading cached values with `data_only=True` and writing through a formula-preserving
load.
- `models.py` — frozen `SignalTypeDef`/`ObjectFamily`/`IoRow`/`DiagBlock` + a mutable `RowResult`;
  `Category`/`BlockKind`/`LinkKind` enums; the sentinels (`<input required>`, the `???` marker, the
  `"-"` mnemonic) and sheet-name constants.
- `columns.py` — `ColumnResolver` (canonical ⇄ letter ⇄ index from `column_map.csv`); **nothing
  else hardcodes a column letter**.
- `reader.py` — read the I/O sheet(s) (regex via `config.resolve_sheets`, `--sheets` overrides),
  detect the first data row (skip the node-meta `50` line), build `IoRow`s with the strike flag.
- `families.py` — load `object_families.csv` + `family_for(script_type)`.
- `script_type.py` (§6) — faithful port of the AC suggested-type regex ladder → `suggested_type`
  (incl. its quirks: Node→`type_hw`, unclassified→`False`, In/Out-unmatched→`???`); `to_canonical`
  maps the legacy names to the catalogue (`ENC→N`, `FA→Z`, `RES→R*`/`R<area>`) and surfaces `???`
  as `<input required>`.
- `index_assign.py` (§7) — per-family contiguous progressive in row order; object grouping (channel
  = strict FLD, series = KQ↔KI, fld = door `DI1/2`/`DD`, pattern = `Z`, none = `R`/standalone);
  unresolvable members → `<input required>` (+ report).
- `diag_alloc.py` (§8) — `in_diag` gating; node cabinets (P from `diag_bit_max` down, non-P from
  `diag_bit_min` up); the PA/PW **Field inference** (lone field bit → shared `+FieldIODevices`); the
  Type-2 per-family bit layouts; returns the ordered `DiagBlock` list (Type-1 FL, then Type-2).
- `blocks.py` (§9) — (re)write the `DiagnosisBlocks` sheet. `ID_Local == ID_SWP`; `FullName`/FU are
  **materialized as text** (`data_type 's'`) so the leading `=` isn't a formula and staging reads
  them via `data_only=True` (the spill `_TRO_TRAILING` formulas aren't reproduced — openpyxl can't
  cache a formula result, and the sheet is regenerated each run).
- `report.py` (§10) — the `_UnresolvedIndex` sheet (one clickable internal hyperlink per entry) +
  the console summary + the Mode-2 audit lines.
- `populate.py` — the orchestrator + `PopulateResult`; writes to
  `OUTPUT_PATHS["populated_iolist"]`.

### `pipeline2/interfaces/`
- `interface_tool.py` — IOC interface-table generator (standalone + invoked by `run.py`/GUI).
- `verify.py` — **coverage check + report**: per CentralDatabase row, which outputs it lands
  in; flags **ORPHAN** / **UNPLACED MEMBER**. Writes `io_project_coverage_report.csv`/`.txt`.

### `pipeline2/gui/` — the Tkinter front-ends
- `gui.py` — the main operator window "**Pipeline2**" (the interactive twin of `run.py`).
  Split for size into a base + two **mixins**: `gui.py` holds module helpers/constants
  (`excel_goto`, `PARAM_SPEC`, `PHASES`, `_get`/`_set`/`_abs`), the `App` base
  (`__init__`, the menu/toolbar/notebook/statusbar builders, the log/drain machinery),
  `class App(ActionsMixin, TabsMixin)`, and `main()`; **`_app_actions.py`** (`ActionsMixin`)
  holds the per-phase pipeline workers, the run actions, and the tooling workers;
  **`_app_tabs.py`** (`TabsMixin`) holds the Files + Configuration tabs and the project
  actions. The pipeline runs on a worker thread (queue → `root.after` drain). **Clickable
  links** open the source workbook in Excel **at that cell** via pywin32 COM (falls back to
  `os.startfile`). Dark-mode toggle; window icon `assets/Pipeline2.ico|png`. The actions live in a
  top **phase bar** (see `phasebar.py`): a row of phase headers (Documents Validation · Fill Out ·
  Staging · Interfaces · Signals · Diagnosis · Hardware · Software · Reporting) separated by `>`,
  with the pink **Run Pipeline** master on the left. A phase header **runs the whole phase**; the
  grey chevron under it opens that phase's dropdown of individual buttons. `_phase_spec()` is the
  declarative wiring (header `run` + per-button `command`s → the existing `_phase_*`/`_work_*`
  workers; "Open" buttons → `_open_*` helpers; the three undefined buttons are disabled stubs).
  Documents Validation's buttons are Validate I/O List `{0A}` · *Validate C&E Matrix* (stub) ·
  Cross-Check CEM→IOL `{1}` · Cross-Check IOL→CEM `{2}` · **Validate Diagnosis Assignments** `{3}` +
  the Opens; the header runs `{0A,1,2,3}`. `_phase_fill` = the `iolist_diag.populate` stage
  (subsequent staging reads its populated copy via `_populated_path`). A **File** menu hosts the
  Project Manager + a **Language** menu (EN/IT). The utility controls (**Open Output / Clear Log /
  Large font / Dark mode**) are `place`d beside the notebook **tab selector** (top-right of the tab
  strip), not on the phase bar.
- `phasebar.py` — the reusable widget layer: `PhaseBar` (the header+chevron grid; `run=None` drops
  the pink master for the designer) and `_Dropdown` (an anchored `overrideredirect` popup with a
  scrollable interior, capped to the window height, that closes on Escape / click-outside / another
  chevron). Sizing: the header is double height, the chevron a short strip; headers, chevrons and
  popup buttons all share one width (`_BTN_WIDTH`, ~6/10 of the old single-line header) and their
  labels **word-wrap** (`_wrap`) + are **centre-justified, Courier New** (the chevron keeps a glyph
  font for ▼), so the popup (sized to the chevron column) lines up under its header. Click-outside is
  detected by **widget ancestry**, not coordinates (DPI-safe). Button colours come from the semantic
  ttk styles in `theme.button_styles`.
- `gui_designer.py` — the slim **"I/O List Checker"** for electrical designers (shipped as a
  one-folder `.exe`); it ships with its **own base params** (`config.DESIGNER_PARAMS_FILE` =
  `config_project/designer_params.yaml`, validation-only). Validation only (Staging → Phase 0A →
  Phases 1/2, never Diagnosis). The body is a single top bar: the `phasebar.PhaseBar` carrying **only
  the Documents Validation** phase (no pink Run, no diagnosis button), a **Clear Log** button, plus,
  to its right, the only inline controls a designer needs (`INLINE_FIELDS`: the two source-file
  pickers + the **Full check** / **Log everything** toggles) — no config form. The persistent
  `LogView` fills the rest; a validation run first saves those inline picks to the project so
  `load_params` sees them. Imports only `core` (config/staging/validation/i18n/error_management) +
  `gui` (theme/logview/project/gui_common/phasebar).
- `logview.py` — `LogView`: the colour-coded, link-aware, thread-safe log pane + `excel_goto`.
- `gui_common.py` — shared widgets: `build_validation_cascade` (the in-popup action cascade), the File/Language menu bar, the
  Archive popup, the **new-project name prompt** (`ask_project_name` — name entry + live
  `<base>/<name>` preview + validation), and `render_validation_log`.
- `project.py` — folder-based **Project Manager** (pure functions). A *project* is a
  self-contained directory: `project.yaml` + `Input/` (copied workbooks) + `Output/` (its
  generated tree). **New / Save As prompt for a name** (`gui_common.ask_project_name`) and create
  `<config.PROJECTS_DIR>/<name>` (env `PIPELINE2_PROJECTS`, default `~/Pipeline2 Projects`);
  `copy_inputs_on_save` copies the I/O List + C&E into `Input/` and rewrites their paths to
  `Input/<name>`. `default_doc` seeds `output_dir: Output`, so an open project writes into
  `<project>/Output` (see "Output tree"); `archive_project` zips the whole folder. Both GUIs launch
  on the built-in `config.PARAMS_FILE` (no auto-reopen of a "last project"); File ▸ Open opens an
  existing project for the session.
- `editor.py` — the GUI's **Files** tab: a file tree beside a `FileEditor` (`.csv`/`.xlsx`
  open in a tksheet grid with filter-rows/columns; `.db`/`.json` in a text editor).
- `theme.py` — light/dark palettes + log tag colours (shared by gui + editor) + `button_styles` /
  the semantic phase-bar button styles (`Run`/`Phase`/`Chevron`/`Action`/`Open`/`Special`/`Disabled`
  `.TButton`, registered in `apply_ttk` from the `assets/ButtonsLayout.xlsx` colours).

### Root entry scripts + tests (in `Pipeline2App/`)
- `run.py` — the pipeline CLI: documents → **I/O-list population** → staging → validation → every
  output. The populator runs first and points staging at its populated copy; the run **halts (exit 1)
  before staging** if any index/type is unresolved. `--strict` fails on validation FAILs; exits 1 on
  a hardware ERROR, 2 on a missing doc.
- `run_populate.py` — the `iolist_diag` populator as a standalone CLI (`--params`/`--out`/`--sheets`);
  exit 1 when entries need manual entry.
- `run_validation.py` — validation-only CLI (console output).
- `launch_gui.py` / `launch_designer.py` — thin launchers (put Pipeline2App on `sys.path`,
  then `from pipeline2.gui import gui` / `gui_designer` and call `main()`).
- `make_demo_inputs.py` — generates `demo/8XXX_IOList_DEMO.xlsx` + `…_CE_DEMO.xlsx` whose rows
  trigger **every** validation case across the 3 phases; `test_demo_validation.py` asserts each
  fires in a temp dir.
- `test_*.py` — plain-`python` test scripts (no pytest); each prints PASS/FAIL and exits
  non-zero on failure. The **data-independent set is the green gate** (`test_i18n`,
  `test_iolist_checks`, `test_validation`, `test_demo_validation`, `test_error_management`,
  `test_outputs`, `test_hardware`, `test_diagnostic_opc`, `test_interface_tool`,
  `test_project`, `test_iolist_diag`). `test_iolist_diag_golden.py` (the §13 acceptance) runs against
  the golden workbook and **skips cleanly** when the golden or the configured catalogue isn't present.
  `test_staging.py` / `test_softwareblocks.py` *integration* parts assume the
  specific real I/O List in `project_params.yaml`, so they FAIL when it points at a different
  project's documents (or when that workbook is open/file-locked) — **data-dependent, not a
  code regression**.

## Config & user input (in `Pipeline2App/`)

```
config_project/                  <- per-project config (config.CONFIG_PROJECT)
  project_params.yaml            <- config.PARAMS_FILE (grouped by concern + commented;
                                    round-tripped by the GUI via ruamel, preserving comments)
  input_docs/   column_map.csv, signal_types.csv,
                iolist_columns.csv, iolist_permanent_parts.csv   (config.INPUT_DOCS_DIR)
  diagnosis/    diagnosis_columns.csv, diagnosis_logic_rules.csv (config.DIAGNOSIS_DIR)
  block_templates.json           <- config.BLOCK_TEMPLATES_JSON (the key inventory)
user_input/
  error_management.csv           <- config.USER_INPUT (user-edited treatments, persist between runs)
```

`project_params.yaml` carries only real project paths (the two workbook paths + project knobs);
the layout plumbing (device DB, interface template, output dir) is **config-defaulted** to the
Shared copies, so those keys can be omitted.

A GUI-created **project** is a separate self-contained directory — `<config.PROJECTS_DIR>/<name>/`
with its own `project.yaml`, `Input/` (copied workbooks), and `Output/` tree — that **reuses** these
app-level config CSVs + the `Shared/` data (only inputs + outputs are per-project). See `project.py`.

## Output tree (`Shared/OutputTree/`)

Every writer asks `config.out_path(out_root, key)` for its destination instead of hardcoding a
folder; `out_root = config.output_root(params)` (default `OUTPUT_ROOT = Shared/OutputTree`; a
**project** carries `output_dir: Output`, which `load_params` resolves to an absolute
`<project>/Output` so the project writes into itself; an absolute `output_dir` also wins). The
semantic keys (`config.OUTPUT_PATHS`):

| key | path under the output root | written by |
|---|---|---|
| `validation_report` | `Reports/documents_validation_report.{txt,html}` | `validation.write_log` |
| `coverage_report` | `Reports/io_project_coverage_report.{csv,txt}` | `verify.py` |
| `io_database` | `ProjectDocumentation/InformationDatabase/IODatabase.csv` | `block_templates.staged` |
| `diagnosis_dir` | `ProjectDocumentation/InformationDatabase/DiagnosisData/` (`DiagList_IO.csv`, `DiagList_Logic.csv`) | `outputs` / `diagnostic_opc` |
| `interfaces_dir` | `ProjectDocumentation/InformationDatabase/Interfaces/` (`IF_*.xlsx`) | `interface_tool` |
| `hardware_dir` | `TiaPortalProjectInterface/BuilderData/HardwareConfiguration/` (`Stations.csv`, `Modules.csv`) | `hardware` |
| `blocks_creation_dir` | `TiaPortalProjectInterface/BuilderData/SoftwareBlocks/CreationInfo/` (`<NN_Name>.csv`, `InstanceDBs.csv`, `SoftwareBlocks.xlsm`) | `softwareblocks` / `blockshells` |
| `blocks_import_dir` | `TiaPortalProjectInterface/BuilderData/SoftwareBlocks/ImportReady/` (`*.db`, `Diagnostic_for_OPC.scl`) | `outputs.write_dbs` / `diagnostic_opc` |
| `io_tags_dir` | `TiaPortalProjectInterface/BuilderData/PlcTags/` (`PLCTags.xlsx`) | `outputs.write_io_tags` |
| `populated_iolist` | `ProjectDocumentation/InformationDatabase/PopulatedIoList/` (the populated `.xlsx`) | `iolist_diag.populate` |

SoftwareBlocks deliberately splits **`CreationInfo/`** (the generation artifacts — the builder
CSVs + shell workbook) from **`ImportReady/`** (the `.db` files + the OPC SCL that `Open2App`
imports directly).

### Renamed artifacts (for grepping the old names)
`CentralDatabase.csv` → `IODatabase.csv` · `validation_log.{txt,html}` →
`documents_validation_report.{txt,html}` · `coverage.{csv,txt}` →
`io_project_coverage_report.{csv,txt}` · `List_IO.csv`/`List_Logic.csv` →
`DiagList_IO.csv`/`DiagList_Logic.csv` · `permanent_parts.csv` → `iolist_permanent_parts.csv` ·
`params.yaml` → `project_params.yaml` · `config/` → `config_project/` (`input_docs/` +
`diagnosis/`) · `safetydb/` → `pipeline2/core/` · `Output/` → `Shared/OutputTree/` ·
`Templates/` → `Shared/Templates/` · `HardwareConfig/` → `Shared/HardwareConfigBuilderData/`.

## Source documents & real I/O List layout

The real I/O List + C&E paths come from `project_params.yaml`; clean sample docs that validate
live in `Shared/DocumentsValidationData/Passing/`. The I/O List sheet is e.g. `NET SAFETY 50`,
header row 1. **`io_list.sheet` may be a single name or a list** — staging reads every listed
sheet and concatenates the rows (each tagged with its `_source_sheet`/`_source_row` so GUI
links jump to the right cell); the interface generator scans them all too. Columns that matter
(by letter): F=ID (node), G=Bit (**full address** like `I0.0`, or the interface base byte),
O/P/Q=Functional unit/Location/Device, R=Type (hardware), AA=Skip Reason, **AB=Script Type**
(the signal type — incl. `PLC`/`PlcCardCm`/`IOC`), AC=Suggested Type, AD=Index, AE/AF=Diag
Cabinet/Bit, **AG=Hardware Parameters**. `FLD` = Functional unit + Location + Device (the
device key used everywhere).

## Signal types (`config_project/input_docs/signal_types.csv`)

One row per type (incl. `IOC` interface + the pattern type `Z#` emergency-area). **Names and comments are
per-type `{canonical}`-interpolation TEMPLATES** resolved per row (`outputs._interp`):
- `tag_name` — the I/O tag name (`''` ⇒ the type isn't tagged on its own, e.g. a channel-2
  type that shares its sibling's device tag);
- `db_element` — the **DB member** name (the full name, not a suffix);
- `io_comment` — the tag + DB-member comment;
- `diag_desc` — the diagnosis alarm/warning description (enriched onto the row, surfaced in the
  CentralDatabase + List_IO/List_Logic).

Other columns: `type_id_desc`, `category` (Safety/Diag/Std/Interface), `pair_key`+`channel`
(paired channels E/B/N/DI/F = x1/2+x2/2), `is_pattern`, `tagtable_name` (PLC tag-table Path; a
channel-2 type with a blank one **inherits its sibling's** by `pair_key`), `db_kind`
(`db`/`safe_db`), `db_names` (**`|`-separated** — several identical DBs / types may share one),
`in_diag`, `diag_logic` (`mirror`→ML TRUE / `invert`→ML FALSE / blank→from `normal_condition`),
`ce_mandatory` (reverse-C&E rule, `validation.check_ce_mandatory`: `yes`→must be in the C&E
else **ERROR**, `warn`→else **WARNING**, `no`/blank→not required), and `diag_container_check`
(which diagnosis cabinet a diagnosed signal maps to — used by `iolist_diag`).

The current keys are the migrated single-letter scheme: encoder `N` (was `ENC`), reset `R*`/`R#`
(was `RES`), emergency-area `Z#` (was `FA#`), fire-alarm `F` (new); `Z#` and `F1/2` are now
`in_diag=yes`. The `iolist_diag` suggested-type port still emits the **legacy** names and maps
old→new, so the catalogue stays the source of truth. **Object grouping** for the populator lives in
the sibling `config_project/input_docs/object_families.csv` (one row per family: `key`, members,
`anchor`, `link` channel/series/fld/pattern/none, `index_stride`, `bits`, `diag_block`).

## Output rules (current)

- **I/O tags** — a single TIA-style workbook `PlcTags/PLCTags.xlsx`: a `PLC Tags` sheet
  (`Name, Path, Data Type, Logical Address, Comment, Hmi Visible/Accessible/Writeable,
  Typeobject ID, Version ID`; **all values text**, Hmi flags `"True"`, addresses **%-prefixed**
  `%I20.0`) + a `TagTable Properties` sheet of the distinct tables. **`Path` = the type's
  `tagtable_name`** (types sharing one land together). **Tag name + comment come from the
  type's `tag_name` / `io_comment` templates.** Only resolved non-interface types with an I/Q
  bit **and a non-empty `tag_name`** become tags.
- **DBs** — grouped by `db_names` over **all rows** of flagged types (so PA, no I/O address,
  still gets its DB); fail-safe if any contributing type is `safe_db`. Every DB opens with
  `ALWAYS_FALSE` + `ALWAYS_TRUE`. Each member is `"<db_element>" : Bool; //<io_comment>`. The
  `.db` files land in `ImportReady/`; on re-run the `ImportReady/` + `PlcTags/` slots are swept
  of prior artifacts.
- **Diagnosis** (`diagnostic_opc.py`) — writes `DiagnosisData/DiagList_IO.csv` (in-diagnosis
  rows A/W/PA/PW/DD), `DiagList_Logic.csv` (rule-generated), and **`ImportReady/
  Diagnostic_for_OPC.scl`** (the OPC alarm/warning bindings — fills the `06_Diagnostic for
  OPC.scl` template directly; Pipeline2 owns this text fill).
  - The `>List_IO`/`>List_Logic` **columns are config-driven** (`diagnosis/diagnosis_columns.csv`:
    `header,expression` where `expression` interpolates `{CentralDatabase column}` tokens); the
    one hardcoded column is **`PLC_Binding`** (sentinel `$PLC_Binding$` → `outputs.plc_binding`:
    `"<leftmost db_name>"."<name_in_db>"` → `"<name_in_tagtable>"` → `bit`).
  - **`diagnosis/diagnosis_logic_rules.csv`** (`name,required_types,dev_type,db_name,member`):
    when all `required_types` (`|`-sep `script_type`s) are present in a cabinet,
    `diagnosis_rules.build_list_logic` emits a `>List_Logic` entry at the **next free bit** of
    that cabinet's alarm/warning family, IN binding `"<db_name>"."<member>"`.
  - **SCL fill**: one FUNCTION, one REGION per cabinet (cabinet→FLD+`TemplateType` from the I/O
    List **`DiagnosticBlocks`** sheet). Per cabinet: a CabState call + one `BoolToUDInt` call
    per packed DWord. Channels: `IN_xx`=`PLC_Binding`, `ML_xx`=`outputs.ml_value`,
    `FL_xx`=`"PROFINET_ALARMS"."<node profinet_name>_<subnet>"`; only assigned channels are
    emitted. Alarm vs warning = `type_hw` ends `W`; `diag_bit` 0-31→DWord1, 32-63→DWord2,
    channel=`bit%32`. The cabinet **`TemplateType`** (1-4) picks the `#Template` variant;
    **Tristate** (2/4) pairs each alarm DWord with its warning DWord.
- **Hardware** Stations/Modules (format 2), from the I/O List + the global
  `DeviceTypesDatabase`, into `HardwareConfiguration/`:
  - roles: Script Type `PLC`/`PlcCardCm` = heads, Type R first letter `P` = IoDevice;
  - a head is emitted only if its model is in the DTD — otherwise log **ERROR** (but
    **WARNING** for switches);
  - Station: Name=Profinet name, Model Id=Part No (no spaces), PN empty, Subnet from IP,
    Group=`<FunctionalUnit>_IODevices`;
  - Modules: cards grouped by Slot (col E); a card whose Slot equals the device's own tag, or a
    `*_AutoPluggedCard`, is TIA-auto-plugged → no row; I Addr = Q Addr = card start byte;
    Comment from DTD;
  - **`PotentialGroup=1`** on the first card only; slots 2+ come from the I/O List (col AG);
  - default cards: DTD ids `<PARENT>:SUFFIX` → one Modules row per station of PARENT;
  - **DTD col-5 `Parameters` are applied by Open2App itself — never written to the output
    CSVs.** Only DTD col-6 "Parameters by Signal Type", col-7 "I/O Addresses Parameter", and
    the I/O List col-AG "Hardware Parameters" are written. **I/O List (AG) params override
    everything, written last.**
- **Interfaces** (`interface_tool.py`) — a row with Script Type `IOC` and Index `MACHINETYPE-nn`
  (e.g. `SORTER-01`): the machine type selects a sheet in
  `Shared/Templates/MachineInterfaces/TEMPLATE_INTERFACES_v0.0.xlsx` (one per type + `<GENERIC>`
  fallback), copied to `Interfaces/IF_<instance>.xlsx`; plugs Base Address (Bit/col G), Base
  Node (ID/col F) into the Side-1 cells and the index into `<index>` tokens. Existing files
  preserved on re-run.

## Software-block templates (tooling, not the pipeline)

TIA Portal Software Block exports live in `Shared/Templates/Tia Portal Software Blocks/*.xml`
and carry placeholders `!!key$$` (e.g. `!!NetworkComment$$`, `!!03_FDBACK_RAW.{db_element}$$`,
`!!tagName:Contactor1_QBadInput$$`, `!!instanceOf-FDBACK$$`). The **whole inner string is the
key** — each distinct placeholder is its own slot. DB-member keys use the **`<DB>.<member>`
struct form** (e.g. `02_COM.{db_element}`, `05_EM_STATE.{matrix_area}_Q`,
`04_SPEED.{db_element:ENC1/2}`). FB-instance keys use **`instanceOf-<FB>$$`** (hyphen — `:` is
invalid in TIA DB names).

`python -m pipeline2.blocks.block_templates keys` (or the GUI panel) scans them into
`config_project/block_templates.json` = `{ template-file-stem : { key : "" } }` (merge-only) —
the **key inventory** that `sync_builders` uses to (re)stub `block_builders.py`. **Generation
is imperative Python, not a DSL**: `block_builders.py` has one `build_*(db)` per template that
**you edit**, and `softwareblocks.py` is the engine.

- `block_builders.py` — each builder gets `db` (the CentralDatabase: staged row dicts with
  `matrix_areas` + `name_in_db`) and returns a list of **instances**, one per `@` row. An
  instance is `{ "<!!key$$>": value }`: a `str` is one cell; a `list[str]` is the horizontal
  **ITERATOR**; `"_pad"` overrides the pad element (default `PAD = "Always TRUE"`). Each builder
  carries `# $keep` / `# $replace`: `sync_builders` re-stubs the `# $replace` ones with the
  template's current keys and adds new templates, but preserves `# $keep` functions verbatim.
  **All 8 builders (`00/02/03/04/05/06/07/08`) are written and generate.**
- `softwareblocks.py` — loads `db`, calls each builder, writes `CreationInfo/<NN_Name>.csv`
  (filename **drops the `TEMPLATE--vX.Y--` prefix**) in the SoftwareBlocksBuilder format —
  markers `$` (template dir), `#`, `%` (`TemplateType` + sidecar-derived meta columns + `!!key$$`
  cols), `@` (one instance). **TemplateType is zero-padded 2-digit**; how it's picked + the meta
  columns come from the template's sidecar `<stem>.csv` (`_load_sidecar`):
  - *single-capacity* (`02/03/06`): meta = Capacity/Index + `#Elements Needed`; the list-valued
    key is the ITERATOR, padded to the smallest Capacity ≥ its length.
  - *multi-family* (`05`): >1 `#Templates Capacity <family>` column; fixed numbered slots;
    `_sizes = {family: count}`, `_pick_multi` picks the smallest sufficient variant.
  - *doors* (`04` ESTOP): Machine Type / Capacity Doors / Index sidecar; `_template_type` via
    `estop_template_type(door_count)`; ITERATOR not padded.
  - *purpose / builder-set* (`08`): `#Templates Purpose` → meta = just `TemplateType`; instance
    sets `"_template_type"` per @row.
  - *no sidecar* (`00/07`): meta = just `TemplateType`; a no-sidecar list-iterator template
    (`00`) renders **vertically**, `TemplateType=01`.
  `_pad`/`_sizes`/`_template_type` are control keys, never emitted; `_pad` defaults to `"Always
  TRUE"` (`06` uses `"Always FALSE"`). `!!ITERATOR_STRINGS$$` is the **last** `%` column.
- **InstanceDBs** — every non-empty `!!instanceOf-<FB>$$` @-value is written to
  `CreationInfo/InstanceDBs.csv` (`Name,InstanceOf,Number,Folder`). Each `<FB>` is backed by a
  `.db` template in `Shared/Templates/Tia Portal Software Blocks/InstanceOf/`.
- **Pipeline2 deliberately STOPS at the CSV**; `Open2App` fills the template XML from it and
  imports it (`TiaPortalOpenness.Blocks.cs::ImportPlcBlock`). A future shared library may unify
  the two.

To author the builders, inspect `IODatabase.csv` (`python -m pipeline2.blocks.block_templates
staged`, or the GUI Configuration tab's Block-templates panel) — canonical columns +
`matrix_areas` + `IsSorterArea` + the three identity columns + `subnet_name` + per-node
`I_/Q_ start/end byte` + `diag_desc` + `diag_block_name`/`diag_block_template` + `source_cell` +
`_source_sheet`/`_source_row`/`type_id_resolved`/`type_category`. A row's three identities (each
`''` when N/A): **`name_in_db`** = the `.db` member name (use for `<DB>.<member>` keys);
**`name_in_tagtable`** = the PLC I/O tag name (use for `tagName:` keys); **`tagtable`** = the
tag-table that tag lands in; **`datablocks`** = the DB(s) the member belongs to. **`matrix_areas`**
(`'|'`-joined) is added in staging (`core/matrix.py`, from the C&E; `''` if the C&E doc is
absent): an **input** gets the area columns marked `X` on its CAUSE&EFFECT MATRIX row; an
**output** gets the AREA n sheet(s) listing that Q address. Paired channels of one device share
the union.

## DeviceTypesDatabase (global, manually maintained)

At `Shared/HardwareConfigBuilderData/DeviceTypesDatabase.csv` (config.DEVICE_TYPES_DB_DEFAULT).
The loader sniffs `,` vs `;`. 7 columns: Identifier, Type, Order Number/FW, Comment, Parameters
(`|`), Parameters by Signal Type, I/O Addresses Parameter. Not generated by this tool — read
only.

## Delimiters

**Comma everywhere.** All CSVs this tool reads and writes are comma-delimited; the loaders still
**sniff** `,`/`;` so older `;` files keep loading, but writers emit comma (Python's `csv`,
`QUOTE_MINIMAL`). Custom parameters use `|` internally, so they never need quoting. Open2App's
C# `CsvTable` uses the same comma default + quoting and tolerates Excel's delimiter padding
(`#!format=2,,,,`). (`project_params.yaml csv_delimiter` = `,`.)

## Conventions & gotchas

- Tag/device strings like `=S1`, `+MS1.CC1`, `-S67001` are **text** in the real docs; in
  synthetic test fixtures force them literal (`cell.data_type="s"`) or openpyxl treats a leading
  `=` as a formula (reads back empty with data_only).
- Header matching is **prefix** + whitespace-collapsed (real headers wrap and carry suffixes
  like `(1° part)`).
- The app lives at `C:\Source\Repos\_Openn2\Pipeline2App`. `_Openn2` is not a git repo yet —
  no commit target until it's initialised. **The earlier `Openn2` clone (`Excel
  Resources\DatabaseTool`) is the pre-reorg copy; don't edit it.** When git is set up, end
  commit messages with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Run/test from the `Pipeline2App` root: GUI `python launch_gui.py` (or `pythonw …` for no
  console); designer `python launch_designer.py`; headless `python run.py [--strict]`;
  validation only `python run_validation.py`; one check `python test_staging.py` etc.
- `Shared/OutputTree/`, regenerable `.xlsx`/`.xlsm`, `demo/*.xlsx`, `__pycache__/` are
  throwaway/gitignored once git is set up.

## Status & still to build

Pipeline (staging → validation → outputs), both GUIs, the coverage report, the full
software-block path (all 8 builders → `CreationInfo/<NN_Name>.csv` + `InstanceDBs.csv`), and the
diagnosis path (`DiagList_IO` + rule-generated `DiagList_Logic` + the OPC `.scl`) are done. Also
done: the **5-phase validation interface** with **Phase 0A** + EN/IT (`i18n`), the **error
registry** (`user_input/error_management.csv` + warn/skip/skip_type), the partial-match
**both-workbooks links**, the folder-based **Project Manager**, the slim **designer GUI**
(shipped as a one-folder `.exe`), the **`_Openn2` relocation** (the `pipeline2/` package on
`Shared/OutputTree/`, with `validation.py`/`gui.py` split), and the **`iolist_diag` populator** —
the pre-staging stage that fills `script_type`/`index`/`diag_cabinet`/`diag_bit`, generates
`DiagnosisBlocks`, reports unresolved entries, and halts the run before staging (verified by the §13
acceptance test against the golden). The data-independent `test_*.py` are green. Remaining:

- **`05_Output Feedback`** only defines `tagName:` keys up to ~Contactor2/4, but `block_builders`
  emits `Contactor3/4/5_*` for projects with more contactors → those keys are dropped. Extend
  the template (or cap the builder) for >2-contactor groups.
- Diagnosis **List_Logic rules** are seeded with the encoder example; add more rules to
  `diagnosis/diagnosis_logic_rules.csv` as needed.
- **Phase 0B** (C&E Matrix standalone validation) is a placeholder — implement it symmetric to
  0A when the matrix-only checks are defined.
- **InstanceDBs `Folder`** is the `<FB>` suffix; add an FB→folder map for friendlier TIA folder
  names. `ESTOP1`/`FDBACK` appear in the list but still need their `.db` templates in
  `Shared/Templates/Tia Portal Software Blocks/InstanceOf/`.
- **Block CSV names** still carry `[ … ]` brackets / old wording from `signal_types.csv` —
  retune those templates to drop them.
- **`iolist_diag` follow-ups**: fire-alarm `script_type` can't be auto-derived (the ladder yields
  `???` → `<input required>`) and the contactor series `KIx/n` channels are human refinements (the
  ladder emits bare `KI`) — both need manual entry on a fresh list. The populator **owns the diagnosis
  numbering**: a fresh list (empty AE) is numbered from scratch and the run is idempotent on its own
  output; a **fully-populated** list (existing `DiagnosisBlocks` + every AE filled) is left untouched
  (the sheet isn't regenerated), so a human numbering survives. The unhandled edge is a *partial*
  hand-edit that both leaves some AE blank **and** reorders nodes — recompute from a blanked AE in that
  case. Per-area reset `R#`/`R2` is indexed via its family but isn't a catalogue pattern (add an `R#`
  row to validate it). Minor/observability follow-ups from the review: `diag_container_check` is loaded
  but routing is derived from `node_fl` + the family `diag_block` (equivalent, kept data-driven); a
  channel-pair FLD-mismatch is reported with its own reason but not a separate ERROR count. No GUI
  button yet (CLI + `run.py` only).
- **Deferred follow-ups**: rework `gui_designer.spec` + the `.exe` build for the new tree, and move
  the root `test_*.py` into a `tests/` subfolder. (Done since the reorg: the doc/print-staleness
  sweep; the self-contained-project Manager rework — name-prompted New/Save As, `Input/`, per-project
  `Output/`; `git init` `_Openn2` on branch `tia181920`; and the `iolist_diag` populator.)
- Out of scope here: filling the template XML (and the InstanceOf `.db` templates) from the CSV
  is **Open2App's** job (Pipeline2 stops at the CSV).
