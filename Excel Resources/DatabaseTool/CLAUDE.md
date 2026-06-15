# DatabaseTool — Safety DB pipeline (Python)

Python rebuild of the safety-database workflow that used to live in the
Power Query / VBA workbooks under `Excel Resources/` (`3_Database`, `2_HwPlc`,
`1_SwPlc`). It replaces them — those workbooks and the `4_PowerQuery` scaffold
are **legacy**. (The root `CLAUDE.md` documents the separate Openn2 C# Openness
app; this file covers only this tool.)

Pipeline: **documentation → staging → validation → database/outputs**

```
I/O List + C&E matrix (customer Excel docs, authored by hand)
   → staging        canonical rows, strikethrough/skip-reason aware
   → validation     C&E + AREA cross-checks → ISSUES log (cell-addressed)
   → outputs        I/O tag tables + DBs, diagnosis List_IO, hardware
                    Stations/Modules, interface I/O tables
```

## Why Python (not Power Query / VBA)

openpyxl reads cell **strikethrough** directly (the thing PQ/VBA couldn't), it
runs and tests **without Excel** (no COM, no zombie processes — that path was
painful), and everything versions cleanly as text. Prefer pure Python here;
don't reach back for Power Query or VBA.

## Layout

- `safetydb/` — the package:
  - `config.py` — loads `config/*.csv` + `params.json`; `load_signal_types`,
    `load_device_types_db`, `resolve_type` (pattern-aware), `parse_params_by_type`,
    `sorter_areas` (the `params.json` `"sorter_areas"` list → which AREAs are sorter-style).
  - `staging.py` — `load_io_list`: reads the I/O List by **column position**
    (header verified by prefix; the doc has duplicate "Description language"
    headers and newline-wrapped headers, so a name map is unsafe). Excludes
    struck rows and rows with a Skip Reason. Resolves each row's signal type.
  - `validation.py` — `validate`: C&E matrix + `AREA n` sheets vs the I/O List, plus
    `check_diagnosis_bits` (always runs, I/O List only): every in-diagnosis signal must
    carry a numeric Diag Cabinet (AE) + Diag Bit (AF), and (cabinet, bit) must be unique
    within its alarm/warning family (col R 'Type' ending 'W' = warning) - missing/invalid
    or colliding slots are FAILs. Each `LogEntry` carries the source `path` (I/O List vs
    C&E doc) so the GUI links the right workbook/cell.
  - `outputs.py` — I/O tags, DBs, diagnosis List_IO (config-driven columns + `plc_binding`/
    `ml_value`).
  - `hardware.py` — `extract`: format-2 Stations + Modules.
  - `staging.load_diagnostic_blocks` — the I/O List `DiagnosticBlocks` sheet
    (`{cabinet_id: {index, fld, template_type}}`).
- `config/` — versioned config: `column_map.csv`, `signal_types.csv`, `params.json`,
  `diagnosis_columns.csv` (>List_IO/>List_Logic columns), `diagnosis_logic_rules.csv`.
- `run.py` — the pipeline CLI: documents → staging → validation → every output
  (I/O tags, DBs, diagnosis, hardware, interfaces). Resolves all paths relative to
  itself, so it runs from any cwd. `--strict` fails on validation FAILs; it exits 1
  on a hardware ERROR (device not in the DeviceTypesDatabase), 2 on a missing doc.
- `gui.py` — Tkinter operator window "**Pipeline2**" (the interactive twin of
  `run.py`): toolbar with **Run All** + one button per phase, a colour-coded **Log**
  viewer, and a **Configuration** tab that edits `params.json`, opens the config CSVs,
  and has a **Block templates** panel (scan → `block_templates.json`, edit it, export
  the Central Database CSV — see "Software-block templates"). The pipeline runs on a
  worker thread (queue → `root.after` drain) so the UI
  stays responsive, mirroring Openn2's `TiaWorker`. **Clickable links**: a validation
  `Sheet!Cell` or a hardware `row N` log line carries an `[open …]` link that opens the
  source workbook in Excel **at that cell and brings Excel to the front**, via
  **pywin32 COM** (`win32com` reuses a running Excel; `win32gui` AttachThreadInput
  forces focus). COM is initialised on the click worker thread; if pywin32 is missing
  it falls back to `os.startfile`. It calls the `safetydb` modules directly (not
  `run.py`) so it can attach those cell links. **Dark-mode** toggle (toolbar) and
  Consolas-16 notebook tabs; all theming lives in `theme.py` (light/dark palettes,
  ttk 'clam' recolour, log tag colours). Window icon: `assets/Pipeline2.ico|png`.
- `theme.py` — light/dark palettes + `apply_ttk` (tab font, widget colours), log tag
  colours, the table font, and the zebra stripe colours. Shared by gui + editor.
- `assets/` — app icon for `gui.py` (see `assets/README.md`).
- `editor.py` — the GUI's **Files** tab: a file tree (config + `HardwareConfig` +
  `Output`) beside a `FileEditor`. `.csv` and `.xlsx`/`.xlsm` open in a **tksheet**
  spreadsheet grid (Consolas font; in-cell edit, multi-select, copy/paste, undo,
  right-click insert/delete row & column; steel-blue header + **zebra rows**
  light-blue odd / light-grey even; a **Filter columns** show/hide popup and a
  **Filter rows** popup — a regex per column, cascading AND, header row pinned,
  view-only via tksheet display_rows so edits/indices survive). CSVs
  read with delimiter sniffing, saved
  comma-delimited; xlsx edits round-trip via openpyxl (per sheet) and show formula
  strings, with a **Show values** checkbox that reloads cached values read-only.
  Other files (`.db`/`.json`/…) open in a text editor. Follows the GUI's dark mode.
  Reusable + meant to grow workflow-specific tooling. Tree refreshes after each run.
