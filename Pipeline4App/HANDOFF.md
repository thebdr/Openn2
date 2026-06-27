# PL4 — HANDOFF (next session)

You are continuing **Pipeline4App (PL4)** — the SSOT-database clean-room rebuild of PL3. Read **`CLAUDE.md`**
(live architecture) and **`DESIGN.md`** (rationale + locked decisions) first. This file is where we are and
what's next.

## Working agreement (the cadence that's been running)
PROPOSE/explore → SHOW/confirm → implement → keep the data-independent gate green → **commit only on the
user's word**, push only when asked. Each chunk is committed with its gate **and** its parity verified. ASK
when domain judgement is needed (it's the user's; you implement). A question is a question — answer it, don't
change code. Commit messages end with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## Where we are
- **Branch `pl4`**. **Phases 400 (a–f) + 510 + 600 COMPLETE** (300 + 520(a/b/c) + 400a–f + 510 + 600a/b/c/d).
- **GIT STATE:** `origin/pl4` PUSHED + synced through **`7c2fa17`** (S1 + S2 `1dade77` + S3 `7322470` + S4 `5838f88`
  + S5 `7c2fa17`, all pushed). **The SEVERITY ROLLOUT IS COMPLETE.** The working tree holds the UNCOMMITTED S6
  finalization (docs only — the code cleanup landed incrementally; CLAUDE.md + HANDOFF.md). The severity
  taxonomy/GUI-filter (`5e291f8`) + S1–S5 are committed + pushed.
  - The repo root carries unrelated pre-existing edits (Openn3App, Pipeline3App config, Shared) from before this
    session — NOT ours; leave them.
- **Gate: 159 tests green** (data-independent). Run from `Pipeline4App/`:
  `for t in tests/unit/test_*.py; do python "$t"; done`
