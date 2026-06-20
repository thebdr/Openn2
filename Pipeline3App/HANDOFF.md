# Pipeline3App — next-session handoff

Paste the fenced block below into a fresh session to continue the rebuild. `CLAUDE.md`
(architecture/status) and the memory index auto-load; the approved design + per-phase contracts
live in the plan at `~/.claude/plans/the-codebase-in-openn2-pipeline2app-rippling-canyon.md`
(§2 contracts, §10 Open2App contract + decisions).

---

```
Continue the Pipeline3App rebuild at C:\Source\Repos\_Openn2\Pipeline3App. First read
Pipeline3App/CLAUDE.md (authoritative architecture/status/gotchas — esp. the Phase 400 section)
and the approved plan ~/.claude/plans/the-codebase-in-openn2-pipeline2app-rippling-canyon.md
(§2 per-phase contracts, §9 Pipeline2 reference files = INTENT only, §10 Open2App contract).

STATUS: M1–M5 + M6 (Phase 100 Validation + M6b treatments) + Phase 400 Interfaces done, committed
on branch tia181920 (origin = github.com/thebdr/Openn2; HEAD ~2 ahead of origin — push when I ask).
Run the data-independent green gate first to confirm the baseline:
    cd Pipeline3App && for t in tests/unit/test_*.py; do python "$t" || break; done
The single database is the staged ctx.rows / Shared/OutputTree/.../IODatabase.csv; every downstream
phase consumes it.

CADENCE: build ONE phase FROM SCRATCH (Pipeline2App = reference for INTENT only, never port
verbatim) → unit-test (synthetic fixtures, tests/unit/_harness.py) → run on the real docs → STOP
for my review. A question is just a question (answer it; don't change code). Commit/push only when I ask.

START — two things, in order:
  (1) PHASE-400 MODIFICATION: ph400 inserts the generated interface tables as sheets into the I/O
      List (domain/interfaces.py::insert_interface_sheets). PREFIX those inserted sheet names with
      `IF_` (e.g. IF_SORTER-01). Update the interface unit tests + re-run on the real docs; stop for review.
  (2) PHASE 500 (Signals): read pipeline2/core/outputs.py + the §2 Phase-500 contract; build
      510 I/O Tags → io_tags_dir/PLCTags.xlsx = the resolved I/O signals PLUS the interface tags read
      from the inserted `IF_` sheets (interface cols `I/O Address Side 1` → logical address,
      `Signal Name Side 1` → tag name); and 520 Data Blocks → blocks_import_dir/*.db, rule-driven by
      config_project/input_docs/datablock_elements_rules.csv (any required_type present → add the
      element to db_name, creating the DB if absent). Reuse domain/identity (name_in_tagtable /
      name_in_db / tagtable / datablocks / plc_binding on ctx.rows). Run on the real docs, stop for
      my review after each.

THEN continue the remaining generators in NUMERICAL order, one phase at a time:
  600 Diagnosis → 700 Hardware → 800 Software → 900 (910 only). 920 deferred (needs Open2App's
  project text export).

HONOR (full detail in CLAUDE.md):
- Reuse the shared primitives: io/workbook (THE reader), registry/phase/context/app, core/config
  (OUTPUT_PATHS + out_path), io/csv_tables, domain/identity, ctx.rows. Each phase self-registers in
  pipeline3/phases/ and is imported from phases/__init__.py.
- Open2App contract is sacred: generators write ONLY under
  Shared/OutputTree/TiaPortalProjectInterface/BuilderData/ (hardware_dir, blocks_creation_dir,
  blocks_import_dir, io_tags_dir) — byte-stable. ProjectDocumentation/* and Reports/* are NOT imported.
- GUI-only buttons are DEFERRED to the GUI milestone (M11): the "Open …" buttons (530 Open IO Tags,
  540 Open Data Blocks Folder, …) cannot run headlessly — build the GENERATION engine + register
  the buttons, leave opens/popups GUI-era.
- DTD params: col-5 applied by Open2App (NEVER written) vs col-6/col-7 + I/O-List col-AG (written;
  AG overrides, last). Comma CSV on write, sniff on read. Tag/device strings (=S1,+MS1,-S67001) are
  text (data_type="s") so a leading =/+/- isn't a formula.
- i18n EN+IT for operator-facing messages; LogEntry model (id = code-traceable "<phase>-<type>",
  per-FAIL uid, links Sheet!Cell with the workbook on .doc).
- Green gate = the data-independent unit tests; data-dependent artifacts follow review-then-freeze
  under tests/golden/ (pattern: tests/unit/test_golden_validation.py, --freeze).

RUN ON REAL DOCS — gotcha: the main pipeline HALTs at Fill (200) (~18 unresolved index entries).
Fill edits the SOURCE in place, so the source is already populated — stage directly, skipping the halt:
    import pipeline3.phases
    from pipeline3 import app
    from pipeline3.context import PipelineContext
    ctx = PipelineContext.create(profile="main"); ctx.completed.add(200); app.run_phase(ctx, <n>)
Real docs: Shared/DocumentsValidationData/Passing/.
```
