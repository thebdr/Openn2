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
- **Description:** `use_project()` repoints the loaders, the `Database/` folder, and the `Output/` tree at a chosen project or the builtin `Shared/`. Nested `project_params.yaml` schema with a safe dotted `get_param` accessor; `generation_params.yaml` and `app_config.yaml`; tolerant config-CSV readers over the table codec. Missing config surfaces a pointed WARN, never a code-baked default.
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
- **Description:** Read the configured I/O List and C&E matrix into the `signals` fact table: resolve each row's `type` (object cell), annotate C&E areas, derive document-side identity (FLDs, tag names), positional node address ranges, and `IsSorterArea`; also stage the `diagnosis_cabinets` table. Split into `stage_iolist` (310, no C&E) then `annotate_cematrix` (320) composing byte-identically. Blocking findings on missing I/O sheet / duplicate `(script_type, index)`.
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

## Pending Contract Deltas

### P-014: Shipped source + peek-code provenance navigation + in-app code explorer
- **Date:** 2026-07-16
- **Source:** discovery (user directive 2026-07-16: src ships with the built executable)
- **Description:** The source code SHIPS with the built executable (standing directive - the guide's src:// links already open shipped source). On top of it: (a) PEEK CODE - right-clicking a phase button / log line / database row / output file / config cell opens the code (or chain-reaction RULE) that generated it, resolved from the registries and provenance the app already carries (phase registry handler binding, Finding phase+slug, table ownership + source_*/spawned_by markers, system.emitters + chain_reactions_log); (b) an internal CODE EXPLORER - the Files-tab machinery + syntax highlighting pointed at the shipped source tree, homed on an INTERACTIVE ARCHITECTURE MAP generated from the real package tree + the signpost __init__ docstrings, every node clickable; (c) comments written as a developer MANUAL (the signpost style, app-wide standard). Design consequence (user): runtime navigation carries the discoverability load, so the folder-structure rules soften to structure-light - keep the enforcement contracts (P-008 R2-R5), drop the navigability-driven re-layout (R1/R7 relaxed). RESOLVED (user, 2026-07-16): the app is FULLY OPEN by design - the exe is zero-install convenience, not a boundary ("in my vision, all software should be shipped like this"); the exe build pins a version stamp. The M1-M6 manual-grade commenting standard + the vision piece are recorded in Evidence. Relates to [[P-008]] (softens it), [[P-006]] (the guide narrows to the operator path), [[P-009]] (rule/template provenance).
- **Evidence:** .zen/evidence/P-014.md
- **Proposed verification:** manual: pilot acceptance - right-click peek on a phase button, a log line, a database row, and an output file each opens the generating code/rule; unit tests for the provenance resolvers (registry->handler source, finding slug->emit site, table->owning phase, file->emitter/rule)

### P-013: Intervalzero_RTX toolchain + 3 system stubs
- **Date:** 2026-07-16
- **Source:** ingest (another-big-step-now-curried-pnueli.md#step7)
- **Description:** The IPC_Based/Intervalzero_RTX toolchain layer (shared by the 3 systems: rtx symbols, output_layout, tag_table_format [shared i/o tags format - user], cpci_hardware [shared hardware configuration - user]) + the sorter/induction/plant system packages (descriptor, main.py with a minimal PhaseSet: staging + a stub delivery phase, config skeletons incl. their address_format). The first external validation of the System contract before RTX emitter investment. RTX delivery artifacts are expected to be largely template-authored via [[P-009]] reactions (the Tempemplator workflow industrialized); actual emitters/formats are a LATER effort, specified when the RTX surfaces are defined. Depends on [[P-008]].
- **Proposed verification:** an intervalzero_rtx_sorter project scaffolds, opens, and stages the shared I/O List into its own Database/; registering sorter flips its New-project row available (availability-from-registry proven); the Siemens byte-parity re-run is untouched

### P-012: Template-builder pilot (context-aware editor)
- **Date:** 2026-07-16
- **Source:** ingest (another-big-step-now-curried-pnueli.md#template-builder-pilot)
- **Description:** A context-aware template editor piloting on chain_reactions/templates.yaml - the upgrade over Tempemplator's static .scl highlighting (xlSyntaxHighLight.bas). Composes existing machinery: the fx dialog (gui/expr_builder.py - lint squiggles, autocomplete, live preview against a REAL SSOT row) + FileXY's langs.json language highlighting. Two-layer highlight (target language UNDER template constructs: @directives, {expr} holes, template refs); context-aware autocomplete (the rule's source_table columns + params + loop vars + template names); live expansion preview against selected SSOT row(s). Reachable from the Files tab; iterate after the pilot. Extends C-019 - merge at promotion. Depends on [[P-009]].
- **Proposed verification:** manual: pilot acceptance by the user over templates.yaml (two-layer highlight visible, autocomplete offers real source-table columns + template names, live expansion preview on a real SSOT row) + unit tests for the lint layer (unknown field via expr Scope, unknown template ref, unbalanced @if/@end)

### P-011: Per-system GUI projection + multi-system selector
- **Date:** 2026-07-16
- **Source:** ingest (another-big-step-now-curried-pnueli.md#gui-integration,step5)
- **Description:** The GUI becomes a projection of the active System: gui/phase_model.py PhaseSet per system (the global PHASES tuple dies), Phase.handler strings key system.handlers (handlers live in the system's main.py, receiving a PhaseContext), icons/i18n stay add-a-row. Project creation: systems.catalog() replaces PROJECT_TYPES (availability = registry membership); project meta types/multi_system finally CONSUMED at open (old PL4 ids get a pointed this-is-a-PL4-project error, no migration). Multi-system v1 = active-system selector (toolbar, visible when >1 type): switches phase bar + config resolver + Database/<sid>/ + Output/<sid>/; Run-all = active system only; single-system projects keep flat Database/ + Output/ (OP4 path compatibility). Extends C-018 - merge at promotion.
- **Proposed verification:** GUI phase-model tests (PhaseSet helpers, handler dispatch via system.handlers, catalog-driven dialog, meta-consuming open with pointed unknown-id error) + a real-data run of every phase button + Run-all output parity vs PL4

### P-010: Config-driven I/O address format (regex)
- **Date:** 2026-07-16
- **Source:** ingest (another-big-step-now-curried-pnueli.md#coupling7)
- **Description:** The I/O address NOTATION differs per system and must be config, not code (user correction 2026-07-16). The %I10.3-style parsing hardcoded in staging (_addr_byte, _add_node_address_ranges) and identity (is_io_signal) becomes a regex-style address_format config entry (named groups: direction/byte/bit + which direction tokens mean input vs output), shipped as each system's default in its config_root (Siemens: %I/%Q; RTX: its own), project-overridable via the 4-tier resolver. Staging itself stays 100% shared. Extends C-006 - merge at promotion.
- **Proposed verification:** address_format regex parsing tests: the Siemens %I/%Q pattern byte/bit-exact vs PL4 over the builtin fixture + a synthetic alternate pattern proving a non-Siemens notation parses without code change

### P-009: Chain-reaction engine + Tempemplator text renderer
- **Date:** 2026-07-16
- **Source:** ingest (another-big-step-now-curried-pnueli.md#chain-reaction-engine,step6)
- **Description:** A kernel rule engine (domain/chain_reactions/) - the app's conditional-data-creation spine. A rule = fire_when (before_<phase>/after_<phase>, wired into the kernel phase dispatch so phase buttons AND Run-all fire identically) + condition (core/expr over each row of a source SSOT table) + action. TWO action kinds: add_rows (spawn rows into ANY SSOT table, every field expr-filled, one match may spawn many rows) and file (render a recursive text template and APPEND - the only mode, created if absent, user responsible for resets; path expr-rendered). The renderer domain/chain_reactions/tempemplator.py integrates the user's Tempemplator VBA tool upgraded onto core/expr: {$field} substitution, named recursive templates in templates.yaml (UNIFIED row + text templates), @use/@for/@if directives (structure = renderer, values = expr, mirroring the original guillemet/dollar split), loops over a count OR an SSOT table query. Expansions: E1 layered scope (row+params+loop vars+$_rule), E2 @-directive grammar, E3 table-query loops; E4 per-system expr functions (with [[P-008]]); E5 arithmetic / E6 inline-if sugar deferred. Config: chain_reactions/reactions.csv + templates.yaml (per-system tier). Traceability: spawned_by + source_uid provenance on every row, chain_reactions_log SSOT table records every firing and file append. Roadmap: fold interfaces/follower_elements.csv + diagnosis/logic_rules.csv onto the engine (parity-gated, separate steps); generated-signals flagship use AFTER its spec review. Promotes to the planned C-022.
- **Proposed verification:** hermetic engine tests: rule parse, condition match, multi-row spawn + provenance, before/after hook ordering, bad-expr located findings; renderer: recursion, count + table-query loops, @if/@else, append-creates-if-absent, path rendering; the 3 worked Tempemplator examples as fixtures; byte-parity re-run with an empty rule set (changes nothing)

### P-008: System-type plugin architecture (PL5 spine)
- **Date:** 2026-07-16
- **Source:** ingest (another-big-step-now-curried-pnueli.md#architecture,steps1-5)
- **Description:** Pipeline5App is organized around explicit System descriptors: a systems/ tree (platform -> toolchain -> system; taxonomy PLC_Based/SiemensS7/Safety + IPC_Based/Intervalzero_RTX/{Sorter,Induction,Plant}), each system a folder with a main routine (phase handlers) calling shared kernel + toolchain + custom functions. The System object carries id (taxonomy ids: siemens_s7_safety, intervalzero_rtx_*), capabilities (needs_ce_matrix, needs_diagnosis_blocks - shared code gates by FLAG, never by type id), phases (PhaseSet), handlers, symbols (binding/quote), emitters (emit_kind -> writer), builders (BuilderRegistry instance), output_layout, config_root. Discovery is explicit (systems/catalog.py: ALL_SYSTEMS/by_id/catalog/PLANNED); dialog availability = registry membership. Kernel code NEVER branches on a type id. Resolves the 10 PL4 couplings incl. plc_binding -> system.symbols.binding and per-system emitter tables. Executes under [[P-001]]; extends C-004 (4-tier config resolver: project-system -> project-shared -> system-builtin -> shared-builtin, neither -> raise) - merge at promotion. Promotes to the planned C-021. STRUCTURE DECIDED + LANDED (2026-07-17): the user approved THE BLEND - Chaptered Pipeline skeleton (components own capability) + Shop Manual part naming (language/truth/documents/findings/config/phases/systems/project/workbench/app) + Phasebook per-phase panels (arrive at step 5). Executed as a mechanical move (102 modules re-homed, 62/62 suite green) with the four laws MACHINE-ENFORCED by tests/unit/test_architecture_contracts.py (L1 layers - zero exceptions on day one; L2 phases-as-filters with a 7-edge Kraken-style ratchet, each edge tagged with its burn-down step; L3 systems sealed; L4 headless pipeline). Full record in Evidence.
- **Evidence:** .zen/evidence/P-008.md
- **Proposed verification:** plugin-seam tests (registry uniqueness/by_id/catalog, 4-tier config resolution fail-loud, BuilderRegistry isolation, emitter routing raises on unknown kind, capability gating via a needs_ce_matrix=False stub, PhaseSet helpers, handler dispatch, per-system scaffolding + assert_config_complete, multi-system Database/Output routing) + the grep-gate (no kernel import of systems/*, no system-id literal in kernel) + byte-parity 0 diffs vs frozen PL4

Parked ideas and not-yet-built workstreams. Promote a `P-xxx` to a `C-xxx` once agreed and underway.

## P-001: Stand up Pipeline5App — the reorganized successor package
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** Create `Pipeline5App` as the public-ready successor to `Pipeline4App`, carried forward from the frozen `pl4` baseline, and reorganize + rename the messy `.py` modules into a clean, coherent structure (the reviewed rename map). Preserves the capabilities in C-001…C-020; this is the umbrella under which each is re-verified against the new package (its clause link then moves PL4→PL5 and flips to verified after a recorded run + refute). EXECUTION PLAN approved 2026-07-16 (7 steps, migration = move-then-modify): the system-type plugin architecture [[P-008]] is the organizing spine; [[P-009]]–[[P-013]] are its capability deltas. PROGRESS: steps 1–2 LANDED 2026-07-16 — the shell + the full kernel move with the rename map applied (194 files, 130 renamed; the whole 61-file suite green in the new layout; see Evidence), plus the REGROUP pass under the user's regrouping grant (config → paths/params/loaders package with a re-exporting signpost `__init__`; filexy_shim/excel_goto/report_runner renames; signpost docstrings on every kernel package; suite re-proven green after each). The C-001…C-020 verification links stay on the still-resolving PL4 tests until the deliberate re-verification pass (recorded run + refute per clause).
- **Verification:** manual: acceptance = the C-001…C-020 suite runs green against the new `Pipeline5App` layout, each re-verified clause carries a fresh recorded run, and the committed byte-parity oracle (`Pipeline5App/scripts/parity_vs_pl4.py`, frozen PL4 vs PL5 over the builtin fixture docs) reports 0 diffs on every BuilderData surface + SSOT table.
- **Evidence:** .zen/evidence/P-001.md
- **Status:** pending verification

## P-002: Review & consolidate configuration data + workflows
- **Date:** 2026-07-16
- **Source:** discovery
- **Description:** Audit the `config_project/` data and the GUI/pipeline workflows for a public release: remove dead/superseded config, confirm every workflow is reachable and correct, and ensure no capability depends on an undocumented or default-baked config value (see [[no-baking-defaults-without-review]], [[project-config-completeness-review]]). PARTIALLY EXECUTED by the approved PL5 plan's config rename/regroup (ingest: another-big-step-now-curried-pnueli.md#config-layering — shared vs per-system tiers, `input_docs/`+system `user_input/` dissolve, `chain_reactions/` reborn as the [[P-009]] engine home, the Siemens-only `project_params` keys relocated); the remaining scope is the workflow review + dead-config audit.
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
