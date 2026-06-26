# Pipeline3App — next-session handoff

Paste the fenced block below into a fresh session. `CLAUDE.md` (architecture/status) + the memory
index auto-load; the approved design lives in the plan
`~/.claude/plans/the-codebase-in-openn2-pipeline2app-rippling-canyon.md`.

---

```
Continue the Pipeline3App rebuild at C:\Source\Repos\_Openn2\Pipeline3App (branch tia181920, local).
First read Pipeline3App/CLAUDE.md (architecture + status; esp. Conventions & gotchas, the phase
sections, the GUI/M11 + Project-Manager + Designer-mode + io/xlsx_edit sections) and the plan
~/.claude/plans/the-codebase-in-openn2-pipeline2app-rippling-canyon.md.

GREEN GATE (data-independent, must stay green — 29 suites):
    cd Pipeline3App && for t in tests/unit/test_*.py; do python "$t" || break; done
test_golden_validation.py is DATA-DEPENDENT: when it's red, check the WORKING TREE FIRST — a changed
config_project/project_params.yaml or a re-saved sample I/O List, NOT a code regression. Phase 200 Fill
is now SURGICAL (io/xlsx_edit: only the edited cells/sheets change, everything else is byte-copied) and
phase 400 freezes any openpyxl-flattened array + drops the stale calcChain, so both stay Excel-valid +
no longer DEGRADE the sample; `git checkout` the sample to restore the bytes. Re-freeze (--freeze) only
if the report text legitimately changed.

DONE — the engine, phases 100–900: documents validation, fill, staging, interfaces, signals,
diagnosis, hardware, all software generation (8 builders + 03 direct FC XML + the editable .xlsm
shells), 910 Pipeline Coverage Report (domain/coverage.py: traces each staged signal across the
ON-DISK outputs; flags ORPHAN/UNPLACED; Reports/io_project_coverage_report.{csv,txt}), + the diag_desc
logic-rule column. The single database is the staged ctx.rows / IODatabase.csv.

RECENT REFINEMENTS (this batch — data-independent gate green; RE-STAGE 300->500 + RE-FREEZE the golden
after reviewing the 130/150 report changes in the GUI):
  - DATA BLOCKS — CENTRALIZED REGISTRY (520): EVERY DB is a SW.Blocks.GlobalDB XML declared in the
    config-driven registry (config_project/datablocks/datablock_definitions.csv + datablock_elements.csv +
    datablock_types.csv via pipeline3/domain/datablocks.py + dbtemplate.py). <ProgrammingLanguage> =
    db_programming_language verbatim (`DB`/`F_DB`); <DBAccessibleFromOPCUA> = false for F_DB else true (the 6
    F_DB DBs set opc_ua=false in CSV1). The legacy signals.build_data_blocks + the datablock_elements_rules
    520 path are REMOVED — the 8 ex-signal_types DBs were migrated byte-identical (member={name_in_db}
    for_each 'row where script_type in [...]', seed=true), plus new DiagnosticTags (per-cabinet UDInt + FB
    instance families -> InstanceDBs.csv). generate_data_blocks HALTS if a signal names an undeclared DB.
    F_DB is canonicalized in signals._db_xml; an unrecognized ProgrammingLanguage warns (datablocks.generate).
    datablock_elements_rules.csv now serves ONLY phase-400 interface mirroring. signal_types `db_kind` is
    REMOVED (the registry owns ProgrammingLanguage); is_db_backed + the staged `datablocks` column now key
    off `db_names` (identity.db_kinds/db_kind_of deleted). signals.DB_CONSTANTS kept for coverage + 02_COM.)
  - INTERFACE ADDRESSES (400/500): insert_interface_sheets now SEEDS the `I/O Address Side 1` cache with
    the value computed in Python (interfaces._interface_address_caches mirrors the LET: {I|Q}{base+offset}
    [.bit], offset/bit chains resolved, columns bound by header), so 510 reads correct addresses WITHOUT
    Excel; the live LET formula survives. The <GENERIC> template's address LET is mis-wired one column off
    (LATENT — header-bound Python value is correct regardless; a task chip tracks the template fix).
    interface_tagname now also resolves {db_element}.
  - NODE BYTE RANGES are POSITIONAL (staging._add_node_address_ranges): a node owns the rows beneath it in
    I/O List order until the next node / sheet end — NOT keyed by FLD/location (which left safety modules
    empty-ranged and silently dropped 94/122 E1/2 from every node_of consumer). Fixes 02/06/08 builders +
    diagnosis FL + coverage.
  - 02_EM Push Button now groups the node's emergency-stop inputs = E1/2 push-buttons AND B1/2 safety-
    breakers (was E1/2 only).
  - DiagnosisBlocks 230/240 are IDEMPOTENT (append-only rows, stable ID_Local, bits continue past used);
    derived Count (real iolist occurrences of ID_Local) + unused_bits + non_unique_bits recomputed each run.
  - VALIDATION: 130 CEM->IOL runs TWO searches (by address + by FLD -> six precise outcomes); 150 adds
    diag_container_check (the cabinet's DiagnosisBlocks FullName must CONTAIN the type's expected
    container). Manual ORANGE 165/175 CLEAN buttons strip `'`/whitespace from addresses+names
    (domain/clean.py). Treatments: right-click a [FAIL]/[WARN] link -> Treat as Warning / Clear Treatment
    Flag (writes error_management.csv, NO auto re-run, appends a "uid: ... flagged as warning" log line).
    A live "Show PASS/SKIP" toolbar toggle elides PASS/SKIP (ce_full_print).