- `interface_tool.py` — standalone IOC interface-table generator (see below); also
  invoked by `run.py` and `gui.py`.
- `block_templates.py` — **tooling, not pipeline** (see "Software-block templates").
  `keys` scans the block templates for `!!key$$` placeholders → `config/block_templates.json`
  (merge-preserving) **and `sync_builders` regenerates `block_builders.py`** from it; `staged`
  exports the CentralDatabase to `Output/CentralDatabase.csv`. Wired into the GUI panel.
- `block_builders.py` — **you edit**: one `build_*(db)` per template returning instances.
  Each builder carries a `# $keep` or `# $replace` marker: `sync_builders` re-stubs the
  `# $replace` ones with that template's current keys (in the docstring) and adds new
  templates, but preserves `# $keep` functions verbatim. The GUI reloads this module
  before each SoftwareBlocks/Coverage run so live edits are picked up.
  `softwareblocks.py` — the engine that writes the SoftwareBlocksBuilder CSV(s) to
  `Output/SoftwareBlocks/` (see "Software-block templates"), honoring each template's
  shell directive (keep/fill/override).
- `blockshells.py` — the per-template **shell workbook** `Output/SoftwareBlocks.xlsm` (in
  the output folder; one sheet per template: `$ template=…`, a `$ <mode>` directive in B2,
  the `%` header with the template's keys, and the Capacity table — no `@` data; path via
  `blockshells.shell_path(params)`). `generate_shells` is additive
  (existing sheets/your overrides are kept). The mode in B2 drives generation:
  **keep** = the Python builder makes the CSV, sheet ignored; **fill** = builder makes the
  CSV *and* writes its `@` rows back into the sheet (to inspect/tweak); **override** =
  generation reads the `@` rows *from* the sheet (hand-filled) instead of running the
  builder. The `.xlsm` is regenerable + user-edited, so it is **not committed**.
- `diagnostic_opc.py` + `diagnosis_rules.py` — the diagnosis SCL generator + the
  rule-generated `>List_Logic` (see "Diagnosis" under Output rules). Wired into the
  pipeline DIAGNOSIS phase (`generate_for(db, params, out_dir)` reuses the staged rows).
