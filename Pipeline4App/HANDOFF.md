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
- **Branch `pl4`**. **8 OF THE 9 GENERATIVE PHASES ARE BUILT** — 300 + 520 + 400 + 510 + 600 + 700 + 800 + 900 +
  **100 (Validation)** + the severity rollout S1–S6, each parity-verified vs PL3; every built GUI button runs
  for real. **ph200 (Documents Fill Out) is NOT built** — the pipeline's 2nd phase that turns a RAW I/O List
  into a classified one (§6 script_type, §7 index, §8 diag cabinet/bit, DiagnosisBlocks). PL4 staging READS
  those fields; it does not COMPUTE them, so **PL4 currently requires a PRE-FILLED I/O List**. Building ph200
  (CSV-driven) is **STEP 4** — see its section below. (Also out of scope by user decision: validation **150**
  diagnosis-slot + the **`accept`** treatment.)
- **THE GUI PORT IS THE ACTIVE EFFORT** — the live tracker + locked decisions are in **`GUI_PLAN.md`**.
  **M0 (worker thread + registry + notebook + Run-all) · M1 (structured clickable log) · M2 (Findings panel) ·
  M3 (Database Explorer, in-memory SQLite) · M4 (Run-all live progress/halt + sub-phase chevron dropdowns,
  REWORKED to the operator oracle `ButtonsLayout.xlsx`: full greyed-deferred button set + sub-buttons that RUN
  THEIR SUB-PHASE via `handler(only=n)` + wired Open buttons + equal-width/width-matched bar) · STEP 1 i18n
  (EN/IT, first-class - **the POINT is the LOGS**: `domain/validation/messages.py` bilingual [EN verbatim +
  IT from PL3], a finding's detail built in the AMBIENT `messages.active_lang(lang)` so the validation log +
  `.txt`/`.html` reports localize [PL3-faithful: uid hashes the localized detail]; plus the chrome via
  `core/i18n.py` + registry `name_key`/`label_key` + the Lang toggle, persisted) are DONE.** NEXT (the
  planning side-chat order): **STEP 2 DONE** (300 staging granularity — `staging.stage()` split into
  `stage_iolist()` [oracle 310 Stage I/O List] + `annotate_cematrix()` [oracle 320 Stage C&E Matrix], the GUI
  300 dropdown wired [310 -> partial, 320/header -> full], byte-identical `signals.csv`). **STEP 3 DONE**:
  **M5 Files tab** (view-only: the 3-section tree + CSV/xlsx grid + text pane + Open-externally, ttk-only,
  `gui/files_view`+`files_panel`+`extedit`) · **M6 Project Manager** (`pipeline4/project/` state+project, a
  toolbar [Project ▾] New/Open/Recent/Set-root/Close + title indicator + auto-reopen; routed by
  `config.use_project`) · **M0b chrome remainder** (darktitle + the full light/dark re-theme - landed in
  STEP 1). NEXT: **STEP 4** ph200 Documents Fill Out (CSV-driven, the LAST backend effort; confirm its 4 open
  decisions first).
- **GIT STATE:** local **`pl4`** is at **`c08d4d1`** and **PUSHED** — `origin/pl4` synced through it. Recent
  milestones: **`c08d4d1`** GUI M6 Project Manager (STEP 3 complete) · **`a5b8cb6`** M5 Files tab · **`5da675c`**
  STEP 2 (the 310/320 staging split) · **`7473ace`** STEP 1 (i18n + Monaspace font + dark/light theme
  compatibility). Standing directive: **push on every major milestone** (Claude decides what
  counts), so origin tracks the latest milestone without asking. M4 base at `243b695`, M0–M3 at
  `d623509`/`3ec6996`/`47addb9`/`fbac770`. `config_project/user_input/*.csv`
  (the runtime treatment registry) is gitignored (matching PL3). The repo root also carries unrelated pre-existing
  edits (Openn3App, Pipeline3App config, Shared) — NOT ours; leave them.
- **Gate: 38 test FILES green** (data-independent; `test_project.py` added at M6; `test_gui_files.py` added at M5; `test_i18n.py` +
  `test_validation_i18n.py` + `test_app_config.py` + `test_gui_fonts.py` added at STEP 1; STEP 1 also added the **always-plural** cosmetic [no `(s)`/`/i` hedge],
  a **log-viewer Font dropdown** 10/12/14 [`LogView.set_font_size`, persisted], and the **app-wide Monaspace Neon
  Var font at size 13** [`gui/fonts.py` + `theme.apply_theme`; M0b fonts done]). Run from `Pipeline4App/`:
  `for t in tests/unit/test_*.py; do python "$t"; done`. The GUI is a manual `python launch_gui.py` check (no
  headless GUI tests; each GUI milestone unit-tests its pure logic + a construction smoke).