DONE — SURGICAL EXCEL WRITE (io/xlsx_edit) — the ONE place that modifies an .xlsx. openpyxl is
UNUSABLE for editing the I/O List: a load_workbook->save round-trip FLATTENS dynamic-array formulas
into a master + literal slaves (Excel reports an "overlapping array formula" / corrupt), DROPS formula
caches, AND leaves a stale xl/calcChain.xml (it lists formula cells a regenerated sheet removed -> Excel
"Removed Records: Formula from calcChain.xml"). io/xlsx_edit edits ONLY the changed worksheet parts
inside the zip and BYTE-COPIES the rest, so the template's arrays / shared formulas / caches / tables /
styles SURVIVE by not being touched. API:
  - edit_workbook(path, cell_edits={sheet:{ref:val}}, new_sheets=[{name,rows,hyperlinks?}],
    delete_sheets=[names]) -> list of (sheet,master,range) FROZEN. A cell edit is a regex rewrite of the
    <c> (inline string, style preserved); an edit landing in an array SPILL freezes that array to its
    cached values (keeps every spilled value, drops the formula + cm/vm meta) -> no overlap (+WARN; the
    formula stays in the backup). new_sheets builds a fresh grid via build_sheet_xml (FULL worksheet
    structure dimension/sheetViews/sheetFormatPr/pageMargins — a bare <sheetData> is Excel-corrupt) +
    registers it in workbook.xml/rels/[Content_Types]. ALWAYS drops xl/calcChain.xml (+ its rel +
    Override).
  - freeze_arrays(path) -> the post-process for openpyxl-based writers that CAN'T avoid the flatten
    (phase 400): freeze every array master to its cached values + drop calcChain.
Phase 200 Fill (domain/iolist_diag/populate.py) is FULLY surgical (cell_edits for AB/AC/AD/AE/AF +
new_sheets for DiagnosisBlocks/_UnresolvedIndex + delete_sheets the legacy alias). Phase 400
interfaces.insert_sheets_into_iolist keeps openpyxl for the styled IF_ sheet-copy then calls
freeze_arrays. io/xlsx_cache is RETIRED. Verified in REAL Excel (the filled I/O List opens clean).
test_xlsx_edit.py (8 cases) + test_p200_phase.py.

DONE — M11 operator GUI ("Broski Session"), pipeline3/gui/ + launch_gui.py: a registry-driven phase
bar (phasebar.build_spec over registry().presentation_order(profile)), sv-ttk dark + bundled Monaspace
Neon + dark Windows title bar, EN/IT + dark/light toggles, worker-thread runs streamed to the LogView.
  - ONE LOG ENGINE (§4.1): EVERY phase emits LogEntries. The engine emits a "<id> <Title>" PHASE banner
    per (sub-)phase; ctx.emit is level-inferred (model.split_level) into INFO/WARN/FAIL, and now takes a
    type= slug so an emit line's id renders <phase>-<type> (e.g. "210-backup"). Each phase block renders
    incrementally (ctx.on_phase_log -> render.render_records -> logview.append_records); live sub-step
    text -> status bar (ctx.on_progress).
  - CLICKABLE LINKS: each Sheet!Cell opens ITS OWN workbook in Excel AT the cell (excel.goto +
    _bring_to_front); [FAIL] opens error_management.csv. A cross-check (130/140) renders BOTH workbooks
    inline "<loc1> vs <loc2>" + an aligned "<addr> op <addr> | <fld> op <fld>" (model.Cmp).
  - HTML VALIDATION REPORT: phase 100 writes each report as BOTH .txt (the golden) AND a no-wrap .html
    (render.render_html/html_reports) that replicates the log viewer (theme.log_tags colours, Sheet!Cell
    link styling) with white-space:pre (lines do NOT wrap). "Open validation logs" prefers the .html.
  - "Log to File" tees the run log to Reports/pipeline_run_log.txt. Files tab: a 3-section tree + a CSV
    grid (zebra, right-click regex sort/filter), the YAML/JSON/XML OBJECT EDITOR (objedit.py) — now with
    a right-click context menu (Browse file/folder into a leaf · Add key/item or Add child
    element/attribute · Delete any non-root node; a per-item _model registry; pure add_key/add_item/
    delete_node helpers; YAML comments + JSON types preserved) — an xlsx read-only preview +
    Edit-externally, full-path header + Open-folder.
  - PHASE BAR (assets/ButtonsLayout.xlsx is the canonical map): chevron dropdowns; bold emoji glyphs ➡/⬇/
    —/▼; no arrow between Run Pipeline and ph100; the dropdown closes on focus loss (GetForegroundWindow
    poll).

