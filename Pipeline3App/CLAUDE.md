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
| 400 | Interfaces Generation | 410 Generate Interfaces · 430 Generate Custom Interface… | TODO (M7) |
| 500 | Signals Mapping | 510 Generate I/O Tags · 520 Generate Data Blocks | TODO (M7) |
| 600 | Diagnosis Mapping | 610 Generate Diag List · 620 Generate Diag Software Blocks | TODO (M8) |
| 700 | Hardware Generation | 710 Generate Stations · 720 Generate Modules | TODO (M7) |
| 800 | Software Generation | 810 Empty Shells · 820 Generate Blocks · 830 Generate Instances | TODO (M9) |
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

## Testing

Plain-`python` tests (no pytest) under `tests/unit/`, via `tests/unit/_harness.py` (PASS/FAIL,
non-zero exit on failure). Run one: `python tests/unit/test_iolist_diag.py`. The **data-independent
suite is the green gate** — it passes with no real documents present. Data-dependent outputs follow
**review-then-freeze**: the user reviews a phase's real-document artifact, and once blessed it is
frozen as a Pipeline3 golden under `tests/golden/` (Pipeline2 is NOT a golden source). The phase-100
reports are the first blessed golden; `tests/unit/test_golden_validation.py` regenerates + compares
them (data-dependent, skips when the real docs are absent; re-freeze with `--freeze`). Current:
**94 unit tests green** (numbering, model, config, i18n, registry, workbook, render, iolist_diag,
staging, the five validation suites + the phase-100 phase test + golden parity + the treatment registry).

## Status & still to build

- **DONE**: M1 foundation (config/numbering/model/i18n), M2 phase abstraction + registry + context
  + profiles, M3 the shared reader + log renderer, M4 Phase 200 Fill (writes the source in place +
  dated backup), M5 Phase 300 Staging (single `IODatabase.csv` + C&E enrichment incl.
  `areas_description`), **M6 Phase 100 Validation** (sub-phases 110–150 + the two reports + golden),
  **M6b** the treatment registry (`core/errors.py`: warn/skip/accept keyed by uid + mark-stale +
  designer suppression).
- **NEXT**: M7 generators (interfaces/signals/hardware/coverage), M8 diagnosis, M9 software, M10 CLI
  + Open2App-path contract test, M11–13 GUIs (dark-by-default, registry-driven phase bar,
  YAML-explorer config, selectable projects root) + designer + Project Manager, M14 packaging
  (two exes). **920** (TIA project coverage) is future — pending Open2App's project text-export.

## Conventions & gotchas

- Pipeline3App has its **own** `config_project/` — edit it, not Pipeline2App's.
- Regex YAML params must be **single-quoted**; JS `/…/flags` literals are accepted (`config.js_to_re`).
- `strike_handling` excludes struck rows only on `"exclude"`.
- Tag/device strings (`=S1`, `+MS1.CC1`, `-S67001`) are **text**; generated cells that start with
  `=`/`+`/`-` are materialized `data_type="s"` (else openpyxl treats them as formulas).
- **Comma CSV** everywhere on write; readers sniff `,`/`;`.
- Run/test from the `Pipeline3App` root. When committing `_Openn2`, end commit messages with
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