- **SEVERITY model (user-directed, IN PROGRESS — full rollout chosen, THEN 700).** Taxonomy (`core/severity.py`):
  FAIL (halts) · ERROR (skip item, continue) · WARN · INFO · SKIP · PASS · DEBUG (dev-only) + PHASE banner;
  first-char-addressable. The GUI filter (`app_config.yaml user_interface.log_levels`, default `[F,E,W,I,S,P,D]`)
  is done. **S1 (the findings/treatment core) is DONE**: `core/finding.py` (frozen `Finding` + uid excluding
  severity + `validation_issues_table` [persisted - user's choice] + `record`); `core/treatments.py` (the
  `error_management.csv` registry generalized - a per-uid treatment names the target level, can escalate to FAIL;
  load/apply/effective_severity/should_halt/reconcile/write/set_treatment); `core/run.py:gate` (apply+render+halt
  iff effective FAIL) + `has_blocking` (raw-FAIL write guard); `config.user_input_dir()`. Tests: +19. S1 touched
  NO phase (parity untouched); committed + pushed (`37559f0`). **S2 retrofit 520 DONE (`1dade77`)**: `generate`
  -> `list[Finding]` (9 FAIL + 4 WARN slugs); `build` -> `(database, findings)` + `run.has_blocking` no-write guard
  + `finding.record` -> `validation_issues`; GlobalDB XMLs byte-identical to pre-S2. **S3 retrofit 300 DONE
  (`7322470`)**: `stage()` -> `(database, findings)`; `stg_no_io_sheet` FAIL replaces `raise SystemExit`;
  `stg_dup_signal_uid` WARN via `_dup_findings`; `record` + save. The handlers **accumulate staging + 520 findings
  and `run.gate` ONCE** (`run.has_blocking(f)` skips the dependent sub-phase; a post-gate `"db_blocks" not in
  database` guard handles a DOWNGRADED prereq FAIL that would otherwise KeyError - found by the review workflow).
  **S4 retrofit 400+510 DONE (uncommitted)**: `find_interfaces`/`collect_mirror_set`/`build_interfaces` ->
  `(…, findings)` (WARN `if_ioc_no_index`/`if_signal_not_mirrored`; `build_interfaces` records + saves);
  `io_tags.interface_tags`/`project` -> findings (WARN `iotag_no_address`; project's dict key `warnings`->`findings`,
  a pure projection - no record). **`core/run.py:render`** = `gate` minus the halt (shared `_render`) for the
  WARN-only PROJECTION phases (output already written -> no misleading `nothing written` line); the GUI 400/510 call
  `run.render`. Gate 158 green; `interface_elements` + PLCTags **byte/content-identical to pre-S4**. **S5 retrofit
  600 DONE (uncommitted)**: `diagnosis.build` -> `(database, findings)` (was the LAST legacy `(errors, warnings)`
  tuple - its errors/warnings were always EMPTY; now records + saves); `diaglist_csv.project` gains `findings: []`;
  `diagnosis_scl.project` renames its dict `warnings`->`findings` + emits the WARN `diag_scl_template_missing`
  (phase 620) on an absent template. GUI `_run_diagnosis` consumes the build tuple + `run.render`s the 600/610/620
  findings (drops the dead if-errors block). Gate 159 green; `diagnosis_entries` + DiagList_IO/Logic.csv +
  Diagnostic_for_OPC.scl **byte-identical to pre-S5**. **S6 (the final sweep) DONE - ROLLOUT COMPLETE**: ZERO legacy
  `(errors, warnings)` tuples / `warnings`-key reads remain in `pipeline4/` (cleanup landed incrementally); the
  **full 5-phase byte-parity re-run** vs the pre-rollout baseline `95d3dfb` is **0 diffs across all 20 BuilderData +
  SSOT outputs** (9 GlobalDB XMLs + PLCTags 214 rows + DiagList_IO/Logic + the OPC SCL + the 8 SSOT tables), only
  `validation_issues.csv` added. **NEXT: phase 700 (Hardware)** - see "What's NEXT" below. PARITY RULE held every
  chunk (report CONTAINER + render call only; 0-byte diff).
  - **TRANSITIONAL (gate reconcile scope):** `run.gate` -> `treatments.reconcile` prunes/stales registry rows
    GLOBALLY; with multiple gated phases across separate clicks this can churn another phase's untreated rows.
    Invisible today (clean data = 0 findings = empty registry); treatments still APPLY (`apply` ignores `stale`).
    Proper fix = reconcile once per RUN over the union, lands with the engine (post-S6).
- **400f landed** (`interfaces.template_native_elements` → the template's shipped per-type interface signals into
  `interface_elements`; the IF_ projection skips `source="template"`). 510 PLCTags is now the complete interface
  tag set. **Interface parity vs current PL3 is EXACT** (see "Interface parity — RESOLVED" below): PL4's
  `collect_mirror_set`/`allocate_bytes` == current-PL3's, 0 differences. The PLCTags oracle's apparent deltas were
  stale inserted IF_ sheets, not PL4 bugs.
- **NOTE — the OutputTree PlcTags/DiagList are NOT a valid parity oracle anymore**: a GUI run wrote PL4's output
  there (it's `config.io_tags_dir()`/`diaglist_dir()` with no project open). Use a FRESH PL3 run to scratch (see
  `scratchpad/oracle_pl3_510.py`) or the known values. The SCL ref (06-23) is intact.
- The SSOT **`Database/`** now holds **8 tables**: `signals` + `diagnosis_cabinets` (300) · `db_blocks`/`db_members`/
  `instance_dbs` (520) · `interfaces`/`interface_elements` (400b, +`io_address_side1`) · `diagnosis_entries` (600).
  Saves to `Shared/Database/`. (`validation_issues` is now WRITTEN by 300 + 520 — S2/S3 record their findings; the
  remaining phases join as S4–S6 retrofit them. On clean data it is an empty table.)

### Commits this session (oldest → newest)
1. `407ed07` staging direct fields — positional node ranges (`I_/Q_startByte/endByte`) + `IsSorterArea`
2. `dfd29ac` **520a+520b** — the `dbtemplate` engine (render + for_each DSL) + `datablocks.generate` over the
   registry → `db_members`/`instance_dbs` + the **write-back** (`name_in_db`/`datablocks`/`plc_binding` onto signals)
3. `4483f0e` **520c** — `datablock_xml.project` (the GlobalDB-XML projector) + the `db_blocks` table + GUI "500"
4. `2ba9462` **400a** — `interface_tagname` (per-type templates relocated → `chain_reactions/interface_tagnames.csv`)
5. `28aa9ff` **400b** — the `interfaces` + `interface_elements` tables (mirror set + byte layout)
6. `11cd5e7` **400c** — the `IF_*.xlsx` projection (`interface_xlsx.project`, openpyxl)
7. `5bc4aca` **400d** — `pipeline4/io/xlsx_edit.py` (the surgical ZIP/regex writer) + the 14-test suite
8. `8da7046` **400e** — `insert_interface_sheets` (the lossless IF_ insertion + address-cache seed)
9. `d558f45` **510** — `domain/io_tags.py` PLCTags.xlsx + `io_address_side1` stored on interface_elements at 400
10. `599c14a` **600a** — `signal_diagnosis.csv` + staging diag fields + `diagnosis_cabinets` + the interp `:03d` fix
11. `256aefe` **600b** — `domain/diagnosis.py` `build()` → the unified `diagnosis_entries` (io + logic)
12. `93a63f7` **600c** — `domain/diaglist_csv.py` → DiagList_IO.csv + DiagList_Logic.csv + GUI "600"
13. `40dde03` **600d** — `domain/diagnosis_scl.py` → Diagnostic_for_OPC.scl (byte-identical to the ref)
14. `2cb6a91` **400f** — `template_native_elements` → the template's native interface signals into the table
15. `754dbd2` doc — interface parity RESOLVED (oracle artifact)
16. `5e291f8` severity taxonomy (+DEBUG) + the GUI log-level filter
17. `37559f0` **severity S1** — `core/finding.py` + `core/treatments.py` + `core/run.py` + `user_input_dir`  **← origin/pl4 PUSHED head**
18. `1dade77` **severity S2** — retrofit 520 (`generate`/`build` → findings + `validation_issues` record + `run.gate`)
19. `7322470` **severity S3** — retrofit 300 (`stage` → findings, `stg_no_io_sheet`/`stg_dup_signal_uid`) + accumulate-and-gate-once + the db_blocks guard
20. `5838f88` **severity S4** — retrofit 400+510 (`build_interfaces`/`io_tags.project` → findings) + `core/run.py:render`
21. `7c2fa17` **severity S5** — retrofit 600 (`diagnosis.build`/`diaglist_csv`/`diagnosis_scl` → findings; the last legacy tuple gone)  **← origin/pl4 PUSHED head**
22. *(uncommitted)* **severity S6** — rollout complete (docs: full 5-phase byte-parity re-run = 0 diffs vs pre-rollout `95d3dfb`)

## What's DONE (verified, parity vs PL3)
- **Phase 300 Staging** — the full `signals` table. Direct fields complete: C&E enrichment, FLDs, tags,
  positional node ranges, `IsSorterArea`. **Pending at staging**: `subnet_name` (from `profinet_ip`).
  Parity: 269 signals, 0 mismatches on every checked field.
- **Phase 520 Data Blocks (a/b/c) — DONE.** One registry evaluator → `db_blocks`/`db_members`/`instance_dbs`;
  `name_in_db`/`datablocks`/`plc_binding` written back onto signals; `db_members`+`db_blocks` projected to
  `<DB>.xml` (BOM/CRLF, F_DB OPC-lock). Parity: 0 mismatches on the 3 signal fields (269); the 5 reference
  GlobalDB XMLs byte-equivalent (member order grouped-by-type — accepted). `InstanceDBs.csv` deferred to ph800.
- **Phase 400 Interfaces — DONE (400a–e).** `interface_tagname` (0 mismatches/269); the `interfaces` +
  `interface_elements` SSOT tables (`find_interfaces`/`collect_mirror_set`/`allocate_bytes`); the `IF_*.xlsx`
  projection (`interface_xlsx.project`, openpyxl); the `xlsx_edit` surgical writer (400d); the lossless
  `insert_interface_sheets` (400e). Parity: all 18 SORTER-01 mirror elements match the reference exactly + are
  WRITTEN with 0 byte mismatches (the lone ref-extra `IF_ENCODER_SPEED` is stale config); the IF_ insertion is
  lossless on the real I/O List (all 7 source sheets kept, formulas + Profinet IP caches survive, 151 + 71 address
  values seeded for 510). GUI "400" runs stage → 520 → build → project → insert.
- **Phase 510 I/O Tags — DONE.** `domain/io_tags.py` projects `signals` + `interface_elements` → `PlcTags/PLCTags.xlsx`
  (the OP4 import surface). Decision (user): interface tags read from the **SSOT** (`interface_elements.io_address_side1`,
  stored at 400), NOT a read-back of the IF_ sheets. Parity vs the reference PLCTags.xlsx: **direct-I/O side EXACT
  (98/98 across all 8 signal tag-tables)**; the interface side emits the mirror block. GUI "500" runs stage → 520 →
  build_interfaces → io_tags.project.
- **Phase 600a — DONE.** The diagnosis config relocation (`signal_diagnosis.csv` keyed by `type_id`: `in_diag`/
  `diag_logic`/`diag_desc`/`tristate`/`tristate_desc`, verbatim from PL3 + the new `tristate` flag) + the staging
  foundation (the type-merge, `diag_desc` resolved, the `diagnosis_cabinets` table, the `interp` `{:03d}` fix). Parity:
  `diag_desc` 0-mismatch/269 vs IODatabase; `diagnosis_cabinets` 0-mismatch vs PL3 `load_diagnostic_blocks`. **It lit
  up the 400 +DIAG auto-mirror** (SORTER+DIAG-02 4 → 83) — so interface-completeness item (b) below is now DONE.
- **Phase 600b — DONE.** `domain/diagnosis.py` `build()` populates the unified `diagnosis_entries` (io + logic) from
  `signals` + `diagnosis_cabinets` + `diagnosis_logic_rules` (`io_entries` + the OR/per-row `resolve_logic`; the SCL
  channel values `in_binding`/`ml_value`/`fl_value`/`node_of`; + the frozen `diag_columns` snapshot). GOTCHA fixed: the
  logic row's `diag_cabinet`/`diag_bit` are injected as STRINGS (interp's `value or ""` turns the falsy int `0` into
  `''`). Parity: **DiagList_IO 73/73 + DiagList_Logic 6/6, 0 field mismatches** vs the reference (by PLC_Binding).
