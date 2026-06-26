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
- **Branch `pl4`**. **Phase 400 is COMPLETE** (300 + 520(a/b/c) + 400a/b/c/d/e done). **Latest PUSHED/committed head
  is `5bc4aca` (400d); everything else this session is UNPUSHED** — push when the user asks. **400e is implemented
  but UNCOMMITTED** (in the working tree).
- **Gate: 107 tests green** (data-independent, was 102 + the 5-case 400e block in `test_interface_xlsx.py`). Run
  from `Pipeline4App/`: `for t in tests/unit/test_*.py; do python "$t"; done`
- **400e landed** (`interface_xlsx.insert_interface_sheets` — the lossless IF_ insertion + Excel-independent
  address-cache seed + `freeze_arrays`; GUI "400" runs it gated). **Resume at the next phase (510 or 600)** below.
- The SSOT **`Database/`** now holds **6 tables**: `signals` (300) · `db_blocks`/`db_members`/`instance_dbs`
  (520) · `interfaces`/`interface_elements` (400b). It saves to `Shared/Database/` (untracked generated artifacts).

### Commits this session (oldest → newest)
1. `407ed07` staging direct fields — positional node ranges (`I_/Q_startByte/endByte`) + `IsSorterArea`
2. `dfd29ac` **520a+520b** — the `dbtemplate` engine (render + for_each DSL) + `datablocks.generate` over the
   registry → `db_members`/`instance_dbs` + the **write-back** (`name_in_db`/`datablocks`/`plc_binding` onto signals)
3. `4483f0e` **520c** — `datablock_xml.project` (the GlobalDB-XML projector) + the `db_blocks` table + GUI "500"
4. `2ba9462` **400a** — `interface_tagname` (per-type templates relocated → `chain_reactions/interface_tagnames.csv`)
5. `28aa9ff` **400b** — the `interfaces` + `interface_elements` tables (mirror set + byte layout)
6. `11cd5e7` **400c** — the `IF_*.xlsx` projection (`interface_xlsx.project`, openpyxl)
7. `5bc4aca` **400d** — `pipeline4/io/xlsx_edit.py` (the surgical ZIP/regex writer) + the 14-test suite
8. (UNCOMMITTED) **400e** — `insert_interface_sheets` (the lossless IF_ insertion + address-cache seed)

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

## What's NEXT (in order)
1. **The `+DIAG` auto-mirror** (the lone open phase-400 item) — needs the per-type **`in_diag`** (stripped from PL4
   signal_types → ph600). `collect_mirror_set` already has the guard; relocate `in_diag` (with ph600, or as a small
   ph400 follow-up, verifying vs PL3 `signal_types`) then the SORTER+DIAG-02 auto-mirror lights up. Until then a
   `+DIAG` interface gets only its `interface_mapping` mirrors.
2. **510 I/O Tags** — reads the now-inserted IF_ sheets (Signal Name Side 1 + the seeded I/O Address Side 1) +
   the resolved I/O signals → `PLCTags.xlsx`. The 400e seed makes the interface addresses readable without Excel.

## Then the other phases (DESIGN §9 order `… 520 → 600 → 400 → 800 → 900 → 100`; 700/510 also open)
510 I/O Tags (reads the inserted IF_ sheets) · 600 Diagnosis (the unified DiagList + **tristate** to IMPLEMENT;
relocates `in_diag`/`diag_logic`/`diag_desc`/`tristate_desc`) · 700 Hardware (Stations/Modules) · 800 Software
(8 builders + `InstanceDBs.csv` + `02_COM`) · 900 Coverage · 100 Validation. Each: port → write its table →
project to `BuilderData/` → parity → wire its GUI button.

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
db = staging.stage(); db,_e,_w = datablocks.build(db); db,_w = interfaces.build_interfaces(db)
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
