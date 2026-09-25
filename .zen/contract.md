# Contract Items

Governance scope: the **`_Openn2`** repo root, focused on the **pipeline's road to public v1.0**
(the **PL5** line, branch `pl5`). The `C-xxx` clauses below are seeded from the **frozen PL4 baseline**
(`Pipeline4App`, `pl4` @ `16ef215`) — the feature-complete pipeline PL5 must **preserve** on the way to v1.0.
Each clause names the PL4 test that proves it **today** as its verification oracle; **status stays
`pending verification`** because PL5 (a new `Pipeline5App`) has not re-verified it yet. As PL5 ports each
capability, its link updates to the PL5 test and — after a recorded run + refute — the clause flips to
`verified`. The v1.0 workstreams themselves (new app, reorg, config/log/i18n review, full coverage, guide,
release) live as `P-xxx` deltas under **Pending Contract Deltas**. Legacy apps (`Openn2App`, `Pipeline2App`,
`Pipeline3App`) are intentionally out of scope.

## C-001: SSOT database — CSV-with-JSON-cells tables
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** Every datum the pipeline retrieves, infers, or creates is written into one in-memory `Database` of typed tables, each persisted as a git-diffable CSV whose declared columns hold real JSON (list/object cells) and decode on read. Deterministic encoding (sorted keys, byte-stable), content-hash `uid` per row, fail-loud on ragged/duplicate/malformed cells. This is the anchor of the whole SSOT thesis — `BuilderData/` exports become byte-stable projections of the tables, not primary state.
- **Verification:** automated → Pipeline4App/tests/unit/test_table.py, Pipeline4App/tests/unit/test_database.py, Pipeline4App/tests/unit/test_keys.py, Pipeline4App/tests/unit/test_signals_schema.py | table codec, Database save/load, uid stability, signals schema
- **Status:** pending verification

## C-002: Unified expression engine (core/expr)
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** One DB-references-only expression language used by every config-CSV expression column (templates, `for_each` predicates, interface tag-names): `$column` fields validated against a `Scope`, `render` with format-specs and missing-key modes, data funcs, `clean/strip/concat/join/extract/if/coalesce/let`, `regex_replace`. Replaces the three retired legacy mini-languages; a bad reference is a located `ExprError`.
- **Verification:** automated → Pipeline4App/tests/unit/test_expr.py, Pipeline4App/tests/unit/test_expr_adversarial.py, Pipeline4App/tests/unit/test_expr_tools.py | grammar, adversarial inputs, tokenizer/lint tools
- **Status:** pending verification

## C-003: Severity, findings & treatment model
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** A uniform outcome model across all phases: a frozen `Finding` (uid excludes severity) recorded into the `validation_issues` table; a per-uid `treatments` registry that can downgrade/escalate (up to FAIL); `run.gate` (apply + render + halt iff effective FAIL) and `run.render` (no-halt, for pure projections). Severity taxonomy FAIL/ERROR/WARN/INFO/SKIP/PASS/DEBUG, first-char addressable.
- **Verification:** automated → Pipeline4App/tests/unit/test_finding.py, Pipeline4App/tests/unit/test_treatments.py, Pipeline4App/tests/unit/test_run.py, Pipeline4App/tests/unit/test_severity.py | finding uid, registry apply/reconcile, gate/render, taxonomy
- **Status:** pending verification

## C-004: Config loading & project isolation
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** `use_project()` repoints the loaders, the `Database/` folder, and the `Output/` tree at a chosen project or the builtin `Shared/`. Nested `project_params.yaml` schema with a safe dotted `get_param` accessor; `generation_params.yaml` and `app_config.yaml`; tolerant config-CSV readers over the table codec. Missing config surfaces a pointed WARN, never a code-baked default. PL5 (step 4e, landed): ONE 4-tier resolver (project-system -> project-shared -> system-builtin -> builtin-shared; find tolerant / resolve fail-loud), `use_system()` beside `use_project()`, tiered scaffolding + per-meta completeness checks.
- **Verification:** automated → Pipeline4App/tests/unit/test_config_loaders.py, Pipeline4App/tests/unit/test_params.py, Pipeline4App/tests/unit/test_generation_params.py, Pipeline4App/tests/unit/test_app_config.py, Pipeline4App/tests/unit/test_project.py | loaders, dotted params, generation/app config, project state
- **Status:** pending verification

## C-005: Workbook I/O & surgical xlsx editing
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** Read workbooks by column position; edit them surgically via a pure stdlib ZIP + regex XML writer (`xlsx_edit`: per-cell edits, whole-sheet add/delete, byte-preserving append, array-freeze guard, atomic replace) with an openpyxl-based path where needed. Preserves formulas, caches, and byte layout the downstream TIA import depends on.
- **Verification:** automated → Pipeline4App/tests/unit/test_workbook.py, Pipeline4App/tests/unit/test_xlsx_edit.py, Pipeline4App/tests/unit/test_sheets.py, Pipeline4App/tests/unit/test_documents.py | reader, surgical writer round-trips, sheet resolution, document paths
- **Status:** pending verification