- **Phase 600c — DONE.** `domain/diaglist_csv.py` `project()` filters `diagnosis_entries` by `source` and writes the
  `diag_columns` snapshot → `DiagList_IO.csv` + `DiagList_Logic.csv` (comma, CRLF, no BOM; `config.diaglist_dir()`).
  GUI "600" runs stage → 520 → diagnosis.build → diaglist_csv.project. Parity: both files **FULL-ROW IDENTICAL** to
  the reference (73/73 + 6/6, 0 PL4-only / 0 ref-only; header + CRLF + no-BOM match).
- **Phase 600d — DONE.** `domain/diagnosis_scl.py` `project()` -> `Diagnostic_for_OPC.scl` from `diagnosis_entries`
  (stored channel values) + `diagnosis_cabinets` (`template_type` -> the 01-04 variant). **Tristate = `template_type`
  in {2,4} OR a per-type `tristate` signal** (the user's flag; forcing it on an odd template_type uses the
  tristate-counterpart variant 1->2/3->4). UTF-8 BOM + CRLF + FUNCTION rename; GUI "600" runs 610 + 620. Parity: the
  SCL is **BYTE-IDENTICAL to the reference** (22752 bytes, 438 lines, 1.0000 similarity, 0 diff lines).
- **Phase 400f — DONE.** `interfaces.template_native_elements` pulls the template's shipped per-type interface
  signals into `interface_elements` (`source="template"`; `<index>` resolved, address per-base); the IF_ projection
  skips them (no doubling). 510 PLCTags is now complete. Fresh-PL3 oracle: IF_SORTER-01 25==25; PL4 213 / PL3 208.

