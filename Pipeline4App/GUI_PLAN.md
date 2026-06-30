# PL4 — GUI PORT PLAN

The PL4 backend has **8 of the 9 generative phases built** (300/520/400/510/600/700/800/900/100 + the S1–S6
severity model, each parity-verified vs PL3) — **ph200 (Documents Fill Out) is NOT built**, so PL4 currently
requires a **PRE-FILLED I/O List** (it READS script_type/index/diag, it does not COMPUTE them); ph200 is the
last backend effort (STEP 4). `HANDOFF.md` has the backend state. This is the plan for the **GUI port**:
replicate PL3's operator GUI **and** add the SSOT-native features PL3 could never have, with **EN/IT i18n a
first-class shipped feature** (STEP 1, DONE). Same toolkit as PL3 (Tkinter + sv-ttk + Monaspace).

## Locked decisions (user, 2026-06-28)
1. **Sequence: NEW features first** — foundations (worker thread) → Findings panel → Database Explorer →
   structured log → Run-all → Files tab → Project Manager → polish.
2. **Database Explorer = in-memory SQLite** (stdlib `sqlite3`, no new deps): load the SSOT tables into
   `:memory:`, a real SQL box with cross-table JOINs (on `uid`/`source_signal`/`db_name`) + `json_extract()`
   for the JSON cells. A read-only query console (the on-disk CSVs are untouched) + saved/sample queries.
3. **SSOT table grids = VIEW-ONLY first** (editing risks the byte-stable JSON-cell parity; add later through
   the `table.read_csv`/`write_csv` codec if needed).
4. **A lightweight PL4 phase registry** drives the bar + the chevron sub-phases + the dependency-ordered
   Run-all (one source of phase no/title/sub-phases/deps/handler — avoids re-encoding the phase order twice).

## Target shape
A notebook on the shared shell:
```
toolbar: brand · [Project ▾] · Run-all · ◐theme · lang · log-to-file
phase bar: Run + 100·300·400·500·600·700·800·900  (each a chevron ▾ of its sub-phases)
[ Log | Files | Database Explorer | Findings ]   + status bar + progressbar
```

## What PL4 already provides (this is a PORT, not a rewrite)
- The runnable `gui/` shell: `app_main.App` (each `_run_*` stages → runs a phase → renders findings via
  `run.gate`/`run.render(findings, log_append)`), `phasebar.PhaseBar` (coloured tk.Buttons), `LogView`
  (per-level tags + the `app_config` log-level filter), `theme.apply_theme` (sv-ttk + graceful fallback).
- **`io/render.py` already emits `render_records` → `RenderRec(kind, level, text, links, uid)` with
  `LinkSpan(start,end,doc)`** — the SAME structured shape PL3's clickable log consumes (the M1 backend is done).
- The Finding/treatment/severity spine: `core/finding.py` (`validation_issues_table`/`record`, the rich
  `location2/doc2/info/cmp` payload), `core/treatments.py` (`load`/`apply`/`effective_severity`/
  **`set_treatment`** = the 1-click hook), `core/run.py` (`gate`/`render`/`has_blocking`).
- The 14 SSOT tables on disk under `Shared/Database/` via `core/table.py` (declared columns/json_columns/
  key_columns, the deterministic byte-stable codec, fail-loud `read_csv`, `effective_columns`) + `database.py`.
- The report projections: `io/render.py` (`render_text`/`render_html`/`reports`/`html_reports`) +
  `coverage.render_txt`/`render_csv`.

PL3's `gui/` (`app_main`/`phasebar`/`logview`/`files`/`grid`/`objedit`/`xlsxview`/`extedit`/`excel`/`theme`/
`fonts`/`darktitle`) + `project/` (`project.py`/`state.py`) are the near-drop-in source for the parity ports.

