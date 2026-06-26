# Pipeline4App (PL4) — SSOT-database rebuild

PL4 is a **clean-room rebuild of Pipeline3App (PL3)** around a **single source of truth (SSOT)
database**. PL3 works and stays shipped; PL4 is built in parallel on branch **`pl4`** (off `tia181920`).
The full design rationale is in **`DESIGN.md`** — read it first. This file is the live architecture +
state; **`HANDOFF.md`** is the point-in-time "what's next".

## The package + the lineages (PLn / OPn)
- **PLn** = the Python pipeline: `Pipeline2App` → `Pipeline3App` → **`Pipeline4App`**. Emits TIA `BuilderData/`.
- **OPn** = the C# TIA-Openness importer: `Open2App` → **`Openn3App`** → **`Openn4App`**. Reads `BuilderData/`.
- **PL3 + OP3 both work today** (the stable, shipped pair + the reference). **v4 = PL4 + OP4**, co-developed.
  The OP side is a separate Claude session; the contract brief for it is **`Shared/PL4_OP4_coordination.md`**.
- (PL3's own CLAUDE.md still says "Open2App" — that's stale; it means OPn.)

## Why (the thesis)
PL3 stages a flat `IODatabase.csv` (`list[dict]`) and each phase writes private output files. That forces
workarounds that exist only because cells are flat scalars: ~20 `|`-join/split sites, the "leftmost db
name" hack, `_type` dropped-on-persist + re-attached, `plc_binding` re-derived every call, and the
created data living only in export files. **PL4's principle (the user's directive): every datum the
pipeline retrieves, infers, or creates is written into the database — every io signal, db_element,
diagnosis element. The `BuilderData/` exports become byte-stable *projections* of the tables.** This is
**not** a SQL engine — it is **CSV files with JSON cells** + an in-memory `Database` object: light,
git-diffable, GUI-grid-able, no new dependency, but structured and comprehensive.

## The parity strategy (how PL4 is verified)
- **Internal tables** (the signals table, …) are a NEW format (JSON cells) → checked by **data-parity**:
  stage the same source documents through PL3 and PL4, assert every PL4 field (decoded) == PL3's value.
- **`BuilderData/` exports** are the OP contract → **byte-parity** while format-preserving (PL4 emits
  PL3-identical bytes; OP3 can cross-import), shifting to **end-to-end equivalence** where PL4+OP4
  deliberately improve the format (since OP4 is co-designed). Build format-preserving first; evolve the
  contract per-phase, verified.

## Architecture: one `Database`, many tables
```
Database
 ├─ signals            one row per I/O signal (+ node/metadata)   ← the fact table (DONE)
 ├─ db_members         every generated DB member (db_element)     ← 520 (TODO)
 ├─ diagnosis_entries  every diagnosis element (unified io|logic) ← 600 (TODO)
 ├─ plc_tags · interfaces · hardware_* · software_blocks · coverage · validation_issues   (TODO, per phase)
```
Each table persists to one **CSV-with-JSON-cells** file in the **top-level `Database/` folder**
(`Shared/Database/` builtin, or `<project>/Database/`). Every created entity carries a content-hash
**`uid`** and FKs to its source's uid; row order is preserved by insertion.

## Package layout (current)
```
Pipeline4App/
  DESIGN.md · CLAUDE.md · HANDOFF.md · launch_gui.py
  config_project/                  (the restructured config — see "Config" below)
  pipeline4/
    core/  keys.py · table.py · database.py · config.py
    io/    workbook.py
    domain/ signals.py · identity.py · matrix.py · staging.py · dbtemplate.py · datablocks.py · db_members.py · datablock_xml.py · interfaces.py · interface_xlsx.py
    gui/   app_main.py · phasebar.py · logview.py · theme.py
  tests/unit/  (plain-python, _harness.py — 88 tests, the green gate)
```

## The spine (`core/`)
- **`keys.uid(*parts)`** — the universal content hash: `sha1('|'.join, None→'')[:10]`. The STABLE
  identifying fields only (excludes workbook/seq/level → survives a document revision). Generalizes PL3's
  finding-uid.
- **`table.Table(name, columns, json_columns, key_columns)`** — rows are dicts; **declared `json_columns`
  are stored as real JSON in the cell** (`["07_DOOR"]`, a `type` object) and decoded on read; the rest are
  plain text. **Deterministic encoding** (`sort_keys`, sorted extra-column tail, `allow_nan=False`) so
  tables diff byte-stably. `add()` stamps a content-hash `uid` from `key_columns`. **Fail-loud**: a
  structured value in a non-JSON column, a ragged/duplicate-header file, or a malformed JSON cell raises a
  located error. `__iter__`/`__len__`/`extend`/`duplicate_uids()`. (Hardened by an adversarial review.)