## Interface parity — RESOLVED (the "2 deltas" were oracle artifacts, NOT PL4 bugs)
The fresh-PL3 PLCTags oracle (`scratchpad/oracle_pl3_510.py`) showed a +2-byte `Door Alarm` shift + a +5
`Contactor Output` delta. **Root cause: PL3's `generate_io_tags` READS the stale IF_ sheets already inserted in
the I/O List (offset 22, old +DIAG=78) — it does NOT regenerate them.** Compared at the SOURCE (`scratchpad/
diff_mirror.py`): **PL4's `collect_mirror_set` + `allocate_bytes` == current-PL3's, EXACTLY** — SORTER-01 18/18
and SORTER+DIAG-02 83/83 mirror elements, **0 address-triple differences**, Door Alarm @ offset 24 in BOTH. So
PL4 has full interface parity with current PL3 (and is MORE correct on naming: PL3 still emits literal
`{db_element}` + the stale `Encoder Speed`; PL4 resolves both). Nothing to fix. (A truly fresh PL3 oracle would
require PL3 to re-insert the IF_ sheets first; the `collect_mirror_set` equivalence is the conclusive check.)

## What's NEXT (in order)
**The SEVERITY ROLLOUT (S1–S6) is COMPLETE** — every phase reports through the Finding/treatment model, the full
5-phase byte-parity re-run is 0 diffs vs the pre-rollout baseline, and zero legacy `(errors, warnings)` tuples
remain. **NEXT: phase 700 (Hardware)** — its full design is already done (the `understand-700-hardware` workflow /
the 700a-b-c plan below): `domain/hardware.py` + `hardware_csv.py`, the `hardware_stations`/`hardware_modules`
tables, `config.load_device_types_db` + `hardware_dir`; missing-DTD head = **FAIL** (now via the severity model -
emit a `hw_*` Finding + `run.gate`), switch = WARN; comma/no-BOM/CRLF format-2; parity vs current-PL3 `extract`.

