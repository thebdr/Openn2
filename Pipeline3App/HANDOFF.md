# Pipeline3App — next-session handoff

Paste the fenced block below into a fresh session. `CLAUDE.md` (architecture/status) + the memory
index auto-load; the approved design lives in the plan
`~/.claude/plans/the-codebase-in-openn2-pipeline2app-rippling-canyon.md`.

---

```
Continue the Pipeline3App rebuild at C:\Source\Repos\_Openn2\Pipeline3App (branch tia181920). First
read Pipeline3App/CLAUDE.md (esp. Conventions & gotchas, the phase sections, and the GUI/M11 section)
and the plan ~/.claude/plans/the-codebase-in-openn2-pipeline2app-rippling-canyon.md.

Run the data-independent green gate first:
    cd Pipeline3App && for t in tests/unit/test_*.py; do python "$t" || break; done
(test_golden_validation.py is DATA-DEPENDENT — when it's red, check the WORKING TREE first: a changed
config_project/project_params.yaml or a mutated sample I/O List, NOT a code regression. Phases 200 Fill /
400 insert_interface_sheets re-save the source in place (so they git-dirty it) but now PRESERVE its
formula caches (io/xlsx_cache.restore), so they no longer DEGRADE it; git checkout the doc to restore the
bytes. Re-freeze with --freeze only if the docs legitimately changed.)

DONE: phases 100–900 — documents validation, fill, staging, interfaces, signals, diagnosis, hardware,
all of software generation (8 builders + the 03 direct FC XML + the editable shells), and 910 Pipeline
Coverage Report (domain/coverage.py: traces each staged signal across the ON-DISK outputs; flags
ORPHAN / UNPLACED; Reports/io_project_coverage_report.{csv,txt}). Plus the diag_desc logic-rule column.
The single database is the staged ctx.rows / Shared/OutputTree/.../IODatabase.csv.

ALSO DONE: M11 the main operator GUI ("Broski Session") — pipeline3/gui/ + launch_gui.py. A registry-
driven phase bar (build_spec over registry().presentation_order()), sv-ttk dark + bundled Monaspace
Neon + dark Windows title bar; EN/IT + dark/light toggles; worker-thread runs streamed to the LogView.
The log is ONE engine (§4.1): EVERY phase (not just 100) emits LogEntries - the engine (app._run_one /
run_subphase) emits a "<id> <Title>" PHASE banner per phase (e.g. "300 Documents Staging") and ctx.emit
is level-inferred into INFO/WARN/FAIL LogEntries, so generators 200-900 now log in phase-100's form;
each phase block renders incrementally (on_phase_log), live sub-step text -> status bar. The validation
log is fed as structured records (render.render_records -> logview.append_records): each Sheet!Cell is a
clickable link opening ITS OWN workbook (I/O List or C&E, via the LogEntry doc/doc2) in Excel (now
brought to the FOREGROUND) and the [FAIL] tag a link to error_management.csv. A cross-check (130/140)
shows BOTH workbooks inline as "<loc1> vs <loc2>" (vs aligned per-phase; loc2 = the matched cell, or on
a miss a workbook LABEL that opens that file) + an aligned "<addr> op <addr> | <fld> op <fld>" (===/=/=)
comparison. A "Log to File" checkbox tees the run log to Reports/pipeline_run_log.txt. And the Files tab
(3-section tree + a CSV grid with
zebra/right-click sort/filter, a
YAML/JSON/XML object editor that preserves YAML comments, an xlsx read-only preview + Edit-externally
via LibreOffice/Excel, a full-path header + Open-folder). The app is Pipeline3; each profile is a named
session shown as "Pipeline3 - <session> (<profile>)".

NEXT (pick one, PROPOSE + SHOW before building):
  - the DESIGNER GUI — the slim validation-only 2nd exe (profile "designer", sub 110–150, no pink
    master, its own designer_params base). app_main already supports profile="designer" and names it
    "IOList & CEMatrix Validation (designer)"; the phase bar should show only Documents Validation.
  - the PROJECT MANAGER — folder projects (project.yaml + Input/ + Output/), New/Save As, a
    USER-SELECTABLE projects root (persisted), archive zip. NB: the default Shared/OutputTree/ is the
    SHARED handoff consumed by Openn3App (the C# importer) — keep that shared BuilderData surface intact
    (a project writes into its own <project>/Output; the shared default stays the Openn3 contract).
  - M10 CLI (run.py / run_validation.py / run_phase.py over the registry) + the Open2App-path CONTRACT
    TEST (assert the 4 BuilderData OUTPUT_PATHS keys = config.OPEN2APP_KEYS, byte-stable).
  - object-editor polish (Browse pickers on path-valued leaves, add/remove nodes); M14 packaging (two
    PyInstaller exes); investigate the phase-400 insert formula-cache drop on the real doc.

920 TIA Project Coverage — STILL DEFERRED (the export is coming). Design decided: ALL-XML, dispatched
on the XML ROOT TAG (SW.Blocks.GlobalDB / FC / FB / OB / SW.Types.* UDTs / tag tables) — ONE SimaticML
loader + a thin per-kind extractor (reuse Pipeline3's own emit schema), plus a small ADAPTER SEAM for
the non-XML hardware data. Re-runs the 910 signal-lifecycle trace over the project export, cross-checked
vs the C&E matrix + diagnosis assignments. You MAY sketch the 920 project-model interface, but ASK for a
real TIA version-control export sample before writing any concrete parser — match real bytes, don't guess.

HOW WE WORK: one focused change at a time; PROPOSE the design + SHOW real output (screenshots: the GUI
can be captured via a screen-region BitBlt — win32gui/win32ui — into a PNG); ASK when domain judgement
is needed (it's mine — you implement); iterate until I bless it; keep the green gate green; add a
data-independent unit case. A question is just a question — answer it, don't change code. Commit/push
only when I ask.

HONOR (full detail in CLAUDE.md): reuse the shared primitives + domain/identity; the Open2App contract
(write only under Shared/OutputTree/TiaPortalProjectInterface/BuilderData/ — byte-stable; the coverage
report goes under Reports/, which is documentation/NOT imported); comma CSV; tag/device strings are text
(data_type="s"); generated TIA Openness XML = UTF-8 BOM + CRLF + multi-line. GUI: tk.Button for the
coloured phase bar (sv-ttk buttons can't take a custom bg); xlsx/xlsm are view-only in-app.
```
