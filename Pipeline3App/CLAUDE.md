# Pipeline3 — safety-document pipeline (clean-room rebuild)

`Pipeline3App` is a from-scratch rebuild of `Pipeline2App`, organized around
`assets/ButtonsLayout.xlsx` — the spreadsheet that lays out the operator GUI's phase bar and is
the canonical map of the pipeline. Pipeline2 grew through many reworks until its tested parts kept
crumbling as structure/formats/intermediates drifted; Pipeline3 treats Pipeline2 + the golden
documents as a **reference for intent** (not a golden source) and is rebuilt phase-by-phase, each
phase reviewed before the next. The approved design lives at
`~/.claude/plans/the-codebase-in-openn2-pipeline2app-rippling-canyon.md`.

Pipeline: **documents → fill → staging → validation + generators → reporting**

## The `_Openn2` monorepo

Pipeline3App is a sibling under `C:\Source\Repos\_Openn2`:

```
_Openn2/
  Pipeline3App/    <- THIS app (Python). The rebuild.
  Pipeline2App/    <- the pilot/reference (do NOT edit as part of P3 work).
  Open2App/        <- the C# WPF TIA-Portal Openness tool (imports what this app writes).
  Shared/          <- the handoff boundary (templates, device DB, golden docs, OutputTree).
```

`_Openn2` is a git repo on branch **`tia181920`** (local-only). `Shared/OutputTree/` is gitignored
(generated artifacts). **Pipeline3App has its OWN `config_project/` copy** — edit
`Pipeline3App/config_project/project_params.yaml`, NOT Pipeline2App's; they are independent.

## Core organizing idea: the phase registry

