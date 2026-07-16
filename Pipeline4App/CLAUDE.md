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
- **STEP 2 - the 310/320 split DONE** (parity-locked): `stage()` is now `stage_iolist()` (oracle **310 Stage
  I/O List**) then `annotate_cematrix()` (oracle **320 Stage C&E Matrix**), composed in memory. `stage_iolist`
  reads the I/O List into the `signals` table WITHOUT the C&E (no `matrix.annotate` -> `ce_*`/`matrix_areas`
  absent -> `combined_FLD` == `iol_FLD`, `IsSorterArea` '') + the `diagnosis_cabinets` table; `annotate_cematrix`
  runs `matrix.annotate` on the staged rows, recomputes the C&E-dependent identity, **re-stamps each uid** from
  the now-C&E `combined_FLD` (the uid key), records the `stg_dup_signal_uid` findings, saves. Shared helpers
  `_read_iolist` (read-only) + `_finalize_identity` (IDEMPOTENT: the no-C&E pass and the post-`annotate` pass
  converge -> the split is byte-exact); `load_io_list` retained as their composition for the no-match guard +
  the tests. The GUI 300 dropdown wires **310 -> `stage_iolist`** (partial, no C&E) and **320 / the 300 header
  -> `stage`** (full); `phases.py` un-greys 320. PL4 reinterprets the oracle's 320 (PL3 = "Generate IO Database",
  moot under PL4's auto-save) as the C&E-staging leg. **PARITY: `stage()` byte-identical to the pre-split monolith**
  - `signals.csv` (130802 B) + `diagnosis_cabinets.csv` + `validation_issues.csv` 0 diffs (verified new-vs-stash).
  Tests: `test_staging.py` (+`finalize_identity_ce_overwrite` [the idempotent/overwrite contract] +
  `annotate_cematrix_records_and_restamps`); GUI verified on screen (310 then 320 over real data, 269 signals).

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
- **`datablocks.generate`** (520b) — port of PL3's validate-and-halt generator: seeds (`AlwaysFALSE/AlwaysTRUE`/ [renamed from `Always FALSE/TRUE` 2026-07-07, user spec - the yaml `seed_members` + every builder literal]/
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
- **400g — the MachineInterfaces SCL projection** (`domain/interface_scl.py`): the `interface_elements`
  table as ONE SCL FUNCTION in ImportReady - a REGION per interface, one assignment per element, the line
  per direction from `generation_params.yaml` `interfaces.scl_line_templates` (expr-rendered; `_q` =
  TIA-quoted), BOM + CRLF. **Renamed to `10_Machine Interfaces.scl` (user spec 2026-07-07)** - the file
  comes from `interfaces.scl_file` and the FUNCTION is named after its stem (the config drives both); the
  legacy `MachineInterfaces.scl` is swept from the output dir so it can't double-import. **A blank line
  opens each new I/O BYTE** within a region (`io_address_side1` up to `.bit` - reads grouped like the IF_
  sheet; skips don't break a group). WARN-only skips (`if_scl_blank_element` /
  `if_scl_no_direction_template`). Tests: `test_interface_scl.py` (6).
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

## Phase 510 — I/O Tags — DONE (interface-completeness RESOLVED, fresh-PL3 oracle 213/213; + severity S4)
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
(The 2026-07-07 `tagtable_elements.csv` third tag source was REVERTED 2026-07-09 — wrong direction; the
replacement is GENERATED SIGNALS appended to the `signals` table itself, marked via `source_sheet`/
`source_cell`/`source_row`, so 510 absorbs them through source (a) with no config of its own.
**`regex_replace(v, /re/, repl)` STAYS in core/expr** — re.sub semantics, `\\1` backrefs, implicit
IGNORECASE, no match -> unchanged; a bad backref = located ExprError; `test_expr.py::regex_replace`.)
Two sheets: **"PLC Tags"** (10 cols: Name/Path/Data Type/Logical Address/Comment/3×Hmi `True`/Typeobject ID/Version
ID) + **"TagTable Properties"** (3 cols: Path/BelongsToUnit/Accessibility, one row per distinct Path). Output via
`write_plc_tags` (a fresh openpyxl workbook; `_append_text_row` forces a leading `=`/`+`/`-` to text). `project`
returns `{path, total, io_count, iface_count, tables, warnings}`. The GUI **"500" button** now runs stage → 520 build
→ project XML → **build_interfaces → io_tags.project**. Clean-room port of PL3's `generate_io_tags`/`build_io_tags`/
`interface_tags`/`write_plc_tags` (the read-the-IF_-sheets path replaced by the SSOT read). Tests: `test_io_tags.py`
(8 cases, hermetic — the two sources, the dtype map + %-address, the text-forcing, the two-sheet structure, the
sort+distinct-props, the skip+warn, the return contract).
- **Parity — RESOLVED (fresh-PL3 oracle, exact).** The two formerly-KNOWN interface-completeness gaps are
  CLOSED: the **template-native** signals via 400f (`source="template"` rows in `interface_elements`) and the
  **+DIAG auto-mirror** via 600a (staging `in_diag` lit up `collect_mirror_set`). Verified by a **fresh-PL3
  oracle PLCTags diff** (`scratchpad/oracle_510.py`): on a scratch copy, PL4 stages → builds → projects +
  RE-INSERTS fresh IF_ sheets, then PL3's `generate_io_tags` reads those fresh sheets — **both produce 213
  tags (98 I/O + 115 interface), 211 unique (Path,Name) keys, 0 PL4-only / 0 PL3-only / 0 field-mismatches**.
  (The old "213 vs 208" delta was PL3 reading the doc's STALE inserted IF_ sheets; with fresh sheets PL3 also
  hits 213.) The direct-I/O side is 98/98; the interface side: IF_SORTER-01 25, IF_SORTER+DIAG-02 90.
- **The duplicate-tag gate (production fix, 2026-07-06).** Two tags on the same **(tag table, name)**
  [case-insensitive — TIA's uniqueness rule; the import breaks] emit one **`iotag_duplicate` FAIL per 2nd+
  occurrence**: `location` = the duplicate's I/O-List row, `location2` = the FIRST occurrence's (the log
  renders `<dup> vs <first>`, both clickable — the tag dicts now carry `location`/`source_uid`, a mirror
  element resolving its `source_signal`'s `source_cell`), detail `… - Count: <n>` (the tag's TOTAL
  occurrence count; the first-occurrence pointer lives in the `location2` link, not the text — user
  feedback after the production test). On any raw FAIL
  `project` **records the FAILs alone** (`finding.record_standalone` — the [FAIL]→Findings jump) and does
  **NOT write the workbook** (`path` = ''); the GUI 510 leg `_gate`s that path (halt; a registry downgrade
  still never writes — the raw-FAIL guard, same as 520/700). The same name on TWO tables stays legal (one
  signal mirrors into several IF_ tables by design — 9 such names in the builtin fixture, 0 flagged).
  Root cause (FVX_PL4_Pilot): I/O-List rows duplicated verbatim (NET SAFETY 50 O113-118 == O121-126, same
  FLD, different bits) → 6 same-table pairs; staging is silent by design (the signal uid includes
  `source_cell`), so the PLCTags surface is where the collision exists. The builtin fixture's own 2
  `Fire Alarm` pairs now FAIL the dev 500 run too — a real defect in the dev I/O List, previously shipped
  silently (the old "213 tags / 211 unique keys" note). Tests: `test_io_tags.py` (11 — +3: the same-table
  FAIL with both links + no-write + record, the cross-table by-design pass, the mirror source-row link).

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
  template-native gap is also closed by 400f - 510 parity is RESOLVED, see §510). **Parity**: `diag_desc`
  **0 mismatches/269** vs PL3 IODatabase; the
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
- **Interface-completeness follow-up — DONE/VERIFIED**: the +DIAG unblock (600a) + the template-native capture
  (400f) closed both 510 PLCTags gaps; a fresh-PL3 oracle confirms exact parity (213/213, 0 diffs — see the
  Phase 510 "Parity — RESOLVED" note).