## C-006: Phase 300 — Staging (the signals table)
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** Read the configured I/O List and C&E matrix into the `signals` fact table: resolve each row's `type` (object cell), annotate C&E areas, derive document-side identity (FLDs, tag names), positional node address ranges, and `IsSorterArea`; also stage the `diagnosis_cabinets` table. Split into `stage_iolist` (310, no C&E) then `annotate_cematrix` (320) composing byte-identically. Blocking findings on missing I/O sheet / duplicate `(script_type, index)`. PL5 (steps 3-4, landed): capability-gated legs (needs_ce_matrix / needs_diagnosis_blocks - flags, never type ids) and the CONFIG-DRIVEN address notation ([[C-022]]).
- **Verification:** automated → Pipeline4App/tests/unit/test_staging.py | 310/320 split idempotence, uid re-stamp, dup-index FAIL, node ranges
- **Status:** pending verification

## C-007: Phase 200 — Documents Fill Out (CSV-driven classification)
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** Turn a raw I/O List into a classified one: §6 script_type via a rules CSV (config-driven, not a hard-coded ladder), §7 per-family contiguous index (range notation + channel n/N suffix), §8 diagnosis cabinet/bit allocation (idempotent, stable IDs) and the DiagnosisBlocks sheet, over the canonical stage→fill→re-stage order. Includes the manual "Risky Index Fill" review path.
- **Verification:** automated → Pipeline4App/tests/unit/test_fillout_classify.py, Pipeline4App/tests/unit/test_fillout_index.py, Pipeline4App/tests/unit/test_fillout_diag.py, Pipeline4App/tests/unit/test_fillout_ranges.py, Pipeline4App/tests/unit/test_fillout_integration.py, Pipeline4App/tests/unit/test_fillout_fill.py | classify, index grouping, diag alloc, ranges, re-stage integration, in-place fill
- **Status:** pending verification

## C-008: Phase 520 — Data Blocks
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** One registry evaluator over `signals` produces the surviving DBs (`db_blocks`), every Global-DB member (`db_members`), and the FB instance families (`instance_dbs`); the three registry-derived signal fields (`name_in_db`/`datablocks`/`plc_binding`) are written back onto the signals. Projected to byte-stable `<DB>.xml` (F_DB OPC-lock). Includes the `for_each` DSL and PEP-3101 member rendering.
- **Verification:** automated → Pipeline4App/tests/unit/test_datablocks.py, Pipeline4App/tests/unit/test_dbtemplate.py | generate + write-back + XML projection, template/for_each engine
- **Status:** pending verification

## C-009: Phase 400 — Interfaces
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** Build the `interfaces`/`interface_elements` SSOT tables from IOC rows: mirror set collection (direct + follower + template-native sources), byte allocation, and the stored `io_address_side1`. Projected to one `IF_<instance>.xlsx` per interface, losslessly inserted back into the I/O List, and emitted as one SCL FUNCTION (`10_Machine Interfaces.scl`).
- **Verification:** automated → Pipeline4App/tests/unit/test_interfaces.py, Pipeline4App/tests/unit/test_interface_xlsx.py, Pipeline4App/tests/unit/test_interface_scl.py | mirror set + allocation + native, xlsx projection/insert, SCL projection
- **Status:** pending verification

## C-010: Phase 510 — I/O Tags (PLCTags)
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** A pure projection of `signals` + `interface_elements` to `PlcTags/PLCTags.xlsx` (the OP import surface): resolved I/O signals plus interface tags, sorted by tag table, two sheets. A duplicate (tag table, name) pair — TIA's case-insensitive uniqueness rule — emits a blocking `iotag_duplicate` FAIL with dual source links and no write; the same name across different tables stays legal.
- **Verification:** automated → Pipeline4App/tests/unit/test_io_tags.py | two tag sources, dtype/address mapping, duplicate-tag FAIL + no-write, cross-table pass
- **Status:** pending verification

## C-011: Phase 600 — Diagnosis
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** A unified `diagnosis_entries` table (`source` = io|logic) built from `signals` + `diagnosis_cabinets` + logic rules, carrying the SCL channel values and a frozen column snapshot; projected to `DiagList_IO.csv` + `DiagList_Logic.csv` and the `06_Diagnostic for OPC.scl` (per-cabinet REGIONs, packed DWords). Tristate is driven by `template_type` ∈ {2,4} or a per-type `tristate` flag.
- **Verification:** automated → Pipeline4App/tests/unit/test_diagnosis.py | build (io+logic), DiagList CSV projection, OPC SCL variants + tristate + BOM/CRLF
- **Status:** pending verification

## C-012: Phase 700 — Hardware
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** One ordered pass over `signals` populates `hardware_stations` (PLC / PlcCardCm / IoDevice heads) and `hardware_modules` (IoDevice cards), resolving custom parameters against the Device Types Database; projected to format-2 `Stations.csv` + `Modules.csv`. Missing-DTD FAIL / switch WARN; duplicate-IP skip (backup-CPU downgraded to INFO). Stations gained a 9th `Connector` column (documented contract evolution).
- **Verification:** automated → Pipeline4App/tests/unit/test_hardware.py | extract (auto-plug/PotentialGroup/by-type/default-cards), missing-DTD FAIL, dup-IP skip, format-2 projection
- **Status:** pending verification

