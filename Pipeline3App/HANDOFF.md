# Pipeline3App — next-session handoff (generators, M7+)

Paste the block below into a fresh session to continue the rebuild. The next session auto-loads
`CLAUDE.md` and the memory index, so this stays focused on the task, cadence, and the one gotcha.

---

```
Continue the Pipeline3App rebuild at C:\Source\Repos\_Openn2\Pipeline3App. First read
Pipeline3App/CLAUDE.md and the approved design plan at
~/.claude/plans/the-codebase-in-openn2-pipeline2app-rippling-canyon.md (per-phase contracts = §2,
the Open2App import contract = §10, the Pipeline2 reference files = §9).

STATUS (committed on branch tia181920, origin = github.com/thebdr/Openn2; data-independent gate green):
M1–M5 foundation/fill/staging, M6 Phase 100 Validation, M6b treatment registry, M7 Phase 400
Interfaces (generation + signal mirroring + interface_tagname/Expression split + BOOL 2-byte-block /
WORD-row layout + the lossless insert_interface_sheets). Phases 100 and 400 are COMPLETE. The single
database is Shared/OutputTree/.../IODatabase.csv (loaded as ctx.rows); every downstream phase consumes it.

NEXT — build the remaining generators in NUMERICAL order, ONE phase at a time:
  500 Signals → 600 Diagnosis → 700 Hardware → 800 Software → 900 Reporting
(910 only; 920 TIA-project coverage is deferred/future — it needs Open2App's project text export.)

CADENCE (unchanged): build one phase FROM SCRATCH (Pipeline2App is a reference for INTENT only —
never port verbatim) → run it on the real docs → STOP for my review before starting the next phase.

HONOR (details in CLAUDE.md):
- Reuse the shared primitives: io/workbook (the one reader), registry/phase/context, core/config
  (OUTPUT_PATHS + out_path), io/csv_tables, domain/identity, the staged ctx.rows. Each phase
  self-registers in pipeline3/phases/ and is imported from phases/__init__.py.
- The Open2App contract is sacred: generators write ONLY under
  Shared/OutputTree/TiaPortalProjectInterface/BuilderData/ (hardware_dir, blocks_creation_dir,
  blocks_import_dir, io_tags_dir) — keep those subpaths byte-stable. ProjectDocumentation/* and
  Reports/* are intermediate / NOT imported by Open2App.
- DTD params: col-5 is applied by Open2App (NEVER written) vs col-6/col-7 + I/O-List col-AG
  (written; AG overrides, last). Comma CSV on write, sniff on read. Tag/device strings (=S1, +MS1,
  -S67001) are text (data_type="s") so a leading =/+/- isn't treated as a formula.
- i18n (EN+IT, the STRINGS table) for any operator-facing message; the log model is LogEntry (id =
  code-traceable "<phase>-<type>"; per-FAIL uid; links are Sheet!Cell, no workbook name).
- Data-independent unit tests (synthetic fixtures via tests/unit/_harness.py) are the green gate;
  data-dependent artifacts follow review-then-freeze under tests/golden/ (parity test pattern:
  tests/unit/test_golden_validation.py, --freeze).
- A question is just a question (answer it; do not change code). Commit/push only when I ask.

RUNNING ON THE REAL DOCS — gotcha: the main pipeline HALTs at Fill (200) because the template has
18 unresolved index entries. The source I/O List is already filled in place, so stage directly:
    import pipeline3.phases
    from pipeline3 import app
    from pipeline3.context import PipelineContext
    ctx = PipelineContext.create(profile="main"); ctx.completed.add(200); app.run_phase(ctx, <n>)
(skips the Fill halt; 300 stages the filled source into ctx.rows). Real docs:
Shared/DocumentsValidationData/Passing/.

PHASE QUICK-MAP (plan §2 contracts + §9 Pipeline2 references — INTENT only):
  400 Interfaces — DONE (domain/interfaces.py + phases/p400_interfaces.py): per-IOC generation +
      signal mirroring (I/O List "Interface Mapping" col AH, the interface_tagname / Expression
      split, +DIAG, BOOL 2-byte-block / WORD-row byte layout) + the lossless insert_interface_sheets.
      The 430 "Custom Interface…" popup is GUI-era (M11); its primitive interfaces.generate_one
      exists. interface_tagname lives in signal_types.csv + all three rule CSVs; swp_cabinet is
      imported at staging. See the Phase-400 section of CLAUDE.md for the full contract.
  500 Signals (req 300): 510 Generate I/O Tags → io_tags_dir/PLCTags.xlsx; 520 Generate Data Blocks
      → blocks_import_dir/*.db, RULE-DRIVEN by config_project/input_docs/datablock_elements_rules.csv
      (when any required_type is present, add the element to db_name, creating the DB if absent).
      Ref: pipeline2/core/outputs.py.
  600 Diagnosis (req 300; DiagnosisBlocks present from Fill): 610 Generate Diag List → diagnosis_dir/
      DiagList_IO.csv + DiagList_Logic.csv (diagnosis_columns.csv, diagnosis_logic_rules.csv);
      620 Generate Diag Software Blocks — fill the OPC SCL template (06_Diagnostic for OPC.scl) →
      blocks_import_dir/Diagnostic_for_OPC.scl. Ref: pipeline2/diagnosis/diagnostic_opc.py + diagnosis_rules.py.
  700 Hardware (req 300): 710 Stations + 720 Modules (one extract) → hardware_dir/Stations.csv +
      Modules.csv (format-2). A head not in the DeviceTypesDatabase is an ERROR (WARNING for switches).
      Ref: pipeline2/core/hardware.py.
  800 Software (req 300): 810 Empty Shells .xlsm (CreationInfo/SoftwareBlocks.xlsm, $<mode> in B2:
      keep/fill/override) FIRST; 820 Blocks — read the shell: an override sheet IS the CSV (emit
      straight, skip the builder), keep/fill run the builder → blocks_creation_dir/CreationInfo/<NN_Name>.csv;
      830 Instances → CreationInfo/InstanceDBs.csv. Ref: pipeline2/blocks/*, block_templates.json.
  900 Reporting: 910 Pipeline Coverage Report → coverage_report (Reports/io_project_coverage_report.{csv,txt});
      every signal lands somewhere; flag ORPHAN / UNPLACED MEMBER. 920 = deferred/future.

START NOW WITH PHASE 500 (Signals): read pipeline2/core/outputs.py and the §2 Phase-500 contract,
propose the approach, then build 510 (I/O Tags → io_tags_dir/PLCTags.xlsx) and 520 (Data Blocks →
blocks_import_dir/*.db, rule-driven by datablock_elements_rules.csv), run on the real docs, and stop
for my review. Reuse domain/identity (name_in_tagtable / name_in_db / tagtable / datablocks already on
ctx.rows) and the signal_types catalogue (tag_name / db_element / db_names / tagtable_name).
```
