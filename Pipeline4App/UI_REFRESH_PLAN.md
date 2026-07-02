# UI_REFRESH_PLAN — the pre-production-test GUI + config refresh

Status: **PROPOSAL — awaiting user review** (the user's directive: "let me review before building").
Scope: the batch of improvements requested before the first PL4 production test (building the same
project PL3 built). Companion visual: the icon-review artifact (phase-bar mockup + per-phase icon
picker). Once reviewed, each section below becomes an implementation step with its own verification.

The exploration facts referenced here come from the current code: `gui/phasebar.py`, `gui/theme.py`,
`gui/app_main.py`, `gui/db_explorer.py` + `gui/dbquery.py`, `gui/files_panel.py` + `gui/files_view.py`,
`core/config.py`, `core/expr/`, `domain/blocks/`.

---

## A. Phase bar redesign — icons + layout + chevron + dropdown scroll

### A1. Current state (facts)
- Classic `tk.Button`, text-only: `"{number}  {name}"` wrapped at 13 chars, Monaspace Neon Var 11 bold
  (`phasebar.py:25–56`, `:215`). Colors follow the ButtonsLayout oracle (`theme.py:19–22`).
- Chevron = a second-row `tk.Button` with the `▼` glyph at the same 11pt font (`phasebar.py:23`, `:224`).
- The `_Dropdown` is a `tk.Toplevel` anchored under the chevron; **no vertical scrolling** — a long
  dropdown renders past the window/screen bottom (`phasebar.py:88–170`).
- tkinter on Windows renders emoji glyphs monochrome → colorful icons must be **PNG assets**
  (`tk.PhotoImage`; tk 8.6 reads PNG natively).

### A2. New button layout (per the user's spec)
```
┌──────────────┐
│  [icon]  100 │   ← row 1: icon (~26 px) + phase number, centered as a group
│  Documents   │   ← row 2: description, centered, wrapped, max 2 lines
│  Validation  │
└──────────────┘
```
- A plain `tk.Button` cannot lay out icon+number over a description → new composite widget
  **`PhaseButton`** (a `tk.Frame` + 2 child rows: `icon+number` Label pair, `description` Label),
  with click/hover/disabled bindings on the frame + children. Behavior contract preserved:
  equal widths across all headers, oracle fill colors, `hand2` cursor, disabled greying, i18n
  relabel via `set_lang()`, retheme via `set_theme()`.
- **Narrow font for the description: `Bahnschrift SemiCondensed`** (ships with Windows 10/11),
  fallback chain `Arial Narrow` → `Segoe UI` (detected via `tkfont.families()`). Size ~9pt.
  The number: same family, ~12pt bold. (Monaspace stays for the log viewer only — it is a wide
  mono face and is part of why the current buttons are bulky.)
- Max-2-line check against the longest labels in BOTH languages ("Validazione Documenti",
  "Generazione Interfacce", "Compilazione Documenti") — wraplength tuned so every current label
  fits 2 lines; a future longer label ellipsizes rather than growing the bar.
- **Run Pipeline** gets the same treatment (icon + "Run" / description "Run Pipeline"), still
  spanning both grid rows, pink fill.

### A3. Chevron −40%
- Chevron stays a full-width strip under its phase but at **60% of the current pixel height**:
  smaller glyph (`▾` at ~7pt) + `pady=0`. Measured with `winfo_height()` before/after to land at
  −40% ±10%.

### A4. Dropdown scrollbar at the app border
- `_Dropdown` clamps its height to `app_bottom − popup_top − margin` (app border, per the user's
  spec — not screen border). If the content is taller: the button column goes inside a
  `Canvas`+inner-frame with a slim `ttk.Scrollbar` + mouse-wheel binding.
- Unchanged: click-away close, Escape, the 150 ms blur-poll, width matching the column above,
  the action/open+special divider grouping.

### A5. Icon set + per-phase mapping  → **see the review artifact (interactive picker)**
- **Icon set CONFIRMED by the user (round 1): Twemoji 72×72 PNGs** (CC-BY 4.0, one attribution
  line in the About/NOTICE). Ship the needed PNGs in `pipeline4/gui/assets/icons/`; load via
  `tk.PhotoImage(...).subsample(2)` → crisp 36 px, **zero new dependencies, zero conversion step**.
- **Custom + composite icons** (user-approved concept): where no real emoji exists, a custom icon
  is drawn in Twemoji's flat style / palette (36×36 SVG → rasterized once → committed PNG);
  composites (e.g. fist-bump = 🤜+🤛) are baked from two official Twemoji PNGs. Both live in the
  same assets folder; the `phase_icons.yaml` registry doesn't care which kind a file is.
- Mapping after the user's round-1 review (round-2 candidates for the open rows are in the artifact):

| Phase | Label | Icon | Status |
|---|---|---|---|
| Run | Run Pipeline | ⚡ high-voltage | **confirmed** |
| 100 | Documents Validation | ✅ check-mark-button | **confirmed** |
| 200 | Documents Fill Out | 🖊️ pen | **confirmed** |
| 300 | Documents Staging | "write to database" → custom DB-cylinder+green-arrow, or 💾 / 🛢️ / 🗄️ | round 2 |
| 400 | Interfaces Generation | 🤝 handshake vs 🤜🤛 fist-bump composite vs 🫱🫲 vs 👊 | round 2 |
| 500 | Signals Mapping | I/O electrical signals → custom green-up/red-down arrows, or ↕️ / ⬆️⬇️ / 📶 | round 2 |
| 600 | Diagnosis Mapping | 🩺 stethoscope | **confirmed** |
| 700 | Hardware Generation | "electronic board" → custom PCB icon, or 📟 / 🎛️ / 🎚️ | round 2 |
| 800 | Software Generation | "source-code file" → custom page-with-`</>`, or 📄 / 📃 / 📑 | round 2 |
| 900 | Reporting | 📈 chart-increasing | **confirmed** |

- Icon registry = a small `assets/icons/phase_icons.yaml` (`phase_number → icon file`) so future
  phases/custom icons are a config edit, not code. Missing icon file → button renders without an
  icon (log a WARN once), never crashes.

---

## B. Theme system — rebuild from scratch

### B1. Current state (facts)
- `theme.py` mixes: sv-ttk (optional) global theme, hardcoded palettes in module constants, a
  named-font override pass, and per-component `set_theme()` methods each reconfiguring their own
  widgets (`app_main._toggle_theme` manually calls 5 of them). Grown by testing, as the user said.
- The theme-toggle path itself is O(widgets) and infrequent — the likelier UI-wide drag is
  **sv-ttk itself** (a heavy ttk style set; Treeview/Notebook redraw cost), the **Monaspace
  variable font** as the app-wide face, or per-tab work on switch. This is measured, not guessed
  (B3).

### B2. New architecture (`gui/theme.py` rewritten)
- **One semantic token table** per mode: `bg, fg, surface, surface_alt, accent, border,
  btn.<kind>.bg/fg (run/phase/action/open/special/chevron/disabled), log.<LEVEL>, link, grid.*` —
  the single place a color is defined. Light + dark are two complete rows of the same tokens
  (no scattered ad-hoc constants).
- **A subscription model**: components call `theme.register(self._apply_theme)` once;
  `theme.set_mode(root, mode)` updates ttk styles + named fonts once, then notifies subscribers.
  `app_main` stops hand-calling five `set_theme` methods; adding a themed component = subscribing.
- `darktitle` (Windows titlebar) folded into `set_mode`.
- **sv-ttk decision**: keep it ONLY if profiling (B3) shows it innocent; otherwise drop it and
  style the handful of ttk classes we use (Notebook, Treeview, Scrollbar, Button, Combobox,
  Progressbar) directly from the token table — we already hand-color everything that matters.
  Dropping it also removes the optional-dependency fork in behavior.
- Same two palettes as today (the oracle button colors are kept exactly).

### B3. Performance: measure first, then fix
Instrumented pass on real data before rewriting (numbers go in the commit message):
1. startup → first paint; 2. tab switch (each tab); 3. theme toggle; 4. phase-run log flood
   (records/s into LogView); 5. the same with sv-ttk off; 6. the same with Segoe UI instead of
   Monaspace as the chrome face.
Known suspects to check: sv-ttk styling cost, variable-font text measurement in tk, LogView
re-tagging, `update_idletasks` in the drain pump. The rewrite lands with the measured wins listed.

---

## C. Database Explorer — analyze + rebuild

### C1. Current state (facts)
- Already an in-memory SQLite over `Database/*.csv` (14 tables), rebuilt by `refresh()` —
  **synchronously on the Tk thread** (`db_explorer.py:118–135`, `dbquery.py:20–38`), also at init.
- Query results: cleared + repopulated `ttk.Treeview`, capped at 2000 rows (`_RESULT_CAP`).
- SQL highlighting exists and is debounced (fine).

### C2. Rebuild plan
1. **Load off the UI thread**: `build_memory_db` runs on the existing worker (busy indicator in
   the tab); the tab is usable-but-empty until ready. Build **lazily on first tab visit**, not at
   startup.
2. **Rebuild only when stale**: stamp the Database dir (per-file `(name, mtime, size)`); refresh
   after a phase run or manual Refresh re-checks the stamp and skips the rebuild when unchanged.
3. **Chunked grid fill**: insert result rows in slices via `after_idle` so 2000×N never freezes
   the window; show "N rows (M shown)" immediately.
4. **Column sizing**: fixed reasonable widths + a "fit column" on double-click of the separator
   (auto-fit over 2000 cells on every query is a known Treeview cost).
5. Measured before/after on the real project database (same metric list as B3 item 2).

---

## D. YAML/JSON files — object explorer view + text highlighting + path picker

### D1. Text mode (read-only, as today) + syntax highlighting
- Reuse the SQL-highlighter pattern (regex tokens + tags, debounced) with YAML and JSON token
  sets: keys, strings, numbers, booleans/null, comments, punctuation. Colors from the theme
  token table (B2).

### D2. New "Object explorer" view (toggle: Text ⇄ Object)
- A 2-column `ttk.Treeview`: key tree (dicts nest, lists show `[0] [1] …`) + value column.
- **Editing**: double-click a value → inline `Entry` overlay; **Save** button writes the file
  atomically — YAML via **ruamel round-trip** (already a dependency of `config.py`; comments +
  ordering preserved), JSON via `json.dump(indent=2)`. Dirty indicator + revert. Scalars only
  (no add/delete/rename of keys in v1 — that stays a text/external edit).
- **Path picker**: any key whose name contains `path` (case-insensitive) renders a `…` button
  between the key and the value → `filedialog.askopenfilename` seeded from the current value;
  keys containing `dir`/`folder`/`root` get `askdirectory` instead. Picked value lands in the
  cell (still needs Save). Relative paths are kept relative if the existing value was relative.
- Applies to `.yaml/.yml/.json` in the Files tab (so `project_params.yaml`, `app_config.yaml`,
  and any project YAML get it).

---

## E. Files tab — config-driven structure (new `files_tab` section in app_config.yaml)

### E1. Current state (facts)
- 3 hardcoded sections + a hardcoded extension whitelist (`files_view.py:16–30`, `:74–87`) —
  which is exactly why "not all the files are shown".

### E2. New schema (in `config_project/app_config.yaml`, its own top-level key)
```yaml
files_tab:
  sections:
    - title: Project configuration        # literal, or title_key for i18n
      roots: ["${config_project}"]
      include: [".*"]                     # regex, matched on the path relative to the root
      exclude: ["~\\$.*", ".*\\.pyc$", "__pycache__"]
    - title: User editable files
      roots: ["${iolist}", "${matrix}", "${user_input}"]
      include: [".*"]
    - title: Generated output
      roots: ["${database_dir}", "${output_root}"]
      include: [".*"]
      exclude: [".*\\.bak_.*"]
```
- **Placeholders** resolved by `config`: `${config_project}`, `${user_input}`, `${database_dir}`,
  `${output_root}`, `${reports}`, `${iolist}`, `${matrix}`, `${project_root}` (a literal absolute
  path also works). Unknown placeholder → that root is skipped with a logged WARN naming it.
- Regex: case-insensitive, matched on the **relative path** (so `Reports/.*\.html` works), files
  only (dirs always traversed; empty branches pruned as today).
- Viewer routing stays extension-based and independent — a matched file with an unknown extension
  shows the "unsupported" pane + the Open-externally buttons rather than being hidden. This is
  the "show everything" fix.
- **No silent default** (project rule): the section ships in the tracked `app_config.yaml`; if a
  user deletes it, the tab shows one node — "files_tab section missing in app_config.yaml" — and
  a WARN. We do not bake a fallback copy of the structure into code.

---

## F. Hardcoded generation data → CSV config (audit result)

**Excluded per the user: `domain/blocks/builders.py`** — the deliberately user-coded builder
section. Nearly all "table-like" literals found live THERE (ZONE_GROUPS, ESTOP_SORTER_TIERS,
OUTPUT_FEEDBACK_VARIANTS, instance-name f-strings, per-block DB.member strings, PAD) and are
**left untouched**.

In-scope findings (outside builders.py), ranked:

| # | Site | Data | Proposal | Risk |
|---|---|---|---|---|
| 1 | `domain/blocks/engine.py:32–34` | `COM_DB="02_COM"`, `COM_MEMBER_COL`, `INSTANCE_OF` | → `config_project/user_input/generation_params.yaml` (`software.safe_db_name`, `software.com_member_column`, `software.instance_prefix`) | cross-phase contract (800c + coverage read it) — migrate with byte-parity re-run |
| 2 | `domain/datablocks.py:26` | `DB_CONSTANTS = ["Always FALSE","Always TRUE","No Operation"]` (the seed members; engine + coverage import it) | → `datablocks/datablock_definitions.csv` gains a proper seed list, or `generation_params.yaml` (`datablocks.seed_members`) | byte-parity re-run (GlobalDB XMLs, 02_COM) |
| 3 | `domain/diagnosis_scl.py:31–34` | `ALARM_DWORDS/WARN_DWORDS/DEFAULT_VARIANT` | → `generation_params.yaml` (`diagnosis.alarm_dwords`, `.warning_dwords`, `.default_scl_variant`) | SCL byte-parity re-run |
| 4 | `domain/diagnosis_scl.py:80` | `f"S1.CABINET{idx}.{role}"` instance pattern | → `generation_params.yaml` (`diagnosis.cabinet_instance_template`, expr-style `{$index}`/`{$role}` holes) — documents the hidden coupling to `datablock_definitions.csv` naming | SCL byte-parity re-run |
| 5 | `domain/diagnosis.py:24` | `PLC_BINDING_SENTINEL="$PLC_Binding$"` (protocol constant shared with `diagnosis_columns.csv` cells) | → `generation_params.yaml` (`diagnosis.plc_binding_placeholder`) — hygiene/traceability | low |
| 6 | `domain/blocks/templates.py:21` + `xml_emit.EMITTERS` | `COIL_COLUMN_BLOCKS={"03_Zone Cumulative"}` / `EMITTERS={"03_Zone Cumulative"}` — which blocks emit direct FC XML | → declare at registration: `@builds("03_Zone Cumulative", emit="fc_xml")` — the flag moves INTO the user-coded builders file where it belongs (no CSV needed) | low |
| 7 | `domain/io_tags.py` | direct-I/O tags hardcode `Bool` (PL3 parity) | future: `data_type` column in `signal_types.csv` — **defer** (behavior change, breaks parity today) | defer |
| 8 | `domain/coverage.py:35–38` | stage display labels | i18n catalog, not CSV (localization-sensitive) | low |

Left in code (framework constants, not project data): TIA Openness XML namespaces/schema
(`datablock_xml.py`), PLCTags workbook column names (`io_tags.py:35–43`), address regexes.

New file: **`config_project/user_input/generation_params.yaml`** (nested schema, `get_param`
accessors, loaded once per run). Every migration = same-value config + a byte-parity re-run of the
affected surfaces (GlobalDB XMLs / SCL / CreationInfo CSVs / 02_COM / InstanceDBs) — 0 diffs
required, same as every retrofit so far. Scaffolding: the file ships in `config_project/` AND in
the new-project template (project-config completeness rule).

> Review question: items 1–2 touch the 800/coverage contract — migrate now (before the production
> test) or after? Recommendation: 3–6 now (cheap, isolated), 1–2 immediately after the test.

---

## G. core/expr — suggested future functionality

The engine is complete and unified (M-E6). Suggestions honor the locked boundary: **no arithmetic
in the grammar** (offset math stays in named host passes).

### G1. Tooling API (needed by the builder UI, cheap now)
- **`expr.tokens(text) -> [(kind, start, end)]`** — expose the existing tokenizer with positions
  (it already has them; `referenced_fields` proves the walk) → editor syntax highlighting.
- **`expr.check(text, scope=None, mode=None) -> list[Issue(pos, len, message)]`** — compile-only
  lint (syntax + unknown-`$field` + bad format spec), no eval → live squiggles + the CSV-config
  validators can pre-flight whole files.
- Fix the noted M-E1 leftover while there: `strict` render mode misses a missing field inside a
  function-call hole; `check` should catch it via `referenced_fields`.
- Cache key: `(text, id(scope))` pins Scopes — swap to `(text, frozenset(scope))` content key
  (noted in EXPR_BUILD_PLAN as a growth risk).

### G2. Function candidates (each small, string-in/string-out, deterministic)
- `contains($f, "s")` / `endswith($f, "s")` — complete the `startswith` family without regex
  escaping pain.
- `replace($f, /re/, "sub")` — the one string transform templates currently can't express.
- `lower($f)` / `upper($f)` — case normalization for comparisons and rendered names.
- `split($f, ",", 2)` — indexed split (returns "", like `extract`, when out of range).
- `extract` named/indexed groups: `extract($f, /(A)(B)/, 2)` — today only group(1)-or-whole.
- Data layer: `exists(table, pred)` (sugar for `count(...) > 0`), `lookup(..., default)`,
  and `min_of/max_of(col, table, pred)` (comparison-only aggregates; no arithmetic).
- `error("msg")` — lets a config rule fail loudly from data (pairs with the severity model).
- Explicitly NOT proposed: arithmetic, date/now (non-deterministic), I/O.

### G3. Diagnostics
- **`expr.explain(expr, ctx) -> trace`** — a per-node value trace for the builder UI's preview
  pane ("why did this row not match") — big authoring-time win, zero runtime cost when unused.

---

## H. Expression builder UI (with suggestions + highlighting + ? guide)

- New dialog `gui/expr_builder.py`, opened from a toolbar **ƒx** button (later also from CSV-grid
  expr columns when in-app CSV editing lands).
- Layout: expression editor (1–3 lines, tk.Text) with **live highlighting** (G1 `tokens`) and
  **live lint** (G1 `check`, red squiggle tags + a message strip).
- **Autocomplete**: after `$` → column names from the selected context; on ident → function names
  + signature hint line; inside data funcs → table names. Context = a table picked from the SSOT
  Database (same source as the DB explorer) or a config-CSV column set; a row picker (first/N-th/
  filtered) supplies the preview ctx.
- **Live preview**: `test()` verdict or `evaluate()`/`render()` result against the picked row;
  errors shown located; optional `explain` trace pane (G3).
- **?** button → opens the guide at section `expressions` (I below).
- Function palette: grouped buttons (string/predicate/control/data) inserting a snippet with
  placeholder args.

---

## I. Guide / help system (the user's proposal, refined)

Agreed direction: classic multi-section help + F1 + tooltips, shipping with the source. Design:

- **Content**: Markdown files in `Pipeline4App/docs/guide/<section-id>.md` (one file per section;
  `docs/guide/index.yaml` gives order + titles + optional IT titles). Markdown renders in-app via
  a small tag-based renderer (headings/bold/code/lists/links) into a tk.Text — **no new
  dependency**, diffable, user-editable next to the shipped source.
- **Viewer**: a Help window (F1 anywhere, or toolbar "?") — left Treeview TOC, right rendered
  pane, back/forward. Link schemes: `guide://section-id`, `src://pipeline4/gui/phasebar.py:120`
  (opens the shipped source file via `os.startfile` — the "user can modify and rebuild" flow),
  plus normal `https://`.
- **Context-sensitivity**: widgets/buttons register a `help_id`; F1 resolves the focused widget's
  nearest `help_id` → section. The phase registry gives this for free for every phase/sub button
  (`help_id = pb_* key`).
- **Missing-section fallback (the user's spec)**: a generated page — *"No instructions provided
  for the requested functionality yet. See the source code: `<module>.py`"* — where the source
  link is derived automatically from the registered handler
  (`inspect.getsourcefile(phase.handler)`), so the fallback needs zero maintenance. A `--stubs`
  helper lists all help_ids without a section (the visible authoring TODO).
- **Tooltips**: one shared tooltip class (short text + "F1 → guide" hint); tooltip text lives
  with the help registry, not scattered per widget.
- **First content**: `expressions.md` (the expr guide the ƒx dialog links to), `phase-bar.md`,
  `files-tab.md`, `database-explorer.md`, `treatments.md`. Everything else starts as the
  fallback page.
- i18n: EN first; `docs/guide/it/` mirror with EN fallback later (matches chrome i18n).

---

## Implementation order (after review sign-off)

1. **A** Phase bar (icons + layout + chevron + dropdown scroll) — isolated, most visible.
2. **B** Theme rebuild + the profiling pass (fix the real slowness, decide sv-ttk).
3. **C** DB explorer (worker-thread load + stale-stamp + chunked fill).
4. **E** Files tab config section.
5. **D** YAML/JSON highlighting + object explorer + path picker.
6. **F** Hardcoded-data migrations 3–6 (byte-parity-gated), 1–2 per review answer.
7. **G1** expr tooling API → **H** ƒx builder dialog.
8. **I** Help system skeleton + first sections (expressions first).

Each step: unit tests where the logic is Tk-free (files_view filters, object-explorer model,
expr.check/tokens, help registry), the 236-test gate stays green, byte-parity re-runs where F
touches generation, and a real-data GUI smoke per step. Push on each landed step (milestone rule).

## Open review questions (answer these + the icon picks in the artifact)

1. **Icon set**: Twemoji (ready PNGs, recommended) / Fluent flat (Windows-11 look, needs a
   one-time rasterization) / Noto? Custom icons stay possible per-phase via the registry.
2. **Per-phase icons**: pick/veto in the artifact (it exports your selection as YAML).
3. **F items 1–2** (02_COM + seed constants): migrate before or after the production test?
4. **Object explorer editing**: scalar-value edits only (proposed) — or do you also want
   add/remove keys in v1?
5. **sv-ttk**: OK to drop it if profiling shows it's the drag (manual styling replaces it)?