### Severity rollout — the S2–S6 retrofit map (user chose: full model + retrofit, THEN 700)
The mechanics per phase: `build`/`project` returns **`list[Finding]`** (drop the `(errors, warnings)` strings) +
calls **`finding.record(database, findings)`** (populates the `validation_issues` table, saved with the phase) +
keeps a **`run.has_blocking(findings)` raw-FAIL no-write guard** before writing BuilderData; the GUI handler calls
**`run.gate(findings, self.log.append, label=…)`** to render + halt. **PARITY RULE: change only the report CONTAINER
+ the gate call — NEVER the skip/write PREDICATES → 0-byte BuilderData diff per chunk** (re-run each phase's scratch
parity after). Slug convention `<area>_<condition>`. Findings to emit (from the design pass; default sev in caps):

- **S2 — 520 `datablocks.py`** ✅ DONE (`1dade77`) — the only live FAIL-blocks-write path; richest:
  FAIL — `db_for_each_invalid`, `db_only_load_optimized`, `db_instance_needs_fb`, `db_global_needs_literal`,
  `db_element_not_declared`, `db_unknown_datatype`, `db_element_for_each`, `db_member_render`,
  `db_instance_name_render`. WARN — `db_for_each_matches_nothing`, `db_unknown_prog_lang`, `db_fdb_opc_ignored`,
  `db_member_duplicate`. (`generate` returns findings; `build` keeps the no-write-on-raw-FAIL guard.)
- **S3 — 300 `staging.py`** ✅ DONE (uncommitted) — `stg_no_io_sheet` (FAIL — replaced the `raise SystemExit`;
  `load_io_list` returns `([], matched)`); `stg_dup_signal_uid` (WARN — moved the GUI dup check into `_dup_findings`).
  `stage()` -> `(database, findings)`. The 4 GUI handlers accumulate staging + 520 findings and gate ONCE.
- **S4 — 400 + 510** (WARN-only, no FAILs) ✅ DONE (uncommitted): 400 `if_ioc_no_index`, `if_signal_not_mirrored`;
  510 `iotag_no_address`. `build_interfaces` -> `(database, findings)` (records + saves); `io_tags.project` swapped
  its `warnings` key for `findings` (pure projection, no record). Added **`core/run.py:render`** (gate minus halt)
  for the WARN-only projections; the GUI 400/510 call `run.render`.
- **S5 — 600** ✅ DONE (uncommitted): `diag_scl_template_missing` (WARN, phase 620); `diagnosis.build` ->
  `(database, findings)` (the last legacy tuple, errors/warnings were always empty; now records + saves);
  `diaglist_csv.project` +`findings:[]`; `diagnosis_scl.project` dict `warnings`->`findings`. GUI `run.render`s them.
- **S6 — cleanup/sweep** ✅ DONE: the cleanup landed incrementally (each chunk removed its own `if errors:` /
  `for w in warnings` block from `app_main.py`). Verified end state: `pipeline4/` has ZERO remaining
  `(errors, warnings)` tuple / `, warnings` unpack / `["warnings"]` read (only a historical comment in
  `datablocks.py`). Full 5-phase byte-parity re-run (all phases, one pass, vs pre-rollout `95d3dfb`): **0 diffs
  across 20 outputs** (9 GlobalDB XMLs + PLCTags 214 rows + DiagList_IO/Logic + the OPC SCL + 8 SSOT tables), only
  `validation_issues.csv` added. **The codebase is ready for phase 700.** (Open: 100/900 will read `validation_issues`
  as their backbone; `accept` [doc-mutating treatment] lands with 100.)