- **`database.Database(tables)`** — named tables; `save(dir)`/`load(dir)` one CSV per table.

## Config (`core/config.py` + `config_project/`)
- **Paths + project isolation**: `use_project()` points the loaders, the `Database/` folder, and the
  `Output/` (BuilderData) tree at the project or the builtin `Shared/`. Sheet resolution (`resolve_sheet(s)`,
  JS-regex). **`project_params.yaml` is the nested schema** (the reviewed proposal): document paths
  (+ `*_previous_path`, reserved for the future ph100 change-tracing), `iolist_params` / `matrix_params`,
  `validation_params` (phase 100, sub-grouped). `load_params` resolves the doc paths; **`get_param(params,
  "a.b.c", default)`** is the safe dotted accessor (a present False/0/[] is returned, not the default).
  `csv_delimiter`/`copy_inputs` are constants; `language` lives in app_config.
- **Config CSVs** (read via `read_config_csv` over `core.table`'s codec, tolerant of hand edits):
  `load_column_map(doc)`, `load_signal_types()` (the **stripped** type schema — identity + tag + ce_mandatory;
  DB/diagnosis/interface attrs moved out), `resolve_type` (exact + `Z#` patterns).
- **`config_project/` restructured** (per the CSV review):
  - `input_docs/`: `column_map.csv`, `signal_types.csv` (18→10 cols).
  - `datablocks/`: `datablock_definitions` · `datablock_elements` (**real per-type member templates** — the
    single DB creation point, `member` + `for_each script_type`; relocated from `signal_types.db_element`) ·
    `datablock_types`.
  - `diagnosis/`: `diagnosis_columns` · `diagnosis_logic_rules` (the **unified trigger-driven DiagList +
    `source` io|logic** + the per-type diag attrs land with the ph600 port).
  - `chain_reactions/`: `object_families` · `interface_elements` (the follower/relationship rules).
  - DROPPED: `iolist_columns` (dead), `iolist_permanent_parts` (→ `validation_params.iolist.permanent_parts`),
    `datablock_elements_rules` (superseded). The device-types DB → `Shared/Database/`.

## Phase 300 — Staging — IN PROGRESS (direct fields done, registry-derived pending)
`domain/staging.py` + `identity.py` + `matrix.py`. **`stage()`** reads the configured I/O List through the
one workbook reader (by column position per `column_map`), drops Skip-Reason + struck rows (per
`strike_handling`), attaches the resolved `type` (object cell), runs **`matrix.annotate`** (C&E: `matrix_areas`
/ `ce_*` / `numerazione_linea` / `areas_description` as **list cells**), derives the document-side identity
(`iol_FLD`/`ce_FLD`/`combined_FLD`, `name_in_tagtable`/`tagtable`), builds the **`signals` table** (content-hash
`uid` = `combined_FLD`+`script_type`+`source_cell`), and saves the Database. The GUI's **"300" button runs it**.
- **Parity achieved**: the real I/O List stages to **269 signals == PL3's IODatabase**, **0 duplicate uids**,
  and **0 mismatches** vs PL3 on `matrix_areas`, `combined_FLD`, `ce_functional_unit`, `IsSorterArea`, and the
  positional node ranges `I_/Q_startByte/endByte` (matched by `source_cell`).
- **Identity reads the `type` cell** (PL4 persists the resolved type as an object; PL3 used the ephemeral `_type`).
- **Direct fields DONE**: the positional node address ranges (`_add_node_address_ranges`: a node owns the rows
  beneath it in I/O-List order until the next node / sheet end → `I_/Q_startByte/endByte`) and `IsSorterArea`
  (`matrix_params.sorter_areas: [1]` number → `"AREA 1"` name → intersect the `matrix_areas` list cell).
- **Still pending**: `subnet_name` (from `profinet_ip`). The registry-derived `name_in_db`/`datablocks`/
  `plc_binding` are now WRITTEN BACK by phase 520 (below), not at staging.

## Phase 520 — Data Blocks — DONE (520a/b/c; InstanceDBs.csv deferred to 800)
`domain/dbtemplate.py` + `domain/datablocks.py` + `domain/db_members.py` + `domain/datablock_xml.py`. The
**SSOT model**: one registry evaluator (`datablocks.generate`) over the **signals** table → three tables
(`db_blocks` the surviving DBs + attrs; `db_members` every Global-DB member; `instance_dbs` the FB instance
families) → projected to `<DB>.xml` (`datablock_xml.project`, from `db_blocks` + `db_members`). The
**3 registry-derived signal fields** (`name_in_db`/`datablocks`/`plc_binding`) are **written back** onto the
signals (decision: write-back after 520, the single evaluator — no drift; DESIGN §9 orders 520 before its
consumers 400/600).
- **`dbtemplate.py`** (520a) — faithful port of PL3's `render` (PEP-3101 + numeric coercion) + the `for_each`
  DSL (`row where P` / `<var> in unique(col) where P`; predicates `numeric()/=/!=/~/in[…]` + `and/or/not/()`).
- **`datablocks.generate`** (520b) — port of PL3's validate-and-halt generator: seeds (`Always FALSE/TRUE`/
  `No Operation`), the `if_elements` seed-only-drop, **F_DB OPC-lock** + `f_db`→`F_DB`, dedup, instance
  families. PL4 additions per member: `source` (the producing signal `uid` / a `unique` bound value / `seed`),
  + `source_row`/`seq` bookkeeping the write-back uses.
