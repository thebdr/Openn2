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
| 800 | Software Generation | 810 Empty Shells · 820 Generate Blocks · 830 Generate Instances | **DONE** (8 builders; 03 direct FC XML; editable shells) |
| 900 | Reporting | 910 Pipeline Coverage Report · 920 TIA Project Coverage Report | **910 DONE** (920 deferred) |

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
  domain/{validation,blocks}/  hardware.py  diagnosis.py  coverage.py   # DONE
  gui/   # M11 operator window DONE: app_main, phasebar, theme, logview, fonts, darktitle,
         #   files, objedit, grid, widgets, extedit, excel  (designer GUI + project mgr = TODO)
  project/  # project.py (folder projects) + state.py (persisted root/recent) - M13 Project Manager DONE
  cli/                                                    # TODO (M10)
config_project/  user_input/  assets/{fonts/}  tests/{unit,golden/}
launch_gui.py                                             # the operator-GUI launcher
```

### Shared primitives (the contracts every phase obeys)
- **One workbook reader** — `io/workbook.py::open_sheet(...)`/`SheetView`. Owns the openpyxl
  load-mode policy (strike-aware `data_only=True`, non-`read_only`; `load_for_write` is
  formula-preserving for the populator), regex sheet resolution, by-**position** cell access, and
  the header check that **normalizes newline→space then prefix-matches**. Every phase reads through
  this — no other module opens a sheet for reading.
- **One log engine — EVERY phase logs the same way (§4.1).** `core/model.py::LogEntry`, fixed
  left/middle, variable right `detail`:
  `[LEVEL] <id>  <location>  | bit | FLD | desc_l1 | desc_l1b | drawing | type-index :: <detail>`.
  TWO index concepts: **`id` = `<phase>-<type>`** — a code-traceable **log-type index**; the `type`
  slug is the i18n key suffix (`v_<type>`) AND the grep anchor that leads to the exact builder (NOT a
  per-run ordinal). **`uid`** = a stable per-FAIL hash of the *finding* (phase+type+location+detail)
  — excludes the level/seq AND the workbook identity, so a treatment survives a doc revision. The
  **`location` is `Sheet!Cell` only — never the workbook name**; the workbook rides on
  `LogEntry.doc`/`doc2` (for the GUI link), not rendered. A **cross-check renders both workbooks
  inline in the location column** as `<loc1> vs <loc2>` (both clickable) — `loc2` is the matched
  `Sheet!Cell` in the other workbook, or, on a **miss**, a workbook LABEL (no `!`) that opens that
  file. A mismatch also carries a structured **`Cmp`** (`io.render` aligns it per-phase as
  `<addr> op <addr> | <fld> op <fld>`, op `===`/`=/=`).
  - **The engine (`app._run_one`/`run_subphase`) emits a `<number> <Title>` PHASE banner** per
    (sub-)phase (`model.banner` prepends the id → `100 Documents Validation`, `300 Documents
    Staging`), with the title from the registry's `name_key` via i18n. So `ctx._current_phase` is set
    before the phase runs and `ctx._phase_start` marks its slice.
  - **`ctx.emit(str)` is part of the engine, not a side-channel**: it appends a `LogEntry`
    (`model.split_level` infers the level from a leading `[FAIL]`/`WARN`/`ERROR`/… token and strips
    it; default INFO) tagged with the current phase, AND forwards the raw text to `ctx.on_progress`
    (the GUI status bar). So phases **200–900 generators** (which only call `ctx.emit`) now produce a
    banner + INFO/WARN/FAIL lines in the SAME form as phase 100 — no separate plain-string path.
  - `io/render.py::render_lines(log, errors_only)` renders both the complete report and the
    error-only view (PHASE+INFO+WARN+FAIL, dropping PASS/SKIP). Its GUI twin **`render_records`**
    returns the SAME text plus, per line, the char spans of `location`/`location2` and their workbook
    (`doc`/`doc2`) — both share the one `_format_line`/`banner_lines` helper, so the report text (the
    golden) is a single source and can't drift from the GUI records.
  - The engine fires **`ctx.on_phase_log(slice)`** as each (sub-)phase completes, so the GUI renders
    each phase's block **incrementally** (and a long `run_all` shows blocks as they finish).
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
unresolved (the `_UnresolvedIndex` sheet lists them). **The write is SURGICAL** (`io/xlsx_edit`): it
edits ONLY the filled cells in place, **APPENDS new `DiagnosisBlocks` rows** (never rewrites existing
ones — see below) + rebuilds the pure-report `_UnresolvedIndex`, and **byte-copies every other part** —
so the template's dynamic-array / shared formulas, caches, tables and styles SURVIVE. A full openpyxl `load_workbook`→`save` round-trip instead FLATTENS dynamic
arrays into an "overlapping array formula" (Excel = corrupt) and drops formula caches; that is what
corrupted the I/O List from the GUI. A fill landing in an array spill **freezes that array to its
cached values + logs a WARN** (the formula stays in the backup). `xlsx_edit` also **drops
`xl/calcChain.xml`** (a stale chain that lists a now-removed formula cell makes Excel report corrupt;
Excel rebuilds it on open). `io/xlsx_edit` is the ONE place that writes an `.xlsx` (phase 400 folds in
next; `io/xlsx_cache` is retired).

- `script_type.py` — the §6 type ladder (In/Out/Node classification → the catalogue type, computed
  **in code**, replacing the legacy Excel array formula). It yields the **canonical** type directly
  (encoder→N, emergency-area output→Z, reset→R<area>/R*; unmatched-but-described→`<input required>`);
  the legacy ENC/FA/RES intermediates + `to_canonical` are **gone**. Fire-alarm rows → `F1/2`/`F2/2`
  (mirrors the E1/2 channel logic). The AC "Suggested Type" column mirrors what the app writes to AB.
- `index_assign.py` — §7 per-family contiguous index with object grouping (channel pairs by FLD,
  KQ↔KI series, door FLD, Z pattern, standalone); unresolvable members → `<input required>`.
- `diag_alloc.py` — §8 cabinet/bit allocation: node cabinets (non-P bits up from `diag_bit_min`,
  P bits down from `diag_bit_max`), PA/PW field inference (`+FieldIODevices`), Type-2 family blocks.
  **IDEMPOTENT** (`allocate(results, params, existing)`): a cabinet's **`ID_Local` is STABLE** — reused
  from the existing `DiagnosisBlocks` (keyed by `full_name` = FU+Location / `project_fu+Stem_inst`), a
  new cabinet gets the next free id above every existing one. Bits **continue past those already used**
  in a cabinet (seeded from rows carrying an `ex_diag_bit`), so re-running 230/240 after rows were added
  never duplicates a `(cabinet, bit)`. Type-2 family bits are a deterministic function of the signal.
- `blocks.py` — the `DiagnosisBlocks` sheet splits into **IDENTITY** columns (ID_Local/ID_SWP/Functional
  Unit/Location/FullName/TemplateType/Notes — **append-only, byte-preserved**) and **DERIVED** columns
  (Count, unused_bits, non_unique_bits — **recomputed and rewritten every run**). `read_existing(wb)`
  returns `({full_name → ID_Local}, {ID_Local → row}, {header → col})`; the populator appends ONLY the
  cabinets not already present (`block_rows`, via `xlsx_edit.append_rows`, which byte-preserves every
  existing row — a hand-edited `ID_SWP`/`Notes`, an orphan cabinet survive) and **creates the sheet fresh
  (`diagnosis_blocks_grid`) only when ABSENT**. The 3 derived columns are refreshed via a surgical
  cell-edit per existing row (`derived_edits`; the two new columns are added at canonical H/I/J on an old
  8-col sheet) and computed by `analyze(placed, …)` from the **REAL post-fill (Diag_Cabinet, Diag_Bit)** of
  every relevant row (effective = the `ex_*` on-disk value if non-blank, else what this run writes) — NOT
  the in-memory `results`: **`Count`** = times the cabinet's ID_Local appears in the Diag_Cabinet column
  across the sheets; **`unused_bits`** = the free bits in `[diag_bit_min, diag_bit_max]` as compact ranges
  (`0-7, 9, 18-62`, via `_fmt_ranges`); **`non_unique_bits`** = the bits a cabinet assigns more than once
  (operator-error surface; the allocator is collision-free), same format. An orphan cabinet → `Count=0`,
  full `unused_bits`, empty `non_unique_bits`. `ID_SWP == ID_Local` on a generated row; FU/Location/FullName
  are TEXT (a leading `=` isn't a formula). The legacy `DiagnosticBlocks` sheet is no longer auto-deleted.
  `report.py` — the `_UnresolvedIndex` sheet (one clickable, sheet-qualified hyperlink per entry) + the
  Mode-2 audit.
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
and write each report as BOTH `.txt` (the golden) and a no-wrap `.html` (complete
`documents_validation_report.{txt,html}` + error-only `documents_validation_errors.{txt,html}`). The
HTML (`render.render_html`/`html_reports`) replicates the GUI log viewer — the same `render_records`
text, the dark `theme.log_tags` palette + level colours, `Sheet!Cell` link styling — but with
`white-space:pre` (lines do NOT wrap, like the pane's `wrap="none"`); the "Open validation logs"
button now prefers the `.html`. `requires=(300,)`; the **designer**
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
- **130 `crosscheck.py`** — CEM→IOL: each C&E ref is run through **TWO independent searches** of the
  I/O List (indexed by FLD *and* by address — `build_io_index` + `build_io_addr_index`). **Search by
  address**: PASS `cem_addr_ok` (address there with a matching FLD) · FAIL `cem_addr_fld` (address there
  under a DIFFERENT FLD — the same-address/different-device case) · FAIL `cem_addr_none` (address absent).
  **Search by FLD**: PASS `cem_fld_ok` (FLD there at a matching address) · FAIL `cem_fld_addr` (FLD there
  at a DIFFERENT address) · FAIL `cem_fld_none` (FLD absent). So a signal present under a different device
  is reported precisely (the address IS there) instead of a blanket "device not declared". Every line
  links **BOTH workbooks** as `<C&E cell> vs <other>` — `<other>` is the matched I/O List cell, or on a
  no-match the **I/O List file** label; a *-fld*/*-addr* FAIL carries a `Cmp` (addr + FLD, `===`/`=/=`).
- **140 `crosscheck.py`** — IOL→CEM decision tree: **typed & `ce_mandatory` yes/warn → CHECK** (yes→FAIL,
  warn→WARN); **typed `no`/unset → NO_CHECK** (skip); **untyped**: always-excluded→skip; `ce_full_check`
  OR a `ce_mandatory_words` safety match → CHECK; otherwise (excluded word / plain) → NO_CHECK (skip).
  `NO_CHECK` rows emit a SKIP that documents why. Every checked line links **BOTH workbooks** as
  `<I/O List cell> vs <other>` — `<other>` is the matched C&E cell (PASS/partial) or, on a not-in-C&E
  miss, the **C&E file** label (opens the file). A mismatch carries a `Cmp` (addr + FLD, `===`/`=/=`).
- **150 `diagnosis.py`** — (cabinet,bit) numeric + unique per ALARM/WARNING family (family = WARNING
  when the type ends `W`, so an alarm+warning on one slot is not a collision).
- **165 / 175 Clean Addresses & Electrical Names** (`domain/clean.py`) — two **manual-only, ORANGE**
  (`KIND_SPECIAL`) phase-bar buttons, NOT in `SUBS`/the DAG (never run by Run-Pipeline, never a
  prerequisite; wired in `gui/app_main._button_cb` "special" branch → a worker-thread `_start_clean`).
  They remove the configured `clean.CLEAN_SYMBOLS` (default `["'"]`, extend as found) and collapse ALL
  whitespace (case preserved — the matcher uppercases) from the **address + Functional Unit/Location/
  Device** cells of the I/O List (165: `bit`/O/P/Q across the `io_list.sheet` sheets) and the C&E (175:
  the matrix `address`/J/K/L + the AREA sheets' `concat_id`/`address`), so the cross-check (130/140) stops
  failing on a stray `'` (the matcher strips whitespace + uppercases but NOT apostrophes). Read with
  `data_only=False` to **skip formula cells** (not flatten them); written back SURGICALLY (`io.xlsx_edit`,
  a leading `=`/`+`/`-` stays text) with a timestamped backup (dropped on a no-op). Logs each
  `Sheet!Cell: old -> new`.
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
  (keyed by `ID_Local`). The interface **`I/O Address Side 1`** is the template's own `_xlfn.LET`
  structured-ref formula, kept live — but on `insert_interface_sheets` its Excel cache (which openpyxl
  drops, and which the LET would recompute against the phase-400-plugged Base Address) is **SEEDED with
  the value computed in Python** (`_interface_address_caches` mirrors the LET: `{I|Q}{base+offset}[.bit]`,
  offset/bit chains resolved, columns bound by header), so phase 510 reads correct addresses **without
  Excel** while the formula survives for an engineer who opens the file. (The `<GENERIC>` template's
  address LET is mis-wired one column off — latent; the header-bound Python value is correct regardless.)
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
- **Unified DB output** (key gotcha): **EVERY DB is a TIA Openness `SW.Blocks.GlobalDB` XML**
  `<name>.xml` (UTF-8 BOM, CRLF, no trailing newline; per-member external-access attrs;
  `MemoryLayout=Optimized`). The ONLY difference between a normal and a fail-safe DB is
  **`<ProgrammingLanguage>` = the type's `db_kind` copied VERBATIM** (`DB` or `F_DB`; `db_kind` is
  `|`-aligned with `db_names` by position — a single value applies to every DB, so `PA` →
  `PROFINET_NODES_ALARM` as `DB` + `00_Commissioning` as `F_DB`; on a mixed contribution **F_DB wins**).
  **`<DBAccessibleFromOPCUA>` follows it**: `false` for `F_DB` (a fail-safe DB must not be OPC-writable —
  an unexpected write can fault the CPU to STOP), `true` otherwise. The `.db` external-source path is
  **gone** (`_db_text` removed); `build_data_blocks` carries `db['prog_lang']`, not a `safe` bool.
  `blocks_import_dir` is still swept of prior `*.db`/`*.xml` on re-run (removing any pre-unification
  `.db`; the phase-620 SCL is left intact).

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
  contains the signal's address — and those ranges are **POSITIONAL** (a node owns the rows beneath it
  in I/O List order until the next node / sheet end; `staging._add_node_address_ranges`), **NOT keyed by
  FLD/location** (a safety module's stops carry their own `+ES..` location, so a location key left such
  modules empty-ranged and silently dropped every `node_of` consumer — 02/06/08 builders, diagnosis FL,
  coverage). The output is **UTF-8 BOM + CRLF** (matching the exported template)
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