The workflow lives in exactly ONE place — the **phase registry** (`pipeline3/registry.py`),
populated by self-registering modules in `pipeline3/phases/`. The CLI and both GUIs consume the
same registry; there is no second hand-written ordering (Pipeline2's bug was encoding the order
twice — in `run.py` and the GUI). The phase bar **renders** by ascending number
(`presentation_order`); the engine **runs** by a real dependency DAG (`topo_order`, Kahn over each
phase's `requires`). "Run any phase" auto-runs its prerequisites.

### Sparse hierarchical numbering (`pipeline3/core/numbering.py`)
Every ordered enumeration uses gapped numbers so steps insert without renumbering:
- **Pipeline phases = hundreds**: `100, 200, … 900` (ButtonsLayout row 1).
- **Sub-phases / steps = parent + tens**: `110, 120, …` (ButtonsLayout col A = the slot id; a
  button's number = phase id + slot id).
- **Ones digit reserved** for finer inserts (e.g. `115` between `110` and `120`).

## The 9 phases (ButtonsLayout.xlsx)

| # | Phase | Buttons (number — label) | Status |
|---|---|---|---|
| 100 | Documents Validation | 110 Validate I/O List · 120 Validate C&E Matrix · 130 Cross-Check CEM→IOL · 140 Cross-Check IOL→CEM · 150 Validate Diagnosis Assignments | **DONE** |
| 200 | Documents Fill Out | 210 Fill Script Type · 220 Fill Index · 230 Fill Diag Cabinet · 240 Fill Diag Bit | **DONE** |
| 300 | Documents Staging | 310 Stage I/O List · 320 Generate IO Database | **DONE** |
| 400 | Interfaces Generation | 410 Generate Interfaces · 430 Generate Custom Interface… | **DONE** |
| 500 | Signals Mapping | 510 Generate I/O Tags · 520 Generate Data Blocks | **DONE** |
| 600 | Diagnosis Mapping | 610 Generate Diag List · 620 Generate Diag Software Blocks | **DONE** |
| 700 | Hardware Generation | 710 Generate Stations · 720 Generate Modules | **DONE** |
| 800 | Software Generation | 810 Empty Shells · 820 Generate Blocks · 830 Generate Instances | **SKELETON** (builders user-written) |
| 900 | Reporting | 910 Pipeline Coverage Report · 920 TIA Project Coverage Report | TODO (M7/future) |

True dependency DAG: `config → 200 Fill → 300 Staging → {100, 400, 500, 600, 700, 800, 900}`
(everything downstream depends only on Staging). **Two run profiles** share one engine: `main`
(full DAG) and `designer` (validation-only: `300 read-only stage → 100`, sub-phases 110–150).

## Package layout

```
pipeline3/
  app.py            # run_phase(ctx, n) / run_all(ctx) - topo-ordered, memoized, halt-aware
  phase.py          # Phase / SubPhase / PhaseResult / Button dataclasses
  registry.py       # PhaseRegistry: register / presentation_order / topo_order / profiles
  context.py        # PipelineContext (state threaded through phases)
  core/             # config.py, numbering.py, i18n.py, model.py, errors.py (treatment registry)
  io/               # workbook.py (THE shared reader), csv_tables.py, render.py
  phases/           # p200_fillout.py (+ p100…p900 as built)
  domain/iolist_diag/   # the populator internals (DONE)
  domain/{validation,blocks}/  hardware.py  diagnosis.py   # TODO
  cli/  gui/  project/                                     # TODO (M10–M13)
config_project/  user_input/  assets/  tests/{unit,golden}/
```

### Shared primitives (the contracts every phase obeys)
- **One workbook reader** — `io/workbook.py::open_sheet(...)`/`SheetView`. Owns the openpyxl
  load-mode policy (strike-aware `data_only=True`, non-`read_only`; `load_for_write` is
  formula-preserving for the populator), regex sheet resolution, by-**position** cell access, and
  the header check that **normalizes newline→space then prefix-matches**. Every phase reads through
  this — no other module opens a sheet for reading.
- **One log structure** — `core/model.py::LogEntry`. Fixed left/middle, variable right `detail`:
  `[LEVEL] <id>  <location>  | bit | FLD | desc_l1 | desc_l1b | drawing | type-index :: <detail>`.
  TWO index concepts: **`id` = `<phase>-<type>`** — a code-traceable **log-type index**; the `type`
  slug is the i18n key suffix (`v_<type>`) AND the grep anchor that leads to the exact builder (NOT a
  per-run ordinal). **`uid`** = a stable per-FAIL hash of the *finding* (phase+type+location+detail)
  — excludes the level/seq AND the workbook identity, so a treatment survives a doc revision. The
  **`location` is `Sheet!Cell` only — never the workbook name**; the workbook rides on
  `LogEntry.doc`/`doc2` (for the GUI link) and is not rendered; a cross-check's matched 2nd-workbook
  cell renders as ` -> <Sheet!Cell>`. `io/render.py::render_lines(log, errors_only)` renders both the
  complete report and the error-only view (PHASE+INFO+WARN+FAIL, dropping PASS/SKIP).
- **No hardcoded input columns** — all IoList/CE/AREA access resolves through `column_map.csv`
  (`config.load_column_map` / `iolist_diag.columns.ColumnResolver`). The only fixed integer columns
  are the two sheets Pipeline3 *generates* (DiagnosisBlocks, _UnresolvedIndex).

## Config & the Open2App contract

`core/config.py` anchors the layout (`APP_ROOT`, `CONFIG_PROJECT`, `SHARED`, `OUTPUT_ROOT`,
`PROJECTS_DIR`), loads `project_params.yaml` + the `config_project/` CSVs, and owns `OUTPUT_PATHS`.

**`OUTPUT_PATHS`** keys resolve under the output root (default `Shared/OutputTree`, or
`<project>/Output`). **Open2App imports ONLY from `TiaPortalProjectInterface/BuilderData/`** —
`hardware_dir`, `blocks_creation_dir`, `blocks_import_dir`, `io_tags_dir` (`config.OPEN2APP_KEYS`).
The `ProjectDocumentation/*` (IODatabase, DiagnosisData, Interfaces, PopulatedIoList) and
`Reports/*` trees are documentation/intermediate — NOT imported. Keep the BuilderData subpaths
byte-stable. There is one additive human-report key, `validation_errors` (the error-only report).

**Regex params** (`io_list.sheet`, `areas`, `safety_nets`) accept JS-style literals
(`/pattern/flags` or `pattern/gmi`) via `config.js_to_re`; the flags are stripped (matching is
case-insensitive). **In YAML they MUST be single-quoted** — a double-quoted `"\d"` is an invalid
escape and fails to parse.

## Phase 200 — Documents Fill Out (the populator) — DONE

`domain/iolist_diag/` + `phases/p200_fillout.py`. Fills the **SOURCE** I/O List **in place** — after
a fill the source workbook IS the populated document (staging/validation read it directly).
Idempotent + non-destructive (writes only blank cells; the `<input required>` sentinel counts as
blank and is recomputed; a genuine human entry is preserved and audit-logged as Mode-2). A
**timestamped backup** (`<name>.bak_<YYYYMMDD_HHMMSS>.xlsx`, gitignored) is taken beside the source
*before* editing and **deleted if the fill changed nothing** (content compared cell-by-cell). The
`populated_iolist` artifact now points at the source itself. **Halts** the pipeline if any entry is
unresolved (the `_UnresolvedIndex` sheet lists them).

- `script_type.py` — the §6 type ladder (In/Out/Node classification → the catalogue type, computed
  **in code**, replacing the legacy Excel array formula). It yields the **canonical** type directly
  (encoder→N, emergency-area output→Z, reset→R<area>/R*; unmatched-but-described→`<input required>`);
  the legacy ENC/FA/RES intermediates + `to_canonical` are **gone**. Fire-alarm rows → `F1/2`/`F2/2`
  (mirrors the E1/2 channel logic). The AC "Suggested Type" column mirrors what the app writes to AB.
- `index_assign.py` — §7 per-family contiguous index with object grouping (channel pairs by FLD,
  KQ↔KI series, door FLD, Z pattern, standalone); unresolvable members → `<input required>`.
- `diag_alloc.py` — §8 cabinet/bit allocation: node cabinets (non-P bits up from `diag_bit_min`,
  P bits down from `diag_bit_max`), PA/PW field inference (`+FieldIODevices`), Type-2 family blocks.
- `blocks.py` — (re)writes the `DiagnosisBlocks` sheet (`ID_SWP == ID_Local`; FU/Location/FullName
  materialized as **text** so a leading `=` isn't a formula). `report.py` — the `_UnresolvedIndex`
  sheet (one clickable, sheet-qualified hyperlink per entry) + the Mode-2 audit.
- The 4 sub-phases (210/220/230/240) each fill one column; the phase header runs the full populate.
  Column **AC** holds the auto-inferred **canonical** type (kept for reference; == AB in Mode-1).
  The output-column **headers (AA…AG)** are written from `column_map` (the template leaves them
  blank). Index/diag numbering is **GLOBAL across all matched sheets** (sheets may share an FL).
  Non-matching sheets are logged as skipped.
- **`strike_handling`** is honored at staging/populate: a struck row is excluded ONLY when
  `strike_handling == "exclude"`; for `"error"`/`"ignore"` the row is KEPT (the distinction drives
  the *validation* severity later, phase 100).

## Phase 300 — Documents Staging (the single database) — DONE

`domain/staging.py` + `domain/matrix.py` + `domain/identity.py` + `phases/p300_staging.py`. Reads
the (populated) I/O List through the ONE shared reader (`io.workbook`), by column position per
`column_map`, into staged rows = the single database. 310 stages (→ `ctx.rows`); 320 writes
`IODatabase.csv` (`io_database` output); the header runs both. Keeps every non-empty row (incl.
node-meta rows), excludes struck rows only on `strike_handling == "exclude"` + Skip-Reason rows;
numbering/enrichment is GLOBAL across matched sheets; non-matching sheets logged as skipped.

- **C&E enrichment** (`matrix.annotate`, best-effort — blanks if the C&E doc is absent):
  - `matrix_areas` — inputs from the CAUSE&EFFECT MATRIX `X` marks (area columns = headers matching
    the `areas` regex); outputs from the AREA n sheets that list the Q-address. Paired channels
    share the union.
  - `ce_functional_unit` / `ce_location` / `ce_device` — the C&E-side FLD (matrix cols J/K/L) for
    every input with a counterpart (paired channels inherit it).
  - `numerazione_linea` — AREA col B, for outputs.
  - `areas_description` — per-area text from the **CONCEPT** sheet (`ce.concept_sheet` /
    `ce.concept_row`), mapped POSITIONALLY to the ordered matrix area columns; newlines→spaces;
    `|`-joined per the row's areas.
- **Identity fields** (`domain/identity.py` — the `{canonical}` template interpolation, shared with
  the generators): `name_in_db`, `name_in_tagtable`, `tagtable`, `datablocks`, `diag_desc`,
  `diag_block_name`/`diag_block_template` (from the DiagnosisBlocks sheet), `subnet_name`,
  I/Q byte ranges, `IsSorterArea`, `type_id_resolved`/`type_category`.
- `IODatabase.csv` = the IoList canonical columns + the enrichment/identity columns above
  (`staging._EXTRA`). The single database in CSV form; `ctx.rows` is just it loaded.

## Phase 100 — Documents Validation — DONE

`domain/validation/` + `phases/p100_validation.py`. Five sub-phases validate the hand-authored docs
and write two reports (complete `documents_validation_report.txt` + error-only
`documents_validation_errors.txt`; `.html` deferred to the GUI). `requires=(300,)`; the **designer**
profile is `(300, 100)` and **disables 150** (its inputs come from Fill, which the designer skips).
110/120 read workbooks through the ONE reader; 130/140/150 read `ctx.rows` (130/140 also read the C&E).
Every builder returns `list[LogEntry]`; each emit site declares a `type` slug (the log-type index).

- **110 `iolist.py`** — standalone I/O List: header glossary from `column_map("IoList")` (only columns
  **not** `preliminary_check_exclude`, i.e. the customer A–Z; AA–AG are pipeline-written and skipped);
  per-row IP-error/dup-IP/dup-FLD (node rows require an FU), G⊕F exclusion, address format (`address.py`),
  permanent-part + TS-ref for A/W(/PA/PW), Profinet identity for PA/PW, node-count thresholds. A clean
  row emits a `row_ok` **PASS** "all checks passed" (full report only). `strike_handling=="error"`⇒struck FAIL.
- **120 `matrix.py`** — C&E standalone (new design): no Q/O on the matrix, no I on AREA sheets, no dup
  address per sheet. C&E absent ⇒ one `ce_absent` **SKIP**.
- **130 `crosscheck.py`** — CEM→IOL: each C&E ref present+consistent in the IOL (io-index by FLD);
  partials link the matched IOL cell via `location2`/`doc2`.
- **140 `crosscheck.py`** — IOL→CEM decision tree: **typed & `ce_mandatory` yes/warn → CHECK** (yes→FAIL,
  warn→WARN); **typed `no`/unset → NO_CHECK** (skip); **untyped**: always-excluded→skip; `ce_full_check`
  OR a `ce_mandatory_words` safety match → CHECK; otherwise (excluded word / plain) → NO_CHECK (skip).
  `NO_CHECK` rows emit a SKIP that documents why; partials link the C&E cell.
- **150 `diagnosis.py`** — (cabinet,bit) numeric + unique per ALARM/WARNING family (family = WARNING
  when the type ends `W`, so an alarm+warning on one slot is not a collision).
- **Treatments (M6b, `core/errors.py`):** keyed by the per-FAIL `uid`, `user_input/error_management.csv`
  records `warn`→WARNING / `skip`→SKIP / `accept`→(write the C&E-side FLD into the I/O List description,
  idempotent + gated to `iol_cem_addr_only`)→SKIP. Each operator run reconciles the registry
  (current FAILs refreshed, untreated-gone pruned, **treated-gone kept + marked `stale`**). The designer
  build instead reads `user_input/designer_suppressions.csv` (suppress-only). Both CSVs are gitignored
  (user-local). Applied in the phase-100 header before rendering.

## Phase 400 — Interfaces Generation — DONE

`domain/interfaces.py` + `phases/p400_interfaces.py`. **410** builds one `IF_<instance>.xlsx` per IOC
row of the staged database (Script Type `IOC`, Index `MACHINETYPE[+DIAG]-nn`) from the
`Shared/Templates/MachineInterfaces` template → `interfaces_dir`
(`ProjectDocumentation/.../Interfaces` — documentation, **NOT** the Open2App BuilderData surface).
The machine type picks a template sheet (else `<GENERIC>`); the trailing digits are the index. Per
IOC row the template is copied, other sheets dropped, the sheet retitled to the full instance
(`IF_SORTER+DIAG-02.xlsx`), and the IOC row's Base Address (Bit) + Base Node (ID) + Index plugged into
the **Side rows only** (via the `Side` column), `<index>` tokens replaced. Existing files are
**preserved** (unless `insert_interface_sheets`, below). Interface **indices must be unique** across
IOC rows (`_idx_key` int-compare, so `02`==`2`) — a collision is an ERROR. `generate_one` is the
shared single-interface primitive the GUI-era **430** "Custom Interface…" popup will call (explicit
machine type / base address / node side 1 / node side 2 / index); **420/430** are GUI-era (M11).

- **Signal mirroring** (the I/O List **`Interface Mapping`** column = col **AH**, a `|`-list of
  interface indices): a flagged signal is mirrored onto the named coupler interface(s) in a "custom
  data" block. **Signal Name Side 1** = the **`interface_tagname`** (per-type template in
  `signal_types.csv` + the three rule CSVs; computed at **staging** into the IODatabase via
  `identity.interface_tagname` with `{tag_name}` resolved + `{interface_name}`/`{interface_id}` kept,
  then filled per-interface by the generator; rules use `{direction}`/`{member}`). **Expression
  Side 1** = the binding `identity.plc_binding` (`"<leftmost db>"."<name_in_db>"` else `"<tag>"`,
  shared with phase 600). A **`+DIAG`** suffix on the IOC Index mirrors **all `in_diag`** signals
  automatically. `datablock_elements_rules` + `diagnosis_logic_rules` followers follow each mirror
  (Q); the new **`interface_elements_rules.csv`** (`config.load_interface_elements_rules`) is the only
  source that may add **input (I)** rows. Direct I/O-list mirrors are always **output (Q)**.
- **Byte layout** (`allocate_bytes`/`_append_custom_rows`): per direction independently, starting
  `≥ INTERFACE_CUSTOM_GAP (8)` free bytes after the template's last used `I/O Offset Byte` (detected
  fresh each run, 2-byte-aligned). Grouped by `script_type`, never two types in a byte. Each **BOOL**
  type fills a **full 2-byte block** (its bits low, the rest blank addressed rows for the engineer) +
  a blank separator; a **WORD** is **one row + a blank separator**. Diagnosis columns
  (`diag_cabinet`/`swp_cabinet`/`diag_bit`) are written only where the chosen sheet has them; staging
  imports **`swp_cabinet`** = the `ID_SWP` of the row's local cabinet from the `DiagnosisBlocks` sheet
  (keyed by `ID_Local`). Addresses are the template's own `_xlfn.LET` structured-ref formulas, copied
  verbatim (Excel recomputes on open).
- **`insert_interface_sheets`** (project_params bool): when true, generation **overwrites** existing
  `IF_*.xlsx` AND **inserts each interface as a sheet named `IF_<instance>`** (e.g. `IF_SORTER-01`)
  into the I/O List if not already present
  (a timestamped `.bak` is taken first; idempotent). The insertion is **lossless**: openpyxl writes
  the combined workbook keeping every formula, then the existing formula cells' cached values — which
  openpyxl drops on re-save — are **patched back at the ZIP/XML level** (`_capture_formula_caches` /
  `_patch_formula_cache`), so data_only readers (staging/validation) still see e.g. Profinet IP/name.
  Atomic save (temp + `os.replace`). Copied tables are **re-created with clean columns** (id+name
  only, dropping the source's out-of-range `dataDxfId` + stale `calculatedColumnFormula`) and given
  per-instance names, else Excel drops the table on open. The interface sheets don't match
  `io_list.sheet`, so staging/validation ignore them; **phase 500's 510 reads the interface tags
  from these `IF_` sheets**.

## Phase 500 — Signals Mapping — DONE

`domain/signals.py` + `phases/p500_signals.py`. Two generators over the staged database (progress
strings only, no LogEntries — like 300/400). `requires=(300,)`; the interface tags additionally need
phase 400 to have inserted the `IF_` sheets (absent ⇒ I/O-only, degrades gracefully). `530/540`
(Open IO Tags / Open Data Blocks Folder) are GUI-era (M11).

- **510 Generate I/O Tags** → `io_tags_dir/PLCTags.xlsx` (single TIA "PLC Tags" workbook: a
  `PLC Tags` sheet + a `TagTable Properties` sheet; values text, addresses **%-prefixed**, Hmi flags
  `True`). TWO sources: (a) the **resolved I/O signals** — reusing the staged identity columns
  `name_in_tagtable` (tag name) + `tagtable` (Path), address = the I/Q bit %-prefixed, comment = the
  type `io_comment`; (b) the **interface tags** from the inserted `IF_` sheets — per the interface
  table columns **`Signal Name Side 1`** (tag name) and **`I/O Address Side 1`** (the LET-formula's
  Excel-cached value, read via `data_only`; %-prefixed), `Data Type`→Bool/Word, `Description`→comment,
  **Path = the `IF_` sheet name**. A named interface row whose address didn't resolve is skipped+warned.
- **520 Generate Data Blocks** → `blocks_import_dir/*` — members from TWO sources: (a) each row's
  staged `name_in_db` into every DB in its `datablocks`; (b) **rule-driven** additions from
  `datablock_elements_rules.csv` (any `required_types` script_type present ⇒ add the interpolated
  `member` to `db_name`, per-row — the phase-400 follower model; `dev_type` not a filter). Every DB
  is seeded with **`Always FALSE` / `Always TRUE`** (space, no underscore). A DATA_BLOCK can't repeat
  a member name, so exact duplicates are dropped (kept once) + warned.
- **Safe vs normal DB output** (key gotcha): a **SAFE DB** (any contributing type is `safe_db`) is
  written as a TIA **Openness `SW.Blocks.GlobalDB` XML** `<name>.xml` carrying
  **`ProgrammingLanguage=F_DB`** (the fail-safe marker the `.db` external-source format CANNOT
  express) + `DBAccessibleFromOPCUA=false` (a safe DB must not be OPC-writable — an unexpected write
  can fault the CPU to STOP) + per-member external-access attrs + `MemoryLayout=Optimized`. A
  **NORMAL DB** is the `.db` external source `<name>.db` (`DB_Accessible_From_OPC_UA := 'TRUE'`). Both
  are **UTF-8 BOM**; `.db` is CRLF, the XML is CRLF + no trailing newline (matching a real export).
  `S7_Optimized_Access` is `'TRUE'` for both — it is **NOT** a safety marker. `blocks_import_dir` is
  swept of prior `*.db`/`*.xml` on re-run (the phase-620 SCL is left intact).

## Phase 600 — Diagnosis Mapping — DONE

`domain/diagnosis.py` + `phases/p600_diagnosis.py`. Two generators over the staged database; progress
strings only (no LogEntries). `requires=(300,)`; the rule cabinet mapping + the SCL cabinets read the
`DiagnosisBlocks` sheet (`staging.load_diagnostic_blocks`, from Fill 230/240). `630/640` (Open Diag
Data / Diag Config folder) are GUI-era (M11).

- **610 Generate Diag List** → `diagnosis_dir` (`DiagList_IO.csv` + `DiagList_Logic.csv`; comma CSV via
  `io/csv_tables`). Columns are config-driven (`diagnosis/diagnosis_columns.csv`: `header,expression`,
  each cell a `{canonical}` interpolation of the row; the one sentinel `$PLC_Binding$` →
  `identity.plc_binding`). **DiagList_IO** = one row per in-diagnosis signal (`_type.in_diagnosis`).
  **DiagList_Logic** = rule-generated from `diagnosis_logic_rules.csv`: **`required_types` is an OR
  list (the `|`), firing once per row whose script_type is ANY of them** (the same per-row model as
  the datablock rules — NOT Pipeline2's "ALL required, once per cabinet"), each at the next free bit
  of its cabinet's alarm/warning family (`type_hw`/`dev_type` ending `W` = warning), bound to
  `"<db_name>"."<member>"`. A matched row's cabinet = its numeric `diag_cabinet`, else a
  **paired-channel sibling**'s cabinet (a row sharing its device FLD that carries one — e.g. the
  diagnosis channel DI2/2 inherits DI1/2's cabinet), else FLD → DiagnosisBlocks.
- **620 Generate Diag Software Blocks** → `blocks_import_dir/Diagnostic_for_OPC.scl` (the Open2App
  surface). Fills the `06_Diagnostic for OPC.scl` template: one FUNCTION, one REGION per cabinet, each
  a CabState call + one BoolToUDInt call per packed DWord (`ALARM1/2`, `WARNING1/2`). Per channel
  `IN_xx` = `identity.plc_binding`, `ML_xx` = `diagnosis.ml_value` (mirror→TRUE/invert→FALSE/else from
  `normal_condition`), `FL_xx` = `diagnosis.fl_value` (the row's node alarm `"PROFINET_NODES_ALARM".
  "<pname> <pip>"`, or `false`; a PA/PW node-alarm never self-filters). `diag_bit` 0-31 → DWord 1,
  32-63 → DWord 2, channel = `bit % 32`; the cabinet variant (01-04) comes from `DiagnosisBlocks`
  `TemplateType`, Tristate (02/04) pairs each alarm DWord with its warning DWord. **node resolution**
  (`node_of`) finds the Profinet node whose I/Q byte range (staging's `I_/Q_startByte/endByte`)
  contains the signal's address. The output is **UTF-8 BOM + CRLF** (matching the exported template)
  and the **FUNCTION is renamed** to drop the `TEMPLATE--vX.Y--` prefix (→ `06_Diagnostic for OPC`).

## Phase 700 — Hardware Generation — DONE

`domain/hardware.py` + `phases/p700_hardware.py`. A single ordered pass over `ctx.rows` produces both
format-2 CSVs → `hardware_dir` (the Open2App BuilderData surface). `requires=(300,)`; 710 Stations +
720 Modules share one `extract` (each sub-phase writes both; the header runs once). `730` (Open
Hardware Data Folder) is GUI-era (M11). DeviceTypesDatabase via `config.load_device_types_db`.

- **Roles / heads**: Script Type `PLC`→`Plc`, `PlcCardCm`→`PlcCardCm`, else Type (col R) first letter
  `P`→`IoDevice`. A head opens a station; the rows after it (until the next head) are its signals. A
  head whose model (Part No) isn't in the DTD → **ERROR** (the phase `ok=False`), **WARNING** for a
  switch (description contains "SWITCH"); the station is skipped either way.
- **Stations**: Name = `profinet_name`, Model Id = Part No (spaces stripped), Subnet from the IP,
  Group = `<functional_unit>_IODevices`. Custom Parameters = the DTD col-7 "I/O Addresses Parameter"
  (`%I%`/`%Q%` → the device start byte, `+N` arithmetic) then I/O-List col-AG (override, last).
- **Modules** (IoDevice only): signal rows grouped into cards by Slot (col E); a card whose Slot == the
  device's own tag is the TIA-auto-plugged card and is skipped. I Addr = Q Addr = the card start byte,
  Comment = the DTD comment. Custom Parameters = `PotentialGroup=1` on the **first** card (2+ come from
  col-AG) + the DTD col-6 "Parameters by Signal Type" blocks (`Ch(#)` → the signal's channel) then
  col-AG (override, last). Default cards (DTD ids `<PARENT>:SUFFIX`) add one row per station of PARENT.
- **DTD col-5 "Parameters" are NEVER written** (Open2App applies them); only col-6/col-7 + col-AG are,
  AG last. Output matches the committed reference (`Shared/.../TestData/Passing`): **comma format-2, no
  BOM, CRLF**, a `#!format=2` tag + a descriptive `# header` comment (the header is a comment; Open2App
  reads by position). NOTE: this reference format differs from Pipeline2's `_format2` (BOM + LF +
  raw-key headers); Pipeline3 follows the reference artifact.

## Phase 800 — Software Generation — SKELETON (builders are user-authored)

`domain/blocks/` (package) + `phases/p800_software.py`. The most-reworked phase, rebuilt clean as a
BASE for hand-written builders over the single database — no rules, no sidecars, no
`block_templates.json` (deprecated). `requires=(300,)`.

- **`database.py` `Database`** — the single source = `ctx.rows` (the staged IODatabase) + query
  helpers (`by_type`/`by_db`/`by_area`/`by_tagtable`/`where`/`areas`).
- **`table.py` `Table(name, columns, rows)`** — what a builder returns (`add(template_type=…, **values)`);
  a list-valued cell is the horizontal ITERATOR (emitted last).
- **`builders.py` — USER-EDITABLE** — one `@builds("<output name>")` per template, free-form Python:
  query `db`, return a `Table`. Currently stubs + a worked example. (Replaces Pipeline2's
  sidecar/capacity/ITERATOR rules + AST `sync_builders`.)
- **`registry.py`** — the `@builds` decorator; the engine runs every registered builder.
- **`shells.py` (810)** — `CreationInfo/SoftwareBlocksBuilderShells.xlsm`, the **KEY INVENTORY**: scans the template
  `*.xml` for `!!key$$` and writes one sheet per template with the FULL key set. Per sheet: B1
  `$ template=<ABSOLUTE path>`, B2 `$ <mode>` (keep/fill/override), row 3 `% TemplateType !!key$$ …`.
  Additive (edits/mode/added keys survive); `read_shells` reads modes + the key set back.
- **`engine.py` (820/830)** — runs builders honoring the shell: fill/keep → `builder(db)`; override →
  the shell sheet's `@` rows ARE the table. Serializes each Table to `CreationInfo/<name>.csv` in the
  kept `$/#/%/@` layout — the `%` header is the shell's FULL key set (builder fills values, blanks for
  the rest), the `$` ref is the ABSOLUTE template path. `instanceOf-<FB>` cells → `InstanceDBs.csv`.
  Output names drop the `TEMPLATE--vX.Y--` prefix.
- **No golden** for this format yet (Pipeline2's output never worked) — produced fresh for review.
  840/850 (Open …) are GUI-era (M11). Delete a stale shell to regenerate in the current format.

## Testing

Plain-`python` tests (no pytest) under `tests/unit/`, via `tests/unit/_harness.py` (PASS/FAIL,
non-zero exit on failure). Run one: `python tests/unit/test_iolist_diag.py`. The **data-independent
suite is the green gate** — it passes with no real documents present. Data-dependent outputs follow
**review-then-freeze**: the user reviews a phase's real-document artifact, and once blessed it is
frozen as a Pipeline3 golden under `tests/golden/` (Pipeline2 is NOT a golden source). The phase-100
reports are the first blessed golden; `tests/unit/test_golden_validation.py` regenerates + compares
them (data-dependent, skips when the real docs are absent; re-freeze with `--freeze`). Current: the
data-independent suite is green (numbering, model, config, i18n, registry, workbook, render,
iolist_diag, staging, the five validation suites + the phase-100 phase test + golden parity + the
treatment registry + the **Phase-400 interface suite** `test_interfaces.py`, ~36 cases: mirroring
membership, byte packing, the names/`interface_tagname` split, the WORD/BOOL layout, the lossless
I/O List insertion + the table-validity regression; the **Phase-500 signals suite** `test_signals.py`,
16 cases: the two tag sources + interface-tag reading, the data-type map, the F_DB-XML vs `.db` split
with BOM/CRLF, the member dedup; the **Phase-600 diagnosis suite** `test_diagnosis.py`, 17 cases: the
DiagList_IO columns + `$PLC_Binding$`, the OR/per-row logic rules + sibling co-location + next-free-bit,
`ml_value`/`fl_value`/`node_of`, and the SCL render incl. tristate + the FUNCTION rename + BOM/CRLF;
the **Phase-700 hardware suite** `test_hardware.py`, 11 cases: roles/address/param-merge-override/
I-O-address-template, the extract (auto-plug skip, PotentialGroup, by-type channel params, default
cards), the missing-DTD ERROR/switch-WARNING, and the format-2 output (no BOM, CRLF, descriptive headers));
the **Phase-800 blocks-skeleton suite** `test_blocks.py`, 6 cases: Database/Table/`@builds`, the
`$/#/%/@` writer (absolute `$` ref + InstanceDBs + ITERATOR-last), the shell scan/inventory + the
full-key `%` header + the override path (shell-dependent cases point `BLOCK_TEMPLATES_DIR` at a
synthetic template to stay data-independent).

## Status & still to build

- **DONE**: M1 foundation (config/numbering/model/i18n), M2 phase abstraction + registry + context
  + profiles, M3 the shared reader + log renderer, M4 Phase 200 Fill (writes the source in place +
  dated backup), M5 Phase 300 Staging (single `IODatabase.csv` + C&E enrichment incl.
  `areas_description`), **M6 Phase 100 Validation** (sub-phases 110–150 + the two reports + golden),
  **M6b** the treatment registry (`core/errors.py`: warn/skip/accept keyed by uid + mark-stale +
  designer suppression), **M7 Phase 400 Interfaces** (generation + signal mirroring +
  `interface_tagname`/Expression split + BOOL 2-byte-block / WORD-row layout + the lossless
  `insert_interface_sheets`), **M7 Phase 500 Signals** (510 I/O Tags incl. the interface tags from
  the inserted `IF_` sheets; 520 data blocks — type-based + rule-driven members, safe ⇒ F_DB Openness
  XML, normal ⇒ `.db`), **M8 Phase 600 Diagnosis** (610 DiagList_IO/Logic — OR/per-row rules +
  paired-channel co-location; 620 the OPC SCL fill — node-resolved FL, tristate variants, FUNCTION
  rename + BOM/CRLF), **M7 Phase 700 Hardware** (710 Stations + 720 Modules, one extract → format-2
  CSVs matching the committed reference; DTD roles + auto-plug + PotentialGroup + by-type params +
  default cards; head-not-in-DTD ERROR/switch-WARNING), **M9 Phase 800 Software — SKELETON** (the clean
  builder base: `domain/blocks/` Database + Table + `@builds` registry + the engine emitting the kept
  `$/#/%/@` CreationInfo CSV with an absolute `$` ref + InstanceDBs; 810 shells scan the template
  `*.xml` for the key inventory; `block_templates.json` deprecated. The per-template builders in
  `domain/blocks/builders.py` are USER-authored free-form Python — currently stubs).
- **NEXT**: the per-template block builders (`domain/blocks/builders.py`, user-authored); 910 Pipeline
  Coverage Report (phase 900); M10 CLI + Open2App-path contract test; M11–13 GUIs (dark-by-default,
  registry-driven phase bar, YAML-explorer config, selectable projects root) + designer + Project
  Manager; M14 packaging (two exes). **920** (TIA project coverage) is future — pending Open2App's
  project text-export.

## Conventions & gotchas

- Pipeline3App has its **own** `config_project/` — edit it, not Pipeline2App's.
- Regex YAML params must be **single-quoted**; JS `/…/flags` literals are accepted (`config.js_to_re`).
- `strike_handling` excludes struck rows only on `"exclude"`.
- Phase 800: `block_templates.json` is **deprecated** (neither read nor emitted) — the
  `SoftwareBlocksBuilderShells.xlsm` shell IS the key inventory (810 scans the template `*.xml`); the `$ template=`
  ref is an **absolute** path; the per-template builders in `domain/blocks/builders.py` are
  user-authored free-form Python. Delete a stale shell to regenerate in the current format.
- Tag/device strings (`=S1`, `+MS1.CC1`, `-S67001`) are **text**; generated cells that start with
  `=`/`+`/`-` are materialized `data_type="s"` (else openpyxl treats them as formulas).
- **Comma CSV** everywhere on write; readers sniff `,`/`;`.
- **Interface mirroring binds template columns by NAME** (the `<GENERIC>` and machine sheets differ;
  tables are user-renamed) — the data table is found by its `Category` header. **`interface_tagname`
  is computed at staging** (keeps `{interface_name}`/`{interface_id}` for the generator to fill).
- **openpyxl can't preserve formula caches** across a re-save — when modifying the I/O List in place,
  capture + patch them back at the ZIP/XML level; and **re-create copied tables with clean columns**
  (no `dataDxfId`/`calculatedColumnFormula`) or Excel drops them ("Removed Records: Table").
- **Data-block output is safety-aware** (phase 520): a `safe_db` type ⇒ an **F_DB Openness XML**
  (`<name>.xml` — the only form that carries fail-safe + `DBAccessibleFromOPCUA=false`, which protects
  the CPU from an OPC write faulting it to STOP); a normal DB ⇒ a `.db` external source
  (`DB_Accessible_From_OPC_UA := 'TRUE'`). **`S7_Optimized_Access` is NOT the safety marker** (it's
  `'TRUE'` on both). Files are UTF-8-BOM.
- **Diagnosis logic rules** (`diagnosis_logic_rules.csv`, phase 610/620) are **OR / per-row**: the `|`
  in `required_types` is OR and the rule fires once per matching row (NOT Pipeline2's "ALL required,
  once per cabinet"). Matching is by **script_type** (exact); a pair_key like `DI`/`N` matches no
  script_type, so it no-ops unless a row with that literal type exists. The **OPC SCL** is UTF-8-BOM +
  CRLF (the exported-template format) with the FUNCTION renamed to drop the `TEMPLATE--vX.Y--` prefix.
- Run/test from the `Pipeline3App` root. When committing `_Openn2`, end commit messages with
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
