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
 ├─ diagnosis_entries  every diagnosis element (unified io|logic) ← 600 (DONE)
 ├─ hardware_stations · hardware_modules   the generatable heads + IoDevice cards   ← 700a (DONE)
 ├─ software_blocks · software_block_members   the built blocks + their @ rows   ← 800a (DONE)
 ├─ coverage   one row per staged signal (cross-stage placement + ORPHAN)   ← 900 (DONE)
 ├─ validation_issues   the severity facts (per phase; DONE)
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
    core/  keys.py · table.py · database.py · config.py · severity.py · finding.py · treatments.py · run.py · model.py
    io/    workbook.py · xlsx_edit.py · render.py
    domain/ signals.py · identity.py · matrix.py · staging.py · dbtemplate.py · datablocks.py · db_members.py · datablock_xml.py · interfaces.py · interface_xlsx.py · io_tags.py · diagnosis_entries.py · diagnosis.py · diaglist_csv.py · diagnosis_scl.py · hardware.py · hardware_csv.py · coverage.py
    domain/blocks/ (ph800) database.py · table.py · registry.py · templates.py · builders.py · engine.py · xml_emit.py
    domain/validation/ (ph100) __init__.py · address.py · messages.py · model.py · iolist.py · matrix.py · ce_refs.py · crosscheck.py · phase.py
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
- **Severity S3 retrofit DONE** (parity-locked): `stage()` returns **`(database, findings)`** instead of a bare
  `Database`. A missing I/O sheet emits the blocking **`stg_no_io_sheet`** FAIL (replacing the `raise SystemExit`;
  `load_io_list` now returns `([], matched)`) and `stage` returns WITHOUT writing (`run.has_blocking` guard); a
  duplicate signal uid emits **`stg_dup_signal_uid`** WARN (moved out of the GUI into `_dup_findings`, one per
  shared uid). On success `stage` `finding.record`s into `validation_issues` + saves. **PARITY: `signals.csv` +
  `diagnosis_cabinets.csv` byte-identical to pre-S3** (verified new-vs-HEAD; only `validation_issues.csv` is added,
  empty on clean data). The 4 GUI handlers accumulate staging + 520 findings and call `run.gate` ONCE (see GUI note).

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
- **Severity S2 retrofit DONE** (the report container swap, parity-locked): `generate` returns
  **`list[Finding]`** (phase 520) instead of `(errors, warnings)` strings — 9 FAIL slugs (`db_for_each_invalid`,
  `db_only_load_optimized`, `db_instance_needs_fb`, `db_global_needs_literal`, `db_element_not_declared`,
  `db_unknown_datatype`, `db_element_for_each`, `db_member_render`, `db_instance_name_render`) + 4 WARN
  (`db_for_each_matches_nothing`, `db_unknown_prog_lang`, `db_fdb_opc_ignored`, `db_member_duplicate`); the
  human message → `detail`, the `DB <name>` / `element <m> -> DB <db>` prefix → `location` (so the uid is
  stable). `build` returns **`(database, findings)`**, keeps the **`run.has_blocking` raw-FAIL no-write guard**,
  and `finding.record`s the facts to the **`validation_issues`** table on success. The GUI handlers (500 owner +
  400/600 prereqs) call **`run.gate(findings, self.log.append, label=…)`** to render + halt. **PARITY: the 9
  GlobalDB XMLs are byte-identical to pre-S2** (verified new-vs-HEAD, 0 diffs); only the report container + the
  log lines changed, never the skip/write predicates.

## Phase 400 — Interfaces — DONE (400a + 400b + 400c + 400d + 400e + 400f; + severity S4)
**Severity S4 (parity-locked):** `find_interfaces` + `collect_mirror_set` return `(records/elems, findings)` (was
warning strings) - WARN slugs **`if_ioc_no_index`** (an IOC row with no Index) + **`if_signal_not_mirrored`** (a
picked signal with no db_element/tag). `build_interfaces` returns **`(database, findings)`**, `finding.record`s them
to `validation_issues`, saves. WARN-only (no FAIL). The GUI **`run.render`s** them (not `gate` - the SSOT tables are
already written). PARITY: `interfaces` + `interface_elements` byte-identical to pre-S4 (verified new-vs-HEAD).
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
- **400 stores `io_address_side1` on each `interface_element`** (added for 510): `build_interfaces` computes the
  `{I|Q}{base+offset}[.bit]` address in Python via `interfaces.io_address_side1` (the pure LET mirror, moved here
  from `interface_xlsx` so both use it) + `template_input_format` (the `$AI$2` isynt, read per sheet), and WRITES it
  into the table — so 510 is a pure projection of the SSOT (no IF_-sheet read-back). Verified: the stored value ==
  the value 400e seeds into the inserted IF_ sheet, for all 22 SORTER custom-block elements (0 mismatch).
- **`+DIAG` auto-mirror DEFERRED**: needs the per-type `in_diag` (relocated with **ph600**). Until then a `+DIAG`
  interface (SORTER+DIAG-02) gets only its `interface_mapping` mirrors. `collect_mirror_set` already has the guard.
  The `+DIAG` auto-mirror was **lit up by 600a** (staging `in_diag` onto the `type`) — SORTER+DIAG-02 grew 4 → 83.
- **400f DONE — template-native interface signals.** `interfaces.template_native_elements(template, sheet,
  interface_id, base, isynt)` reads the MachineInterfaces template's SHIPPED per-type rows (the SORTER sheet's 7:
  HEARTBEAT / POWER ENABLED / EMERGENCY RESET / SORTER- RUNNING / …) — `<index>` resolved to the interface_id, the
  address RE-computed for this interface's base (the template's cached I/O Address Side 1 is base-10000-stale) — and
  `build_interfaces` adds them to `interface_elements` as `source="template"` (offsets fixed by the template, NOT
  allocated). The IF_ projection (`_append_custom_rows`) SKIPS `source="template"` (already in the copied sheet, no
  doubling). So `interface_elements` is now the COMPLETE interface tag set (native + mirror) and 510's PLCTags
  includes the native signals. **Parity (fresh-PL3 oracle, to scratch)**: IF_SORTER-01 **25 == PL3's 25** (the 14
  native match PL3); PL4 PLCTags 213 vs PL3 208. **Interface mirror parity vs current PL3 is EXACT** — comparing at
  the source (`collect_mirror_set` + `allocate_bytes`), PL4 == current-PL3 for both interfaces (SORTER-01 18/18,
  SORTER+DIAG-02 83/83, 0 address-triple diffs, Door Alarm @ offset 24 in both). The PLCTags oracle's apparent
  deltas (a +2-byte `Door Alarm` shift, +5 `Contactor` mirrors) were **stale inserted IF_ sheets** — PL3's
  `generate_io_tags` READS the IF_ sheets already in the I/O List (offset 22, old +DIAG=78) rather than
  regenerating them; NOT PL4 bugs. PL4 is also MORE correct than current PL3 on naming (PL3 still emits a literal
  `{db_element}` + the stale `Encoder Speed`; PL4 resolves both). Tests: `test_interfaces.py`
  `template_native_elements` + `test_interface_xlsx.py` `append_custom_rows_skips_template_source`.
