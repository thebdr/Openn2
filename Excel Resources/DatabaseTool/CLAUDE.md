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
    `load_device_types_db`, `resolve_type` (pattern-aware), `parse_params_by_type`.
  - `staging.py` — `load_io_list`: reads the I/O List by **column position**
    (header verified by prefix; the doc has duplicate "Description language"
    headers and newline-wrapped headers, so a name map is unsafe). Excludes
    struck rows and rows with a Skip Reason. Resolves each row's signal type.
  - `validation.py` — `validate`: C&E matrix + `AREA n` sheets vs the I/O List.
  - `outputs.py` — I/O tags, DBs, diagnosis List_IO.
  - `hardware.py` — `extract`: format-2 Stations + Modules.
- `config/` — versioned config: `column_map.csv`, `signal_types.csv`, `params.json`.
- `run.py` — the pipeline CLI: documents → staging → validation → every output
  (I/O tags, DBs, diagnosis, hardware, interfaces). Resolves all paths relative to
  itself, so it runs from any cwd. `--strict` fails on validation FAILs; it exits 1
  on a hardware ERROR (device not in the DeviceTypesDatabase), 2 on a missing doc.
- `gui.py` — Tkinter operator window "**Pipeline2**" (the interactive twin of
  `run.py`): toolbar with **Run All** + one button per phase, a colour-coded **Log**
  viewer, and a **Configuration** tab that edits `params.json` and opens the config
  CSVs. The pipeline runs on a worker thread (queue → `root.after` drain) so the UI
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
  (merge-preserving); `staged` exports the staged DB to `Output/staged.csv` for inspection.
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

21 types incl. `IOC` (interface) and pattern type `FA#` (matches FA1, FA2…).
Per type: `category` (Safety/Diag/Std/Interface), `pair_key`+`channel` (paired
channels E/B/ENC/DI = x1/2+x2/2), `in_diagnosis`, `db_kind` (`db`/`safe_db`),
`db_names` (**`|`-separated** — a type may feed several identical DBs; types may
also share one), `add_to_name` (text appended to each **DB member** name; `{canonical}`
tokens are replaced by that column's value from the source row, e.g. `{profinet_ip}`),
`tagtable_name` (the PLC tag-table the type's I/O tags go to). A paired channel-2 type
with a blank `tagtable_name` **inherits its sibling's** (same `pair_key`) so both
channels land in one table; an explicit value always wins.

## Output rules (current)

- **I/O tags** — a single TIA-style workbook `Output/IoTags/PLCTags.xlsx`: a
  `PLC Tags` sheet (`Name, Path, Data Type, Logical Address, Comment, Hmi Visible/
  Accessible/Writeable, Typeobject ID, Version ID`; **all values text**, Hmi flags
  `"True"`, addresses **%-prefixed** `%I20.0`) + a `TagTable Properties` sheet of the
  distinct tables. **`Path` = the type's `tagtable_name`** (types sharing one land
  together). Tag name = type description + FLD, except PA/PW/A/W use Description
  language 1 (p1 + p2). Comment = `[<ScriptType> <Index>] <descr> [<drawing> <sheet>]`.
  Only resolved non-interface types with an I/Q bit become tags.
- **DBs** — grouped by `db_names` over **all rows** of flagged types (so PA, no I/O
  address, still gets its DB); fail-safe if any contributing type is `safe_db`. Every
  DB opens with `ALWAYS_FALSE` + `ALWAYS_TRUE`. Each member is `"<tag name><add_to_name>"
  : Bool; //<tag comment>` (the same comment string as the I/O tag). On re-run the
  `DBs/` and `IoTags/` folders are swept of prior artifacts so only the current run
  remains.
- **Diagnosis** `List_IO` — in-diagnosis rows (A/W/PA/PW/DD) in the SWP_04
  17-column layout. (List_Logic / generated alarm PLC code come later.)
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
`{ template-file-stem : { key : <binding> } }`. It **merges**: existing template/key
bindings are kept, only new ones are added (default binding `""`); keys dropped from a
template are kept and just noted. A binding is one of: a **canonical column name**
(`"device"` → that row's value), a **literal list** (`["a","b"]`), or a **query** over the
staged DB (object; the query schema + the actual template-filling generation are still
to build). To author bindings, inspect the data with `python block_templates.py staged`,
which writes `Output/staged.csv` (canonical columns + `matrix_areas` +
`_source_sheet`/`_source_row`/`type_id_resolved`/`type_category`); open it in the
Pipeline2 **Files** tab and use the regex **Filter rows** to prototype queries. CSV was
chosen for inspection because it opens in that editor; if real SQL is wanted later, an
SQLite export is the alternative. **`matrix_areas`** (`'|'`-joined, e.g. `AREA 1|AREA 2`)
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

## Still to build

- Diagnosis **List_Logic** + the generated alarm PLC code — the user will supply the
  format (their SWP_04 workbook). `List_IO` is done; this is the remaining diagnosis
  output, to be wired into `outputs.py` + `run.py` once the format is known.
- **Software-block generation** — resolve the `config/block_templates.json` bindings
  (canonical column / literal list / query) against the staged DB and fill the
  `!!key$$` placeholders in the template XML to emit per-instance blocks. The binding
  schema (esp. the query form) and the iterator semantics (`ITERATOR_STRINGS`) are TBD.