- **`write_back`** — denormalizes membership onto each signal: `datablocks` (ordered DBs, element-row order),
  `name_in_db` (its member in the LEFTMOST DB = earliest matching element row), `plc_binding`
  (`"<leftmost db>"."<name_in_db>"`, else the tag, else ''). Only `row`-kind members attribute (not seeds /
  `unique` aggregates).
- **Parity (real data)**: vs PL3 IODatabase — **0 mismatches** on `name_in_db`/`datablocks`/`plc_binding`
  across 269 signals; `db_members` **member SETS identical** to PL3's 5 reference GlobalDB XMLs (order is
  grouped-by-type vs PL3's interleaved row-order — accepted/functional, set-equal). The 4 DBs `DiagnosticTags`/
  `00_Commissioning`/`PROFINET_NODES_*` aren't in the frozen ImportReady (it predates them); the IODatabase
  write-back parity covers their PA/PW signals.
- **520c projection** (`datablock_xml.py`): port of PL3's `_db_xml` reading the `db_blocks` + `db_members`
  tables (a PURE projection — the chosen `db_blocks` table holds the per-DB attrs, no config re-read). Writes
  `<db_name>.xml` to `config.blocks_import_dir()` (BOM/CRLF, no trailing newline), name-sorted `<Number>`
  placeholder. It writes ONLY the DBs in `db_blocks` and leaves other files untouched (NO hardcoded keep-list
  — `db_blocks` is the ownership record, so a phase-800-owned `02_COM.xml` survives by not being a 520 DB).
  The F_DB OPC-lock is code-enforced here. **Parity**: all 5 reference GlobalDB XMLs (01_Pushbutton, 03_FDBACK, 03_FDBACK_RAW,
  04_SPEED, 07_DOOR) are **byte-equivalent** (header + footer + every member fragment identical; only member
  ORDER differs — accepted). The GUI **"500" button** runs stage → build → project (510 I/O Tags not yet ported).
- **Deferred to phase 800**: `instance_dbs` → `InstanceDBs.csv` (a `blocks_creation_dir` surface that MERGES
  520's config families with 800's builder instances — the `instance_dbs` table is ready for it).

## Phase 400 — Interfaces — IN PROGRESS (400a + 400b + 400c done; 400d–e TODO)
`domain/interfaces.py`. Builds one `IF_<instance>.xlsx` per IOC signal from the MachineInterfaces template,
mirrors flagged signals into a byte-packed block, and (gated) inserts each as an `IF_` sheet into the I/O
List. The mirrored signals + byte layout land in the **`interfaces`** SSOT table; the `IF_*.xlsx` are its
projection. **Decisions (user)**: include the `xlsx_edit` port + `insert_interface_sheets` in 400 (not
deferred); the per-type `interface_tagname` templates live in a **new `chain_reactions/interface_tagnames.csv`**
(not re-added to `signal_types`).
- **400a DONE — `interface_tagname`** (the Signal Name Side 1 base): `chain_reactions/interface_tagnames.csv`
  (relocated from PL3 `signal_types` col 18) + `config.load_interface_tagnames()`; `identity.interp_keep` +
  `identity.interface_tagname` (PL4: `{tag_name}`→staged `name_in_tagtable`, `{db_element}`→520 `name_in_db`,
  keeping `{interface_name}`/`{interface_id}`); `interfaces.annotate_interface_tagnames` runs AFTER 520
  (DESIGN §9 `520 → 400`). **Parity: 0 mismatches** vs PL3 IODatabase `interface_tagname` (269 signals, 113 non-empty).
