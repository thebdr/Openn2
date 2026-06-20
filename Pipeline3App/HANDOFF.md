# Pipeline3App — next-session handoff

Paste the fenced block below into a fresh session to continue the rebuild. `CLAUDE.md`
(architecture/status) and the memory index auto-load; the approved design + per-phase contracts
live in the plan at `~/.claude/plans/the-codebase-in-openn2-pipeline2app-rippling-canyon.md`
(§2 contracts, §10 Open2App contract + decisions).

---

```
Continue the Pipeline3App rebuild at C:\Source\Repos\_Openn2\Pipeline3App. First read
Pipeline3App/CLAUDE.md (authoritative architecture/status/gotchas — esp. the Phase 800 section +
Conventions & gotchas) and the approved plan
~/.claude/plans/the-codebase-in-openn2-pipeline2app-rippling-canyon.md
(§2 per-phase contracts, §9 Pipeline2 reference files = INTENT only, §10 Open2App contract).

STATUS: M1–M6 + M6b + Phase 400 Interfaces + Phase 500 Signals + Phase 600 Diagnosis + Phase 700
Hardware done; Phase 800 Software is a SKELETON (the clean builder base — engine/shells/registry/
Database/Table done; the per-template builders in domain/blocks/builders.py are USER-authored stubs).
Committed on branch tia181920 (origin = github.com/thebdr/Openn2; HEAD ahead of origin — push when I
ask). The single database is the staged ctx.rows / Shared/OutputTree/.../IODatabase.csv.

Run the data-independent green gate first to confirm the baseline:
    cd Pipeline3App && for t in tests/unit/test_*.py; do python "$t" || break; done
NOTE: test_golden_validation.py is DATA-DEPENDENT (regenerates the phase-100 reports from the real
docs vs the frozen golden); it FAILs (and the `|| break` stops there) when the real I/O List legit
changed — confirm the drift is the intended doc edit, then re-freeze:
    python tests/unit/test_golden_validation.py --freeze

CADENCE: build ONE phase FROM SCRATCH (Pipeline2App = reference for INTENT only, never port
verbatim) → unit-test (synthetic fixtures, tests/unit/_harness.py) → run on the real docs → STOP
for my review. A question is just a question (answer it; don't change code). Commit/push only when I ask.

NEXT (pick per my direction):
  - PHASE 900: 910 Pipeline Coverage Report → coverage_report (Reports/io_project_coverage_report.
    {csv,txt}); every signal lands somewhere; flag ORPHAN / UNPLACED MEMBER. 920 deferred (needs
    Open2App's project text export).
  - The PHASE-800 block builders (domain/blocks/builders.py) are MINE to author (free-form Python
    over the Database) — only touch them if I ask; they are not an AI task by default.
  - Then M10 CLI (run.py/run_validation.py/run_phase.py) + the Open2App-path contract test;
    M11–13 GUIs (dark-by-default, registry-driven phase bar, YAML-explorer config, selectable
    projects root) + designer + Project Manager; M14 packaging (two exes).

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
  under tests/golden/.

FORMATS established (full detail in CLAUDE.md — match these; THE USER SUPPLIES REAL EXPORTED
REFERENCES for output bytes — check for a committed reference + ASK for a real export, don't guess):
- Data blocks (520): safe_db → TIA Openness SW.Blocks.GlobalDB XML (F_DB + DBAccessibleFromOPCUA=false);
  normal DB → the .db external source. Both UTF-8 BOM. Every DB seeded Always FALSE/TRUE; dup members dropped.
- Diagnosis SCL (620): UTF-8 BOM + CRLF; FUNCTION renamed (drop TEMPLATE--vX.Y--). Logic rules are
  OR/per-row; a matched row with no diag_cabinet co-locates via a paired-channel sibling.
- Hardware (700): format-2 CSV per the committed reference (Shared/.../TestData/Passing) — comma, NO
  BOM, CRLF, descriptive `# header` (Open2App reads by POSITION).
- Software (800): NO golden (Pipeline2's never worked) — produced fresh for review. block_templates.json
  is DEPRECATED; SoftwareBlocks.xlsm IS the key inventory (810 scans the template *.xml for !!key$$);
  output is the $/#/%/@ CSV with the % header = the shell's FULL key set and an ABSOLUTE $ template= ref.
- IF_ prefix: ph400 inserts interface sheets named IF_<instance>; ph500's 510 reads their tags.

RUN ON REAL DOCS — gotcha: the main pipeline HALTs at Fill (200) (~18 unresolved index entries).
Fill edits the SOURCE in place, so the source is already populated — stage directly, skipping the halt:
    import pipeline3.phases
    from pipeline3 import app
    from pipeline3.context import PipelineContext
    ctx = PipelineContext.create(profile="main"); ctx.completed.add(200); app.run_phase(ctx, <n>)
The real I/O List carries the inserted IF_ sheets; I update it between runs — re-run + re-freeze the
golden when a legit doc edit drifts it. Real docs: Shared/DocumentsValidationData/Passing/.
(assets/ButtonsLayout.xlsx may show a cosmetic Excel re-save in the working tree — no content change;
ignore it when staging a phase commit. Delete a stale SoftwareBlocks.xlsm to regenerate the shells.)
```