- **START THE NEXT SESSION HERE → `GUI_PLAN.md`** (the live GUI tracker). **M0–M6 + STEP 1 i18n + STEP 2 +
  STEP 3 done** — the GUI port is feature-complete bar polish (M7): M5 Files tab + M6 Project Manager
  (`pipeline4/project/`: state+project, a toolbar [Project ▾] + title indicator + auto-reopen, routed by
  `config.use_project`) + M0b chrome remainder all landed. **NEXT = STEP 4** ph200 Documents Fill Out — the
  LAST backend effort (PL4 currently requires a PRE-FILLED I/O List; ph200 computes script_type/index/diag).
  Confirm its 4 open decisions before building. The Run-all **stage-once** optimization stays deferred
  (optional); **M7 polish** (theme/size persistence, log-to-file) is the remaining GUI tail. See the
  `## phase 200 (Fill)` section below.
- **SEVERITY model (COMPLETE — historical detail; the rollout S1–S6 is done).** Taxonomy (`core/severity.py`):
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
  `validation_issues.csv` added. PARITY RULE held every chunk (report CONTAINER + render call only; 0-byte diff).
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
- The SSOT **`Database/`** now holds **14 tables**: `signals` + `diagnosis_cabinets` (300) · `db_blocks`/`db_members`/
  `instance_dbs` (520) · `interfaces`/`interface_elements` (400b) · `diagnosis_entries` (600) · `hardware_stations`/
  `hardware_modules` (700a) · `software_blocks`/`software_block_members` (800a) · `coverage` (900) · `validation_issues`.
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
21. `7c2fa17` **severity S5** — retrofit 600 (`diagnosis.build`/`diaglist_csv`/`diagnosis_scl` → findings; the last legacy tuple gone)
22. `7f84320` **severity S6** — rollout complete (full 5-phase byte-parity re-run = 0 diffs vs pre-rollout `95d3dfb`)  **← origin/pl4 PUSHED head**
23. `ddad2fa` **phase 700a** — Hardware build: `config` DTD loader + `domain/hardware.py` (`hardware_stations`/`hardware_modules` + `build`); parity vs PL3 `extract` exact
24. `76afb75` **phase 700b** — `domain/hardware_csv.py` (format-2 `Stations.csv`/`Modules.csv`) + the GUI "700" button; CSVs byte-identical to PL3
25. `be017ad` **phase 800a** — `domain/blocks/` spine + engine + the 00/06/07 builders -> `software_blocks`/`software_block_members` -> CreationInfo CSVs; parity vs PL3 exact
26. `30eead2` **phase 800b** — the 5 complex builders (02/03/04/05/08) in `builders.py` + 8 tests; 7 CreationInfo CSVs byte-identical to PL3 + all 5 builders table-identical (03 at table level, PL3 emits it as XML)
27. `e153843` **phase 800c** — NEW `domain/blocks/xml_emit.py` (03 FC XML) + `engine.write_com_db`/`write_instance_dbs` + `engine.project` 03-CSV-drop + the GUI "800" button + 6 tests; all three byte surfaces (03 FC XML / 02_COM.xml / InstanceDBs.csv) byte-identical to PL3  **← origin/pl4 PUSHED head**
28. `3726a01` **phase 900** — NEW `domain/coverage.py` (the `coverage` SSOT table + ORPHAN/UNPLACED WARN findings) + `config.coverage_dir` + the GUI "900" button + 9 tests; reads the SSOT tables (user decision); real-data ORPHAN=0/UNPLACED=0, tags match io_tags exactly  **← origin/pl4 PUSHED head**
29. `a74db5e` **phase 100a** — the validation reporting spine: NEW `core/model.py` (InfoBlock+Cmp) + `core/finding.py` extended (4 optional render fields) + `domain/validation/address.py` + `io/render.py` (rich txt+HTML, Cmp + dual-links) + `config.validation_report_dir` + 6 tests  **← origin/pl4 PUSHED head**
30. `c0c4178` **phase 100b** — the 110 (I/O List) + 120 (C&E) standalone validators: NEW `domain/validation/` messages.py (verbatim EN templates) + model.py (the Finding factory + helpers) + iolist.py + matrix.py + 9 tests; real-data sanity clean (110 273 PASS/0 FAIL, 120 24 refs/0 FAIL)  **← origin/pl4 PUSHED head**
31. `e2c0f66` **phase 100c** — the 130/140 cross-checks: NEW `domain/validation/ce_refs.py` (the io/ce indexes + the C&E refs reader) + `crosscheck.py` (the two-search 130 + the 140 decision tree, Cmp + dual-links) + the cross-check message slugs + 6 tests; real-data sanity clean (130 48 PASS/0 FAIL, 140 20 PASS/4 WARN/0 FAIL)  **← origin/pl4 PUSHED head**
32. *(uncommitted)* **phase 100d** — the orchestrator + GUI + reports + PARITY (the rebuild's final chunk): NEW `domain/validation/phase.py` (`run_validation`: 110-140 -> record the issues -> the 4 reports) + the GUI "100" button + 1 test; **PL3 parity EXACT: 596/596 findings, 0 diffs** over the real docs (`scratchpad/parity_100.py`)

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
**The SEVERITY ROLLOUT (S1–S6) is COMPLETE; PHASE 700 (Hardware) is COMPLETE** (700a build `ddad2fa` + 700b
projection uncommitted): `domain/hardware.py` (`hardware_stations`/`hardware_modules` + `build`, `hw_device_not_in_dtd`
FAIL / `hw_switch_not_in_dtd` WARN) + `domain/hardware_csv.py` (the format-2 `Stations.csv`/`Modules.csv` projection)
+ the GUI "700" button (stage -> build -> project). PARITY vs current PL3 `extract`/`_format2` over the same staged
rows: **9 stations + 18 modules, 0 field mismatches; Stations.csv (1145B) + Modules.csv (1896B) byte-identical**.
**PHASE 800 (Software) COMPLETE** (`.xlsm` operator shells DEFERRED per the locked decision; CSVs built directly).
**800a (`be017ad`):** `domain/blocks/` package + the 3 simple builders (00/06/07) -> `software_blocks`/
`software_block_members` tables + `project` -> CreationInfo CSVs. **800b (`30eead2`):** the 5 complex builders
(02/03/04/05/08), verbatim from PL3 except `_as_list` for the list cells (areas_desc keeps empties for the positional
`_area_descriptions`) + `source_row` (was `_source_row`) + 05's `|`-joined NetworkComment. **800c (uncommitted):**
NEW `domain/blocks/xml_emit.py` (the **03** `SW.Blocks.FC` direct emit, AND->Coil FlgNet, BOM/CRLF) + `engine.project`
wired to ship 03's XML to `blocks_import_dir` and **drop its CSV** + `engine.write_com_db` (the **02_COM** safe F_DB,
reusing `datablock_xml.db_xml`; members = `DB_CONSTANTS` + the distinct `02_COM.{db_element}` cumulatives) +
`engine.write_instance_dbs` (**InstanceDBs.csv** = builder `instanceOf-*` cells FIRST, then the 520 `instance_dbs`
table, deduped; plain UTF-8 no BOM) + the GUI **"800" button** (`_run_software`: stage -> 520 -> build -> project ->
com -> instances). PARITY over the same 269 staged rows: **all three byte surfaces byte-identical to PL3** - 03 FC XML
(38018 B), 02_COM.xml (9578 B, F_DB OPC-locked, 15 members), InstanceDBs.csv (8569 B, 102 entries); the 7 non-03
CreationInfo CSVs stay byte-identical. Tests +6 (22 total in `test_blocks.py`); gate 191. Parity oracle:
`scratchpad/parity_800c.py` (+ `parity_800b.py` re-run as a regression).
**PHASE 900 (Coverage/910) COMPLETE (uncommitted):** `domain/coverage.py` (port of PL3's) reading the **SSOT
TABLES** (user decision - PL4 exports are byte-stable projections, so coverage over the tables == over the
artifacts; the one gap = hand-filled interface Side-2, documented). The per-signal trace is **persisted as a
`coverage` SSOT table** + ORPHAN/UNPLACED emitted as **WARN findings** into `validation_issues` (both user
decisions), `run.render`ed. `collect_outputs(database)` builds the emitted sets from signals/db_members(+02_COM)/
diagnosis_entries/interface_elements/interfaces/hardware_*/software_block_members; `attribute`/`find_unplaced`/
`render_*` port near-verbatim (reads the `type` cell + stored `plc_binding`). `config.coverage_dir()`
(ProjectDocumentation/Reports) + the GUI **"900" button** (`_run_reporting`: build the full SSOT then
coverage.build + project). **VERIFICATION (real data; documentation, byte-parity NOT the bar): 269 rows, ORPHAN=0,
UNPLACED=0, tags == io_tags exactly (202==202).** Tests +9 (`test_coverage.py`); gate 200. Verify:
`scratchpad/verify_900.py`. **920 (TIA coverage) stays deferred.**
**PHASE 100 (Validation) IN PROGRESS — the LAST phase, chunked 100a/b/c/d. USER DECISIONS:** reproduce PL3's
**rich txt+HTML reports** (the aligned line + cross-check Cmp + dual-workbook links); land **110+120+130+140 now,
DEFER 150** (needs relocating `diag_container_check` + populating `diag_block_name` at staging → touches the
locked 300 parity); **DROP `accept` entirely**. 110/120 read the RAW workbooks; 130/140 read the SSOT; the phase
**never halts** (`run.render`); the EN `v_*` message text is ported verbatim into each finding `detail`.
**100a DONE (uncommitted):** the reporting spine — `core/model.py` (InfoBlock+Cmp) + `core/finding.py` extended
(4 OPTIONAL render fields `location2`/`doc2`/`info`/`cmp`, not hashed/persisted, Finding stays lean+hashable) +
`domain/validation/address.py` (verbatim) + `io/render.py` (the rich report renderer, verbatim port of PL3's:
banners, per-phase width auto-fit, the Cmp + dual-link, txt + no-wrap HTML) + `config.validation_report_dir()` +
the two stems. Tests +6 (`test_validation_render.py`); gate 206. PARITY NOTE: PL4 `finding._norm` doesn't
lowercase (PL3's does), so the 100 parity oracle compares finding TUPLES `(phase,type,norm(location),norm(detail))`
with a matching norm on both sides, NOT raw uids (PL4's registry is project-local, so cross-PL3 uid parity is
not needed). **100b DONE (uncommitted):** `domain/validation/` messages.py (EN `v_*` templates verbatim +
`msg`) + model.py (the `entry()` Finding factory + key/addr/raw/fld_text/info_for_row + the fuzzy
levenshtein/first_match + cmp_detail for 130/140) + **iolist.py (110)** + **matrix.py (120)** (verbatim ports
reading the RAW workbooks via `io/workbook`, `params`/`get_param` instead of ctx). Tests +9
(`test_validation_standalone.py`, hermetic via a StubView + monkeypatched openers); gate 215. Real-data sanity
(clean Passing fixtures): 110 273 row_ok PASS / 0 FAIL, 120 24 refs / 0 FAIL (the unit tests prove the checks
fire on bad input). **100c DONE (uncommitted):** `ce_refs.py` (`build_io_index`/`build_io_addr_index` over the
signals rows + `read_ce_refs` over the C&E via `matrix_params` + `build_ce_index`) + `crosscheck.py` (130 = the
two independent searches by ADDRESS + by FLD -> cem_addr_*/cem_fld_*; 140 = the decision tree typed/untyped ->
iol_cem_* with the Cmp + dual-link; reads the `type` cell + `validation_params.crosscheck.*`) + the cross-check
message slugs. Tests +6 (`test_validation_crosscheck.py`, hermetic via synthetic refs + a synthetic signals DB);
gate 221. Real-data sanity (clean Passing): 130 48 PASS/0 FAIL, 140 20 PASS + 239 SKIP + 4 missing_plain WARN/0 FAIL.
**100d DONE (uncommitted) — THE FINAL CHUNK:** `domain/validation/phase.py` `run_validation(database, params)`
runs 110->120->130->140, records the treatable issues into `validation_issues` + saves, applies the registry
READ-ONLY for the report's effective severity, interleaves per-(sub)phase banners, and writes the 4 reports
(`documents_validation_report`/`_errors` x txt/html). The GUI **"100" button** (`_run_validation`: stage ->
run_validation -> `run.render` the issues; never halts). Test +1 (`test_validation_phase.py`); gate 222. **PARITY
EXACT: PL4 596 findings == PL3 596, 0 diffs** in the tuple `(phase, type, norm(location), norm(detail))` across all
4 validators over the real docs (`scratchpad/parity_100.py`, PL3 fed PL4's staged rows). Real-data counts: 341
PASS / 239 SKIP / 12 INFO / 4 WARN / 0 FAIL.

## NEXT BACKEND SESSION — phase 200 (Fill / classification), built CONFIGURABLE (user-flagged)
**Gap:** PL4 never built **phase 200** (PL3's `domain/iolist_diag/` populator). PL4 reads the source I/O List
fresh and ASSUMES it arrives pre-filled (`script_type`/`index`/`diag_cabinet`/`diag_bit` present); if a raw doc
isn't pre-classified, staging has nothing to read. PL3 COMPUTES those in code: `script_type.py` (the §6
In/Out/Node type ladder — **hard-coded conditions**, the pain point), `index_assign.py` (§7 per-family
contiguous index), `diag_alloc.py` (§8 cabinet/bit, idempotent + stable IDs), `blocks.py` (the DiagnosisBlocks
sheet), written surgically in place via `io/xlsx_edit` (which PL4 already has).
**The opportunity (user's directive):** the hard-coded classification makes adding/changing a type hard — make
it **CSV-DRIVEN**. A rules CSV (condition → resulting script_type) replaces the §6 ladder so a new type is a
config edit, not code.
**Decisions for that session (don't pre-bake):**
1. **CSV home:** a dedicated `config_project/input_docs/script_type_rules.csv` vs extend `signal_types.csv`
   (the user is open to either). A dedicated rules CSV keeps the type SCHEMA (signal_types) separate from the
   CLASSIFICATION rules — likely cleaner, but confirm.
2. **The rule grammar (the crux):** how to express a condition over the raw IoList columns (In/Out/Node, the
   description keywords, the ENC/FA/RES/Z/R special cases). Candidate: reuse the existing predicate DSL from
   `dbtemplate.py` (`numeric()`/`=`/`!=`/`~/re/`/`in[…]` + `and`/`or`/`not`/`()`) — already ported, tested, and
   familiar — evaluated top-down (first matching rule wins), like the §6 ladder.
3. **Write target:** mutate the source I/O List in place (PL3's way, via `io/xlsx_edit`) vs compute the fields
   into the **SSOT `signals` table at staging** (PL4-idiomatic — every datum in the DB, no doc mutation). The
   SSOT route fits PL4's thesis; the user may also want the filled doc as an operator artifact. Likely: compute
   into the SSOT, with an OPTIONAL surgical write-back as a projection.
4. **Scope:** classification first (script_type) vs the full ph200 (also `index` + diag cabinet/bit allocation).
   index/diag are the larger, stateful parts (PL3's idempotent stable-ID allocation).
**Parity oracle:** PL3's populator over the same raw doc → compare the computed script_type/index/diag per row.

## 8 OF 9 GENERATIVE PHASES BUILT (ph200 Fill NOT built) — ACTIVE EFFORT: the GUI port (see `GUI_PLAN.md`)
The 8 generative phases (300/520/400/510/600/700/800/900/100) + the S1–S6 severity model are DONE, each
parity-verified vs PL3; every built GUI button runs for real. **ph200 (Documents Fill Out) is NOT built** — PL4
requires a pre-filled I/O List until STEP 4 builds it (CSV-driven; see the `phase 200` section above). **The
active effort is the GUI port — the plan + locked decisions are in `Pipeline4App/GUI_PLAN.md`** (replicate PL3's
GUI + add the SSOT-native Findings panel, Database Explorer [in-memory SQLite], and Run-all/live-progress; NEW
features first; **EN/IT i18n is a first-class shipped feature — STEP 1, DONE**). **M0 (foundations) DONE (uncommitted):** the
`gui/phases.py` registry + the worker thread/queue-drain pump + a basic Run-all + the notebook scaffold (single
-phase runs no longer freeze the window). **M2 (Findings panel) DONE (uncommitted):** a Treeview tab over
`validation_issues` ⋈ the treatment registry with right-click 1-click treatments. **M3 (Database Explorer)
DONE:** a SQL console tab over the SSOT (in-memory SQLite, `json_extract` + cross-table JOINs + sample queries;
loads all 14 tables). **M1 (structured clickable log) DONE (uncommitted):** the LogView consumes
`render_records` - clickable Sheet!Cell → Excel, errlink → treat, Show-PASS/SKIP. **NEXT: M4** (Run-all +
sub-phase dropdowns) — then M5 Files, M6 Project, M0b chrome. (The detailed GUI tracker is `GUI_PLAN.md`.) **Deferred by user decision** (not blockers): validation **150** (needs a
staging change touching the locked 300 parity) + the **`accept`** doc-mutating treatment (dropped). Possible
future polish: the GUI grid/files/threading; a CLI; the engine (a real phase registry + worker thread); the
transitional gate-reconcile-once-per-run fix. See `DESIGN.md` for the locked decisions.

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