- **400b DONE — the `interfaces` + `interface_elements` tables** (the SSOT parent/child). `find_interfaces`
  (per IOC row), `collect_mirror_set` (direct `interface_mapping` mirrors→Q; `diagnosis_logic_rules` followers→Q;
  `interface_elements` followers→I/Q, the only **I** source; dedup on `(direction, script_type, mirror_name)`),
  `allocate_bytes` (≥8-byte gap, group by script_type, BOOL→full 2-byte block / WORD→row), `template_last_used_byte`
  (reads the template). `config.load_diagnosis_logic_rules` / `load_interface_elements` / `INTERFACE_CUSTOM_GAP` /
  `INTERFACE_TEMPLATE`. PL4 NOTE: PL3's `datablock_elements_rules` was **consolidated into `diagnosis_logic_rules`**
  (so 400 has 2 follower sources, not 3); `_mirror_name` = the stored `plc_binding`; the per-DI1/2 signal name now
  resolves `{db_element}`→`name_in_db`. **Parity (SORTER-01)**: all **18 mirror elements match the reference exactly**
  (category/direction/expression + offset/bit, keyed by `plc_binding`); the lone ref-extra `IF_ENCODER_SPEED` is
  stale config (dropped). The frozen ref left `{db_element}` literal (old PL3 bug) — PL4's resolved names match PL3's
  current `interface_tagname` (400a 0-mismatch).
- **`+DIAG` auto-mirror DEFERRED**: needs the per-type `in_diag` (relocated with **ph600**). Until then a `+DIAG`
  interface (SORTER+DIAG-02) gets only its `interface_mapping` mirrors. `collect_mirror_set` already has the guard.
- **400c DONE — the `IF_*.xlsx` projection** (`interface_xlsx.py`, openpyxl - PL3 does the same; these files are
  documentation, not read back except via 400e): per `interfaces` row, copy the template → keep the chosen machine
  sheet → retitle `IF_<instance>` → `_plug` Base Address/Node/Index (Side rows, by header) + replace `<index>` →
  `_append_custom_rows` lays the `interface_elements` onto the data table WITH the BOOL-block padding (full 2-byte
  block: real signals low, blank addressed rows + separator; WORD = row + separator) → save. Output `config.interfaces_dir()`.
  The GUI **"400" button** runs stage → 520 → build_interfaces → project. **Verify (SORTER-01)**: all 18 mirror
  elements written with **0 byte mismatches**, the 16-row BOOL blocks, sheet retitled, re-opens cleanly (real-Excel
  validity is the user's check). 182 data rows vs the ref's 184 = the stale `IF_ENCODER_SPEED` WORD+separator PL4 omits.
- **400d–e TODO**: the **`xlsx_edit`** surgical writer port (`pipeline4/io/xlsx_edit.py`, ~446 lines ZIP/regex);
  `insert_interface_sheets` + the address cache (`_interface_address_caches`). Then 510 reads the inserted IF_ sheets.

## GUI — runnable shell (`gui/` + `launch_gui.py`)
`python launch_gui.py` opens a sv-ttk dark window (graceful fallback) with a toolbar, the **phase-button
bar** (Run + the 9 phases, ButtonsLayout colours), a colour-coded **log viewer**, and a status bar. Wired in
EARLY (gui-less PL3 builds hid integration problems). **"300 Documents Staging" runs `stage()` for real**;
the other buttons log "not implemented". The handler is wrapped so a not-yet-ready phase can't take the
window down. (Phase registry-driven bar, the structured-record clickable log, the Files tab, threading →
later.)

## Testing
Plain-`python` tests under `tests/unit/` via `_harness.py` (PASS/FAIL, non-zero exit). The
**data-independent suite is the green gate** (currently **44**: keys/table/database, signals schema,
sheets/workbook, params/config_loaders, staging identity+read). Data-dependent parity (staging vs PL3) is
verified by a script against the real docs (not in the gate). Each phase is committed only with its gate +
parity green.

## Conventions & gotchas
- **JSON cells are schema-declared** (a column is JSON by the table's `json_columns`, not by guessing). The
  codec is deterministic (sorted keys) for byte-stable diffs. `None` ↔ empty cell; `[]` ↔ `[]`.
- **Identity reads `row["type"]`** (the object cell), not PL3's `_type`.
- **openpyxl makes a leading `=` a formula** → in test xlsx use non-`=` values (real IoLists store FU/Loc/Dev
  as text, so `stage()` reads them fine).
- **The `datablock_elements` real-template relocation changes member declaration order** (grouped-by-type vs
  PL3's row-order). For `Optimized` DBs that's cosmetic (same members), and OP4 is co-designed → 520 parity is
  functional/end-to-end, not byte-identical to PL3. (User accepted.)
- **No legacy management** (DESIGN 10.6): PL4 reads the source documents fresh; it never ingests PL3
  intermediates. Config is the JSON-cell skeleton, no `|`-list back-compat.
- **Verbose/explicit naming preferred** (DESIGN 10.7); reuse a PL3 name only where it's the same concept.
- Run/test from the `Pipeline4App` root. Commit messages end with
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