## C-013: Phase 800 — Software blocks
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** Hand-written per-template builders (`@builds`) over the `signals` rows produce `software_blocks` + `software_block_members`, serialized to the `$/#/%/@` CreationInfo CSV import surface. Additional emit kinds: `03 Diagnostic Nodes` as ready SCL, `03` as a `SW.Blocks.FC` XML; the engine also materializes builder-owned DBs (`02_COM`, `05_EM_STATE`) and `InstanceDBs.csv`.
- **Verification:** automated → Pipeline4App/tests/unit/test_blocks.py | Table list-cells, serialization, simple + complex builders, build→project round-trip, emit routing
- **Status:** pending verification

## C-014: Phase 900 — Coverage
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** A per-signal placement trace persisted as the `coverage` SSOT table, built by reading the emitted sets across the other SSOT tables (signals, db_members, diagnosis_entries, interface_elements, hardware, software). Unplaced/orphan signals surface as WARN findings. Documentation-grade (not a byte-parity surface).
- **Verification:** automated → Pipeline4App/tests/unit/test_coverage.py | output collection, attribute/find-unplaced, ORPHAN/UNPLACED WARN, render
- **Status:** pending verification

## C-015: Phase 100 — Validation (110–140 + reports)
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** Standalone document validators — 110 (I/O List), 120 (C&E), 130/140 (cross-checks between the I/O List and C&E, typed/untyped decision tree) — reading the raw workbooks and the SSOT, recording issues without ever halting, and rendering rich aligned txt + no-wrap HTML reports with comparison blocks and dual-workbook links. (150 diag-slot and `accept` are deliberately out of scope.)
- **Verification:** automated → Pipeline4App/tests/unit/test_validation_standalone.py, Pipeline4App/tests/unit/test_validation_crosscheck.py, Pipeline4App/tests/unit/test_validation_diagcheck.py, Pipeline4App/tests/unit/test_validation_render.py, Pipeline4App/tests/unit/test_validation_phase.py | 110/120, 130/140 cross-checks, diag check, report renderer, orchestrator
- **Status:** pending verification

## C-016: ph100b — Before/After changes quality report
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** An effort-framed, viewer-facing HTML/CSV report comparing a current vs previous document revision: composition bar, per-field "what was changed" breakdown (neutral, no right/wrong verdict), device-centric AREA membership deltas, identity-noise cleanups, and struck-row counts. Intended for a non-pipeline reader.
- **Verification:** automated → Pipeline4App/tests/unit/test_changes.py | diff classification, composition/field breakdown, report shape
- **Status:** pending verification

## C-017: Internationalization (EN/IT, logs & reports first)
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** First-class bilingual operation (EN/IT): validation messages carry EN + IT templates, and a finding's detail is built in the ambient active language so the log and the txt/HTML reports localize; the GUI chrome localizes via a registry of label/name keys and a persisted language toggle. The point is that the operator-facing output, not just the UI frame, is translated.
- **Verification:** automated → Pipeline4App/tests/unit/test_i18n.py, Pipeline4App/tests/unit/test_validation_i18n.py | i18n core + toggle, localized validation detail/report
- **Status:** pending verification

## C-018: GUI — operator shell
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** The desktop application frame: a background worker thread, a phase-button bar with sub-phase chevron dropdowns that run their sub-phase, Run-all with live progress and halt-on-FAIL, a structured clickable log with a severity-level filter, a Findings panel, and the themed chrome (fonts/icons).
- **Verification:** automated → Pipeline4App/tests/unit/test_gui_phases.py, Pipeline4App/tests/unit/test_gui_phasebar.py, Pipeline4App/tests/unit/test_gui_chasebar.py, Pipeline4App/tests/unit/test_gui_findings.py, Pipeline4App/tests/unit/test_gui_levels.py, Pipeline4App/tests/unit/test_gui_fonts.py, Pipeline4App/tests/unit/test_gui_icons.py | phase registry/bar, run-all chase, findings, level filter, fonts, icons
- **Status:** pending verification

## C-019: GUI — data & authoring tools
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** The in-app tooling around the pipeline: a Database Explorer (lazy, stamped, chunked) over a shared DataGrid canvas; a config-driven Files tab with CSV/xlsx grid + in-place text/CSV editing; yaml/json syntax highlighting and a Text⇄Object explorer editor with path pickers; the ƒx expression builder (lint + autocomplete + live preview against a real SSOT row); and the F1 in-app guide/help window.
- **Verification:** automated → Pipeline4App/tests/unit/test_gui_dbquery.py, Pipeline4App/tests/unit/test_gui_datagrid.py, Pipeline4App/tests/unit/test_gui_files.py, Pipeline4App/tests/unit/test_gui_highlight.py, Pipeline4App/tests/unit/test_gui_object_editor.py, Pipeline4App/tests/unit/test_gui_expr_builder.py, Pipeline4App/tests/unit/test_gui_helpwin.py | db explorer, grid, files, highlight, object editor, ƒx builder, help
- **Status:** pending verification