- `verify.py` — **coverage check + report**: per CentralDatabase row, which outputs it
  lands in (io_tag/db/diagnosis/interface/hardware/block); flags **ORPHAN** (a *typed*
  row in no output) and **UNPLACED MEMBER** (a DB member not in any block ITERATOR — the
  worklist for finishing the builders). Untyped/spare rows aren't flagged. Writes
  `Output/Report/coverage.csv` (per-row matrix, Files-tab filterable) + `coverage.txt`.
  Wired into `run.py` (a COVERAGE section, lazy/guarded) and the GUI Block-templates
  panel (Generate SoftwareBlocks CSV · Coverage report · Open coverage report ·
  Generate block shells · Open shell workbook).
- `requirements.txt` — `openpyxl` (core); `tksheet` + `pywin32` (GUI). pywin32 is
  optional (Excel cell-jump falls back to `os.startfile` without it).
- `test_*.py` — plain-`python` test scripts (no pytest); each prints PASS/FAIL
  and exits non-zero on failure. Run them after any change.
- `Output/`, `Templates/*.xlsx` (except the committed interface template),
  `__pycache__/` are gitignored.

GUI: `python gui.py` (or `pythonw gui.py` for no console). Headless: `python run.py
[--strict]`. Run one check: `python test_staging.py` etc. Always invoke the copy under
`C:\Source\Repos\Openn2\...` explicitly (a sibling clone exists; a relative path can
run the wrong one).

## Source documents & real I/O List layout

Real docs live in `../3_Database/Source Data/` (paths in `params.json`). The I/O
List sheet `NET SAFETY 50`, header row 1. **`io_list.sheet` may be a single name or a
list** — staging reads every listed sheet and concatenates the rows (each tagged with
its `_source_sheet`/`_source_row` so the GUI links jump to the right cell); the
interface generator scans them all too. Columns that matter (by letter):
F=ID (node), G=Bit (**full address** like `I0.0`, or the interface base byte),
O/P/Q=Functional unit/Location/Device, R=Type (hardware), AA=Skip Reason,
**AB=Script Type** (the signal type — incl. `PLC`/`PlcCardCm`/`IOC`),
AC=Suggested Type, AD=Index, AE/AF=Diag Cabinet/Bit, **AG=Hardware Parameters**.
`FLD` = Functional unit + Location + Device (the device key used everywhere).

## Signal types (`config/signal_types.csv`)

