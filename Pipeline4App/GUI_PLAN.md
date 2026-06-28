# PL4 — GUI PORT PLAN

The PL4 **backend rebuild is COMPLETE** (all 9 phases + the S1–S6 severity model, each parity-verified vs
PL3; `HANDOFF.md` has the backend state). This is the plan for the **GUI port**: replicate PL3's operator GUI
**and** add the SSOT-native features PL3 could never have. Same toolkit as PL3 (Tkinter + sv-ttk + Monaspace).

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
  single source the bar + dispatch + Run-all consume; no Fill phase). The **worker thread + queue/drain pump**:
  `_on_phase` spawns a daemon thread per click, the handler emits via `self._emit`/`self._status` (thread-safe
  enqueue) instead of touching Tk, `_drain` (`root.after(50)`) applies log/status/done on the main thread, a
  `ttk.Progressbar` + a `_busy` guard grey the bar during a run (single-phase runs no longer freeze the
  window). A basic **Run-all** (registry `run_order`, each handler self-contained / re-stages - M4 optimizes to
  a stage-once shared DB). The **`ttk.Notebook`** scaffold (the Log tab; Findings/Explorer/Files tabs slot in
  later). `phasebar` is registry-driven + `set_enabled`. Tests: `test_gui_phases.py` (4). Verified: py_compile +
  a headless construction smoke (9 buttons, 1 tab, drain wired); the live worker-run is the manual launch check.
  **DEFERRED to M0b** (chrome, independent verbatim ports): `fonts.py` (the Monaspace TTF) + `darktitle.py` +
  the `theme`/`LogView` re-theme.
- **M1 — Structured clickable log** (PL3 parity; backend mostly done): `LogView.append_records` over
  `render.render_records`, `Sheet!Cell` → Excel-at-cell (`gui/excel.py` COM port), `[FAIL]` errlink →
  `treatments.set_treatment`, the Show-PASS/SKIP toggle. The validation handler feeds
  `render.render_records(findings)` to `append_records`.
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
- **M4 — Run-all + sub-phase dropdowns** *(NEW: live progress)*: the registry drives a dependency-ordered
  Run-all on the worker (live per-phase progress + halt-on-FAIL); chevrons list each phase's sub-steps.
- **M5 — Files tab**: the 3-section tree (config / user-editable / output) + a CSV grid **through the codec**
  + object editor (yaml/json/xml) + xlsx read-only viewer + external-edit. (The SSOT-aware grid from M3 can
  subsume the generic CSV grid.)
- **M6 — Project Manager**: port `project/project.py` + `state.py` (folder projects, persisted root, recent,
  auto-reopen) + the toolbar cluster. `config.use_project()` already routes the loaders/Database/Output.
- **M7 — Polish**: theme/size persistence (`app_config.yaml` already read by `load_app_ui`), log-to-file,
  EN/IT (optional, low priority — needs a `core/i18n.py`).

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