- **400c DONE — the `IF_*.xlsx` projection** (`interface_xlsx.py`, openpyxl - PL3 does the same; these files are
  documentation, not read back except via 400e): per `interfaces` row, copy the template → keep the chosen machine
  sheet → retitle `IF_<instance>` → `_plug` Base Address/Node/Index (Side rows, by header) + replace `<index>` →
  `_append_custom_rows` lays the `interface_elements` onto the data table WITH the BOOL-block padding (full 2-byte
  block: real signals low, blank addressed rows + separator; WORD = row + separator) → save. Output `config.interfaces_dir()`.
  The GUI **"400" button** runs stage → 520 → build_interfaces → project. **Verify (SORTER-01)**: all 18 mirror
  elements written with **0 byte mismatches**, the 16-row BOOL blocks, sheet retitled, re-opens cleanly (real-Excel
  validity is the user's check). 182 data rows vs the ref's 184 = the stale `IF_ENCODER_SPEED` WORD+separator PL4 omits.
- **400d DONE — the `xlsx_edit` surgical writer** (`pipeline4/io/xlsx_edit.py`): faithful port of PL3's module
  (pure stdlib ZIP + regex XML surgery, no openpyxl on write — it is architecture-independent, like `io/workbook.py`).
  `set_cells` (per-sheet engine, with the ARRAY GUARD freezing a spill an edit lands in) · `edit_workbook` (the
  zip-level orchestrator: surgical `cell_edits`, whole-sheet `new_sheets`/`delete_sheets`, byte-preserving
  `append_rows`, always drops the stale `xl/calcChain.xml`; atomic temp + `os.replace`) · `build_sheet_xml`/
  `build_row_xml`/`append_to_sheet` (fresh-grid + append, inline strings so a leading `=` stays TEXT) ·
  `freeze_arrays` (the post-process the openpyxl-based 400e insert calls). Covered by `test_xlsx_edit.py`
  (14 cases, ported verbatim — the array-freeze/no-overlap, style/neighbour preservation, column-sorted insert,
  the grid/row builders, add-replace-delete + append round-trips through a real openpyxl-saved zip).
- **400e DONE — `insert_interface_sheets`** (in `interface_xlsx.py`, gated by `iolist_params.insert_interface_sheets`):
  losslessly splice each projected `IF_<instance>.xlsx` into the I/O List as an `IF_<instance>` sheet (idempotent —
  skips one already present; a timestamped `.bak` first). Clean-room port of PL3's insertion path: `_copy_sheet`
  (re-creates each table with **clean id+name-only columns** — dropping the source's out-of-range `dataDxfId` +
  stale `calculatedColumnFormula`, else Excel drops the table — and a per-instance table name) → openpyxl save →
  `_capture_formula_caches`/`_patch_formula_cache` restore the I/O List's own formula caches (openpyxl drops them →
  a `data_only` reader would see None for Profinet IP/name) → **seed the interface address cache**
  (`_interface_address_caches`/`_io_address`/`_resolve_num` MIRROR the `I/O Address Side 1` LET in Python:
  `{I|Q}{base+offset}[.bit]`, the offset/bit chains resolved, columns bound by header — so 510 reads correct
  addresses without Excel while the LET survives for an engineer) → atomic ZIP rewrite → **`xlsx_edit.freeze_arrays`**
  (400d) freezes any dynamic array openpyxl flattened in the untouched sheets. Reuses `xlsx_edit._sheet_name_to_part`
  + `freeze_arrays` (no duplication). The GUI **"400" button** now runs stage → 520 → build → project → insert.
  **Parity (real data, non-destructive scratch copy)**: the 2 IF_ sheets insert losslessly — all 7 source sheets
  kept, a sample formula survives, all 15 Profinet IP cached values survive a `data_only` re-stage, and 151 + 71
  `I/O Address Side 1` values are seeded + read back via `data_only`. Tests: `test_interface_xlsx.py` (+5 cases:
  the LET mirror, the offset/bit chain resolver, the address-cache seed, the lossless+idempotent insert with the
  table-dxf/calc strip + the array-freeze).