One row per type (incl. `IOC` interface + pattern type `FA#`). **Names and comments are
per-type `{canonical}`-interpolation TEMPLATES** resolved per row (`outputs._interp`):
- `tag_name` — the I/O tag name (`''` ⇒ the type isn't tagged on its own, e.g. a
  channel-2 type that shares its sibling's device tag);
- `db_element` — the **DB member** name (the full name, not a suffix);
- `io_comment` — the tag + DB-member comment;
- `diag_desc` — the diagnosis alarm/warning description (enriched onto the row as
  `diag_desc`, surfaced in the CentralDatabase + List_IO/List_Logic).

Other columns: `type_id_desc`, `category` (Safety/Diag/Std/Interface), `pair_key`+`channel`
(paired channels E/B/ENC/DI = x1/2+x2/2), `is_pattern`, `tagtable_name` (PLC tag-table Path;
a channel-2 type with a blank one **inherits its sibling's** by `pair_key`), `db_kind`
(`db`/`safe_db`), `db_names` (**`|`-separated** — several identical DBs / types may share
one), `in_diag`, `diag_logic` (`mirror`→ML TRUE / `invert`→ML FALSE / blank→from
`normal_condition`).

## Output rules (current)

- **I/O tags** — a single TIA-style workbook `Output/IoTags/PLCTags.xlsx`: a
  `PLC Tags` sheet (`Name, Path, Data Type, Logical Address, Comment, Hmi Visible/
  Accessible/Writeable, Typeobject ID, Version ID`; **all values text**, Hmi flags
  `"True"`, addresses **%-prefixed** `%I20.0`) + a `TagTable Properties` sheet of the
  distinct tables. **`Path` = the type's `tagtable_name`** (types sharing one land
  together). **Tag name + comment come from the type's `tag_name` / `io_comment`
  templates.** Only resolved non-interface types with an I/Q bit **and a non-empty
  `tag_name`** become tags (so channel-2 types with blank `tag_name` are skipped).
- **DBs** — grouped by `db_names` over **all rows** of flagged types (so PA, no I/O
  address, still gets its DB); fail-safe if any contributing type is `safe_db`. Every
  DB opens with `ALWAYS_FALSE` + `ALWAYS_TRUE`. Each member is `"<db_element>"
  : Bool; //<io_comment>`. On re-run the
  `DBs/` and `IoTags/` folders are swept of prior artifacts so only the current run
  remains.
- **Diagnosis** (`diagnostic_opc.py`) — writes `Output/Diagnosis/`: `List_IO.csv`
  (in-diagnosis rows A/W/PA/PW/DD), `List_Logic.csv` (rule-generated), and
  **`Diagnostic_for_OPC.scl`** (the OPC alarm/warning bindings — fills the
  `06_Diagnostic for OPC.scl` template directly; Pipeline2 owns this text fill).
  - The `>List_IO`/`>List_Logic` **columns are config-driven** (`config/diagnosis_columns.csv`:
    `header,expression` where `expression` interpolates `{CentralDatabase column}` tokens);
    the one hardcoded column is **`PLC_Binding`** (sentinel `$PLC_Binding$` →
    `outputs.plc_binding`: `"<leftmost db_name>"."<name_in_db>"` → `"<name_in_tagtable>"` → `bit`).
  - **`config/diagnosis_logic_rules.csv`** (`name,required_types,dev_type,db_name,member`):
    when all `required_types` (`|`-sep `script_type`s) are present in a cabinet (matched
    rows' FLD → `DiagnosticBlocks`), `diagnosis_rules.build_list_logic` emits a `>List_Logic`
    entry at the **next free bit** of that cabinet's alarm/warning family, IN binding
    `"<db_name>"."<member>"` (`member` interpolates `{columns}`).
  - **SCL fill**: one FUNCTION, one REGION per cabinet (cabinet→FLD+`TemplateType` from the
    I/O List **`DiagnosticBlocks`** sheet via `staging.load_diagnostic_blocks`). Per cabinet:
    a CabState call + one `BoolToUDInt` call per packed DWord. FB instance = the DWord it
    backs (`S1.CABINET<idx>.ALARM1`; CabState = `…STATE`). Channels: `IN_xx`=`PLC_Binding`,
    `ML_xx`=`outputs.ml_value` (type `diagnosis_logic` mirror→TRUE/invert→FALSE, blank→from
    `normal_condition`), `FL_xx`=`"PROFINET_ALARMS"."<node profinet_name>_<subnet>"`; only
    assigned channels are emitted. Alarm vs warning = `type_hw` ends `W`; `diag_bit` 0-31→
    DWord1, 32-63→DWord2, channel=`bit%32`. The cabinet **`TemplateType`** (1-4) picks the
    `#Template` variant; **Tristate** (2/4) pairs each alarm DWord with its warning DWord
    (`Tristate_DW =>`, the "was-active" state) instead of carrying real warnings.
- **Hardware** Stations/Modules (format 2), from the I/O List + the global
  `DeviceTypesDatabase`:
  - roles: Script Type `PLC`/`PlcCardCm` = heads, Type R first letter `P` = IoDevice;
  - a head is emitted only if its model is in the DTD — otherwise log **ERROR**
    (but **WARNING** for switches);
  - Station: Name=Profinet name, Model Id=Part No (no spaces), PN empty, Subnet
    from IP, Group=`<FunctionalUnit>_IODevices`;
  - Modules: cards grouped by Slot (col E); a card whose Slot equals the device's
    own tag, or a `*_AutoPluggedCard`, is TIA-auto-plugged → no row; I Addr = Q
    Addr = card start byte; Comment from DTD;
  - **`PotentialGroup=1`** on the first card only; slots 2+ come from the I/O List
    (col AG) — the electrical designer decides per module;
  - default cards: DTD ids `<PARENT>:SUFFIX` → one Modules row per station of PARENT;
  - **DTD col-5 `Parameters` are applied by Openn2 itself — never written to the
    output CSVs.** Only DTD col-6 "Parameters by Signal Type" (`<ST>…<ST>`,
    `Ch(#)`→channel, literal `Ch(n)` kept), col-7 "I/O Addresses Parameter"
    (`%I%`/`%Q%` = device start byte, `+N` arithmetic), and the I/O List col-AG
    "Hardware Parameters" are written. **I/O List (AG) params override everything,
    written last.**
- **Interfaces** (`interface_tool.py`) — a row with Script Type `IOC` and Index
  `MACHINETYPE-nn` (e.g. `SORTER-01`): the machine type selects a sheet in
  `Templates/TEMPLATE_INTERFACES_v0.0.xlsx` (one per type + `<GENERIC>` fallback),
  copied to `Output/Interfaces/IF_<instance>.xlsx`; plugs Base Address (Bit/col G),
  Base Node (ID/col F) into the Side-1 cells and the index into `<index>` tokens.
  Existing files preserved on re-run.

## Software-block templates (tooling, not the pipeline)

TIA Portal Software Block exports live in `Templates/Tia Portal Software Blocks/*.xml`
and carry placeholders `!!key$$` (e.g. `!!NetworkComment$$`, `!!Error_memberOf:03_FDBACK$$`,
`!!tagName:Contactor1_QBadInput$$`). The **whole inner string is the key** — each distinct
placeholder is its own slot (so `tagName:Contactor1…` ≠ `tagName:Contactor2…`).

`python block_templates.py keys` scans them into `config/block_templates.json` =
`{ template-file-stem : { key : "" } }` (merge-only) — the **key inventory** that
`sync_builders` uses to (re)stub `block_builders.py`. **Generation is imperative Python,
not a DSL**: `block_builders.py` has one `build_*(db)` per template that **you edit**, and
`softwareblocks.py` is the engine. (The output CSV's `%` header keys come from each
builder's own instance keys, first-seen order, falling back to a template scan — not the json.)

- `block_builders.py` — each builder gets `db` (the CentralDatabase: staged row dicts
  with `matrix_areas` + `name_in_db`) and returns a list of **instances**, one per `@`
  row. An instance is `{ "<!!key$$>": value }`: a `str` is one cell; a `list[str]` is
  the horizontal **ITERATOR** (one per instance); `"_pad"` overrides the pad element
  (default `block_builders.PAD = "AlwaysTRUE"`). Row multiplication is just your loops.
  **All 8 builders (`00/02/03/04/05/06/07/08`) are written and generate.**
- `softwareblocks.py` — the engine: loads `db`, calls each builder, writes
  `Output/SoftwareBlocks/<stem>.csv` in the SoftwareBlocksBuilder format — markers `$`
  (template dir), `#`, `%` (meta columns + `!!key$$` cols), `@` (one instance) — and picks
  **TemplateType** per @row by one of **three sizing models** (from the sidecar `<stem>.csv`,
  which rides along in the meta columns):
  - *single-capacity* (`02/03/06`): sidecar `#Templates Capacity,#Templates Index`; the
    instance's one list-valued key is the ITERATOR, padded to the smallest Capacity ≥ its
    length (`_pick`); `#Elements Needed` = that length.
  - *multi-family* (`05`): sidecar with **>1** `#Templates Capacity <family>` column; fixed
    numbered slots (no ITERATOR). The instance adds `"_sizes" = {family: count}`;
    `_build_multi`/`_pick_multi` pick the smallest variant whose every family capacity ≥ that count.
  - *purpose / builder-set* (`08`): the instance sets `"_template_type"` = the Index per @row
    directly (08: 1 per sorter, 2 per door DQ; sidecar `#Templates Purpose`).
  `_pad`/`_sizes`/`_template_type` are control keys, never emitted as columns.
  `!!ITERATOR_STRINGS$$` is always the **last** `%` column (keyed by the list value when
  there are instances, by name for the empty-instance shell).
- The target/example is `SoftwareBlocksBuilder/test - Copy.csv`. **Pipeline2 deliberately
  STOPS at the CSV**; Openn2 fills the template XML from it and imports it
  (`TiaPortalOpenness.Blocks.cs::ImportPlcBlock`). A future shared library may unify the two.

To author the builders, inspect `Output/CentralDatabase.csv` (`python block_templates.py
staged`, or the GUI Configuration tab's Block templates panel) — canonical columns +
`matrix_areas` + `IsSorterArea` + the three identity columns below + `subnet_name` +
per-node `I_/Q_ start/end byte` + `diag_desc` + `_source_sheet`/`_source_row`/
`type_id_resolved`/`type_category`; open it in the Pipeline2 **Files** tab and use the
regex **Filter rows** to explore. A row's three identities (each `''` when N/A) — pick the
one a `!!key$$` expects: **`name_in_db`** = the `.db` member name (the type's `db_element`
template) — use for `…_memberOf:<DB>` keys; **`name_in_tagtable`** = the PLC I/O tag name
(the `tag_name` template) — use for `tagName:` keys; **`tagtable`** = the tag-table (Path)
that tag lands in; **`datablocks`** = the DB(s) the member belongs to (`'|'`-joined). **`matrix_areas`** (`'|'`-joined, e.g. `AREA 1|AREA 2`)
is added in **staging** (`safetydb/matrix.py`, from the C&E workbook; `''` if the C&E
doc is absent): for an **input** (I-address) it's the area columns marked `X` on that
signal's CAUSE&EFFECT MATRIX row (EFFECT block from column `S`; the area = the column
header); for an **output** (Q-address) it's the AREA n sheet(s) listing that Q address
(col C). Matched by the signal's own I/Q address, then **paired channels of one device
(same pair_key + FU+Loc+Dev) share the union** so e.g. `E2/2` inherits `E1/2`'s areas.

## DeviceTypesDatabase (global, manually maintained)

At `../../HardwareConfig/DeviceTypesDatabase.csv`. **Comma-delimited**, 7 columns:
Identifier, Type, Order Number/FW, Comment, Parameters (`|`), Parameters by
Signal Type, I/O Addresses Parameter. The loader sniffs `,` vs `;`. Not generated
by this tool — read only.

## Delimiters

**Comma everywhere.** All CSVs this tool reads and writes are comma-delimited:
config (`signal_types.csv`, `column_map.csv`), the global `DeviceTypesDatabase`,
and the format-2 outputs (`Stations.csv`/`Modules.csv`, plus the I/O-tag and
diagnosis CSVs). Writers use Python's `csv` module (`QUOTE_MINIMAL`): a field is
`"`-quoted only when it contains a comma or `"`. Custom parameters use `|`
internally, so they never need quoting. Openn2's C# `CsvTable` was switched to the
same comma default and quoting, and its `#!format=N` parser tolerates Excel's
delimiter padding (`#!format=2,,,,`). The loaders still **sniff** `,`/`;` so older
`;` files keep loading, but write comma. (`params.json csv_delimiter` = `,`.)

## Conventions & gotchas

- Tag/device strings like `=S1`, `+MS1.CC1`, `-S67001` are **text** in the real
  docs; in synthetic test fixtures force them literal (`cell.data_type="s"`) or
  openpyxl treats a leading `=` as a formula (reads back empty with data_only).
- Header matching is **prefix** + whitespace-collapsed (real headers wrap and
  carry suffixes like `(1° part)`).
- Working repo is this clone, `C:\Source\Repos\Openn2` (git remote
  thebdr/Openn2.git, branch upgrade_refactor_1). Commit here.

## Status & still to build

Pipeline (staging → validation → outputs), the GUI, the coverage report, the full
software-block path (all 8 builders → `Output/SoftwareBlocks/*.csv`; coverage = 0 orphans),
and the diagnosis path (`List_IO` + rule-generated `List_Logic` + the OPC `.scl`) are done;
the `test_*.py` suite is green. Remaining:

- Diagnosis **List_Logic rules** are seeded with the encoder example; add more rules to
  `config/diagnosis_logic_rules.csv` as the project needs them.
- Minor: confirm the `$` template-path prefix the SoftwareBlocksBuilder tool expects.
- Out of scope here: filling the template XML from the CSV is **Openn2's** job (Pipeline2
  stops at the CSV).