## Phase 800 — Software Generation — DONE (8 builders + 03 direct-XML + editable shells)

`domain/blocks/` (package) + `phases/p800_software.py`. Rebuilt clean over the single database — no
rules, no sidecars, `block_templates.json` deprecated. `requires=(300,)`. All 8 per-template builders
are written (data-independent cases in `tests/unit/test_builders.py`; real-doc CSVs/XML are review-then-freeze).

- **`database.py` `Database`** — the single source = `ctx.rows` + helpers (`by_type`/`by_db`/`by_area`/
  `by_tagtable`/`where`/`first`/`areas`).
- **`table.py` `Table`** — what a builder returns (`add(template_type=…, **values)` / `add_row`); a
  list-valued cell is the horizontal ITERATOR (emitted last).
- **`builders.py`** — one `@builds("<output>")` per template, free-form Python over `db`. The 8:
  `00` commissioning bypass (one network per diag node = a node carrying `name_in_db`), `02` EM push
  button (a `00_Push-Button_Input` FB per node = the node's emergency-stop inputs, **E1/2 push-buttons
  AND B1/2 safety-breakers**, grouped by node in address order, chunked to the FB's 4 slots), `03` zone
  cumulative (per AREA: `PB`/`FDB` always + `SAFETY_BREAKERS`/`DOORS` when present →
  one `02_COM` AND-coil each), `04` ESTOP (per AREA; SORTER door-capacity tier 01-05 when sorter-area
  OR has doors, else GENERIC `06`), `05` output feedback (per K-family `index` group; 3-family capacity
  variant), `06` feedback error (a `03_FDBACK error` FB per node, KQ chunked to 8), `07` speed control
  (per N1/2+N2/2 encoder pair by numeric index), `08` gate manager (one row per sorter + one per door
  `DQ`). Node grouping is by I/Q address range; **`index` (global) groups the K family + the door
  family**; **`No Operation`** (a ph-520 DB seed member) pads a template's unused fixed slots.
- **`registry.py`** — the `@builds` decorator; the engine runs every registered builder.
- **`shells.py` (810)** — `CreationInfo/SoftwareBlocksBuilderShells.xlsm` is BOTH the key inventory AND
  the **editable working surface**. Per sheet: B1 `$ template=<ABS path>`, B2 `$ <mode>`
  (fill/keep/override). Saved as a **valid macro-enabled .xlsm**: openpyxl writes the xlsx content type
  even to a `.xlsm` (Excel rejects the mismatch as corrupt), so `_save_xlsm` patches `[Content_Types].xml`
  to macro-enabled after every save, and loads use `keep_vba=True` so user VBA survives a re-run. Two
  sheet layouts: **standard** (`%`/`@` key header) for 7 blocks; **coil-columns** for `03`
  (`COIL_COLUMN_BLOCKS`) — one column per coil = the cause→effect linking (row3 `%coil` the `02_COM`
  member, row4 `nameOfDB`, row5 `comment`, rows6+ the AND inputs).
- **`engine.py` (820/830)** — per block, by B2 mode: **fill** → `builder(db)` → CSV + seed the sheet
  (standard = exact `$/%/@` copy of the CSV via `write_standard_sheet`; `03` = `write_coil_columns`);
  **keep** → `builder(db)` → CSV, sheet left alone; **override** → write the CSV **from the sheet
  VERBATIM** (`read_override_grid`, preserving the ITERATOR spread) — `03` reads its coil columns
  instead. `%` header = the shell's full key set; `instanceOf-<FB>` cells → `InstanceDBs.csv`; output
  names drop the `TEMPLATE--vX.Y--` prefix.
- **`xml_emit.py` — direct FC XML.** A block in `xml_emit.EMITTERS` (currently `03`) is emitted as a
  ready `SW.Blocks.FC` XML into the Open2App **ImportReady** surface (one exactly-sized `A`(AND)→`Coil`
  network per cumulative; **UTF-8 BOM + CRLF + indented**, modelled on the template's FlgNet) and its
  CreationInfo **CSV is dropped** (Open2App imports the XML, not a template-fill CSV). `02_COM` is
  generated here too — a custom safe F_DB (`signals.write_safe_db`), members = the standard seeds + the
  AREA-n cumulatives.
- 840/850 (Open …) are GUI-era (M11). A file-write `OSError` (e.g. a locked output) is a logged ERROR
  that HALTS the run (`app._run_one`), not a traceback.

## Phase 900 — Reporting — 910 DONE (920 deferred)

`domain/coverage.py` + `phases/p900_reporting.py`. **910 Generate Pipeline Coverage Report** traces
each staged signal's life from validation (100) through staging (300) to every downstream output, by
**reading the ACTUAL on-disk output artifacts** (NOT an in-memory re-derivation — phases 400–800 permit
user inputs: the editable `.xlsm` shells in override/keep mode, hand-filled interface Side-2 rows,
treatments; only the produced files reflect reality). It reuses each staged row's identity (`name_in_db`/
`name_in_tagtable`/`plc_binding`/`profinet_name`) to find where that signal landed. `requires=(300,)` and
reads artifacts as-they-are (richer once 400–800 have run; a missing artifact degrades to a noted gap —
run-all runs 400→800 before 900, so a full run is current). Writes `Reports/io_project_coverage_report.{csv,txt}`
— **documentation, NOT an Open2App import surface**. `ok=True` (informational); 930 (Open Reports) is GUI-era.

- **What it reads** (`collect_outputs`, split from the pure `attribute` so the green gate stays hermetic):
  `PlcTags/PLCTags.xlsx` (tags) · `ImportReady/*.db`+`*.xml` GlobalDB (DB members) · `DiagList_*.csv` +
  `Diagnostic_for_OPC.scl` (diagnosis bindings) · `IF_*.xlsx` Expression Side 1 (interface mirrors) +
  the IF_ instance files · `Stations/Modules.csv` (hardware station names) · `CreationInfo/*.csv` +
  ImportReady FC-XML `<Component>` (software refs). A channel is "covered by hardware" when its node
  (via `diagnosis.node_of`) is a generated station.
- **Row kinds**: `signal` (resolved type OR carries a DB/tag identity) · `channel` (untyped row with an
  I/Q address = a raw module point) · `structural` (untyped, no address — headers, CM partner cards).
- **ORPHAN** = a `signal` whose identity appears in NONE of the output artifacts (channels/structural
  are never ORPHAN). **UNPLACED** = a qualified `"<db>"."<member>"` reference an output emits (a
  diagnosis binding / an interface-mirror Expression) whose DB is one Pipeline3 generates (it has an
  actual `.db`/`.xml`) but whose member is NOT in that DB's actual members — an output pointing at a
  data-block member that was never created. Refs to DBs Pipeline3 does NOT generate (`05_EM_STATE`,
  `SPEED_STATE_REC` — hand-authored in TIA) are 920's scope, ignored here.
- **920 TIA Project Coverage** — a disabled stub (no `run`), deferred pending a real TIA project export.

## GUI — M11 operator window ("Broski Session") — DONE (+ designer mode)

`pipeline3/gui/` + `launch_gui.py` (`python launch_gui.py`). A Tkinter window; the app is **Pipeline3**,
each profile is a **named session** shown in the title + log banner as `Pipeline3 - <session> (<profile>)`:
**Broski Session (main)** / **IOList & CEMatrix Validation (designer)** (`app_main._SESSIONS`).

- **`app_main.py`** — the window: a top toolbar (PIPELINE3 brand · Lang EN/IT · ◐ Theme · Open Output ·
  Clear Log), the registry-driven phase bar, and a **Log | Files** notebook + a status bar/progress.
  The pipeline runs on a **worker thread**; its `emit` output is queued and drained into the LogView via
  `root.after`. A phase header runs the whole phase; a sub-phase button runs that step (prereqs first);
  opens `startfile` the artifact. Holds ONE session `ctx` (memoized). **EN/IT** + **dark/light** toggles
  rebuild the bar / re-theme live (incl. the title bar).
- **`phasebar.py`** — the `PhaseBar`/`_Dropdown` widget, but the spec is **generated from the registry**
  (`build_spec` over `registry().presentation_order()` + i18n labels), never a hand-written ordering.
  The buttons are **classic `tk.Button`s** coloured from `theme.tk_button_opts` (the ButtonsLayout fills:
  pink run / white phase / grey chevron / white action / light-blue open / orange special / grey disabled)
  — sv-ttk's themed buttons are image-based and can't take a custom bg, so the colored bar uses plain tk.
- **`theme.py`** — applies **sv-ttk** (Sun Valley dark/light) for the chrome + sets the bundled **Monaspace
  Neon** as the default UI font; returns a palette read back from the active theme. `darktitle.py` darkens
  the native **Windows title bar** (DWM `IMMERSIVE_DARK_MODE` on the caption HWND; reversible). `fonts.py`
  loads `assets/fonts/MonaspaceNeon-Var.ttf` privately per-process (`AddFontResourceEx(FR_PRIVATE)`;
  resolves as `"Monaspace Neon Var"`).
- **`logview.py`** — the colour-coded log (level tags). EVERY phase's log is fed as **structured
  records** (`render.render_records`) via the engine's per-phase `on_phase_log` hook (`app_main._phase_log`
  → one `("records", …)` event per phase, rendered as each phase completes — live sub-step text goes to
  the status bar via `ctx.on_progress`). `append_records` makes each line's `location`/`location2` cell a
  **clickable link that opens ITS OWN workbook** (I/O List or C&E, from the record's `doc`/`doc2`) in
  Excel at that cell via COM (`excel.py`, worker thread) — `_open_link(doc, sheet, cell)` resolves the
  basename to a path — and tags the leading **`[FAIL]`/`[ERROR]`** as an `errlink` opening
  `error_management.csv`. Binding from the record (not by re-parsing text against "known sheets")
  is what makes cross-workbook links work and can't race; the old `set_sheets`/regex shortcut is gone.
  A **"Log to File"** toolbar checkbox tees each rendered phase block to `Reports/pipeline_run_log.txt`
  (the `run_log` OUTPUT_PATHS key; phase 100's own reports are unaffected). **`excel.py::goto`** now
  **brings Excel to the foreground** after the cell jump (`_bring_to_front`, ported from Pipeline2:
  `ShowWindow(SW_RESTORE)` + `AttachThreadInput` around `BringWindowToTop`/`SetForegroundWindow`).
- **`files.py`** — the Files tab: a **3-section tree** (Project configuration / User editable files / Bare
  output files) + a type-aware editor. `.csv` → editable tksheet **grid** (Save = comma CSV); `.yaml/.json/
  .xml` → the **object editor** (`objedit.py`); `.scl/.db/.txt/...` → text editor; `.xlsx/.xlsm` → the
  **read-only Excel viewer** (`xlsxview.py`: a **sheet selector** + **Tab/Shift+Tab** to step sheets, a
  **Show formulas** checkbox = openpyxl `data_only=False`, 3000-row cap; "Edit externally" since the Excel
  files carry formulas/array-formula/VBA an openpyxl save would drop). **Arrow keys** navigate the tree
  (Up/Down visible items, Left collapse/out, Right expand/in; selection loads the file and keyboard focus
  stays on the tree). Every editor shares `widgets.editor_header`: a **selectable full-path field** + an
  **Open folder** button (`extedit.reveal` = `explorer /select`). The tree right-click also has Open
  containing folder / Open externally. **`grid.py`** decorates each tksheet with **zebra** + right-click
  **Sort ↑/↓ · Filter… · Clear** (active column marked ` ↑`/` ↓`/` ▽` on its header). **Filter** is a
  case-insensitive **regex** (or pick distinct values), view-only + save-safe (`display_rows` hides rows,
  all kept by a Save); **sort** physically reorders the rows (tksheet can't reorder a display) — Clear /
  Reload reverts (the original order is snapshotted on first sort/filter).
- **`objedit.py`** — a `ttk.Treeview` **object editor** for YAML/JSON/XML, edited in each format's own
  structure: **YAML via ruamel `CommentedMap` in place (comments survive; `width=4096` so a Save doesn't
  re-wrap long lines)**, JSON type-preserving, XML element/`@attr`/`#text`. Scalars edit inline (double-
  click the Value); a **right-click context menu** (a per-item `_model` registry) adds the structural
  edits — **Browse file/folder** into a leaf, **Add key/item** (dict/list) / **Add child element /
  attribute** (XML), **Delete** any non-root node — mutating the in-memory tree (Save persists; the pure
  `add_key`/`add_item`/`delete_node` helpers are unit-tested for comment + type preservation). A **Tree |
  Text** toggle drops to raw and re-parses. (No off-the-shelf lib fit — JSON-only / web-based + strip YAML comments.)
- **`extedit.py`** — `open_external` (the spreadsheet editor: **LibreOffice → Excel → OS default**) +
  `reveal` (containing folder, file selected). Embedding LibreOffice in-window is not feasible; it opens
  as its own app.

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
the **Phase-800 blocks suite** `test_blocks.py` (Database/Table/`@builds`, the `$/#/%/@` writer +
full-key `%` header, the shell scan/inventory, the direct-FC-XML emit — exactly-sized AND + the
CSV-drop, the coil-columns round-trip, the standard-sheet CSV mirror, the **override-verbatim** CSV
preserving the ITERATOR spread; shell-dependent cases point `BLOCK_TEMPLATES_DIR` at a synthetic
template) + the **per-builder suite** `test_builders.py` (one group per template `00/02/03/04/05/06/07/08`
over synthetic rows: the grouping/membership/variant/naming of each builder + the `combined_FLD` dedup);
the **Phase-900 coverage suite** `test_coverage.py` (9 cases: signal/channel/structural classification,
the per-stage attribution + ORPHAN-only-for-signals, the UNPLACED dangling-member detector `find_unplaced`,
and the output-artifact readers over a tiny synthetic output tree — hermetic, the trace splits file-I/O
`collect_outputs` from the pure `attribute`); `test_diagnosis.py` also covers the optional `diag_desc`
rule column (override + absent + blank fallback); `test_registry.py` also covers the file-write-error halt.

## Status & still to build

- **DONE**: M1 foundation (config/numbering/model/i18n), M2 phase abstraction + registry + context
  + profiles, M3 the shared reader + log renderer, M4 Phase 200 Fill (writes the source in place +
  dated backup), M5 Phase 300 Staging (single `IODatabase.csv` + C&E enrichment incl.
  `areas_description`), **M6 Phase 100 Validation** (sub-phases 110–150 + the two reports + golden),
  **M6b** the treatment registry (`core/errors.py`: warn/skip/accept keyed by uid + mark-stale +
  designer suppression), **M7 Phase 400 Interfaces** (generation + signal mirroring +
  `interface_tagname`/Expression split + BOOL 2-byte-block / WORD-row layout + the lossless
  `insert_interface_sheets`), **M7 Phase 500 Signals** (510 I/O Tags incl. the interface tags from
  the inserted `IF_` sheets; 520 data blocks — type-based + rule-driven members, every DB a GlobalDB
  XML with `<ProgrammingLanguage>` = `db_kind` verbatim, F_DB ⇒ OPC-locked), **M8 Phase 600 Diagnosis** (610 DiagList_IO/Logic — OR/per-row rules +
  paired-channel co-location; 620 the OPC SCL fill — node-resolved FL, tristate variants, FUNCTION
  rename + BOM/CRLF), **M7 Phase 700 Hardware** (710 Stations + 720 Modules, one extract → format-2
  CSVs matching the committed reference; DTD roles + auto-plug + PotentialGroup + by-type params +
  default cards; head-not-in-DTD ERROR/switch-WARNING), **M9 Phase 800 Software — DONE** (all 8
  per-template builders `00/02/03/04/05/06/07/08` over the single DB; the FLD dedup
  `iol_FLD`/`ce_FLD`/`combined_FLD` + `No Operation` DB seed; `02_COM` safe-DB generated in phase 800;
  `05_DOORS`→`07_DOOR` rename; `03` emitted as a direct exactly-sized `SW.Blocks.FC` XML
  (`xml_emit`, BOM+CRLF, CSV dropped); the editable `.xlsm` shell — standard `%`/`@` sheets seeded as a
  CSV copy on `fill`, `03` as a coil-columns cause→effect sheet; `override` writes the CSV from the
  sheet verbatim; a file-write error halts cleanly), **Phase 900 / 910 Pipeline Coverage Report — DONE**
  (`domain/coverage.py`: trace each staged signal across the on-disk outputs; ORPHAN = a signal in no
  output, UNPLACED = a `"<db>"."<member>"` reference to a generated-DB member 520 never created; reads
  the actual artifacts so user edits to shells/interfaces are honored; CSV + TXT under `Reports/`),
  the **`diag_desc` rule column** (optional `diagnosis_logic_rules.csv` column → the List_Logic Diag Desc),
  and **M11 the main operator GUI ("Broski Session")** — `pipeline3/gui/` + `launch_gui.py`: the
  registry-driven phase bar (sv-ttk dark + Monaspace + dark title bar), EN/IT + dark/light toggles,
  worker-thread runs streamed to a clickable LogView, and the **Files tab** (3-section tree + a CSV grid
  with zebra/sort/filter, a YAML/JSON/XML object editor, an xlsx read-only preview + LibreOffice/Excel
  external edit, full-path header + Open-folder). See the **GUI** section above.
- **Project Manager (M13) — DONE.** Folder projects + a user-selectable, **persisted** projects root. A
  project is a self-contained `<root>/<name>/` = `project.yaml` (run params) + `Input/` (the copied I/O List
  + C&E) + `Output/` (its OUTPUT_PATHS tree) + its OWN `config_project/` (the config CSVs) + `user_input/`
  (the treatment registry) — **fully ISOLATED**. `pipeline3/project/project.py` (pure new/open/save/
  copy_inputs + helpers; ruamel round-trip keeps project.yaml comments; workbooks copied BINARY) + `state.py`
  (`%LOCALAPPDATA%/Pipeline3/state.json`: projects root + recent + last_opened). **`config.use_project(root)`**
  / `use_builtin()` points the CSV loaders + the treatment registry at the project's copies (the dir
  functions `config_project_dir`/`input_docs_dir`/`diagnosis_dir`/`user_input_dir`); **no project open =
  the builtin app config + `Shared/OutputTree`, the Open2App/Openn3 import contract**, kept intact by
  construction (an open project gets an absolute `<project>/Output` via `load_params`, and the BuilderData
  subpaths are relative → byte-identical either way). The operator GUI threads `self.params` everywhere and
  adds the toolbar cluster **New Project · Open Project ▾** (recent · Open… · Set projects root… · Re-select
  IOList… · Re-select CEMatrix… · Close) + an active-project indicator in the title/banner; it **auto-reopens
  the last project** on launch. `tests/unit/test_project.py` (module + state + `use_project` routing).
- **Designer mode (M11b) — DONE.** ONE GUI; the launch profile is `config_project/app_config.yaml`
  (`profile: main|designer`, read by `config.load_app_profile`; unknown/missing → main). The registry now
  separates **presentation** from the runnable keep-set (`define_profile(present=, attrs=)`) + carries
  per-profile GUI **attrs** (`input_pickers`/`live_source`), so the designer bar shows **ONLY ph100** (300
  stages as a hidden prerequisite, Fill 200 skipped). It reads `designer_params.yaml`
  (`config.profile_params_file`), uses a **full Project-Manager project** (New Project seeds from the
  designer base, no file prompts), adds **two input pickers** beside ph100, and **re-copies each input's
  `source` into Input/ on every ph1x0 run** (`project.refresh_inputs` + a ctx re-stage).
  `app_config.yaml` is **tracked** (a normal in-repo config) and also carries a **`user_interface`**
  launch block — `width`/`height` (START size; the window stays **resizable**), `theme` (`dark`|`light`),
  `log_to_file` — read by `config.load_app_ui` and applied in `App.__init__`. Covered by
  `test_registry` (present-subset/attrs), `test_config`
  (`load_app_profile`/`load_app_ui`/`profile_params_file`), `test_project` (`refresh_inputs`/`default_doc`).
- **NEXT**: M10 CLI + the Open2App-path contract test; object-editor polish (Browse pickers on path leaves,
  add/remove nodes); M14 packaging (now **ONE** PyInstaller exe — the profile is a shipped config value).
  **920** (TIA project coverage) is future — pending Open2App's project text-export.

## Conventions & gotchas

- Pipeline3App has its **own** `config_project/` — edit it, not Pipeline2App's.
- Regex YAML params must be **single-quoted**; JS `/…/flags` literals are accepted (`config.js_to_re`).
- `strike_handling` excludes struck rows only on `"exclude"`.
- Phase 800: `block_templates.json` is **deprecated** — `SoftwareBlocksBuilderShells.xlsm` IS the key
  inventory + the editable surface (`$ template=` ref is an **absolute** path). Modes (B2): **fill**
  (default — rewrite the sheet from the builder each run), **keep** (builder drives, sheet untouched),
  **override** (the sheet drives — CSV written verbatim, preserving the ITERATOR spread). `03` uses the
  **coil-columns** layout + is emitted as a direct **FC XML** (no CSV). The shell is a **macro-enabled
  `.xlsm`**: openpyxl emits the xlsx content type even to `.xlsm` (Excel = "corrupt"), so `_save_xlsm`
  patches `[Content_Types].xml` and loads use `keep_vba=True`. Delete a stale shell to regenerate.
- A direct-FC-XML block (`xml_emit.EMITTERS`) ships a ready `SW.Blocks.FC` to ImportReady — **UTF-8 BOM
  + CRLF + multi-line** (a double BOM / LF-only / single-line file fails the Openness importer at line 1)
  — and its CreationInfo CSV is dropped.
- A **file-write `OSError`** (e.g. an output locked open in TIA/Excel) is caught at `app._run_one`,
  logged `[ERROR] … could not write file …; pipeline stopped`, and HALTS the run (the phase stays
  un-completed, so it retries once the lock clears) — never a raw traceback.
- Tag/device strings (`=S1`, `+MS1.CC1`, `-S67001`) are **text**; generated cells that start with
  `=`/`+`/`-` are materialized `data_type="s"` (else openpyxl treats them as formulas).
- **Comma CSV** everywhere on write; readers sniff `,`/`;`.
- **Interface mirroring binds template columns by NAME** (the `<GENERIC>` and machine sheets differ;
  tables are user-renamed) — the data table is found by its `Category` header. **`interface_tagname`
  is computed at staging** (keeps `{interface_name}`/`{interface_id}` for the generator to fill).
- **openpyxl can't preserve formula caches** across a re-save — when modifying the I/O List in place,
  capture + patch them back at the ZIP/XML level; and **re-create copied tables with clean columns**
  (no `dataDxfId`/`calculatedColumnFormula`) or Excel drops them ("Removed Records: Table").
- **Data-block output is unified + safety-aware** (phase 520): EVERY DB is a **`SW.Blocks.GlobalDB`
  Openness XML** (`<name>.xml`); the type's **`db_kind` is the verbatim `<ProgrammingLanguage>`** (`DB` /
  `F_DB`, `|`-aligned with `db_names` by position, F_DB-wins on conflict), and `<DBAccessibleFromOPCUA>`
  follows it (**`false` for `F_DB`** — protects the CPU from an OPC write faulting it to STOP — else
  `true`). The old `.db` external-source path is gone. Files are UTF-8-BOM, CRLF.
- **Diagnosis logic rules** (`diagnosis_logic_rules.csv`, phase 610/620) are **OR / per-row**: the `|`
  in `required_types` is OR and the rule fires once per matching row (NOT Pipeline2's "ALL required,
  once per cabinet"). Matching is by **script_type** (exact); a pair_key like `DI`/`N` matches no
  script_type, so it no-ops unless a row with that literal type exists. The **OPC SCL** is UTF-8-BOM +
  CRLF (the exported-template format) with the FUNCTION renamed to drop the `TEMPLATE--vX.Y--` prefix.
  A rule's **`member` must name a DB member 520 actually creates** (a `datablock_elements_rules` member
  or a signal type's `db_element`), else the diagnosis binding dangles — the 910 coverage report flags
  it **UNPLACED**. The optional **`diag_desc`** column (`config.load_rules`) gives the rule-generated
  DiagList_Logic row its OWN Diag Desc (a `{canonical}` template, e.g. `SAFETY ENCODER FAILURE {combined_FLD}`);
  blank/absent ⇒ the row keeps the source signal's `diag_desc` (`diagnosis.build_diag_list_logic`).
- **GUI (M11) gotchas**: the phase bar uses **classic `tk.Button`** for its coloured buttons (sv-ttk's
  themed buttons are image-based and ignore a custom `bg`). A bundled **private font** must be inserted
  before-or-after `tk.Tk()` via `AddFontResourceEx(FR_PRIVATE)` and used by its resolved family
  (`"Monaspace Neon Var"`, NOT `"Monaspace Neon"` → Arial). A path **`ttk.Entry`** must `insert` then go
  readonly — a local `StringVar` gets GC'd and blanks it. The Files object editor writes YAML via ruamel
  with **`width=4096`** so a Save doesn't re-wrap. **`.xlsx`/`.xlsm` are view-only** in-app (edit hands
  off to LibreOffice/Excel) — never round-trip them through openpyxl (drops formulas/array-formula/VBA).
- **The golden test is DATA-DEPENDENT** (`test_golden_validation.py`, phase 100 vs the frozen golden):
  when it goes red, check the **working tree first** — a changed `config_project/project_params.yaml`
  (e.g. `strike_handling`) or a mutated source I/O List, not a code regression. **Phase 200 Fill / 400
  `insert_interface_sheets` write the source in place** (so they git-dirty it), but no longer DEGRADE it:
  phase 200 is **surgical** (`io/xlsx_edit` — only the edited cells/sheets change, everything else is
  byte-copied) and phase 400 **freezes any openpyxl-flattened array + drops the stale calcChain**
  (`xlsx_edit.freeze_arrays`), so both stay Excel-valid and don't break the golden — a `git checkout`
  restores the bytes. (`io/xlsx_cache` is retired; surgical editing never re-serialises, so there is no
  cache to drop/restore.)
- Run/test from the `Pipeline3App` root. When committing `_Openn2`, end commit messages with
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