## Phase 510 — I/O Tags — DONE (interface-completeness follow-up tracked; + severity S4)
**Severity S4 (parity-locked):** `interface_tags` returns `(tags, findings)` with the WARN slug **`iotag_no_address`**
(a named interface element with no resolved I/O address - skipped); `project()`'s return dict renames `warnings` →
**`findings`**. A PURE projection - it does NOT `record` (only the build steps do); the GUI **`run.render`s** the
findings. PARITY: the PLCTags tag list is content-identical to pre-S4 (verified new-vs-HEAD, 213 tags).
`domain/io_tags.py` + `config.io_tags_dir()`. A PURE projection of the `signals` + `interface_elements` SSOT tables
to **`PlcTags/PLCTags.xlsx`** (the OP4 BuilderData import surface — leaf `PlcTags` to match PL3's contract path).
Two tag sources mixed into one workbook, sorted by Path (= tag table), all values text:
- **(a) resolved I/O signals** — one tag per `identity.is_io_signal` row with a non-empty `name_in_tagtable`:
  Name=`name_in_tagtable`, Path=`tagtable`, Data Type=`Bool` (PL3 hard-codes Bool for direct I/O — a future non-Bool
  needs a `signal_types` `data_type` col), Address=`%`-prefixed `bit`, Comment=`identity.tag_comment` (the type's
  `io_comment` template resolved).
- **(b) interface tags** — one per `interface_elements` row (NOT a read-back of the IF_ sheets — the user's SSOT
  decision): Name=`signal_name`, Path=`IF_<instance>`, Data Type=`_tia_dtype(data_type)` (BOOL→Bool/WORD→Word),
  Address=`%`+the STORED `io_address_side1`, Comment=`description`. A named element with no resolved address is
  skipped+warned (mirrors PL3); the addresses come from the SSOT column 400 stores (verified == the 400e seed).
Two sheets: **"PLC Tags"** (10 cols: Name/Path/Data Type/Logical Address/Comment/3×Hmi `True`/Typeobject ID/Version
ID) + **"TagTable Properties"** (3 cols: Path/BelongsToUnit/Accessibility, one row per distinct Path). Output via
`write_plc_tags` (a fresh openpyxl workbook; `_append_text_row` forces a leading `=`/`+`/`-` to text). `project`
returns `{path, total, io_count, iface_count, tables, warnings}`. The GUI **"500" button** now runs stage → 520 build
→ project XML → **build_interfaces → io_tags.project**. Clean-room port of PL3's `generate_io_tags`/`build_io_tags`/
`interface_tags`/`write_plc_tags` (the read-the-IF_-sheets path replaced by the SSOT read). Tests: `test_io_tags.py`
(8 cases, hermetic — the two sources, the dtype map + %-address, the text-forcing, the two-sheet structure, the
sort+distinct-props, the skip+warn, the return contract).
- **Parity (real data, non-destructive scratch copy vs the reference `PlcTags/PLCTags.xlsx`)**: headers identical;
  the **direct-I/O side is EXACT — 98/98 across all 8 signal tag-tables** (Alarms_Warnings 34, SAFETY_Doors 24,
  SAFETY_Contactors 18, …). The interface side emits the SSOT mirror block; two KNOWN gaps remain (both
  interface-table completeness, not 510 bugs): **(1)** the ~14 **template-native** interface signals (the SORTER
  template's 7 shipped signals × 2 instances — in the IF_ sheet, not in `interface_elements`); **(2)** the ~74
  **+DIAG auto-mirror** tags on SORTER+DIAG-02 (the deferred `in_diag`/ph600 feature). Both are captured together at
  ph600 (pull the template-native rows + the `in_diag` set into `interface_elements`) — see the Phase 400 follow-up.

## Phase 600 — Diagnosis — DONE (600a + 600b + 600c + 600d; + severity S5)
**Severity S5 (parity-locked):** `diagnosis.build` returns **`(database, findings)`** (was `(database, errors,
warnings)` - the last legacy tuple; its errors/warnings were always EMPTY/vestigial), `finding.record`s + saves;
`diaglist_csv.project` gains a `findings: []` key; `diagnosis_scl.project` renames its dict `warnings` → **`findings`**
and emits the WARN slug **`diag_scl_template_missing`** (phase 620) on an absent SCL template. All three are WARN-only;
the GUI `_run_diagnosis` consumes the build tuple + `run.render`s the combined 600/610/620 findings (no halt). PARITY:
`diagnosis_entries` + DiagList_IO/Logic.csv + Diagnostic_for_OPC.scl byte-identical to pre-S5 (verified new-vs-HEAD).
`domain/diagnosis_entries.py` (the table defs) + the per-type config relocation + the staging prereqs. The plan
(from the 600 understand pass): a UNIFIED `diagnosis_entries` table (`source` = io|logic) → projected to
`DiagList_IO.csv` + `DiagList_Logic.csv` (600c) + the OPC SCL (600d), with a parent `diagnosis_cabinets` table.
- **600a DONE — the config relocation + staging foundation.** The per-type diagnosis attrs PL4 stripped from
  `signal_types.csv` are relocated to a NEW **`config_project/diagnosis/signal_diagnosis.csv`** keyed by `type_id`
  (`in_diag`, `diag_logic`, `diag_desc`, **`tristate`** [a new explicit per-type enable flag - the user's addition],
  `tristate_desc`), values verbatim from PL3. `config.load_signal_diagnosis()` + `load_diagnosis_columns()`.
  **Staging** now merges `in_diag`/`diag_logic`/`tristate`/`tristate_desc` onto the resolved **`type` object** and
  resolves **`diag_desc`** (the per-type template) onto the row; it also reads the DiagnosisBlocks sheet
  (`staging.load_diagnosis_blocks`, port of PL3's `load_diagnostic_blocks`) into the **`diagnosis_cabinets`** SSOT
  table (`cabinet_id`/`index`/`fld`/`template_type`/`swp`) - so 600 is a pure table read. **`identity.interp` now
  honors a `{token:spec}` format spec** (`{diag_cabinet:03d}`->`000`; a blank value is NOT padded) - PL3's
  bare-token resolver emitted the literal `{diag_cabinet:03d}`, so this is a deliberate FIX (the `:03d`/`:02d` specs
  are restored in `diagnosis_columns.csv`). **Side effect (intended): the phase-400 `+DIAG` auto-mirror lights up** -
  `collect_mirror_set`'s `type.in_diag` guard now fires, so SORTER+DIAG-02 grows 4 -> 83 mirror elements (the
  template-native gap still remains). **Parity**: `diag_desc` **0 mismatches/269** vs PL3 IODatabase; the
  `diagnosis_cabinets` table **0 field mismatches** vs PL3's `load_diagnostic_blocks` (16 cabinets).
  **NOTE staging now emits 2 tables** (`signals` + `diagnosis_cabinets`).
- **600b DONE - the builder** (`domain/diagnosis.py` `build()`): populates the unified `diagnosis_entries` from
  `signals` + `diagnosis_cabinets` + the `diagnosis_logic_rules`. Clean-room port of PL3's `build_diag_list_io`/
  `_resolve_logic`/`ml_value`/`fl_value`/`node_of` reading the PL4 `type` object + the STORED `plc_binding` (no
  re-derivation). Each entry: `source` (io|logic), `source_signal`, `rule_name`, `cabinet`/`bit`/`is_warning`, the
  SCL channel values (`in_binding`/`ml_value`/`fl_value` computed HERE so the SCL projector is pure), + a frozen
  `diag_columns` snapshot ({header->cell}, the `$PLC_Binding$` sentinel resolved, the `:03d`/`:02d` specs honored).
  `resolve_logic` = the OR/per-row rules (cabinet: numeric `diag_cabinet` -> paired-channel sibling -> FU+LOC ->
  `diagnosis_cabinets`; the next free bit per alarm/warning family). GOTCHA fixed: inject the logic row's
  `diag_cabinet`/`diag_bit` as STRINGS (interp's `value or ""` turns the falsy int `0` into `''` -> a bit-0 row
  rendered blank). **Parity (real data, vs the reference DiagLists by `PLC_Binding`)**: **DiagList_IO 73/73 and
  DiagList_Logic 6/6 - 0 field mismatches** (logic_count == #N1/2 + #DI1/2 staged rows). Tests: `test_diagnosis.py`
  (11 total; +5 for 600b: `ml_value`, `node_of`/`fl_value`, `resolve_logic` OR/next-free-bit/cabinet, the build).
- **600c DONE - the DiagList CSV projections** (`domain/diaglist_csv.py` `project()`): filter `diagnosis_entries`
  by `source` and write each entry's frozen `diag_columns` snapshot under the config headers -> `DiagList_IO.csv`
  (source=io) + `DiagList_Logic.csv` (source=logic), comma CSV, **CRLF, no BOM** (`csv.writer`, `config.diaglist_dir()`
  under ProjectDocumentation - documentation, not a BuilderData surface). The GUI **"600" button** now runs stage ->
  520 build -> diagnosis.build -> diaglist_csv.project. **Parity (real data, scratch)**: both files are **FULL-ROW
  IDENTICAL** to the reference (DiagList_IO 73/73 + DiagList_Logic 6/6, 0 PL4-only / 0 ref-only; header match, CRLF,
  no BOM). Tests: `test_diagnosis.py` (+2: the two-file projection + the CRLF/no-BOM format). 13 total in the suite.
- **600d DONE - the OPC SCL** (`domain/diagnosis_scl.py` `project()`): port of PL3's SCL section reading the
  `diagnosis_entries` (channel values already stored) + `diagnosis_cabinets` (`template_type` -> the 01-04 variant).
  `render_scl` parses the `06_Diagnostic for OPC.scl` template (`config.DIAG_SCL_TEMPLATE`) and emits one FUNCTION,
  one REGION per cabinet (CabState + one BoolToUDInt per packed DWord: bit 0-31->DW1/32-63->DW2, ch = bit%32). UTF-8
  BOM + CRLF; the FUNCTION is renamed (drop `TEMPLATE--vX.Y--`); output `config.blocks_import_dir()`. **TRISTATE
  (user's decision): a cabinet is tristate when `template_type` in {2,4} OR it contains a signal whose type has
  `tristate=yes`** (the per-type flag, an additional trigger; when it forces tristate on an odd template_type the
  tail uses the tristate-counterpart variant 1->2/3->4). The GUI **"600" button** now runs 610 + 620. **Parity (real
  data)**: the SCL is **BYTE-IDENTICAL to the reference** (22752 bytes, 438 lines, 1.0000 similarity, 0 diff lines;
  32 REGIONs, 7 Tristate_DW). Tests: `test_diagnosis.py` (+4: render_scl variants/rename, the per-type tristate
  trigger, the BOM/CRLF write, the synthetic-template project). 17 total in the suite.
- **Still open (the interface-completeness follow-up)**: re-verify 510 PLCTags after the +DIAG unblock + add the
  template-native capture (see the Phase 400 section). Then 800/900/100.

## Phase 700 — Hardware — DONE (700a build + 700b CSV projection)
`domain/hardware.py` + `domain/hardware_csv.py` - a clean-room port of PL3's `hardware.extract` + format-2 writer
into PL4's SSOT model. A single ordered pass over the `signals` table populates **`hardware_stations`** (one row per
generatable head - a PLC/PlcCardCm/IoDevice) + **`hardware_modules`** (the IoDevice cards); the
`HardwareConfiguration/Stations.csv` + `Modules.csv` BuilderData surface is a pure projection of these tables. The
GUI **"700" button** runs stage -> build -> project.
- **700a DONE - `build()` + the tables + config.** A head opens a station (`script_type` PLC->Plc, PlcCardCm->
  PlcCardCm, or Type col-R first letter P->IoDevice); the rows beneath it (until the next head) are its signals.
  Stations: name=`profinet_name`, Model Id=Part No (spaces stripped), Subnet from the IP, group=
  `<functional_unit>_IODevices`, Custom Parameters = the DTD col-7 `%I%`/`%Q%`+N address template then col-AG
  (override). Modules (IoDevice only): cards grouped by Slot (a Slot == the device's own tag is the TIA-auto-plugged
  card, skipped); I/Q Addr = the card start byte; Custom Parameters = `PotentialGroup=1` on the first card + the DTD
  col-6 by-signal-type `Ch(#)`->channel blocks then col-AG; default cards (DTD `<PARENT>:SUFFIX`) add one row per
  station of PARENT. **Severity model:** a head whose Part No isn't in the DeviceTypesDatabase -> **`hw_device_not_in_dtd`
  FAIL** (halts + no write; operator-downgradable) / **`hw_switch_not_in_dtd` WARN** (a switch, "SWITCH" in the
  description). `build` returns `(database, findings)` + `run.has_blocking` guard + `record` + save. **Config:**
  `config.load_device_types_db` (delim-sniffed; `by_id` + `default_cards`; cols model_id/dev_type/order/comment/
  params/params_by_type/io_addr_params - col-5 `params` is OP4-applied, NEVER written) + `parse_params_by_type` +
  `hardware_dir()` + `DEVICE_TYPES_DB_DEFAULT` (`Shared/HardwareConfigBuilderData/DeviceTypesDatabase.csv`).
  **PARITY (vs current PL3 `extract` over the same staged rows - the frozen reference is DTD-drift-stale):
  9 stations + 18 modules, 0 field mismatches** across every station/module field; 2 `hw_switch_not_in_dtd` WARN,
  0 FAIL (all non-switch devices are in the DTD, so the build always succeeds on the real data). Tests:
  `test_hardware.py` (9: helpers, the extract incl. auto-plug/PotentialGroup/by-type/default-cards, the missing-DTD
  FAIL/switch-WARN, the table fill + int->str of slot/addr).
- **700b DONE - the format-2 projection.** `domain/hardware_csv.py` `project()` reads the two tables and writes
  `Stations.csv` + `Modules.csv` to `config.hardware_dir()` - **comma format-2, no BOM, CRLF**, a `#!format=2` tag +
  a descriptive `# header` comment (OP4 reads by POSITION; the header is a comment). The snake_case table columns are
  emitted in the format-2 column order (`_STATIONS_KEYS`/`_MODULES_KEYS`); `_format2` + the tag/header literals are
  verbatim from PL3. Pure projection (`findings: []`, no record). The GUI `_run_hardware` runs stage -> `hardware.build`
  (halt-capable, `run.gate`) -> `hardware_csv.project` (hardware needs only staging, NOT 520). **PARITY: `Stations.csv`
  (1145 bytes) + `Modules.csv` (1896 bytes) byte-identical to PL3's `_format2` over the same extract.** Test:
  `test_hardware.py::format2_projection` (no BOM, CRLF, the fmt2 tag + descriptive header + data rows).

## Phase 800 — Software — DONE (800a spine + 800b complex builders + 800c XML/02_COM/InstanceDBs/GUI)
`domain/blocks/` (package) - a clean-room port of PL3's `domain/blocks/`. The model: **`Database`** (read-only
accessors over the `signals` rows) -> **builders** (hand-written Python, `@builds("name")`, one per template) ->
**`Table`** (columns + rows; a list cell = the horizontal ITERATOR) -> the **engine** serializes to the `$/#/%/@`
**CreationInfo CSV** (the OP4 import surface). **Decision (user): the editable `.xlsm` shells are DEFERRED** (an
operator-editing surface, NOT part of the OP4 contract); the CSVs are produced directly in `fill` mode. **Phase 800
depends on 520** (the builders read the write-back fields `name_in_db`/`datablocks`/`plc_binding`).
- **800a DONE - the spine + engine + simple builders.** `table.py` (Table, verbatim) · `registry.py` (`@builds`,
  verbatim) · `database.py` (Database - ADAPTED: PL4's `datablocks`/`matrix_areas` are JSON **list** cells, so
  `by_db`/`by_area`/`areas` read the lists via `_as_list`, no `|`-split) · `templates.py` (`scan_templates` over the
  shipped `*.xml` for the `!!key$$` key inventory + `short_name`/`template_ref`/`COIL_COLUMN_BLOCKS` - the `.xlsm`
  scan is deferred, only the template scan is ported) · `builders.py` (the helpers `_node_of`/`_group_by_node`/
  `_chunked`/`PAD` + the 3 simple builders **00** Commissioning / **06** Feedback Error / **07** Speed Control,
  verbatim) · `engine.py` (the serialization verbatim + `build`/`project`). **`build()`** runs every registered
  builder -> the **`software_blocks`** (name/template/the `%` key inventory `["TemplateType"]+scan`/the Table
  column ORDER) + **`software_block_members`** (one row per @ row, the `values` JSON cell = the row, a list value =
  the ITERATOR) tables + `record` (`blk_builder_no_rows` WARN) + save. **`project()`** reconstructs each Table from
  `software_blocks.columns` + the members' `values` -> the `$/#/%/@` CreationInfo CSV (the `%` header = the
  template's full placeholder inventory). `config.BLOCK_TEMPLATES_DIR` + `config.blocks_creation_dir()`. **PARITY:
  the 3 CreationInfo CSVs are BYTE-IDENTICAL to PL3's builders+serializer** over the same 520-enriched rows, modulo
  the deliberate `pipeline3`->`pipeline4` `#` comment line. Tests: `test_blocks.py` (8: Table/Database list-cells,
  the serialization, the 3 builders, the build->project round-trip).
- **800b DONE - the complex builders.** Added to `builders.py` (verbatim from PL3 except the two PL4 adaptations):
  **02** EM Push Button (E1/2 + B1/2 by node, chunked to 4, the padded quartet emitted twice) · **03** Zone Cumulative
  (per AREA × signal group -> a 02_COM AND-coil; `ZONE_GROUPS`, `_area_descriptions`) · **04** ESTOP (per AREA; SORTER
  door-capacity tier 01-05 vs GENERIC 06; `ESTOP_SORTER_TIERS`, `_sorter_areas`, `_area_nn`) · **05** Output Feedback
  (per K-family `index` group; the 3-family capacity variant `OUTPUT_FEEDBACK_VARIANTS`/`_of_variant`) · **08** Gate
  Manager (one TT01 per sorter + one TT02 per door DQ). The two adaptations vs PL3: the multi-valued cells
  (`matrix_areas`/`areas_description`/`datablocks`) are read via **`_as_list`** (not `.split("|")`) - `matrix_areas`/
  `datablocks` drop empties (PL3 does too), but `_area_descriptions` reads `areas_description` KEEPING empties to
  preserve PL3's positional `descs[i]` indexing; and PL3's `_source_row` (05's unit sort key) is PL4's **`source_row`**.
  05's NetworkComment `|`-joins the `matrix_areas` list (PL3 rendered the joined string). **PARITY (over the same 269
  520-enriched staged rows):** the 7 CreationInfo CSVs PL3 also emits (00/02/04/05/06/07/08) are **byte-identical to
  PL3's builders+serializer** (modulo the `pipeline3`->`pipeline4` `#` line); all 5 new builders are **table-identical**
  to PL3's (03 verified at the table level - PL3 emits it as FC XML, 800c). Tests: `test_blocks.py` (+8: the 5 builders'
  grouping/variant/tier/list-cells/`source_row`-sort, `_area_descriptions`, `_of_variant`). 16 cases total.
- **800c DONE - the 03 FC XML + 02_COM safe-DB + InstanceDBs.csv + the GUI button.**
  - **`domain/blocks/xml_emit.py`** (verbatim port of PL3's): `and_coil_fc` emits **03_Zone Cumulative** as a ready
    `SW.Blocks.FC` XML - one `A`(AND)->`Coil` FlgNet network per @ row (the row's `nameOfDB.<member>` inputs ->
    the `02_COM.<element>` coil; UIds restart at 21 per network; >50 inputs split into leaf+combiner ANDs), the
    template head reused verbatim swapping `<Name>`. UTF-8 BOM + CRLF + indented. `EMITTERS = {"03_Zone Cumulative"}`.
    The PL4 `blocks.table.Table` has PL3's interface (rows are dicts, `ITERATOR_STRINGS` a list) so the emitter body
    is unchanged.
  - **`engine.project` wired** (`import_dir` param, default `blocks_import_dir()`): a block in `xml_emit.EMITTERS`
    ships its FC XML to ImportReady and its CreationInfo **CSV is DROPPED** (a stale one removed) - OP4 imports the
    XML, not a template-fill CSV. Returns `xml_files`; `count`/`files` are the CSVs only.
  - **`engine.write_com_db`** - the **02_COM** custom safe-DB (a fail-safe F_DB GlobalDB XML): members =
    `DB_CONSTANTS` (Always FALSE/TRUE/No Operation) + the distinct `02_COM.{db_element}` cumulatives across all
    builder rows (`_com_members`), deduped. **Reuses `datablock_xml.db_xml`** (so the bytes + the F_DB OPC-lock match
    the 520 DBs - no second XML emitter); written to `blocks_import_dir` (the 520 projector leaves it untouched -
    not a `db_blocks` DB). No cumulatives -> nothing written.
  - **`engine.write_instance_dbs`** - **InstanceDBs.csv** (the CreateInstanceDB surface): the builders'
    `instanceOf-<FB>` cells FIRST (`_builder_instance_rows`, in block x column x seq order from
    `software_block_members.values`), then the 520 config families (`_config_instance_rows` reads the
    **`instance_dbs` SSOT table** - PL4 does NOT re-run `datablocks.generate` like PL3's `_config_instance_rows`),
    deduped by Name (first-seen). Plain UTF-8 (NO BOM), csv.writer CRLF, `#`/`%`/`@` rows `Name/InstanceOf/Number/Folder`.
  - **GUI "800" button** (`gui/app_main._run_software`): stage -> 520 build -> `engine.build` -> `engine.project`
    (CSVs + 03 FC XML) -> `write_com_db` -> `write_instance_dbs`; accumulates staging+520 findings + `run.gate`
    ONCE (the `db_blocks not in database` downgrade guard), `run.render`s the WARN-only build/project findings.
  - **PARITY (over the same 269 520-enriched staged rows, vs PL3's real writers):** all three byte surfaces are
    **BYTE-IDENTICAL** - 03 FC XML (38018 B), 02_COM.xml (9578 B, F_DB OPC-locked, 15 members), InstanceDBs.csv
    (8569 B, 102 entries); the 03 CreationInfo CSV is dropped (so 7 CSVs remain, still byte-identical from 800b).
    Tests: `test_blocks.py` (+6: the FC-XML emit/BOM/network-per-row, the 03 CSV-drop, the 02_COM members+F_DB,
    the no-cumulatives no-write, the InstanceDBs merge+dedup+no-BOM). 22 cases total.

## Phase 900 — Reporting (Coverage) — DONE (910; 920 deferred)
`domain/coverage.py` - a clean-room port of PL3's `domain/coverage.py`, adapted to PL4's SSOT model. **910
Pipeline Coverage Report** traces each staged signal across the six downstream stages (interfaces/io_tags/
data_blocks/diagnosis/hardware/software) and flags two cross-check defects: **ORPHAN** (a staged SIGNAL whose
identity lands in NO output) and **UNPLACED** (an output emits a `"<db>"."<member>"` reference whose DB the
pipeline generates but whose member was never created). Row kinds `signal` | `channel` (untyped + an I/Q
address = a raw module point) | `structural` (untyped, no address); only a `signal` can be ORPHAN.
- **READ SOURCE (user decision): the SSOT TABLES, not the on-disk artifacts.** PL3 re-reads the produced
  BuilderData files (its phases admit user edits); PL4 deferred the editable shells and every export is a
  byte-stable PROJECTION of an SSOT table, so coverage over the tables == coverage over the artifacts by
  construction - hermetic, no openpyxl/glob/XML re-parse, and UNPLACED is exact (`db_members` is the truth).
  `collect_outputs(database)` reads: `tags` = io-signal `name_in_tagtable` (`identity.is_io_signal`) +
  `interface_elements.signal_name` (== what 510 emits); `db_members` = the `db_members` table grouped by
  `db_name` PLUS the 800-owned **02_COM** members (assembled from `software_block_members` 02_COM.{db_element}
  cumulatives + `DB_CONSTANTS`); `diag_bindings` = `diagnosis_entries.in_binding` + the DiagList PLC_Binding
  cell; `iface_exprs` = `interface_elements.expression`, `iface_instances` = `interfaces.instance`; `stations`
  = `hardware_stations`/`hardware_modules` `station_name`; `sw_refs` = the `software_block_members.values`
  @-cells (block id = name before `_`, ITERATOR cells spread, pads dropped - the 03 FC-XML refs come free since
  its rows are in the table). The ONE fact not in a table is a hand-filled interface **Side-2** row (lives only
  in the inserted IF_ sheet) - a documented gap.
- **The per-signal trace is PERSISTED as a `coverage` SSOT table** (the PL4 thesis: every created datum is
  written; the CSV is its projection). `binding` is the STORED `plc_binding` column (not re-derived); the
  `type` object cell replaces PL3's `_type`. **ORPHAN/UNPLACED are emitted as WARN Findings**
  (`cov_orphan_signal`/`cov_unplaced_member`) into `validation_issues` and `run.render`ed (informational - never
  halts), matching the severity model. `build()` -> the `coverage` table + findings + save; `project()` ->
  `ProjectDocumentation/Reports/io_project_coverage_report.{csv,txt}` (`config.coverage_dir()` + the verbatim
  PL3 `render_csv`/`render_txt`). The GUI **"900" button** (`_run_reporting`) builds the full SSOT
  (stage -> 520 -> 700 halt-capable; then the WARN-only 400/600/800) then coverage.build + project.
- **VERIFICATION (real data - the report is documentation, byte-parity is NOT the bar; the bar is the same
  findings):** over the 269 staged rows - 115 signals / 148 channels / 6 structural; per-stage coverage
  hardware 261 / io_tags 98 / diagnosis 75 / interfaces 77 / data_blocks 37 / software 61; **ORPHAN = 0 and
  UNPLACED = 0** (every signal lands somewhere, every emitted DB-member reference resolves), and coverage's
  table-derived `tags` set is **identical to what `io_tags` emits** (202 == 202, the one drift risk). Tests:
  `test_coverage.py` (9, hermetic: classification, the pure attribute placement + ORPHAN-only-for-signals, the
  interface defines/mirror + hardware station/module attribution, find_unplaced, collect_outputs over a
  synthetic Database, render + build->project). **920 (TIA Project Coverage) stays deferred** (pending an OP4
  project export), matching PL3.

## Phase 100 — Documents Validation — DONE (110/120/130/140; 150 + accept out of scope)
`domain/validation/` - a clean-room port of PL3's `domain/validation/`, the LAST phase (PL3's first). Validates
the hand-authored I/O List + Cause&Effect workbooks via 5 sub-phases: 110 standalone I/O List, 120 standalone
C&E, 130 cross-check CEM->IOL, 140 cross-check IOL->CEM, 150 diagnosis-slot uniqueness. **User decisions:**
reproduce **PL3's rich txt+HTML reports** (the aligned line + the cross-check Cmp + dual-workbook links); land
**110+120+130+140 now, DEFER 150** (it needs relocating `diag_container_check` + populating `diag_block_name`
at staging, touching the locked 300 parity); **DROP the `accept` doc-mutating treatment** entirely. 110/120 read
the RAW workbooks (facts staging normalizes away); 130/140 read the SSOT. Findings flow through the existing
Finding/treatment/severity spine; the phase **never halts** (`run.render`, not `gate`). The English `v_*` message
text is ported verbatim into each finding's `detail`.
- **100a DONE - the reporting spine.** `core/model.py` (the `InfoBlock` + `Cmp` render value-objects - the part
  of PL3's `LogEntry` the rich report still needs). **`core/finding.py` extended** with 4 OPTIONAL render fields
  (`location2`/`doc2`/`info`/`cmp`, default `""`/None) - non-validation phases leave them unset, so the universal
  Finding stays lean + hashable + the uid unchanged (they are NOT hashed, NOT persisted to `validation_issues`).
  `domain/validation/address.py` (verbatim - the dotted I/Q/O 2-or-4-part format check). **`io/render.py`** - the
  report renderer over Findings (verbatim port of PL3's `io/render.py`): a banner per `severity==PHASE` finding,
  the `[LEVEL] <phase>-<type>  <loc>  | bit|FLD|desc|drawing|type-idx  :: <detail>` line with per-(sub)phase
  width auto-fit, the cross-check `<loc1> vs <loc2>` dual-link + the aligned `<addr> op <addr> | <fld> op <fld>`
  Cmp, the errors-only filter (banners + INFO/WARN/ERROR/FAIL, drops PASS/SKIP/DEBUG), and the standalone
  no-wrap HTML (the GUI-log-viewer look). `config.validation_report_dir()` (ProjectDocumentation/Reports) +
  `VALIDATION_REPORT_STEM`/`VALIDATION_ERRORS_STEM`. Tests: `test_validation_render.py` (6: address + the
  renderer's banner/line/InfoBlock/Cmp+dual-link/errors-filter/HTML). NOTE on parity: PL4's `finding._norm`
  collapses whitespace but does NOT lowercase (PL3's does), so the phase-100 parity oracle compares finding
  TUPLES `(phase, type, norm(location), norm(detail))` with a matching normalization, not raw uids.
- **100b DONE - the two standalone validators** (read the RAW workbooks via `io/workbook`). `messages.py` (the EN
  `v_*` templates ported VERBATIM from PL3's i18n + `msg(slug, **fmt)`) · `model.py` (the `entry()` Finding factory
  resolving the detail through `messages.msg`, + `key`/`addr`/`raw`/`fld_text`/`info_for_row` + the fuzzy
  `levenshtein`/`first_match`/`matches_words` + `cmp_detail` for 130/140) · **`iolist.py` (110)** (verbatim port:
  header glossary over the non-`preliminary_check_exclude` columns, IP-error/dup-IP/dup-FLD, G⊕F, address format,
  permanent-part + TS-ref for A/W(/PA/PW), Profinet identity, node-count thresholds, a `row_ok` PASS per clean row;
  takes the resolved `params`, reads via `get_param`) · **`matrix.py` (120)** (the CAUSE&EFFECT MATRIX inputs-only /
  AREA outputs-only / no-dup-within-sheet checks; C&E absent -> one `ce_absent` SKIP). Tests:
  `test_validation_standalone.py` (9, hermetic via a `StubView` + monkeypatched openers). **Real-data sanity (the
  clean "Passing" fixtures):** 110 = 273 `row_ok` PASS / 8 INFO / 0 FAIL; 120 = 24 address refs checked / 0 FAIL
  (no false positives) - the unit tests prove the checks FIRE on bad input.
- **100c DONE - the two cross-checks** (read the SSOT `signals` + the C&E refs). `ce_refs.py` (port of PL3's
  `indexes.py`: `build_io_index`/`build_io_addr_index` over the signals rows + `read_ce_refs` over the C&E
  workbook via `matrix_params` + `build_ce_index`) · **`crosscheck.py`**: **130 (CEM->IOL)** runs each C&E ref
  through TWO independent searches (by I/O ADDRESS + by FLD) -> `cem_addr_ok`/`cem_addr_fld`/`cem_addr_none` +
  `cem_fld_ok`/`cem_fld_addr`/`cem_fld_none` (each FAIL carries the aligned `Cmp` + the matched I/O cell as the
  dual-link); **140 (IOL->CEM)** the decision tree (typed & `ce_mandatory` yes/warn -> CHECK [yes=FAIL/warn=WARN];
  typed no/unset -> `iol_cem_not_required` SKIP; untyped: a `bypass_words` hit -> SKIP, a safety/`full_check` match
  -> CHECK, else `iol_cem_unclassified`/`iol_cem_skipped` SKIP) -> `iol_cem_match`/`_missing_*`/`_fld_only`/
  `_addr_only` with the Cmp + dual-link. Reads the `type` object cell (PL3's `_type`) + the nested
  `validation_params.crosscheck.{global.full_check, iol_in_matrix.{mandatory_words,excluded_words,bypass_words,
  levenshtein_deviation}}`. Tests: `test_validation_crosscheck.py` (6, hermetic via synthetic refs + a synthetic
  `signals` DB). **Real-data sanity (clean Passing fixtures):** 130 = 48 PASS / 0 FAIL (every C&E ref matched);
  140 = 20 PASS + 239 SKIP + 4 `iol_cem_missing_plain` WARN / 0 FAIL (no false positives).
- **100d DONE - the orchestrator + GUI + reports + parity.** `domain/validation/phase.py` `run_validation`
  (database, params): runs 110->120->130->140, **records only the treatable (FAIL/ERROR/WARN) findings** into
  `validation_issues` (PASS/INFO/SKIP are report-only noise) + saves, applies the treatment registry READ-ONLY
  for the report's EFFECTIVE severity, interleaves a per-(sub)phase banner, and writes the **4 report files**
  (`documents_validation_report`/`_errors` x `.txt`/`.html`) to `config.validation_report_dir()`. NEVER halts.
  The GUI **"100" button** (`_run_validation`: stage -> run_validation -> `run.render` the ISSUES to the GUI log
  [reconcile + write the registry; never halts] -> a summary). Tests: `test_validation_phase.py` (1, hermetic:
  the banner interleaving + the 4 files + treatable-only recording). **PARITY (the real bar - the report is
  documentation, NOT byte-parity): the PL4 finding set == PL3's, EXACTLY.** Over the same real documents (the
  Passing fixtures), PL4 produced **596 findings and PL3 produced 596, with 0 differences** in the tuple
  `(phase, type, norm(location), norm(detail))` across all 4 validators (`scratchpad/parity_100.py`; PL3 is fed
  PL4's staged rows so both validate the same data). Real-data counts: 341 PASS / 239 SKIP / 12 INFO / 4 WARN /
  0 FAIL (a clean project).
- **OUT OF SCOPE (user decisions):** **150** (diagnosis-slot uniqueness - needs relocating `diag_container_check`
  + populating `diag_block_name` at staging, which would touch the locked 300 parity) + the **`accept`**
  doc-mutating treatment (dropped).

## GUI — runnable shell (`gui/` + `launch_gui.py`)
`python launch_gui.py` opens a sv-ttk dark window (graceful fallback) with a toolbar, the **phase-button
bar** (Run + the 9 phases, ButtonsLayout colours), a colour-coded **log viewer**, and a status bar. Wired in
EARLY (gui-less PL3 builds hid integration problems). **ALL phase buttons run their phases for real**
(100/300/400/500/600/700/800/900, each through `staging.stage` -> the phase build/project; 800 = stage -> 520 ->
`engine.build` -> `engine.project` + `write_com_db` + `write_instance_dbs`; 900 = build the full SSOT ->
`coverage.build` + `project`; 100 = stage -> `validation.run_validation` -> `run.render` the issues). The handler is
wrapped so a not-yet-ready phase can't take the window down. Each real handler **accumulates the findings of its
gated sub-phases (staging + 520) and calls `run.gate(findings, self.log.append, label=…)` ONCE** - render at
effective severity + halt iff any effective FAIL; `run.has_blocking(f)` skips a dependent sub-phase when a prereq
already blocks. **Guard:** the skip decision is RAW-severity but the gate's continue is EFFECTIVE (a treatment can
DOWNGRADE a prereq FAIL→WARN, so the gate continues while 520 was skipped) - each handler checks `"db_blocks" not
in database` after the gate and returns gracefully (no KeyError on the never-built 520 table). The WARN-only
PROJECTION phases (400/510) call **`run.render`** (gate minus the halt) instead - their BuilderData is already
written, so an escalated WARN is shown but no misleading `nothing written` halt line is printed. (Phase
registry-driven bar, the structured-record clickable log, the Files tab, threading → later.)
- **Severity taxonomy + the GUI log-level filter.** `core/severity.py` is the single source of the level set:
  **FAIL** (halts), **ERROR** (skip the item, continue), **WARN**, **INFO**, **SKIP**, **PASS**, **DEBUG**
  (dev-only, hidden by default) + the **PHASE** banner. Each level has a distinct first char (F E W I S P D), so
  config lists can use single chars or full names interchangeably (`severity.resolve`/`resolve_set`). **`config_project/app_config.yaml`**
  (NEW — a tracked, COSMETIC GUI launch config, NOT per-project run params) carries `user_interface.log_levels`
  (default `[F, E, W, I, S, P, D]` — all 7 levels shown); `config.load_app_ui()` reads it → the shown-level set;
  `LogView(shown_levels=…)` filters `append` (PHASE always shown). This is the first piece of the severity model.
  **S1 (the findings/treatment core) is DONE too:**
  - **`core/finding.py`** - a frozen `Finding(phase, type, severity, detail, location, source_uid, doc)`;
    `uid = keys.uid(phase, type, norm(location), norm(detail))` EXCLUDING severity (so a treatment can change the
    level without breaking the match). `validation_issues_table()` (the SSOT record of the FACTS, one row per
    finding at its default severity - treatments live separately) + `record(database, findings)` (passes each
    Finding's own uid so the row uid == the registry key).
  - **`core/treatments.py`** - the `error_management.csv` registry (`config.user_input_dir()`), generalizing PL3's:
    a per-uid treatment NAMES the target level (`fail`/`error`/`warn`/`skip`/`ignore`) so it can DOWNGRADE *or*
    ESCALATE to a halting FAIL. `load`/`apply`/`effective_severity`/`should_halt`/`reconcile` (refresh current,
    prune untreated-gone, mark treated-gone `stale`)/`write`/`set_treatment`. (`accept` deferred to ph100.)
  - **`core/run.py:gate(findings, log_append, label)`** - the halt seam (no engine yet): apply the registry, render
    each finding at its EFFECTIVE level, return CONTINUE; halt iff any effective level in `severity.HALTING`.
    `has_blocking` is the build-side raw-FAIL guard (never write BuilderData on a raw FAIL). **`run.render`** (S4)
    is `gate` minus the halt (shared `_render`) for WARN-only projection phases whose output is already written.
  Tests: `test_severity.py` (5) + `test_finding.py` (4) + `test_treatments.py` (5) + `test_run.py` (5).
  **Decision (user): persist `validation_issues` now + full model + retrofit 300/520/400/510/600, THEN 700.** S1
  touched NO phase (parity trivially preserved). **S2 (520) + S3 (300) + S4 (400+510) + S5 (600) are DONE** (see the
  phase sections: `generate`/`stage`/`build`/`build_interfaces`/`diagnosis.build -> (..., findings)` + the
  `validation_issues` record + the `run.has_blocking` no-write guard; GlobalDB XMLs + `signals.csv` +
  `interface_elements` + PLCTags + `diagnosis_entries`/DiagList/SCL byte/content-identical to pre-retrofit). The 4
  GUI handlers **accumulate staging + 520 findings and call `run.gate` ONCE** per click (halt-capable), then
  **`run.render`** the WARN-only 400/510/600 projection findings (`render` = gate minus the halt, for phases whose
  BuilderData is already written). **S6 (the final sweep) is DONE - the SEVERITY ROLLOUT IS COMPLETE**: zero legacy
  `(errors, warnings)` tuples / `warnings`-key reads remain in `pipeline4/` (the cleanup landed incrementally across
  S2-S5); the **full 5-phase byte-parity re-run** vs the pre-rollout baseline (`95d3dfb`) is **0 differences across
  all 20 BuilderData + SSOT outputs** (9 GlobalDB XMLs + PLCTags + DiagList_IO/Logic + the OPC SCL + the 8 tables),
  with only the new `validation_issues.csv` added. Every phase now reports through the Finding/treatment model; the
  codebase is ready for **phase 700 (Hardware)**.
  - **TRANSITIONAL NOTE (gate reconcile scope).** `run.gate` calls `treatments.reconcile`, which prunes/stales
    registry rows GLOBALLY (any uid not in the gated finding set). With multiple gated phases this can churn an
    OTHER phase's untreated registry rows across separate button clicks (e.g. clicking 300 vs 500). It is
    **invisible today** (clean data -> 0 findings -> empty registry) and treatments still APPLY regardless of the
    cosmetic `stale` flag (`apply` ignores status). The proper fix - reconcile once per RUN over the union of all
    findings - lands with the engine (post-S6); until then the per-handler single-gate keeps WITHIN-click churn out.

## Testing
Plain-`python` tests under `tests/unit/` via `_harness.py` (PASS/FAIL, non-zero exit). The
**data-independent suite is the green gate** (currently **222**: keys/table/database, signals schema,
sheets/workbook, params/config_loaders, staging identity+read (+ the S3 `stg_dup_signal_uid` finding + the
no-match `load_io_list` branch), dbtemplate/datablocks (+ all 13 S2 finding slugs), interfaces (+ the S4
`if_ioc_no_index`/`if_signal_not_mirrored` slugs) + interface_xlsx (incl. the 400e insertion/seed/freeze),
the **`io/xlsx_edit` suite** (14, ported verbatim), the **510 `io_tags` suite** (8, + the S4 `iotag_no_address`
slug), the **600 `diagnosis` suite** (18, + the S5 `diag_scl_template_missing` slug), the **severity/findings core**
(`test_severity`/`test_finding`/`test_treatments`/`test_run` = 20, incl. S4's `run.render`), the **700 `hardware`
suite** (10: the helpers, the extract incl. auto-plug/PotentialGroup/by-type/default-cards, the missing-DTD
FAIL/switch-WARN, the table fill + int->str of slot/addr, the format-2 projection), the **800a+b+c `blocks` suite**
(22: Table/Database list-cells, the $/#/%/@ serialization, the 00/06/07 simple builders, the 02/03/04/05/08 complex
builders + `_area_descriptions`/`_of_variant`, the build->project round-trip, the 800c FC-XML emit + 03 CSV-drop +
02_COM safe-DB + InstanceDBs merge/dedup), and the **900 `coverage` suite** (9, hermetic: the signal/channel/
structural classification, the pure attribute placement + ORPHAN-only-for-signals, the interface defines/mirror +
hardware station/module attribution, find_unplaced, collect_outputs over a synthetic Database, render + build->project),
and the **100 validation suites** (`test_validation_render` 6: address + the rich renderer banner/line/InfoBlock/
Cmp+dual-link/errors-filter/HTML; `test_validation_standalone` 9: 110+120 via a StubView + monkeypatched openers;
`test_validation_crosscheck` 6: the io/ce indexes + the 130 two-search + the 140 decision tree; `test_validation_phase`
1: the orchestrator's banner interleaving + the 4 reports + treatable-only recording)).
Data-dependent parity (staging/520/400/510/600/700/800 vs PL3, the byte-parity of `signals.csv`/GlobalDB XMLs/
`interface_elements`/PLCTags/`diagnosis_entries`/DiagList/SCL + `Stations.csv`/`Modules.csv` + the CreationInfo CSVs
vs PL3 `_format2`/`write_creation_csv`) is verified by a script (not in the gate). Each phase is committed with its gate + parity green.

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