## C-020: FileXY viewer/editor integration
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** The pipeline integrates the standalone FileXY table viewer/editor (Rust-backed load) through a shim so large CSV/xlsx artifacts open in the faster viewer path; the shim isolates the pipeline from FileXY's internals and degrades gracefully when the Rust engine is opted out.
- **Verification:** automated → Pipeline4App/tests/unit/test_filexy_shim.py | shim surface + fallback
- **Status:** pending verification

## C-021: System-type plugin architecture (PL5 spine)
- **Date:** 2026-07-16
- **Source:** ingest (another-big-step-now-curried-pnueli.md#architecture,steps1-5)
- **Description:** Pipeline5App is organized around explicit System descriptors: a systems/ tree (platform -> toolchain -> system; taxonomy PLC_Based/SiemensS7/Safety + IPC_Based/Intervalzero_RTX/{Sorter,Induction,Plant}), each system a folder with a main routine (phase handlers) calling shared kernel + toolchain + custom functions. The System object carries id (taxonomy ids: siemens_s7_safety, intervalzero_rtx_*), capabilities (needs_ce_matrix, needs_diagnosis_blocks - shared code gates by FLAG, never by type id), phases (PhaseSet), handlers, symbols (binding/quote), emitters (emit_kind -> writer), builders (BuilderRegistry instance), output_layout, config_root. Discovery is explicit (systems/catalog.py: ALL_SYSTEMS/by_id/catalog/PLANNED); dialog availability = registry membership. Kernel code NEVER branches on a type id. Resolves the 10 PL4 couplings incl. plc_binding -> system.symbols.binding and per-system emitter tables. Executes under [[P-001]]; extends C-004 (4-tier config resolver: project-system -> project-shared -> system-builtin -> shared-builtin, neither -> raise) - merge at promotion. STRUCTURE DECIDED + LANDED (2026-07-17): the user approved THE BLEND - Chaptered Pipeline skeleton (components own capability) + Shop Manual part naming (language/truth/documents/findings/config/phases/systems/project/workbench/app) + Phasebook per-phase panels (arrive at step 5). Executed as a mechanical move (102 modules re-homed, 62/62 suite green) with the four laws MACHINE-ENFORCED by tests/unit/test_architecture_contracts.py (L1 layers - zero exceptions on day one; L2 phases-as-filters with a 7-edge Kraken-style ratchet, each edge tagged with its burn-down step; L3 systems sealed; L4 headless pipeline). Full record in Evidence.
- **Evidence:** .zen/evidence/C-021.md
- **Verification:** automated → Pipeline5App/tests/unit/test_systems_contract.py, Pipeline5App/tests/unit/test_system_siemens.py, Pipeline5App/tests/unit/test_architecture_contracts.py, Pipeline5App/scripts/parity_vs_pl4.py | the plugin seam + the Siemens descriptor + the four structure laws + the PL4 byte-parity oracle (exit code = verdict). Remaining scope (4-tier resolver, PhaseSet/handlers, per-system scaffolding, multi-system routing) arrives at steps 4-5 and extends these links then.
- **Status:** verified

## C-022: Config-driven I/O address format (regex)
- **Date:** 2026-07-16
- **Source:** ingest (another-big-step-now-curried-pnueli.md#coupling7)
- **Description:** The I/O address NOTATION differs per system and must be config, not code (user correction 2026-07-16). The %I10.3-style parsing hardcoded in staging (_addr_byte, _add_node_address_ranges) and identity (is_io_signal) becomes a regex-style address_format config entry (named groups: direction/byte/bit + which direction tokens mean input vs output), shipped as each system's default in its config_root (Siemens: %I/%Q; RTX: its own), project-overridable via the 4-tier resolver. Staging itself stays 100% shared. Extends C-006 - merge at promotion.
- **Verification:** automated → Pipeline5App/tests/unit/test_address_format.py
- **Status:** pending verification

## C-023: Per-system GUI projection + multi-system routing
- **Date:** 2026-07-17
- **Source:** promotion of P-011 (landed as PL5 migration step 5)
- **Description:** The GUI is a PROJECTION of the active System - the App is the HOST, not the pipeline. Phase/Sub/PhaseSet are CONTRACT types (systems/system_contract.py - they sit at the systems layer so a descriptor never imports upward); each system authors its whole run-plan in its own main.py: the PhaseSet (bar order + an EXPLICIT, construction-validated `run_plan` tuple - Siemens keeps 200 Fill out of Run-all by design) and the `run_x(ctx, only=…)` handler table (System.handlers; Phase.handler and a wired special's Sub.opens are its keys - the App carries zero per-system knowledge). Handlers report ONLY through PhaseContext seams (emit/status/gate/render/records/halt) - Tk-free, so every phase button also runs HEADLESS (the real-data smoke test drives the full run_plan chain exactly as the App dispatches it). The stage->fill->re-stage wiring lives in the run-plan (document_fill takes the caller's staged database - the LAST L2 ratchet edge is PAID; the ratchet is EMPTY). Open-target resolution: System.open_targets first, then System.output_layout.dirs(), then the kernel targets. Project meta types are CONSUMED at open: catalog-resolved to System objects, unknown id -> pointed UnknownSystemError (PL4-era ids - registry-owned catalog.PL4_LEGACY_IDS, law L5 - get the "this is a PIPELINE4 project" message; no migration), auto_reopen skips such projects. Multi-system v1 = active-system toolbar selector (visible when >1 meta type): switching re-points use_system + the phase bar (PhaseBar.set_phases rebuild) + Database/<sid>/ + Output/<sid>/ (config.set_multi_system; single-system stays FLAT - the OP4 path contract); Run-all = active system only. Step-5 finds fixed in passing: the 900 handler's system-less engine.build (a guaranteed click-time crash the parity oracle cannot see - caught by the new headless smoke class), coverage.project now system-routed like the oracle chain, the stale error_management.csv open target -> treatments.registry_path(), the dead diag_config target -> resolver-backed, the PIPELINE4 toolbar brand. Extends C-018 (the PL4 GUI baseline - merge when C-018 re-verifies on PL5) and completes [[C-021]] coupling #9.
- **Evidence:** .zen/evidence/C-023.md
- **Verification:** automated → Pipeline5App/tests/unit/test_gui_phase_model.py, Pipeline5App/tests/unit/test_siemens_main_handlers.py, Pipeline5App/tests/unit/test_project_manager.py, Pipeline5App/tests/unit/test_architecture_contracts.py, Pipeline5App/scripts/parity_vs_pl4.py | the PhaseSet contract + Siemens registry pins, the HEADLESS real-data run of the whole run_plan (the phase buttons without Tk; the clean fixture completes with ZERO halts and a WRITTEN PLCTags surface - re-pinned 2026-07-17 after the fire-alarm ruling: the historic duplicate-tag FAILs were a signal_types.csv defect [F1/2+F2/2 sharing one tag rule over one shared device], fixed with a {$script_type} disambiguator in BOTH the PL5 system tier and the PL4 config copy on this branch [user-authorized; the frozen pl4 branch untouched] - PLCTags.xlsx thereby ENTERED the parity comparison, 39 output files), meta consumption + multi-system routing, the empty ratchet, and the byte-parity oracle (exit code = verdict).
- **Status:** verified

## C-024: Chain-reaction engine + Tempemplator text renderer
- **Date:** 2026-07-17
- **Source:** promotion of P-009 (landed as PL5 migration step 6, engine leg)
- **Description:** The app's conditional-data-creation spine, LANDED DARK (zero shipped rules - the parity guarantee). TWO modules: (1) `language/tempemplator.py` - the recursive text renderer named for the user's VBA tool, rebuilt on `language/expr`: `{expr}` value holes rendered STRICT (a missing top-level FREE field is a located error - a data-function predicate's row column and a let-bound name are not fields of the hole - and inside a `@for` TABLE loop so is a `$row.column` naming no column of that table - its DECLARED columns: the engine's `_db` rows AND each matched source row carry every one (absent -> ""), a freshly staged row included - a SCHEMA check read from the PARSED hole (a predicate's row column or a let-bound name sharing the loop var's name is not the loop row): `{$r.tagg}` no longer renders blank; deeper JSON sub-keys and `_params` keys stay OPTIONAL per C-002 - guard them with `@if present(...)`/`coalesce`; predicates stay lenient - the guard idiom), `@use` (recursive, cycle-guarded), `@for $var in a..b` (inclusive, rendered WHOLE-number ends - a BLANK end (an empty cell) is an EMPTY range, no iterations (user decision 2026-09-25: it used to read as 0 and invent an iteration); a missing end (`..3` / `1..`), a non-integer / non-finite end - validated even beside a blank one - or an un-iterable range is a located error; the loop-column check covers the range ends too; any whitespace around `in`; inline `:` or block/@end form), `@for $var in <table> [where <pred>]` (the E3 SSOT upgrade - where() semantics, the row dict is the loop value; a `/regex/`, a quoted string or a call's arguments (a slice `0:1`, a `let(n := ...)`) in the predicate are opaque - their `..` / `:` never split the line), `@if/@else/@end` with LAZY branches (the untaken side never evaluates), all failures located `TempemplatorError`s (template + line). (2) `phases/chain_reactions/engine.py` - the rule engine: `reactions.csv` rows {name, fire_when(before_<n>/after_<n>), source_table (empty = fire once), condition (expr per source row), action(add_rows|file), target, template, comment} compiled with per-row validation (a malformed rule - an empty name, a bad hook/action/target/template, or a condition that does not COMPILE - = a located ERRR finding, dropped; compiling never raises: a row the compiler cannot even read is an index problem named by its position; only fully blank CSV lines are skipped; the named template's existence, kind for the action, and row shape are checked BEFORE any matching); `templates.yaml` is the UNIFIED named-template file (a LIST entry = a ROW template for add_rows, a STRING = a text template for file). The E1 scope: row fields + `_params` + `_rule{name,hook}` + `_db` (every SSOT table). add_rows spawns expr-filled rows WITH provenance (`spawned_by` + `source_uid`) - every row-template value a template STRING (a YAML-typed list / number / bool is rx_bad_template, never coerced) - and rules fire in CSV order with a later rule SEEING an earlier rule's spawns (the `_db` layer is rebuilt after a spawn: the chain reaction within one hook); file renders per match and APPENDS (the only mode - user decision 2026-07-16; relative paths under the output root). Every firing audited in the `chain_reactions_log` SSOT table (hook/rule/action/target/matches/created/outcome - `ok` or the failure's finding type; `created` is counted as it goes, so a mid-action failure keeps the true partial count; REPLACED per hook on every fire that has rules, so the Explorer shows the last run even when it failed); a DATABASE-LESS hook (before_300) returns its audit rows + findings as a `Deferred` that the run-plan `settle`s into the staged record; failures are ERRR findings recorded (uid-deduplicated; APPENDED to the on-disk record when the staged database never loaded it - the 310 leg - and likewise the audit keeps other hooks' rows) to validation_issues - never silent, never a crash: a per-rule backstop turns any unforeseen exception into `rx_rule_crashed`, an unwritable target is `rx_file_write`, an unloadable reactions.csv / templates.yaml / params file is a finding that blocks the hook's rules (each audited with that outcome). A rule on a hook the run-plan never fires is `rx_unfired_hook` (the run-plan passes its `hooks`). A reaction record that will not LOAD (a hand-edited CSV gone ragged) is left UNTOUCHED - `rx_record_unreadable`, nothing recorded over it, while the REST of the Database (an add_rows spawn) is still saved; both record tables attach from disk or neither - and one that will not SAVE (a file held open) is `rx_record_unwritable`; both rendered, never a crash (the run-plan renders what `settle` returns too). File-level findings carry phase 0, so one broken file is ONE record whichever hook or phase meets it. Rule-INDEX problems (a row naming no hook, an unfired hook, an unreadable reactions.csv) are every hook's business - rendered at each fire, recorded once. A HALTED staging commits no reaction record: the deferred before_300 firings are listed in the log (INFO) and their findings were already rendered (settling into a half-committed record would mix runs - the no-I/O-sheet halt writes nothing at all). `fire(hook, database)` is a STRICT NO-OP when the hook has nothing to do - no rule for it (valid or malformed) and no rule-INDEX problem (beyond reading the rule index itself, nothing further loads, nothing writes, nothing logs; another hook's malformed rule still surfaces). HOOKS fire from the SYSTEM RUN-PLAN (Siemens: before_300/after_300 around the staging leg in safety/main.py) so phase buttons and Run-all react identically - the plan's "kernel dispatch" wiring re-read through the step-5 architecture (L2 forbids chapter-to-chapter calls; the run-plan is the dispatch). DEVIATION from the P-009 draft: the CSV carries `action`+`target` instead of the draft's single `target_table` (the file action needs a path - the draft predated it). KNOWN BOUNDARY (deliberate): an after_300 spawn persists to the saved SSOT but downstream phases re-stage - the flagship generated-signals absorption lands with its own spec review (the standing gate). Found + fixed at the C-002 surface: the expr parser raised a raw IndexError on a truncated expression (`let(`) - now a located ExprError (the EOF guard); refute round 6: a malformed `/regex/` raised a raw re.error - now a located ExprError at all three regex sites; round 7: a non-integer slice bound (`1.3` typed for `1:3`) and a format spec overflowing on `inf` - now located ExprErrors too; round 8: keep/strict decide over the PARSED free fields (`free_fields`) - a data-function predicate's `$col` and a let-bound name no longer raise a false "missing field"; round 9: keep mode falls back to the token scan for a malformed hole (its pre-round-8 behavior - identity's two-stage tagnames), and `expr.hole_paths` exposes a hole's parsed free paths; STRICT render itself stays TOP-LEVEL (the round-6 implications check refuted a deep-strict pre-scan: it broke the guard functions, misread data-function predicates, failed on empty JSON cells and would have halted project-tier C-008 templates) - both pinned in test_expr_adversarial. Extends [[C-002]] - merge when C-002 re-verifies on PL5. Shipped Siemens config: an EMPTY reactions.csv + templates.yaml carrying the THREE VBA worked examples as executable reference templates. Roadmap unchanged from P-009: fold follower_elements/logic_rules onto the engine (parity-gated steps); E4 per-system expr functions; E5/E6 only on demand. The template-builder pilot stays [[P-012]].
- **Evidence:** .zen/evidence/C-024.md
- **Verification:** automated → Pipeline5App/tests/unit/test_tempemplator.py, Pipeline5App/tests/unit/test_chain_reactions.py, Pipeline5App/tests/unit/test_siemens_main_handlers.py, Pipeline5App/tests/unit/test_expr_adversarial.py, Pipeline5App/scripts/parity_vs_pl4.py | the renderer grammar (recursion/loops/LAZY branches pinned refuter-grade - an absent-field hole / unknown @use / unknown-table @for in the untaken branch never evaluate - + the 3 shipped worked examples rendered for real), the engine lifecycle (compile validation, provenance spawn, append-per-match, audit log replacement, the empty-hook no-op, every failure an ERRR finding), the RUN-PLAN WIRING asserted through the real dispatch (staging fires before_300 with no database then after_300 with the staged one - the smoke's hook recorder; the parity oracle drives staging directly and structurally cannot see this wiring, refuter round 1's find), the parser EOF + bad-regex pins and the C-002 top-level-strict pin, the table-loop column check, the round-6 failure matrix (every former raw exception a located finding, the failed-refire audit replacement, the uid-deduplicated record, the Deferred/settle pair, unfired hooks, index problems recorded), a configured PROJECT-tier rule pair driven through the REAL run_staging (real loaders + defaults, the before_300 Deferred settled, the declared hooks, every failure rendered AND recorded - the only surface that sees the loaders/defaults/render wiring) plus the HALTED path (listed, never recorded), and the byte-parity oracle (the engine lands dark: parity proves that an empty rule set changes nothing AND that the expr edits left the strict emitters byte-identical - it never imports the engine; exit code = verdict).
- **Status:** pending verification

