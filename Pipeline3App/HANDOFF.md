# Pipeline3App — next-session handoff

Paste the fenced block below into a fresh session to continue the rebuild. `CLAUDE.md`
(architecture/status) and the memory index auto-load; the approved design + per-phase contracts
live in the plan at `~/.claude/plans/the-codebase-in-openn2-pipeline2app-rippling-canyon.md`
(§2 contracts, §10 Open2App contract + decisions).

---

```
Continue the Pipeline3App rebuild at C:\Source\Repos\_Openn2\Pipeline3App. First read
Pipeline3App/CLAUDE.md (authoritative architecture/status/gotchas — esp. the Phase 500/600/700
sections + Conventions & gotchas) and the approved plan
~/.claude/plans/the-codebase-in-openn2-pipeline2app-rippling-canyon.md
(§2 per-phase contracts, §9 Pipeline2 reference files = INTENT only, §10 Open2App contract).

STATUS: M1–M6 + M6b + Phase 400 Interfaces + Phase 500 Signals + Phase 600 Diagnosis + Phase 700
Hardware done, committed on branch tia181920 (origin = github.com/thebdr/Openn2; HEAD ahead of
origin/tia181920 — push when I ask). Latest commits: 41612cf (Phase 700), d2dfc17 (Phase 600),
ed604a4 (Phase 500). The single database is the staged ctx.rows / Shared/OutputTree/.../IODatabase.csv;
every downstream phase consumes it.

Run the data-independent green gate first to confirm the baseline:
    cd Pipeline3App && for t in tests/unit/test_*.py; do python "$t" || break; done
NOTE: test_golden_validation.py is DATA-DEPENDENT (it regenerates the phase-100 reports from the
real docs and compares the frozen golden); it FAILs (and the `|| break` loop stops there) when the
real I/O List legitimately changed — confirm the drift is only the intended doc edit, then re-freeze:
    python tests/unit/test_golden_validation.py --freeze
The other suites are the data-independent gate (currently 20/20).

CADENCE: build ONE phase FROM SCRATCH (Pipeline2App = reference for INTENT only, never port
verbatim) → unit-test (synthetic fixtures, tests/unit/_harness.py) → run on the real docs → STOP
for my review. A question is just a question (answer it; don't change code). Commit/push only when I ask.

START — PHASE 800 (Software), the most complex generator. Read pipeline2/blocks/* for INTENT
(block_templates.py, block_builders.py, softwareblocks.py, blockshells.py) + the §2 Phase-800
contract. Build in order, STOP for review after each sub-phase:
  810 Generate Empty Shells .xlsm → blocks_creation_dir/CreationInfo/SoftwareBlocks.xlsm — one sheet
      per block template, carrying the `$ <mode>` directive (keep / fill / OVERRIDE) in B2. Generated
      /refreshed FIRST so 820 can read it.
  820 Generate Blocks — reads the shell first: an OVERRIDE sheet *is* the CSV data (emit <NN_Name>.csv
      straight from the sheet, skipping the Python builder); keep/fill run the builder logic →
      blocks_creation_dir/CreationInfo/<NN_Name>.csv (filename DROPS the TEMPLATE--vX.Y-- prefix).
  830 Generate Instances → CreationInfo/InstanceDBs.csv (the non-empty instanceOf-<FB> @-values;
      cols Name,InstanceOf,Number,Folder).
  840/850 (Open shells / Open generated-blocks folder) are GUI-era (M11) — register, defer.
  Reuse domain/identity (name_in_db / name_in_tagtable / matrix_areas on ctx.rows); inputs are the DB
  + the TIA block *.xml + *.csv sidecars + InstanceOf/*.db + block_templates.json.

THEN: 900 (910 Pipeline Coverage Report only). 920 deferred (needs Open2App's project text export).

HONOR (full detail in CLAUDE.md):
- Reuse the shared primitives: io/workbook (THE reader), registry/phase/context/app, core/config
  (OUTPUT_PATHS + out_path), io/csv_tables, domain/identity, ctx.rows. Each phase self-registers in
  pipeline3/phases/ and is imported from phases/__init__.py.
- Open2App contract is sacred: generators write ONLY under
  Shared/OutputTree/TiaPortalProjectInterface/BuilderData/ (hardware_dir, blocks_creation_dir,
  blocks_import_dir, io_tags_dir) — byte-stable. ProjectDocumentation/* and Reports/* are NOT imported.
- GUI-only buttons are DEFERRED to the GUI milestone (M11): the "Open …" buttons cannot run
  headlessly — build the GENERATION engine + register the buttons, leave opens/popups GUI-era.
- DTD params: col-5 applied by Open2App (NEVER written) vs col-6/col-7 + I/O-List col-AG (written;
  AG overrides, last). Comma CSV on write, sniff on read. Tag/device strings (=S1,+MS1,-S67001) are
  text (data_type="s") so a leading =/+/- isn't a formula.
- i18n EN+IT for operator-facing messages; LogEntry model (id = code-traceable "<phase>-<type>",
  per-FAIL uid, links Sheet!Cell with the workbook on .doc).
- Green gate = the data-independent unit tests; data-dependent artifacts follow review-then-freeze
  under tests/golden/ (pattern: tests/unit/test_golden_validation.py, --freeze).

FORMATS established this session (full detail in CLAUDE.md — match these exactly):
- Data blocks (520): a safe_db type → a TIA Openness SW.Blocks.GlobalDB XML (<name>.xml,
  ProgrammingLanguage=F_DB + DBAccessibleFromOPCUA=false); a normal DB → the .db external source.
  Both UTF-8 BOM. S7_Optimized_Access is NOT the safety marker. Every DB seeded with
  "Always FALSE"/"Always TRUE"; duplicate members dropped + warned.
- Diagnosis SCL (620): UTF-8 BOM + CRLF; the FUNCTION is renamed to drop the TEMPLATE--vX.Y-- prefix.
  Logic rules (diagnosis_logic_rules.csv) are OR / per-row (`|` = OR, fire once per matching row); a
  matched row with no diag_cabinet co-locates via a paired-channel sibling (shared device FLD).
- Hardware (700): format-2 CSV matching the committed reference (Shared/.../TestData/Passing) — comma,
  NO BOM, CRLF, a descriptive `# header` comment (Open2App reads by POSITION). Differs from
  Pipeline2's _format2 (BOM/LF/raw-key headers); follow the reference artifact.
- IF_ prefix: ph400 inserts interface sheets named IF_<instance>; ph500's 510 reads the interface
  tags from them.
- THE USER SUPPLIES REAL EXPORTED REFERENCE FILES for output formats (the .db/.xml, the SCL template
  "is an exported block", the Stations/Modules reference) and wants the generated bytes to MATCH them
  (BOM, line-endings, attributes). When building a new artifact format: check for a committed
  reference, and ASK me for a real export rather than guessing the byte format.

RUN ON REAL DOCS — gotcha: the main pipeline HALTs at Fill (200) (~18 unresolved index entries).
Fill edits the SOURCE in place, so the source is already populated — stage directly, skipping the halt:
    import pipeline3.phases
    from pipeline3 import app
    from pipeline3.context import PipelineContext
    ctx = PipelineContext.create(profile="main"); ctx.completed.add(200); app.run_phase(ctx, <n>)
The real I/O List also carries the inserted IF_ sheets now, and I update it between runs — re-run the
phase + re-freeze the golden when a legit doc edit drifts it. Real docs: Shared/DocumentsValidationData/Passing/.
(assets/ButtonsLayout.xlsx may show a cosmetic Excel re-save in the working tree — no content change;
ignore it when staging a phase commit.)
```