## Phase 700 — Hardware — DONE (700a build + 700b CSV projection)
`domain/hardware.py` + `domain/hardware_csv.py` - a clean-room port of PL3's `hardware.extract` + format-2 writer
into PL4's SSOT model. A single ordered pass over the `signals` table populates **`hardware_stations`** (one row per
generatable head - a PLC/PlcCardCm/IoDevice) + **`hardware_modules`** (the IoDevice cards); the
`HardwareConfiguration/Stations.csv` + `Modules.csv` BuilderData surface is a pure projection of these tables. The
GUI **"700" button** runs stage -> build -> project.
- **700a DONE - `build()` + the tables + config.** A head opens a station (`script_type` PLC->Plc, PlcCardCm->
  PlcCardCm, or Type col-R first letter P->IoDevice); the rows beneath it (until the next head) are its signals.
  Stations: name=`profinet_name`, Model Id=Part No (spaces stripped), Subnet from the IP, group=
  `<functional_unit>_IODevices` (**EMPTY for the Plc head** - the PLC stays at the TIA root; OP honors
  Group for every row - user decision 2026-07-07), Custom Parameters = the DTD col-7 `%I%`/`%Q%`+N address
  template then col-AG
  (override), + **`connector`** = the head row's I/O-List col-I cell VERBATIM (added 2026-07-06, user spec;
  e.g. the pilot's `X1-P1 R` port designations - the OP side extracts the `X\d\d?` designation). Modules (IoDevice only): cards grouped by Slot (a Slot == the device's own tag is the TIA-auto-plugged
  card, skipped); I/Q Addr = the card start byte; Custom Parameters = `PotentialGroup=1` on the first card + the DTD
  col-6 by-signal-type `Ch(#)`->channel blocks then col-AG; default cards (DTD `<PARENT>:SUFFIX`) add one row per
  station of PARENT. **Severity model:** a head whose Part No isn't in the DeviceTypesDatabase -> **`hw_device_not_in_dtd`
  FAIL** (halts + no write; operator-downgradable) / **`hw_switch_not_in_dtd` WARN** (a switch, "SWITCH" in the
  description). `build` returns `(database, findings)` + `run.has_blocking` guard + `record` + save.
  **Duplicate-IP skip (production fix, 2026-07-06):** a head whose IP a GENERATED station already uses is
  SKIPPED (only the first station per IP is generated; its signal rows drop with it - no cards) ->
  **`hw_duplicate_ip` WARN**, downgraded to **INFO** when the head's `description_module` mentions
  "backup" (the documented redundant-CPU pair, e.g. FVX_PL4_Pilot's Master+Backup 1518F on 192.168.50.1 -
  which doc-validation 110 deliberately exempts: `ip_duplicated` skips `.1`-suffixed IPs). The finding
  dual-links the skipped head's row (`location`) vs the generated station's (`location2`); the detail is
  IDENTICAL for both severities so the uid (which excludes severity) survives a backup-description edit.
  Never halts. Test: `test_hardware.py::duplicate_ip_stations_skipped`. **Config:**
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
  **CONTRACT EVOLUTION (2026-07-06): `Stations.csv` gains the 9th `Connector` column** (the station's
  `connector`, appended LAST so an un-updated positional reader is unaffected; the fmt2 tag/header lines grew
  a comma) - deliberate byte-parity break vs PL3 on Stations only (Modules stays byte-identical); logged in
  `Shared/PL4_OP4_coordination.md`'s update log with the OP4 to-do.

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
  verbatim - except **06's iterator now emits the padded 8-slot bank TWICE** (16 cells, the second an exact
  copy: one bank per template side - user spec 2026-07-07, a deliberate PL3 deviation) ·
  `engine.py` (the serialization verbatim + `build`/`project`).
  **NEW builder + emit kind (user spec, 2026-07-07): `03_Diagnostic Nodes`, `emit="scl"`.** The third
  output surface: a builder registered `@builds(name, emit="scl")` ships a READY SCL FUNCTION source to
  ImportReady (`domain/blocks/scl_emit.py`, UTF-8 BOM + CRLF like the 620 SCL; the stale CreationInfo CSV
  drops, no template ships; `project` returns it in `scl_files`). The builder mirrors the PROFINET_NODES
  member domains (the 520 config `row where $script_type = 'PA'|'PW'`): one assignment per node -
  `"PROFINET_NODES_ALARM|_WARNING"."<profinet_name> <ip>" := "10_PN_NETWORK".SUBNET_<s>[<last octet>];` -
  grouped one `REGION Subnet <s> <prefix>.xxx` per subnet (sorted; staged order within). `10_PN_NETWORK`
  is the hand-maintained per-subnet network-status DB on the TIA side. Tests: `test_blocks.py`
  (+3: the builder's PA/PW/malformed rows, the region/line rendering, the project routing + CSV drop).
  **08 door-network interlock (template evolution, user decisions 2026-07-07):** the 08 template's TT02
  (door) network now consumes the sorter interlock itself, so each door row fills
  `tagName:SorterRunningIOC` + the `05_EM_STATE` `SORTER_nn_NOT_RUNNING` member (nn via `sorter_nn`: the
  N1/2 encoder whose areas intersect the door DI's, FALLBACK the DI's sorter-AREA number - the real
  encoders carry no areas; '' for a non-sorter door, ruled out in practice) and **`tagName:DoorReset` =
  the DR tag** (the one reset button feeds both the open-request and reset FB pins). ALSO fixed: the
  synthesized running tag is **`PNC_I_SORTER-nn SORTER- RUNNING`** (the MachineInterfaces native
  spelling, verified to exist in the pilot's interface tags) - the old `SORTER RUNNING` named a
  non-existent tag. Empty TT02 Component slots broke the TIA import (the OP error that triggered this). **`build()`** runs every registered
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
  (per AREA × signal group -> a 02_COM AND-coil; `ZONE_GROUPS`, `_area_descriptions`) · **04** ESTOP (per AREA; template
  **v1.1** feature-driven TT + NO iterator - see the v1.1 note below; `_sorter_areas`, `_area_nn`) · **05** Output Feedback
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
- **04_ESTOP template v1.1 (user spec, 2026-07-16) - a deliberate divergence from PL3.** The reviewed template
  (`Shared/Templates/Tia Portal Software Blocks/TEMPLATE--v1.1--04_ESTOP.xml`; v1.0 xml+csv retired) drops the door
  ITERATOR and the raw-breaker / `_COM`-intermediate wiring: the door/breaker AND-ing now lives in **02_COM** (block
  03's `DOORS`/`SAFETY_BREAKERS` cumulatives), and the ESTOP block just references those coils. `build_04_estop` picks
  the TemplateType by the area's **safety features** (feature PRESENCE, not door count): sorter -> **TT06** (E-STOP +
  doors + breakers + encoder), doors+breakers -> **TT05**, breakers-only -> **TT04**, doors-only -> **TT03**, bare ->
  **TT02** (Emergency STOP / reset-required); **TT01** ('Safety STOP' / reset-NOT-required, ACK_NEC=FALSE) is reserved
  for the future. The FB's `TIME_DEL` is baked per-network IN THE TEMPLATE: **TT06 keeps T#10s, TT01-05 use T#150ms**
  (the delay is a pure function of sorter-ness == TT06). **Datablock impact (`datablock_elements.csv`):** 05_EM_STATE's
  `_SAFETY_BREAKERS_COM`/`_SAFETY_DOORS_COM` members are **removed** (they are the 02_COM cumulatives now), and the
  old sorter-only config-literal `AREA 1 POWER_CUT` becomes a **per-area `{$area} POWER_CUT`** member.
  `ESTOP_SORTER_TIERS`/`ESTOP_GENERIC_RESET` retired. **Verified real-data** (4 dev areas -> TT06/TT05/TT02x2; every
  DOORS/SAFETY_BREAKERS ref resolves in 02_COM; 05_EM_STATE.xml has 4 per-area POWER_CUT + 0 `_COM` members). Test:
  `test_blocks.py::builder_04_estop_feature_types`.
- **05_Output Feedback fix + a DYNAMIC FDBACK FC XML alternative (user spec, 2026-07-16).** (1) FIX: the shipped
  `TEMPLATE--v1.1--05_Output Feedback.csv` sidecar mislabeled the template's 2-area networks TT9-12 as
  `OnCondition=1` (a copy of TT3-6), so a 2-area unit with 2 contactors / 4 feedbacks matched no
  `OUTPUT_FEEDBACK_VARIANTS` entry -> an **empty TemplateType**. Corrected the builder table + the sidecar to the
  real `(2,4,1)/(2,1,2)/(2,2,2)/(2,4,2)` (verified vs the XML network shapes) - the FVZ 2-area/2-contactor units
  now pick TT11. (2) NEW SURFACE: besides the corrected 12-variant template CSV (default), 05 can emit a **ready
  `SW.Blocks.FC` XML built to each unit's EXACT element counts** - no fixed-capacity ceiling (a unit with >2 areas
  / >4 feedbacks / >2 contactors is expressible; the overflow-empty-TT can't happen). A **code flag
  `builders.FDBACK_XML`** (user decision - a code setting) picks the surface: `False` -> CSV, `True` -> XML
  (`@builds("05_Output Feedback", emit="fdback_xml" if FDBACK_XML else "csv")`; `xml_emit.EMIT_FUNCS["fdback_xml"]
  = fdback_fc`). The builder Table is IDENTICAL either way - `xml_emit._fdback_row` reconstructs each unit's
  element lists from the same flat @ cells (dropping the AND-neutral `No Operation` pad, so a fitting unit yields
  its exact-size network, not a padded one). `_fdback_flgnet_lines` is a **parametric reproduction of the
  template's own 12 networks** (1 F_FDBACK FB per unit; ON=AND(areas), FEEDBACK=AND(feedbacks), ACK=OR(resets),
  QBAD_FIO=[C=1 direct + FB-pin-Negated | C>1 AND of NEGATED qbads], Q->outputs=[C=1 direct | C>1 FB.Q-open +
  a instanceOf-F_FDBACK.Q read-back driving a chain of C coils]; ACK_NEC=true, FDB_TIME=T#300ms,
  ERROR->03_FDBACK_RAW, en/ACK_REQ/DIAG open). **PROVEN: every one of the 12 (A,F,C) template networks is
  reproduced byte-exact (whitespace-normalized)**; real-data (FVZ, flag on) 05 ships a well-formed FC XML (5 units,
  the 2-area/2-contactor units get the OR gate + 2-coil chain), CSV dropped. Tests: `test_blocks.py`
  (`of_variant_picks_smallest_cover` +TT11/TT12, `fdback_reproduces_12_template_networks`,
  `fdback_row_reconstructs_and_drops_pad`, `fdback_fc_emits_oversized_and_flag_wired`).
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
    `DB_CONSTANTS` (AlwaysFALSE/AlwaysTRUE/No Operation) + the distinct `02_COM.{db_element}` cumulatives across all
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
    **Verbose per-block log (production feedback, 2026-07-06):** after `engine.build` the handler emits one
    INFO line per generated block via **`engine.block_report(database)`** (a pure read of the SSOT tables +
    the registry): `<block>  <-  builders.<fn>()  template=<stem>  ->  CreationInfo CSV|FC XML (ImportReady),
    <n> rows [+ k instance DBs]` - the template omitted when none is shipped (stem fell back to the name),
    the surface from the registration's `emit`, the instance count = the block's non-empty `instanceOf-<FB>`
    cells (`_builder_instance_rows` refactored into per-block `_block_instances`, order-preserving).
    Test: `test_blocks.py::block_report_verbose_log_data`.
  - **Templates SHIP with the CSVs (contract evolution, 2026-07-07 - user report: the absolute `$ template=`
    path is dead on the OP machine).** `engine.project` copies each CSV-emitting block's template XML to
    **`blocks_creation_dir/Templates/<file>.xml`** (`_ship_template`, byte-exact/BOM-preserved, overwrite)
    and writes the CSV `$` line as the RELATIVE **`template=Templates/<file>.xml`** (forward slash) - the
    CreationInfo folder is self-contained. `software_blocks.template_ref` STAYS the absolute local path (the
    build input + the copy source); the relative form is a projection concern. The 03 FC-XML block ships no
    template (nothing references one); a missing template source still writes the relative ref, ships
    nothing. Deliberate byte-parity break vs PL3 on the `$` line; logged in the coordination doc (OP4
    resolves `template=` against the CSV's folder). Test: `test_blocks.py::project_ships_templates_with_relative_refs`.
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
  dual-link). **Production-test deviation (user, 2026-07-03): a ref flagged `cem_addr_fld` SUPPRESSES its own
  `cem_fld_none`** ("address found under a different FLD" already says the FLD isn't there - the second FAIL was
  redundant on the same row); **140 (IOL->CEM)** the decision tree (typed & `ce_mandatory` yes/warn -> CHECK [yes=FAIL/warn=WARN];
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
  (`documents_validation_report`/`_errors` x `.txt`/`.html`) to `config.validation_report_dir()`.
  `run_validation` itself never raises (reports always written); since the 2026-07-03 severity contract the
  GUI then HALTS the pipeline on any FAIL finding (see THE SEVERITY CONTRACT above).
  The GUI **"100" button** (`_run_validation`: stage -> run_validation -> the FULL banner-interleaved `items`
  render to the GUI log via `render.render_records` [EVERY level - the Levels dropdown elide-filters the view;
  the tee gets it all] + `treatments.apply_and_reconcile` over the issues [registry maintenance; never halts]
  -> a summary; the `only=` sub-runs render their full finding list too). **Production-test log refresh (user,
  2026-07-03):** the 110/120/130/140 banners render in the GUI as the SMALLER **SUBPHASE** style (phase blue,
  normal weight, 1pt smaller, `-` underline vs the bold main PHASE header); a cross-check line's aligned
  `<caller> op <other>` comparisons render IN the bit+FLD info columns (no longer duplicated before the detail),
  with `RenderRec.marks` styling them - `===` whole-comparison NEUTRAL grey (`cmpeq`), `=/=` the DIFFERING
  chars underlined (`cmpdiff`) - in both the LogView and the HTML reports. Tests: `test_validation_phase.py`
  (1, hermetic: the banner interleaving + the 4 files + treatable-only recording). **PARITY (the real bar - the report is
  documentation, NOT byte-parity): the PL4 finding set == PL3's, EXACTLY.** Over the same real documents (the
  Passing fixtures), PL4 produced **596 findings and PL3 produced 596, with 0 differences** in the tuple
  `(phase, type, norm(location), norm(detail))` across all 4 validators (`scratchpad/parity_100.py`; PL3 is fed
  PL4's staged rows so both validate the same data). Real-data counts: 341 PASS / 239 SKIP / 12 INFO / 4 WARN /
  0 FAIL (a clean project).
- **THE 4-STEP VALIDATION WORKFLOW (production-test restructure, 2026-07-03):** 1 validate doc 1 (110
  I/O List) · 2 validate doc 2 if present (120 C&E; SKIPs when absent) · 3 cross-checks (130+140) ·
  4 diagnosis checks (**150 - NOW LIVE**, `domain/validation/diagcheck.py`): PL4-NATIVE over the SSOT
  (no staging/parity touch - the old blocker was PL3's doc-based approach): per in-diag signal the
  (Diag Cabinet, Diag Bit) pair must be numeric (`diag_invalid` FAIL), the cabinet must exist in
  DiagnosisBlocks (`diag_unknown_cab` FAIL - a new PL4 check), and the slot must be unique per
  ALARM/WARNING family (`diag_dup_slot` FAIL / `diag_unique` PASS; family = type_hw ends 'W', PL3's
  rule). **Step 4 requires a FILLED doc**: a virgin one (no in-diag row assigned) SKIPs
  (`diag_virgin`) pointing at 200 Fill. PL3's `diag_container_check` is NOT ported (needs the per-type
  container config column + the cabinet FullName - a reviewed config addition when wanted). The
  **before/after quality report moved 145 -> 940 under 900 Reporting** (it is a REPORT, not a document
  check). Tests: `test_validation_diagcheck.py` (4, hermetic).
- **OUT OF SCOPE (user decisions):** the **`accept`** doc-mutating treatment (dropped).

## Phase 100b — Before/After Quality Report — DONE (PL4-native, standalone; see `CHANGES_SPEC.md`)
`domain/changes/` (reader · match · classify · report · run). A **standalone, non-pipeline** analysis under
ph100: compares the PRIOR revision (`*_previous_path`) of the project's documents (I/O List + C&E Matrix +
AREA) with the CURRENT one and **summarizes the EFFORT that brought the project to its current state**
(completions, corrections, address re-mapping, safety-logic changes; costliest-first) - a NEUTRAL measure,
not a blame / right-wrong verdict. The report is **viewer-facing**: no references to the pipeline, the
producing software, or internal field keys / coined acronyms (readable labels + bare reference
designations). Never touches the SSOT/BuilderData, never gates/halts, not in `run_order`; writes a graphical
HTML dashboard + a CSV audit trail to `ProjectDocumentation/Reports/`. **Full current design in `CHANGES_SPEC.md`.**
- **The design (evidence-derived from the real 8FVX R0.0→R1.2 pair):** address (`bit`) is the MOST
  important parameter - a re-addressing is the costliest correction to apply on a built machine (re-read
  manuals, re-test, propagate to many devices). So structural / re-scheme changes (address, slot, pin,
  device-tag) are **GROUPED BY NODE and COUNTED at the field's weight - never hidden**. The coordinated-
  re-map detection survives only as CONTEXT (a one-line "looks like a re-base"), never as a reason to drop
  rows. (Earlier the design wrongly netted these OUT of the count - corrected per the user's feedback.)
- **Matching (`match.py`)** — node-scoped, ADDRESS-BLIND, deterministic 5-tier cascade (normalize → partition
  by the stable `profinet_name` nodes → T1 exact fld+desc → T2 multichannel by connector+pin/position → T3
  within-node connector+pin [recovers device-tag renames] → T4 fuzzy → T5 positional spacer-fill with a
  no-blank→named guard). Address/slot/pin are NEVER identity keys. **Validated: 883/883 old rows matched, 0
  false buckets.** Leftovers force-match within a node (so removed≈0 by design). C&E matches by CONCATENATE
  ID; AREA matches by line+desc across pooled sheets (a row can MOVE sheet → `moved`).
- **Non-defect categories (kept OUT of the counts):** a NO-DESCRIPTION row = an unused channel - unchanged
  → `unused` (grey), changed → `complementary` review (a re-addressed free slot, shown LAST, faded).
  FunctionalUnit+Location-Device **noise** (punctuation / ≤1-alphanumeric-char identity change, `_fld_noise`
  = alnum-strip Levenshtein ≤1) split PER DIFF into a listing-only Noise category (counts unchanged).
  **Struck-through rows** counted + flagged (formatting to avoid).
- **Classification (`classify.py`)** — STRUCTURAL fields (`_GROUP_BY_NODE` = bit/slot/pin/connector + a bulk
  device-tag rename) GROUPED BY NODE (`grouped_changes`/`structural`), COUNTED at the field weight; report
  leads with them. Per described changed row: `by_tier` (once, max tier), `by_nature` (once, costliest:
  address > completion[all gap-fills] > other), `by_field` (per-field inventory = the neutral "what was
  changed" list) + `comp_addr`. Itemized diffs direction-tagged (gap-fill/value-change/value-loss; a crit/maj
  value-loss = regression). Tiers from `change_weights.csv` (critical/major/minor/exclude). Channel-uncertain
  blocks aggregate + flag. Node-aware **upgrade** (contiguous ≥4) vs forgotten. C&E: address counted (crit);
  lost effect = crit regression; new effect column = upgrade (orange). **AREA = device-centric MEMBERSHIP**:
  group by device, compare its SET of areas old→new → extended (areas added = the safety logic grew) / moved
  / reduced. Read **with formulas** (`data_only=False` - cached reads fabricate phantom deletions).
- **Output** — `io_documents_quality_report.{html,csv}`; self-contained light/dark HTML (every value
  HTML-escaped); first-issue mode (missing/identical prior → "no prior revision" notice).
- **Config/GUI** — `config_project/input_docs/change_weights.csv` + `config.load_change_weights()` /
  `changes_report_dir()` / `CHANGES_REPORT_STEM`. The `preliminary_check_exclude` (pipeline-owned AA–AH)
  columns are NOT compared. GUI phase-100 sub-button **145** `pb_change_report` (PL4-native, EN/IT) →
  `_run_change_report` (opens the HTML). Tests: `test_changes.py` (27, hermetic).

## GUI — runnable operator window (`gui/` + `launch_gui.py`) — GUI PORT IN PROGRESS (M0–M6 + STEP 1 i18n + STEP 2 + STEP 3 DONE; see `GUI_PLAN.md`)
**STEP 3 DONE (M5 Files + M6 Project Manager + M0b chrome remainder).**
**M5 — Files tab** (view-only): a notebook **Files** tab (`gui/files_panel.py` + the Tk-free
`gui/files_view.py`, tested) - a 3-section tree (Project configuration / User editable files / Generated
output, resolved from the active config/project) with read-only viewers: `.csv` -> a Treeview grid, `.xlsx`
-> a grid + sheet picker (openpyxl `data_only`, capped), text/yaml/json/xml -> a monospace pane; each with a
path strip + **Open externally** / **Open folder** (`gui/extedit.py`, port of PL3's LibreOffice/OS-default
open + reveal). ttk-only (no tksheet/ruamel dep; in-app editing waits on the codec-write path).
**Documents tab** (`gui/documents_panel.py`): the 4 input-document file pickers - current + previous I/O
List, current + previous C&E Matrix (the `*_previous_path` feed the ph100 before/after report). Each row has
a **Browse…** picker + a **Clear** button; a change is persisted IMMEDIATELY to the active
`project_params.yaml` (round-trip, comments preserved) via `config.save_document_path` /
`load_document_paths` (`DOCUMENT_KEYS`); follows a project switch (`refresh()`). Tests: `test_documents.py` (3).
**M6 — Project Manager**: `pipeline4/project/` (`state.py` = `%LOCALAPPDATA%/Pipeline4/state.json` recent/
last/root; `project.py` = `is_project`/`open_project`/`close_project`/`new_project`/`auto_reopen` over a
project ROOT folder routed by `config.use_project`) + a toolbar **Project ▾** menubutton (New/Open/Recent/
Set root/Close) + an active-project **title indicator** + auto-reopen on launch + `_apply_project_switch`
(reload Files/Explorer/Findings against the new config/Database). Tests: `test_project.py` (6).
**M0b chrome remainder** (in STEP 1): `gui/darktitle.py` + the full light/dark re-theme (`set_theme` on
LogView/PhaseBar/DatabaseExplorer/FilesPanel). NEXT: **STEP 4** ph200 (Documents Fill Out) - the last
backend effort.
**Backend status: ALL backend phases are built — 300/520/400/510/600/700/800/900/100 + ph200 (Documents Fill
Out).** ph200 (`domain/fillout/`) computes script_type (210, on `core/expr`) / index (220) / diag cabinet+bit
(230/240) over the staged signals and writes them back to the doc via the canonical **stage→fill→re-stage**
flow (`fill.fill_out`); the unified expression engine `core/expr` (which `rule_expr` was retired onto) is built
+ retrofitted everywhere — see **`EXPR_ENGINE.md`** + **`EXPR_BUILD_PLAN.md`** + **`PH200_SPEC.md`** (incl. the
device-tag RANGE notation + channel `n/N` suffix, and the manual orange "Risky Index Fill" button). The GUI port
(replicate PL3 + add SSOT-native features) is the active effort - the
plan + locked decisions are in **`GUI_PLAN.md`**. **M0 (foundations) DONE:** a **lightweight phase registry**
(`gui/phases.py` - the single source of the phase order: number/title/kind/subs/requires/handler +
`RUNNABLE`/`run_order`; ph200 Fill IS wired - subs 210/220/230/240 + the orange 245 - but kept OUT of
Run-all by design since it mutates the source doc), a **worker thread + queue/drain pump** (each phase runs off the Tk main
thread - the handler emits via `self._emit`/`self._status` enqueue, `_drain` applies on the main thread, a
`ttk.Progressbar` + `_busy` guard; single-phase runs no longer freeze the window), a basic **Run-all** (registry
`run_order`, each handler self-contained - M4 optimizes to a stage-once shared DB), and a **`ttk.Notebook`**
(Log tab). **M2 (Findings panel) DONE — rebuilt on the shared DataGrid (production-test feedback, 2026-07-03):** the tab
over `validation_issues` ⋈ the treatment registry now uses `gui/datagrid.py` (zebra, data-adapted column
widths, the small narrow font for >64-char cells, drag/double-click column resize) with row MULTI-selection
(plain/Ctrl/Shift — the pure `updated_selection` model, tested) + severity-coloured rows (`set_data(row_fg=…)`)
+ theme-registered. **`validation_issues` now PERSISTS the log line's key context** (`location2`/`doc2`/`bit`/
`fld`/`compared` — the flattened `===`/`=/=` comparison via `finding.compared_text`) so the panel answers
"what differed, where do both sides live"; context columns hide when empty across the view. Right-click treats
the WHOLE selection in ONE registry write (`findings_view.apply_treatments`); **`skip` + `ignore` are GREYED
(UI-only, panel + log menus) until the app reaches a stable version**. Filters + auto-refresh unchanged. The
pure join/treat logic is `gui/findings_view.py` (tested); `gui/findings_panel.py` is the Tk view. **M3
(Database Explorer) DONE:** a SQL console tab over the SSOT - `gui/dbquery.py` (`build_memory_db` loads
`Database/*.csv` into in-memory SQLite, JSON cells queryable via `json_extract()`; `run_query`; `SAMPLE_QUERIES`
- SELECT*/json_extract/GROUP BY/cross-table JOINs) + `gui/db_explorer.py` (schema sidebar, SQL editor
[Ctrl+Enter], results grid, samples combo, Refresh). Read-only over an in-memory copy. **M1 (structured
clickable log) DONE:** `LogView` is a Frame+Text (v/h scroll) with `append_records` over `io.render.render_records`
- clickable `Sheet!Cell` spans → open Excel at the cell (`gui/excel.py`, COM, graceful fallback), a treatable
line's `[LEVEL]` errlink → right-click Treat, a **Levels ▾ dropdown** (per-level checkboxes; FAIL/ERROR forced
+ greyed; toggles LIVE via per-level elide; persists the combination to `app_config.yaml` via
`config.save_app_log_levels`); the GUI `_gate`/`_render` (replacing `run.gate`/`run.render` in the handlers)
render EFFECTIVE-severity findings to structured records via `findings_view.apply_and_records`. **M4
(Run-all + sub-phase chevron dropdowns) DONE:** the phase bar (`phasebar.py`) is a 2-row registry-driven
grid - the pink Run master (spans both rows), per-phase **header** (row 0, runs the whole phase) + a grey
**▼ chevron** (row 1) opening an anchored, click-away/Escape/blur-poll **`_Dropdown`**. **Run-all**
(`_run_all`) drives a **determinate** progressbar (a `progress_step` per completed phase; single phases
bounce), emits a `[k/N]` marker per phase, and **halts the chain on a blocking FAIL** (`_gate` sets
`self._run_halted`; a handler crash is attributed to the named phase + stops the chain). **M4 REWORK (user
feedback):** the registry + bar now follow the operator **ORACLE `Pipeline3App/assets/ButtonsLayout.xlsx`**.
`gui/phases.py` carries each phase's FULL sub-button set (`Sub(number,label_key,kind,enabled,opens)`: action /
open / special, minus phase 200); deferred/unported buttons (150, 155/156, 320, 430, 810, 840, 920) are
kept VISIBLE but **greyed** (`enabled=False`) for oracle fidelity. **Sub-buttons RUN THEIR SUB-PHASE**
(PL3's model): each handler takes `only=None|<sub#>`; `_sub_command`/`_on_sub`/`_sub_worker` dispatch an
action sub to `phase_of_sub(n).handler(only=n)`, which builds the prerequisites then runs ONLY that
sub-phase (`only=510` still builds 520; `only=520` skips the I/O-Tags leg). **Open buttons** are wired
(`_on_open`/`_open_target` -> `os.startfile`). Layout: all header/run buttons are **EQUAL width** and the
**dropdown width MATCHES the column above**. **STEP 1 i18n (EN/IT, first-class) - the POINT is the LOGS:** the operator-facing **validation findings +
reports** are localized (an Italian operator reads IT findings); the chrome is secondary.
**LOGS:** `domain/validation/messages.py` is bilingual (the 50 `v_*` slugs, EN verbatim/parity-byte-identical +
IT from PL3); a finding's `detail` is built in the ACTIVE language via the AMBIENT `messages.active_lang(lang)`
(PL3's `ctx.lang` analog; single-threaded since the GUI runs one phase at a time; default `en` keeps the parity
oracle EN) - so the 53 builder call sites + `io/render.py` are untouched and the log line + `.txt`/`.html`
reports come out localized. `phase.run_validation(…, lang)` wraps the validators in `active_lang`, localizes the
sub-phase banners (`_BANNER_KEYS` -> registry `pb_*` keys) + the report chrome (`render.html_reports(items,
lang)`, `rpt_*` keys); the GUI `_run_validation` threads `self.lang`. **PL3-faithful: the `uid` hashes the
localized detail** (treatments key per operating language). **CHROME:** `core/i18n.py` (`tr(key, lang, **fmt)`) +
`phases.py` `name_key`/`label_key` + `phasebar.PhaseBar(lang=…)`/`set_lang()` + the toolbar **Lang EN/IT** button
(`_toggle_lang`/`_retranslate_chrome`, persisted to `app_config.yaml` via `config.load_app_ui()["language"]` +
`save_app_language`) + a **Font-size dropdown** (10/12/14) that live-resizes the log viewer
(`LogView.set_font_size` reconfigures the Text body + every level tag, preserving bold; `config.APP_FONT_SIZES`
/ `save_app_font_size`, persisted). **App-wide font (M0b fonts DONE):** `gui/fonts.py` (port of PL3's) registers
the bundled `assets/fonts/MonaspaceNeon-Var.ttf` privately (`AddFontResourceEx(FR_PRIVATE)`, resolves as
`Monaspace Neon Var`, graceful `Consolas` fallback); `theme.apply_theme` points the named Tk fonts
(`TkDefaultFont`/`TkTextFont`/…) + `theme.MONO_FONT` at it at `theme.APP_FONT_SIZE=13` - so the whole UI (chrome
+ phase bar + log) is Monaspace Neon Var 13 (the log size overridable via the Font dropdown). **COSMETIC: always-plural** - the validation messages + run-log lines drop
the `(s)`/`/i` singular-or-plural hedge (always plural, even at 0/1; the one deliberate deviation from PL3's
verbatim text, on the 5 INFO summary slugs - guarded by `test_validation_i18n.always_plural_no_hedge`).
**Stays EN** (PL3-consistent): the generator run-log data-lines + the non-100 phase
banners. NEXT (planning order): STEP 2 (300 staging granularity) · STEP 3 M5 Files / M6 Project / M0b chrome ·
STEP 4 ph200 Fill. Tests: `test_validation_i18n.py` + `test_i18n.py` + `test_gui_phases.py` (rebuilt to the
oracle, +`labels_resolve_in_both_languages`) + `test_gui_findings.py` + `test_gui_dbquery.py` +
`test_gui_levels.py` + `test_gui_phasebar.py`; verified by a real-data run of every `only=` branch + an EN<->IT
toggle smoke + a real-data EN-vs-IT validation report. The GUI itself is a manual `python launch_gui.py` check.
`python launch_gui.py` opens a sv-ttk dark window (graceful fallback) with a toolbar, the registry-driven
**phase-button bar** (Run + the 8 phases, ButtonsLayout colours), a colour-coded **log viewer** (in a notebook),
and a status bar + busy progressbar. Wired in EARLY (gui-less PL3 builds hid integration problems). **ALL phase
buttons run their phases for real** (on the worker thread)
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
- **Severity taxonomy + the GUI log-level filter.** `core/severity.py` is the single source of the level set -
  ALL levels are FOUR-LETTER codes (production-test decision, the `[XXXX]` column is always 4 chars):
  **FAIL** (halts), **ERRR** (skip the item, continue), **WARN**, **INFO**, **SKIP**, **PASS**, **RSLT**
  (the phase's ENDING-SUMMARY line, own cyan-bold colour - a LOG level, never a finding/treatment target;
  a NORMAL Levels-dropdown toggle, the yaml wins - every handler's outcome line emits it), **DEBG**
  (dev-only, hidden by default) + the **PHASE** banner and the **HEAD** column-header line (chrome, always
  shown). Each level has a distinct first char (F E W I S P R D), so config lists/registries can use single
  chars, the 4-letter codes, or legacy full names (`ERROR`/`DEBUG` resolve unchanged) interchangeably
  (`severity.resolve`/`resolve_set`).
- **THE SEVERITY CONTRACT (production-test decision, 2026-07-03): FAIL ALWAYS HALTS THE PIPELINE.**
  FAIL = halts (pre-write via `_gate`: nothing written; post-write via `_render`: the output already on
  disk is flagged SUSPECT + the run/Run-all chain stops - incl. a treatment-ESCALATED finding); ERRR =
  possibly-corrupt output, no halt; WARN/SKIP/PASS/INFO = informative. Every phase seam enforces it:
  the gated builds (300/520/700 + ph200 fill via `_gate`), the projection/report phases (400/510/600/800/
  900/145 via the now-halt-capable `_render`), and the full 100 (halt after reconcile - reports written,
  generation blocked). **ph200 findings are RECORDED**: the fill is doc-only, so `fill._finalize_findings`
  stamps `doc` onto every Sheet!Cell-located finding (the log links + the [FAIL]->Findings jump need it)
  and `finding.record_standalone` appends the treatable ones to `validation_issues.csv` alone (loads/saves
  ONLY that table - no other SSOT file touched). NOTE: in Run-all, validation (100) runs LAST by design -
  its halt marks the run, it does not protect the already-run generation phases.
- **THE LOG ENGINE (production-test consolidation, 2026-07-03).** All TABULAR log data flows through ONE
  engine - `io/render.render_records` over Findings - consumed by every phase via the GUI `_gate`/`_render`
  seam and `run_validation` (and persisted to `validation_issues` for the Findings tab). Its layout rules:
  the `| |` info columns are computed PER (SUB)PHASE GROUP and ONLY the columns some line in that group
  actually fills are rendered (`_phase_widths` returns `used`; no empty `| |` placeholders - a no-info group
  carries no pipes at all); every group opens with a **[HEAD]** line carrying the column titles in the same
  alignment (title widths participate in the layout; emitted after the level filter so a filtered-empty
  group has no orphan header). The handlers' NARRATIVE progress lines (counts/paths) stay free text by
  design - they follow the uniform `[LEVL]  <sub#>: <counts> -> <target>` 2-space-indent convention and are
  heterogeneous one-off facts, not columns. **`config_project/app_config.yaml`**
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

## GUI/config REFRESH (pre-production-test, 2026-07-02 — UI_REFRESH_PLAN A–I, all landed + pushed)
The user-reviewed refresh before the first production test (the full spec + commits: `UI_REFRESH_PLAN.md`):
- **Phase bar**: composite `_PhaseButton` ([icon] number / 2-line narrow description; `theme.narrow_family`
  = Bahnschrift SemiCondensed→fallbacks); icons via **`assets/icons/phase_icons.yaml`** (Twemoji PNGs + 4
  project-drawn customs from `scripts/gen_custom_icons.py`; new phase = a row + a 72px PNG); chevron at 61%
  height; the dropdown clamps at the app border + scrolls.
- **Theme**: `gui/theme.py` rebuilt — one `TOKENS[mode][role]` table + native clam styling + a
  `theme.register(cb)`/`set_mode` subscription model. **sv-ttk REMOVED on measurement** (36.6→7.8 ms/log-line
  repaint, 164→31 ms/toggle on the VMware target). Do NOT add explicit TScrollbar styles (measured ~5x
  per-repaint cost; scrollbars inherit from the "." root style).
- **DB Explorer**: lazy async load + `dbquery.dir_stamp` reuse + chunked fill. **Files tab**: CONFIG-DRIVEN
  via the `files_tab:` section in app_config.yaml (${placeholder} roots + include/exclude regex; active →
  builtin fallback; no code-baked structure). **yaml/json**: highlighted text view + an Object-explorer
  editor (`gui/object_editor.py`, ruamel round-trip, `…` path pickers on *path*/*dir* keys).
- **DataGrid sort + cascade filters (production test, 2026-07-03)** - every table viewer (Files CSV/xlsx,
  DB Explorer results, Findings) at once: header CLICK = tri-state NATURAL sort (asc -> desc -> release;
  `I2.2 < I2.10 < I10.1`, blanks last; NON-destructive - only the `_view` source-index list permutes);
  header RIGHT-CLICK = the filter popup (substring / regex / an Excel-style pick list of the VISIBLE rows'
  distinct values - the CASCADE: each filter narrows what the previous left; filters compose as AND);
  active sort/filters render as removable CHIPS above the header + a `k of n rows` count; filtered column
  headers read accent-coloured. `selection()`/`raw_of`/`on_edit` stay SOURCE-indexed, so hosts (the
  Findings treat, the CSV cell editor) are sort/filter-agnostic. `XLSX_MAX_ROWS` 3000 -> 50_000 (real
  projects reach 10-20k rows - user).
- **Table viewer EXTRACTED (2026-07-03) -> RENAMED `FileXYApp/` (package `filexy`, 2026-07-03)** - the
  file-EDITOR logic joined it (user: "I'm liking the whole file editor vibe"): `highlight.py` (now with
  DATA-DRIVEN languages a la Notepad++ UDL - `langs.json` ships scl/sql/ini; a language = a JSON entry:
  extensions/comments/strings/keyword groups/extra regexes; `load_languages` merges a user file;
  `available_kinds()` feeds the Files tab's SELECTABLE `Lang:` picker in the text editor) and
  `objectview.py` (the object explorer/editor). PL4 shims: `gui/_filexy.py` is the ONE bootstrap
  (sys.path + theme binding); `gui/datagrid.py`, `gui/highlight.py`, `gui/object_editor.py` re-export -
  hosts + tests untouched. Doc-view routing now keys on `object_kind_of` (yaml/json/xml only), so scl/sql
  route to the TEXT editor with highlighting. (The old on-disk `TableViewerApp/` was LOCKED by the
  user's running app during the rename; DELETED 2026-07-05 once the app closed.)
  (`filexy`:
  `core.py` PURE engine [the executable spec for the Rust port] · `grid.py` Tk widget+popups · `theme.py`
  REBINDABLE palette/fonts · `files.py` csv/xlsx loaders · `app.py`+`launch_viewer.py` standalone window).
  **`pipeline4/gui/datagrid.py` is now the EMBEDDING SHIM**: sys.path's the sibling package, binds
  `tableviewer.theme` to PL4's tokens + bundled fonts (pixel-identical, theme-toggle follows), re-exports
  the historical surface - the 3 hosts + the test suite unchanged. Landed WITH the extraction (every PL4
  table at once): **Ctrl+F global quick search** (col=None spec, live, a removable chip), **Ctrl+C TSV
  copy** (selection in view order, else the filtered view), **row-detail card** (double-click on read-only
  grids; set_data keeps raw rows so multi-line cells show whole), **column stats** in the filter popup
  footer. Tests: `test_filexy_shim.py` (4: re-exports+theme binding, quick-search spec, tsv/stats,
  the package STANDS ALONE - subprocess runs its own tests + imports pipeline4-free);
  `FileXYApp/tests/test_core.py` (bare-python standalone sanity). **PINNED COLUMNS DONE** (the last
  viewer feature): `set_frozen(n)` / the filter popup's Pin-≤-here/Unpin + the removable ⚲ chip - while
  x-scrolled the first n columns re-draw as an opaque STRIP (header + body, an accent separator) at the
  viewport's left edge; EVERY hit test maps through the pure `core.hit_x` (strip coords = the natural
  [0, frozen_w) coords; past-strip = canvasx - the covered zone is unreachable), so sort clicks /
  filters / cell edits land on pinned columns (a pinned cell's edit overlay re-anchors to the strip).
  ALSO fixed the latent x-scroll-without-redraw culling bug (xscrollcommand now schedules the body
  redraw + the header repaint).
  **Production-test viewer fixes (2026-07-06, user feedback):** (1) `set_data` pads the header to the
  WIDEST row via `core.pad_columns` - a ragged file (InstanceDBs.csv opens with a 2-cell `#` comment row
  over 5-cell `@` data rows) no longer hides its extra data columns (fixes every host at once; the CSV
  editor still saves the ORIGINAL header - the pad is display-only). (2) **Click-select is UNIVERSAL**:
  every grid highlights the clicked row (select_bg; Ctrl/Shift/drag multi-select) + outlines the clicked
  CELL (`_cursor`, accent, pinned-strip aware; reset with the view on sort/filter/set_data);
  `selectable=True` now gates only the host context menu, and Ctrl+C copies the clicked selection on any
  grid. (3) **Width-aware render font** (`core.render_kind`): a >64-char cell drops to the narrow font
  only WHILE it can't show whole in the normal font - widening the column past the text RE-EXPANDS it
  (the static `cell_kind` rule never recovered after a resize); short cells never narrow.
- **SCL highlight v2 + the Rust core port STARTED (2026-07-05)** - `langs.json` scl entry upgraded from
  the vscode-simatic-scl rule INVENTORY (repo has NO license -> only Siemens language FACTS extracted,
  all regexes written fresh): OOP keywords (METHOD/INTERFACE/EXTENDS/...), the full type+builtin set,
  typed literals (`WORD#16#F0`, `T#2d_3h` - whole-token), `%DB1.DBX0.0` addresses, `#locals` incl.
  `#"quoted"`, `x_TO_y` conversions, `S7_*` pragmas, `"quoted globals"`. FIX in
  `filexy/highlight.py::_compile_language`: EXTRA rules compile BEFORE keyword groups + numbers (else
  the keyword alternation split typed literals). **`FileXYApp/rust/filexy-core/`** = the Rust port of
  the pure engine (user's learning goal; toolchain: rustup/cargo 1.96.1 + VS18 MSVC): `sort.rs`
  (derive-Ord NaturalKey replaces Python's tuple trick) / `filter.rs` / `select.rs` / `layout.rs`
  (measure CLOSURES injected; + `sanitize`) / `export.rs` - every test vector mirrors a Python golden
  test (15/15 `cargo test`; behaviour contracts: broken regex matches NOTHING, blank = `""` exactly,
  `%g`-style integral printing). `rust/README.md` = port map + roadmap. Bash note:
  `export PATH="$PATH:/c/Users/bogdan.dragoi/.cargo/bin"` first.
- **The Rust engine is LIVE (2026-07-06)** - `src/python.rs` (PyO3 0.26, abi3-py310) + `src/xlsx.rs`
  (calamine): `py rust/install_native.py` (from FileXYApp/) maturin-builds and drops
  `FileXYApp/filexy_core.pyd` (gitignored); `filexy/core.py`'s end-of-module `_install_native()`
  swaps apply_filters/sorted_view/distinct_values/to_tsv/column_stats/sanitize_rows, `files.py`
  routes read_xlsx/xlsx_sheets through calamine - transparently for PL4's embedding too (the shims
  re-export AFTER the swap; the full PL4 gate runs green with ENGINE=rust). `core.ENGINE` reports
  the active engine; `FILEXY_RUST=0` = the escape hatch; TypeError falls back to Python (non-str
  cells), Python-only regex (lookarounds/backrefs) routes to `re` (`_needs_python_regex`);
  `core.PY_IMPLS` keeps the originals for tests. PARITY (`FileXYApp/tests/test_native.py`, 48
  checks): golden vectors through BOTH engines + CELL-BY-CELL loader comparison on the real
  workbooks (DeviceTypesDatabase.xlsx 28 sheets ~7k rows: openpyxl ~300ms vs calamine ~15ms,
  **~19-24x**) - found+fixed: stable-DESC ties (Python sorted(reverse=True) keeps original order ->
  a reversed comparator, NOT sort+reverse), XML CRLF normalization (openpyxl normalizes per XML
  1.0, quick-xml doesn't). `set_data` now uses bulk `core.sanitize_rows`; the standalone title
  shows the engine. An adversarial multi-agent review then confirmed+fixed 7 more: regex routing
  made EXACT (re.compile pre-check + native `regex_ok` - no token lists; Python-only syntax
  [\Z, \4+, (?P=, conditionals, atomics] runs on `re`, Python-BROKEN patterns [(?i) mid-pattern]
  match nothing), FULL Unicode case folding via `caseless` (Python casefold: ss<->ß) in substring
  filters + natural_key, per-spec regex PRECOMPILE in apply_filters (was per-cell!), duration
  formats ([h]:mm:ss) render as Python str(timedelta) ('1 day, 12:00:00'), out-of-range date
  serials -> '#VALUE!' like openpyxl, `files.py` falls back to openpyxl (warn-once) when calamine
  ERRORS (e.g. #SPILL!-class cached errors - the file stays openable), install_native.py handles
  the Windows-locked .pyd (rename-aside + atomic replace + 'close the app' message), stale-.pyd
  AttributeError guarded (falls back to Python), `__version__` stamped. ACCEPTED divergences
  (documented in xlsx.rs/files.py): leading/trailing formatting-only rows dropped; writers that
  emit '<v>4.0</v>' text (POI etc.) show '4'; plain-digit ints >=1e16 lose exact digits (f64);
  regex-internal (?i) is simple-fold (İ). REMAINING: a resident #[pyclass] Table handle (skip the
  per-call list[list[str]] conversion) once 50k+ rows feel slow; an egui shell only if the
  standalone exe needs it.
- **`user_input/generation_params.yaml`** (active→builtin, neither→RAISE): the 620 SCL DWord names/variant/
  `S1.CABINET{$index}.{$role}` instance template (core/expr, strict) + the DiagList `$PLC_Binding$` sentinel;
  a builder declares its output surface at registration (`@builds(name, emit="fc_xml")`) — migrated at
  byte-parity 26/26. The 02_COM constants + `DB_CONSTANTS` seeds stay in code until after the production test.
- **expr tooling** (`core/expr/tools.py`): `tokens`/`check`/`check_template`/`function_names` (editor-grade,
  lenient, precise unknown-$field spans) + the toolbar **ƒx** Expression Builder (`gui/expr_builder.py`,
  live preview against a real SSOT row). **Guide**: `docs/guide/*.md` + `gui/helpwin.py` (F1 opens the
  focused area's section; `src://` links open the shipped source; missing sections render the
  "no instructions provided" page; `scripts/list_guide_stubs.py` lists authoring TODOs).

## Testing
Plain-`python` tests under `tests/unit/` via `_harness.py` (PASS/FAIL, non-zero exit). The
**data-independent suite is the green gate** (currently **236**: keys/table/database, signals schema,
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
- **ONE expression engine (`core/expr`), native `$`-syntax everywhere.** Every config-CSV expression column is
  authored in the engine's native form: `{$col}` template holes (`identity.interp`/`interp_keep`/`dbtemplate.render`
  all delegate to `expr.render`), `$col` predicates (ph200 `when` + `for_each`'s `where` via `expr.test`), and the
  host funcs `clean()`/`join()`/`extract()`/`numeric()`/`where`/`unique`/`node_of`. The three legacy mini-languages
  (`_dollarize` bridge, `dbtemplate`'s `for_each` tokenizer/`_Parser`, the `interp_keep` regex) are RETIRED. See
  `EXPR_BUILD_PLAN.md` (M-E6). NOTE: this made `signals.csv` store its `type`/`interface_tagname` templates in
  `{$token}` form — so it is NOT byte-identical to the pre-M-E6 300 lock (all resolved outputs unchanged; re-run
  strict 300 parity with `$`-normalization on those two cells).
- Run/test from the `Pipeline4App` root. Commit messages end with
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