### Then the remaining phases (DESIGN §9)
**700 Hardware** (Stations + Modules — **its full design is already done**: see the `understand-700-hardware` workflow
output / the 700a-b-c plan: `domain/hardware.py` + `hardware_csv.py`, `hardware_stations`/`hardware_modules` tables,
`config.load_device_types_db` + `hardware_dir`; missing-DTD head = **FAIL** per the severity model, switch = WARN;
comma/no-BOM/CRLF format-2; parity vs current-PL3 `extract`, the frozen reference is DTD-drift-stale) ·
**800 Software** (8 builders + `InstanceDBs.csv` + `02_COM`) · **900 Coverage** · **100 Validation**.
Each: port → write its table → project to `BuilderData/` → parity → wire its GUI button.

## Locked decisions (don't relitigate)
- **Keying**: content-hash `uid` excluding volatile bits. **DB on disk**: top-level `Shared/Database/` folder.
- **Registry-derived signal fields**: computed by the **single evaluator** and **written back after 520** (not at
  staging — no drift; DESIGN §9 orders 520 before its consumers).
- **520 member order** is grouped-by-type (PL4's per-type element rows) — functional parity, not byte-identical
  (user accepted). **`db_blocks` table** holds per-DB attrs so the XML projection is a pure function of the DB.
- **Phase 400**: the `xlsx_edit` port + `insert_interface_sheets` are IN scope (not deferred). The per-type
  `interface_tagname` templates live in **`chain_reactions/interface_tagnames.csv`** (NOT re-added to signal_types).
  The `interfaces`/`interface_elements` split mirrors the `db_blocks`/`db_members` parent/child pattern.
- **No legacy management**: PL4 reads source docs fresh, never PL3 intermediates. Verbose naming.

## Parity tooling (reuse it)
The frozen `Shared/OutputTree` references are **STALE relative to PL3's CURRENT config** (a recurring trap — the
ImportReady XMLs predate `DiagnosticTags`/`PROFINET_NODES_*`; `IF_SORTER-01.xlsx` predates the `{db_element}`
resolution + has a dropped `IF_ENCODER_SPEED`). So: prefer **`IODatabase.csv`** (current for the signal fields)
and compare by **`source_cell`** (signals) or the **stable `plc_binding`/expression** (interface elements); when a
frozen output disagrees, check whether it's config drift before assuming a regression. The PL3 reference IODatabase
is `Shared/OutputTree/ProjectDocumentation/InformationDatabase/IODatabase.csv`. Pattern:
```python
from pipeline4.domain import staging, datablocks, interfaces
db,_sf = staging.stage(); db,_f = datablocks.build(db); db,_w = interfaces.build_interfaces(db)   # 300/520 now -> (database, findings)
pl4 = {r['source_cell']: r for r in db['signals'].rows if r.get('source_cell')}
# load IODatabase.csv by source_cell; compare (PL4 list-cell vs PL3 '|'-split, scalars direct)
```

## Gotchas
- **openpyxl turns a leading `=` into a formula** + drops formula caches + flattens dynamic arrays — that's WHY
  ph400's `insert_interface_sheets` needs `xlsx_edit` (ZIP/regex surgery), not a `load→save`. The standalone
  `IF_*.xlsx` (400c) CAN use openpyxl (PL3 does: copy + plug + save) — those files are documentation, not read
  back by a data_only reader except via the inserted sheets.
- The `Table.read_csv` is strict (ragged/dup-header/bad-JSON → located error). Config CSVs use `read_config_csv`
  (tolerant). Bool config columns need `_bool_default` (PL4's `_as_bool` reads a blank as False).
- Staging/build run **inline on the GUI thread** for now (a worker thread comes with the engine).
- Run/test from the `Pipeline4App` root. The Bash CWD sometimes resets to the repo root — `cd Pipeline4App` first.

## OP4 coordination
`Shared/PL4_OP4_coordination.md` briefs the OP-side session. The `BuilderData/` contract is co-designed: build
format-preserving first (byte-stable to PL3), evolve per-phase + verify. The 520 GlobalDB XML is the first landed
surface (byte-equivalent modulo member order). The interfaces dir is documentation, NOT a BuilderData surface.