## Milestones (each gate-green + committed on the user's word)
- **M0 — Foundations. DONE** (the worker thread + registry + notebook + Run-all). `gui/phases.py` (the
  lightweight registry: number/title/kind/subs/requires/handler + `RUNNABLE`/`run_order`/`by_number` - the
  single source the bar + dispatch + Run-all consume; ph200 Fill is wired but kept out of Run-all by design).
  The **worker thread + queue/drain pump**:
  `_on_phase` spawns a daemon thread per click, the handler emits via `self._emit`/`self._status` (thread-safe
  enqueue) instead of touching Tk, `_drain` (`root.after(50)`) applies log/status/done on the main thread, a
  `ttk.Progressbar` + a `_busy` guard grey the bar during a run (single-phase runs no longer freeze the
  window). A basic **Run-all** (registry `run_order`, each handler self-contained / re-stages - M4 optimizes to
  a stage-once shared DB). The **`ttk.Notebook`** scaffold (the Log tab; Findings/Explorer/Files tabs slot in
  later). `phasebar` is registry-driven + `set_enabled`. Tests: `test_gui_phases.py` (4). Verified: py_compile +
  a headless construction smoke (9 buttons, 1 tab, drain wired); the live worker-run is the manual launch check.
  **M0b partly DONE:** `gui/fonts.py` (port of PL3's - registers the bundled `assets/fonts/MonaspaceNeon-Var.ttf`
  privately via `AddFontResourceEx(FR_PRIVATE)`, resolves `Monaspace Neon Var`, Consolas fallback) +
  `theme.apply_theme` now makes it the **app-wide UI font at `APP_FONT_SIZE=13`** (the named Tk fonts +
  `theme.MONO_FONT`; chrome + phase bar + log). **M0b chrome remainder DONE (STEP 1):** `gui/darktitle.py`
  (the Windows immersive dark title bar via `DwmSetWindowAttribute` + `SetWindowPos` FRAMECHANGED, applied
  LAST in `__init__`/`_toggle_theme` so it doesn't flush sv-ttk against a half-built window) + a full light/
  dark re-theme (`theme.bg_for`/`fg_for`/`log_colors_for`/`phasebar_bg` + `set_theme(mode)` on LogView /
  PhaseBar / DatabaseExplorer / FilesPanel, all driven by `_toggle_theme`). Test: `test_gui_fonts.py`.
- **M1 — Structured clickable log. DONE** (PL3 parity). `LogView` rewritten as a Frame+Text with v/h
  scrollbars + `append_records` (over `io.render.render_records`): banners, level-coloured lines, **clickable
  `Sheet!Cell` spans** → `gui/excel.py` (verbatim COM port; reuse an open Excel, graceful `os.startfile`
  fallback) on `on_link`, and a treatable line's `[LEVEL]` is an **errlink** → right-click Treat
  (fail/error/warn/skip/ignore/clear). A **Levels ▾ dropdown** (a checkbox per severity level; FAIL+ERROR
  always shown + greyed/disabled) toggles visibility LIVE via per-level elide and **persists the combination to
  `app_config.yaml`** (`config.save_app_log_levels`, comment-preserving round-trip). The GUI's
  `_gate`/`_render` (replacing `run.gate`/`run.render` in the handlers) produce structured records via
  `findings_view.apply_and_records` (apply the registry → render the EFFECTIVE-severity findings) posted
  through the worker queue → the clickable log. `_on_link` resolves the doc basename → the configured workbook
  → `excel.goto` (off-thread); `_on_errtreat` → `set_treatment` + refresh the Findings panel. Tests:
  `apply_and_records` (+1).
- **M2 — Findings panel. DONE** *(NEW)*: `gui/findings_view.py` (the pure join: `panel_rows` =
  `validation_issues` ⋈ the registry with the EFFECTIVE severity per uid, `filter_rows`, `apply_treatment` =
  create-or-update the registry row — more forgiving than `set_treatment` so a freshly-shown finding treats
  immediately) + `gui/findings_panel.py` (a `ttk.Treeview` tab: phase/type/severity/**effective**/treatment/
  location/detail, phase + effective-severity filter combos, severity-coloured rows, **right-click → Treat as
  FAIL/ERROR/WARN/SKIP/IGNORE / Clear** → writes `error_management.csv` → re-render; `refresh()` reloads the
  table + registry, auto-called after each run via the drain's `done`). Tests: `test_gui_findings.py` (3).
  NOTE: `validation_issues` reflects the LAST run's findings (each phase re-stages + rebuilds the table), so
  the panel shows that run's set; treatments persist by uid across runs. A cumulative cross-phase view waits on
  the engine's per-run union-reconcile.
- **M3 — Database Explorer. DONE** *(NEW, headline)*: `gui/dbquery.py` (the engine, tested:
  `build_memory_db(db_dir)` loads every `Database/*.csv` into `:memory:` SQLite [one TEXT-column table each,
  JSON cells as their JSON string → `json_extract()` works], `run_query` → (columns, rows), `SAMPLE_QUERIES`
  showcasing SELECT */json_extract/GROUP BY/JOIN) + `gui/db_explorer.py` (the tab: a schema sidebar
  [double-click a table → `SELECT * FROM`], a SQL editor [Ctrl+Enter], a results grid, a samples combobox, a
  Refresh that reloads + auto-refresh after a run). Read-only over an in-memory copy (the CSVs are never
  touched). Tests: `test_gui_dbquery.py` (4). Real `Database/` loads all 14 tables into the explorer.
- **M4 — Run-all + sub-phase dropdowns. DONE** *(NEW: live progress)*: the phase bar is now a faithful
  port of PL3's **2-row registry-driven grid** — the pink Run master (spans both rows) · `➡` separators ·
  per-phase **header** (row 0, runs the phase) + a grey **▼ chevron** (row 1) that opens an anchored,
  click-away / Escape-close / blur-poll **`_Dropdown`** popup listing that phase's `subs`. PL4 NOTE: a
  handler is monolithic (620 SCL still needs stage→520→build), so a **sub-step button RUNS ITS PARENT
  PHASE** like the header — the dropdown is the visual MAP of a phase; independent per-sub-phase runs wait
  on the engine. **Run-all** (`_run_all`) now drives a **determinate** progressbar (one `progress_step`
  per completed phase; a single phase still bounces indeterminately), emits a `[k/N] <num> <title>`
  per-phase marker, and **halts the chain on a blocking FAIL** (`_gate` sets `self._run_halted`; the
  remaining phases are skipped + logged). `theme` gained a `chevron` fill. Stage-once Run-all optimization
  stays DEFERRED (explicitly optional; each handler self-stages). Tests: `test_gui_phasebar.py` (3, the
  pure `_wrap`); verified by py_compile + a headless construction smoke (9 header/run buttons, 8 chevrons,
  the 600 dropdown fires the parent phase + closes, the determinate Run-all bar). The live dropdown/bar
  are the manual `launch_gui.py` check. **Adversarially reviewed pre-commit** (a 5-dimension workflow);
  3 confirmed findings HARDENED: (1) `_Dropdown.close` now removes ONLY its own `<Button-1>` handler from
  the global 'all' bindtag (`_remove_global_binding`) instead of `unbind_all` wiping every global hook;
  (2) the first blur-poll `after` id is captured so a fast close cancels it; (3) `_run_all` wraps each
  per-phase call so a handler CRASH is attributed to the named phase + stops the chain with the same
  "N remaining skipped" accounting a gate-halt gets (no bare traceback that hides the lost phases).
- **M4 REWORK (user feedback). DONE**: the bar/registry now follow the **operator ORACLE
  `Pipeline3App/assets/ButtonsLayout.xlsx`** (the canonical button map). (a) **`gui/phases.py` rebuilt from the
  oracle** — every phase carries its FULL sub-button set (`Sub(number,title,kind,enabled,opens)`): action /
  open / special, in oracle order, minus phase 200 (no Fill). Deferred/unported buttons (150, 155/156 Clean,
  320, 430, 810, 840, 920) are kept **VISIBLE but greyed** (`enabled=False`) for 1:1 oracle fidelity (user
  decision). (b) **Sub-buttons RUN THEIR SUB-PHASE, not the whole phase** (PL3's model) — each handler now
  takes `only=None|<sub#>`; the App's `_sub_command`/`_on_sub`/`_sub_worker` dispatch an action sub to
  `phase_of_sub(n).handler(only=n)`, which builds the prerequisites then runs ONLY that sub-phase's projection
  (e.g. `only=510` still builds 520 since I/O Tags needs the write-back; `only=520` skips the I/O-Tags leg).
  Validation 110/120/130/140 each run their own validator (`run_iolist`/`run_ce_matrix`/`run_xcheck_*`);
  hardware 710/720 share one extract (each writes both CSVs, like PL3). (c) **Open buttons wired** —
  `_on_open`/`_open_target` `os.startfile` the resolved folder/file (13 wired keys). (d) **Layout** — all
  header/run buttons are **EQUAL width** (`width=_BTN_WIDTH=16`) and the **dropdown width MATCHES the column
  above** (`geometry width = anchor.winfo_width()`); a thin divider separates the action steps from the
  open/special tail; disabled subs render greyed. Verified: gate **32 files** (`test_gui_phases.py` rebuilt to
  the oracle, +`subs_match_oracle`/`kinds_and_enablement`/`phase_of_sub`); a headless smoke (equal widths,
  dropdown 5-buttons-with-2-greyed + width-match, `only=` dispatch); and a **real-data run of every `only=`
  branch** (310/520/510/610/620/710/820/830/110/130 all PASS, 0 errors). Reviewed pre-commit (5-dimension
  workflow).
- **M5 — Files tab. DONE** *(view-only, decision #3)*: `gui/files_view.py` (the Tk-free logic, tested:
  `allowed`/`viewer_kind` ext dispatch, `populate` [the pruned/sorted file tree], `file_sections` [the 3
  sections under the active config/project], `sniff_delim`/`read_csv_rows`, `read_xlsx`) + `gui/files_panel.py`
  (the `FilesPanel` tab: a 3-section tree [Project configuration / User editable files / Generated output] on
  the left, a read-only viewer on the right - a `.csv` opens in a ttk.Treeview grid, an `.xlsx`/`.xlsm` in a
  grid + sheet picker [openpyxl `data_only`, capped 3000x80], a `.yaml`/`.json`/`.xml`/`.scl`/text file in a
  monospace text pane; every viewer carries a path strip + **Open externally** / **Open folder**) + `gui/
  extedit.py` (port of PL3's: LibreOffice-then-OS-default open + `reveal` the folder). ttk-only (NO tksheet /
  ruamel deps - the rich object editor + in-app grid editing wait on the codec-write path). Wired into
  `app_main` (the Files tab after Log; `_file_sections` re-resolved from `config.load_params()`, refreshed
  after each run + on a theme toggle [`set_theme` re-themes the text pane]). Tests: `test_gui_files.py` (7).
  GUI-verified on screen: the 3-section tree over the real project, the CSV grid (`db_blocks.csv`), the YAML
  text pane (`app_config.yaml`), and the light/dark toggle following through.
- **M6 — Project Manager. DONE** *(STEP 3 complete)*: `pipeline4/project/` (clean-room port of PL3's,
  tested) - `state.py` (`%LOCALAPPDATA%/Pipeline4/state.json`: projects_root + recent + last_opened, storing
  project ROOT folders) + `project.py` (`is_project` [a folder with config_project/project_params.yaml],
  `open_project` [validate -> `config.use_project` + push_recent], `close_project` [`use_builtin` + clear
  last], `new_project` [scaffold: copy the builtin config_project + Database/+Output/, then open],
  `auto_reopen` [re-point at last_opened on launch]). Wired into `app_main`: a toolbar **Project ▾**
  menubutton (New / Open / Recent ▸ [postcommand-rebuilt, marks the active] / Set projects root / Close,
  Close disabled on builtin), `auto_reopen()` at launch, an active-project **title indicator**
  (`...  -  <name>` / `builtin (Shared)`), and `_apply_project_switch` (retitle + reload Files/Explorer/
  Findings against the new config/Database). i18n `tb_project`/`pm_*` keys (EN/IT). Tests: `test_project.py`
  (6). GUI-verified on screen: the Project ▾ menu + the builtin title marker.
- **i18n (EN/IT) — DONE (STEP 1, first-class, NOT polish).** The POINT of i18n here is the operator-facing
  **validation LOGS + reports** (an Italian operator must read the findings in Italian), with the chrome a
  secondary benefit.
  - **The LOGS (the core):** `domain/validation/messages.py` is now **bilingual** (the 50 `v_*` slugs, EN
    verbatim [byte-identical, parity-verified] + IT from PL3). A finding's `detail` is built in the ACTIVE
    language - PL3's `tr("v_<type>", ctx.lang)` model, ported as an **ambient** `messages.active_lang(lang)`
    (PL4 has no ctx; the GUI runs one phase at a time so the ambient is single-threaded; default `en` keeps
    the parity oracle English). So the 53 builder call sites + `io/render.py` are UNTOUCHED - the rendered
    log line + the `.txt`/`.html` reports come out localized. `phase.run_validation(…, lang)` wraps the 4
    validators in `active_lang`, localizes the sub-phase banners (`_BANNER_KEYS` -> the registry `pb_*`
    keys), and `render.html_reports(items, lang)` localizes the report title + summary (`rpt_*` keys). The
    GUI `_run_validation` threads `self.lang` (the `only=None` full run + an `active_lang` wrap for an
    individual `only=110/120/130/140` validator). **PL3-faithful: the `uid` hashes the localized detail**,
    so treatments key per operating language (an operator works in one language). Verified on real data: the
    EN/IT banners + WARN finding text differ correctly; EN byte-identical to pre-i18n.
  - **The CHROME:** `core/i18n.py` (`tr(key, lang, **fmt)`) + `gui/phases.py` `name_key`/`label_key` (no
    English literals) + `phasebar.PhaseBar(lang=…)`/`set_lang()` + the toolbar **Lang EN/IT** button
    (live-retranslates the bar + toolbar + tabs + status; persists to `app_config.yaml` via
    `config.load_app_ui()["language"]` + `save_app_language`).
  - **Stays EN** (a noted boundary, PL3-consistent): the GENERATOR run-log data-lines (`staged 269 signals`,
    `projected 9 XMLs`) + the non-100 phase banners. Tests: `test_validation_i18n.py` (6) + `test_i18n.py`
    (5) + `test_gui_phases.py` (`labels_resolve_in_both_languages`); a headless EN<->IT chrome toggle smoke +
    a real-data EN-vs-IT report check.
- **M7 — Polish. DONE** (pending a manual GUI smoke): **theme persistence** (`app_config.yaml`
  `user_interface.theme` light|dark; `load_app_ui` reads it, the window starts in it, the Theme button
  persists via `config.save_app_theme`), **window-size persistence** (`width`/`height` read at startup +
  saved on close via a `WM_DELETE_WINDOW` handler + `config.save_app_window_size`; default 1180x720), and
  **log-to-file** (a toolbar toggle that tees every log line - `LogView._sink` - to a timestamped
  `ProjectDocumentation/Reports/Logs/pl4_log_<stamp>.txt`; on/off persisted via `config.save_app_log_to_file`,
  resumed next launch). The 5 simple `save_app_*` savers now share `config._save_app_ui(**updates)`. Tests:
  `test_app_config.py` (+the resolvers/roundtrip/log-dir; 5 cases).

## Risks / gotchas
- **JSON cells corrupt under a naive grid edit** — any table edit MUST go through `table.read_csv`/`write_csv`
  (fail-loud + deterministic codec), never a blind cell write. (Why M3/M5 grids are view-only first.)
- **Worker-thread seam** (the highest-risk port): the halt decision + `treatments.reconcile` run on the
  worker, but every Tk widget touch (the log render) must marshal back via the queue/`root.after` — getting
  this wrong reintroduces cross-thread Tk crashes the inline shell currently avoids.
- **Excel-COM cell-jump** is Windows/Excel + pywin32 specific; the clickable link degrades gracefully without it.
- **Treatment reconcile churn** across separate clicks (the CLAUDE.md TRANSITIONAL NOTE) — a per-run
  union-reconcile is the proper fix and lands with the engine; the Findings panel uses `set_treatment` (a
  targeted write) to avoid global churn.
- **No phase registry yet** — M0 ports a small one so the bar/Run-all/sub-phases share one source.

## Out of scope (carried from the backend, user decisions)
Validation **150** (diagnosis-slot — needs a staging change touching the locked 300 parity) + the **`accept`**
doc-mutating treatment.