DONE — DESIGNER MODE (M11b) — ONE GUI, the launch profile chosen by config_project/app_config.yaml
(profile: main|designer, read by config.load_app_profile; unknown/missing -> main; app_main validates
against the registry). The registry now separates PRESENTATION from the runnable keep-set
(define_profile(present=, attrs=)) + carries per-profile GUI attrs (input_pickers/live_source). Designer:
the bar shows ONLY ph100 (300 stages as a hidden prerequisite, Fill 200 skipped), reads designer_params
.yaml (config.profile_params_file -> <profile>_params.yaml convention), uses a FULL Project-Manager
project (New Project seeds from the designer base, no file prompts), adds two input-file PICKERS beside
ph100, and re-copies each input's `source` into Input/ on EVERY ph1x0 run (project.refresh_inputs +
a ctx re-stage). app_config.yaml is TRACKED and also carries a user_interface launch block
(width/height = START window size — stays resizable; theme; log_to_file) via config.load_app_ui, applied
in App.__init__. test_registry/test_config/test_project cover the wiring.

DONE — PROJECT MANAGER (M13), pipeline3/project/{project.py,state.py} + the GUI toolbar (New Project /
Open Project ▾ = recent / Open… / Set projects root… / Re-select IOList… / Re-select CEMatrix… /
Close) + an active-project indicator + AUTO-REOPEN of the last project. A project is self-contained
<root>/<name>/ = project.yaml + Input/ + Output/ + its OWN config_project/ + user_input/ (FULLY
ISOLATED). config.use_project(root)/use_builtin() routes the loaders + treatment registry; NO project
open = the builtin config + Shared/OutputTree (the Open2App/Openn3 import contract, byte-identical
BuilderData). Persisted root + recent + last_opened: %LOCALAPPDATA%/Pipeline3/state.json. v1 defers
Save As + Archive.

NEXT (pick one, PROPOSE + SHOW before building):
  - M10 CLI (run.py / run_validation.py / run_phase.py over the registry) + the Open2App-path CONTRACT
    TEST (assert the 4 BuilderData OUTPUT_PATHS keys = config.OPEN2APP_KEYS, byte-stable).
  - M14 packaging — now ONE PyInstaller exe (the profile is a shipped app_config.yaml value): bundle
    config_project/ + assets/fonts/ + the .png icon + sv-ttk's .tcl + pywin32; decide how the sibling
    ../Shared folder ships.
  - PROJECT MANAGER v2 — Save As (clone under a new name) + Archive (zip the project folder); port
    save_project_as/archive_project from Pipeline2; wire the Open Project ▾ dropdown.
  - phase-400 FULL surgical sheet-copy (merge styles/sharedStrings/tables at the XML level so phase 400
    stops using openpyxl entirely — the openpyxl + freeze_arrays path is the pragmatic choice for now);
    more object-editor polish (path-leaf detection, nested-structure add).

920 TIA Project Coverage — STILL DEFERRED (the export is coming). Design decided: ALL-XML, dispatched
on the XML ROOT TAG (SW.Blocks.GlobalDB / FC / FB / OB / SW.Types.* UDTs / tag tables) — ONE SimaticML
loader + a thin per-kind extractor (reuse Pipeline3's emit schema) + a small adapter for the non-XML
hardware data. Re-runs the 910 signal-lifecycle trace over the project export, cross-checked vs the C&E
matrix + diagnosis assignments. ASK for a real TIA version-control export sample before writing any
concrete parser — match real bytes, don't guess.

HOW WE WORK: one focused change at a time; PROPOSE the design + SHOW real output (the GUI can be
captured via a screen-region BitBlt — win32gui/win32ui — into a PNG, then Read it; a generated .xlsx is
verified by sending it for the user to open in Excel — Excel is STRICTER than openpyxl/zipfile, so
"valid zip + openpyxl re-opens" is NOT proof, and the Excel "repair log" names the exact bad part);
ASK when domain judgement is needed (it's mine — you implement); iterate until I bless it; keep the
green gate green; add a data-independent unit case. A question is just a question — answer it, don't
change code. Commit/push only when I ask (end commit messages with the Co-Authored-By trailer).

HONOR (full detail in CLAUDE.md): reuse the shared primitives (io.workbook reader, core.model LogEntry
+ io.render, domain/identity); the Open2App contract (write only under
Shared/OutputTree/TiaPortalProjectInterface/BuilderData/, byte-stable; Reports/* is documentation, NOT
imported); comma CSV; tag/device strings are text (data_type="s"); generated TIA Openness XML = UTF-8
BOM + CRLF + multi-line. **io/xlsx_edit is the ONE .xlsx writer — NEVER do an openpyxl load->save on
the I/O List** (it flattens dynamic arrays into an Excel-corrupting overlap + drops caches + leaves a
stale calcChain); edit surgically, or for an openpyxl-based writer call freeze_arrays after. GUI:
classic tk.Button for the coloured phase bar (sv-ttk buttons can't take a custom bg); xlsx/xlsm are
view-only in-app (edit hands off to LibreOffice/Excel).
```