## Pending Contract Deltas

Parked ideas and not-yet-built workstreams. Promote a `P-xxx` to a `C-xxx` once agreed and underway.

### P-014: Shipped source + peek-code provenance navigation + in-app code explorer
- **Date:** 2026-07-16
- **Source:** discovery (user directive 2026-07-16: src ships with the built executable)
- **Description:** The source code SHIPS with the built executable (standing directive - the guide's src:// links already open shipped source). On top of it: (a) PEEK CODE - right-clicking a phase button / log line / database row / output file / config cell opens the code (or chain-reaction RULE) that generated it, resolved from the registries and provenance the app already carries (phase registry handler binding, Finding phase+slug, table ownership + source_*/spawned_by markers, system.emitters + chain_reactions_log); (b) an internal CODE EXPLORER - the Files-tab machinery + syntax highlighting pointed at the shipped source tree, homed on an INTERACTIVE ARCHITECTURE MAP generated from the real package tree + the signpost __init__ docstrings, every node clickable; (c) comments written as a developer MANUAL (the signpost style, app-wide standard). Design consequence (user): runtime navigation carries the discoverability load, so the folder-structure rules soften to structure-light - keep the enforcement contracts (P-008 R2-R5), drop the navigability-driven re-layout (R1/R7 relaxed). RESOLVED (user, 2026-07-16): the app is FULLY OPEN by design - the exe is zero-install convenience, not a boundary ("in my vision, all software should be shipped like this"); the exe build pins a version stamp. The M1-M6 manual-grade commenting standard + the vision piece are recorded in Evidence. Relates to [[C-021]] (softens it), [[P-006]] (the guide narrows to the operator path), [[C-024]] (rule/template provenance).
- **Evidence:** .zen/evidence/P-014.md
- **Proposed verification:** manual: pilot acceptance - right-click peek on a phase button, a log line, a database row, and an output file each opens the generating code/rule; unit tests for the provenance resolvers (registry->handler source, finding slug->emit site, table->owning phase, file->emitter/rule)

### P-013: Intervalzero_RTX toolchain + 3 system stubs
- **Date:** 2026-07-16
- **Source:** ingest (another-big-step-now-curried-pnueli.md#step7)
- **Description:** The IPC_Based/Intervalzero_RTX toolchain layer (shared by the 3 systems: rtx symbols, output_layout, tag_table_format [shared i/o tags format - user], cpci_hardware [shared hardware configuration - user]) + the sorter/induction/plant system packages (descriptor, main.py with a minimal PhaseSet: staging + a stub delivery phase, config skeletons incl. their address_format). The first external validation of the System contract before RTX emitter investment. RTX delivery artifacts are expected to be largely template-authored via [[C-024]] reactions (the Tempemplator workflow industrialized); actual emitters/formats are a LATER effort, specified when the RTX surfaces are defined. Its run-plans take on the [[C-024]] run-plan duties: pass their `hooks` to every fire and settle a database-less hook's `Deferred` once the phase gate passes (a halted phase lists the deferred firings). Depends on [[C-021]].
- **Proposed verification:** an intervalzero_rtx_sorter project scaffolds, opens, and stages the shared I/O List into its own Database/; registering sorter flips its New-project row available (availability-from-registry proven); the Siemens byte-parity re-run is untouched

### P-012: Template-builder pilot (context-aware editor)
- **Date:** 2026-07-16
- **Source:** ingest (another-big-step-now-curried-pnueli.md#template-builder-pilot)
- **Description:** A context-aware template editor piloting on chain_reactions/templates.yaml - the upgrade over Tempemplator's static .scl highlighting (xlSyntaxHighLight.bas). Composes existing machinery: the fx dialog (gui/expr_builder.py - lint squiggles, autocomplete, live preview against a REAL SSOT row) + FileXY's langs.json language highlighting. Two-layer highlight (target language UNDER template constructs: @directives, {expr} holes, template refs); context-aware autocomplete (the rule's source_table columns + params + loop vars + template names); live expansion preview against selected SSOT row(s). Reachable from the Files tab; iterate after the pilot. Extends C-019 - merge at promotion. Depends on [[C-024]]. The lint must match the CONSUMERS (round-6 implications): the preview renders STRICT against the selected row, and `$row.column` inside a @for table loop is checked against that table's columns - the renderer's schema check - so the builder never approves a template the engine rejects.
- **Proposed verification:** manual: pilot acceptance by the user over templates.yaml (two-layer highlight visible, autocomplete offers real source-table columns + template names, live expansion preview on a real SSOT row) + unit tests for the lint layer (unknown field via expr Scope, unknown template ref, unbalanced @if/@end)

## P-001: Stand up Pipeline5App — the reorganized successor package
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** Create `Pipeline5App` as the public-ready successor to `Pipeline4App`, carried forward from the frozen `pl4` baseline, and reorganize + rename the messy `.py` modules into a clean, coherent structure (the reviewed rename map). Preserves the capabilities in C-001…C-020; this is the umbrella under which each is re-verified against the new package (its clause link then moves PL4→PL5 and flips to verified after a recorded run + refute). EXECUTION PLAN approved 2026-07-16 (7 steps, migration = move-then-modify): the system-type plugin architecture [[C-021]] is the organizing spine; [[C-024]]–[[P-013]] are its capability deltas. PROGRESS: steps 1–2 LANDED 2026-07-16 — the shell + the full kernel move with the rename map applied (194 files, 130 renamed; the whole 61-file suite green in the new layout; see Evidence), plus the REGROUP pass under the user's regrouping grant (config → paths/params/loaders package with a re-exporting signpost `__init__`; filexy_shim/excel_goto/report_runner renames; signpost docstrings on every kernel package; suite re-proven green after each). The C-001…C-020 verification links stay on the still-resolving PL4 tests until the deliberate re-verification pass (recorded run + refute per clause).
- **Verification:** manual: acceptance = the C-001…C-020 suite runs green against the new `Pipeline5App` layout, each re-verified clause carries a fresh recorded run, and the committed byte-parity oracle (`Pipeline5App/scripts/parity_vs_pl4.py`, frozen PL4 vs PL5 over the builtin fixture docs) reports 0 diffs on every BuilderData surface + SSOT table.
- **Evidence:** .zen/evidence/P-001.md
- **Status:** pending verification

## P-002: Review & consolidate configuration data + workflows
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** Audit the `config_project/` data and the GUI/pipeline workflows for a public release: remove dead/superseded config, confirm every workflow is reachable and correct, and ensure no capability depends on an undocumented or default-baked config value (see [[no-baking-defaults-without-review]], [[project-config-completeness-review]]). PARTIALLY EXECUTED by the approved PL5 plan's config rename/regroup (ingest: another-big-step-now-curried-pnueli.md#config-layering — shared vs per-system tiers, `input_docs/`+system `user_input/` dissolve, `chain_reactions/` reborn as the [[C-024]] engine home, the Siemens-only `project_params` keys relocated); the remaining scope is the workflow review + dead-config audit.
- **Verification:** manual: acceptance = a written config/workflow review with each gap either fixed or captured as a clause.
- **Status:** pending verification

## P-003: Test environment with complete coverage
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** A test environment that exercises the whole pipeline end-to-end with complete coverage — closing the gaps the current data-independent unit gate leaves (the GUI is a manual smoke today; several phases are proven only by scratch parity scripts, not committed tests). Coverage is enforced as a floor that fails the run below threshold, not a reported number.
- **Verification:** manual: acceptance = a committed end-to-end/coverage gate that exits non-zero below the agreed threshold; becomes the verification link for the re-verified phase clauses.
- **Status:** pending verification

## P-004: Review & rationalize the logs
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** Review the pipeline's log output for the public release — consistency of severity use, message clarity, no noise/leaks, and that every log line an operator sees is intentional and localizable (ties into [[C-003]] severity and [[C-017]] i18n).
- **Verification:** manual: acceptance = a log review pass with the agreed changes landed.
- **Status:** pending verification

## P-005: i18n applied everywhere
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** Extend [[C-017]] from "logs + reports + chrome" to full coverage: audit every user-facing string (GUI, dialogs, guide, errors) so nothing operator-visible is hardcoded and both EN and IT are complete. This is the expansion goal, distinct from the existing capability C-017 already verifies.
- **Verification:** manual: acceptance = an i18n coverage audit showing zero hardcoded user-facing strings, both languages complete.
- **Status:** pending verification

## P-006: Complete the user guide
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** Finish the in-app / shipped guide (`docs/guide/`) so every phase and tool has real instructions — no "no instructions provided" stub pages remain — bringing it to public-release quality.
- **Verification:** manual: acceptance = the guide-stub authoring TODO is empty and each phase/tool section has real content.
- **Status:** pending verification

## P-007: Release v1.0 to the public
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** Ship the first official public version of the pipeline — the milestone that P-001…P-006 feed into: packaging, versioning, and the public-facing release once the surface (C-001…C-020) is re-verified on `Pipeline5App`.
- **Verification:** manual: acceptance = a tagged v1.0 release with C-001…C-020 verified against Pipeline5App and P-002…P-006 closed.
- **Status:** pending verification
