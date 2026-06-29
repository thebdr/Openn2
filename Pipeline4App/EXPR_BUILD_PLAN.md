# PL4 Expr — BUILD PLAN (hardened by codebase audit; corrected to DB-references-only — awaiting sign-off; no code yet)

Decision: **go_custom** (`EXPR_ENGINE.md`). Build path: extend `core/rule_expr.py` → a **`core/expr/` package**,
keep its tokenizer + thunk-compiler + existing host funcs, add the decided grammar, **re-verify every parity at
every step**, retrofit, THEN resume ph200 220/230/240. Hardened by a 3-way adversarial codebase audit
(grammar / parity / sequencing); then **corrected per the user's hard rule: `$`-fields are EXPLICIT DATABASE
REFERENCES ONLY** — which reasserts `EXPR_ENGINE.md`'s already-decided **stage → fill** order (the audit's
"decouple the reorder" is overridden).

## Canonical pipeline order (the user's hard rule)
```
stage  →  fill (ph200)  →  re-stage [ONLY if fill modified the docs]  →  validate (ph100)  →  generate  →  report (ph900)
 300         200                    300 (again, conditional)                    100         520/400/510/600/700/800   900
```
**Why it's forced:** if a rule may reference *only* database columns, the data must be IN the database when the
rule runs. So fill (ph200) evaluates over the **staged** `signals` table — staging runs FIRST (tolerant of a
blank `script_type`), fill writes the computed `script_type`/`index`/`diag_*` back to the **doc**, and staging
re-runs **only if the doc changed** (the idempotent no-op skips it — `PH200_SPEC` decision 3 keeps fill DOC-only).
This is the operational run order; it is NOT the GUI button numbering.

## The hard rule — `$` = explicit database references ONLY
A `$name` resolves **only** to a real column of a database table in scope (an SSOT table; a config CSV loaded as
a table). There are **no** synthetic/derived bare fields and **no** aliases:
- **Dropped: derived ctx fields** `$d1 / $d2 / $desc / $gate`. Joining is explicit: `join(" ", $desc_l1, $desc_l1b)`.
  Cleaning is explicit: **`clean($desc_l1)`** (a host function — control-chars→space, whitespace-collapse, strip).
- **Dropped: overlay aliases** `{tag_name}`/`{db_element}`. Rules use the **real column**: `$name_in_tagtable`,
  `$name_in_db`.
- **`gate`** is a rule-metadata column (the rule's own `In/Out/Node/any`, matched in code), not a `$`-field.
- **Sentinels** (`<input required>`) are literal result strings, not field references — unaffected.

**Evaluation scope** = the database columns reachable for that rule: the current row's table (during fill =
`signals`) ⋈ any config/SSOT tables joined via the data funcs ⋈ a `for_each` bound iteration var (itself a DB
column value, e.g. `unique($diag_cabinet)`). Every name is a database reference; the engine validates each
top-level `$name` at LOAD against that scope (unknown `$x` → located load error). Dotted `$obj.key` into a JSON
object cell is **silent-empty on a missing sub-key at EVAL** (the decided CEL divergence; matches `rule_expr`).

**Staging contract (the agreement — M-E2 must deliver it):** the staged `signals` table must carry **all
`column_map.csv` IoList columns + the derived/enriched columns**, so every fill-referenced `$column` resolves:
`$id_node` (col F), `$desc_l1b` (col L), `$bit` (G), `$type_hw` (R), `$functional_unit`/`$location`/`$device`
(O/P/Q), `$normal_condition` (H), `$profinet_*` (V/W), etc. The schema *builder* already allows this
(`signals_table(iolist_columns)` = `["uid"] + iolist + ENRICHED`, `signals.py:46-52`), **but the current staged
output does NOT yet include the full column_map set (user-verified)** — so M-E2 makes staging read + persist the
complete IoList column_map list + derived. The cleaned text and the join stay functions (`clean()`/`join()`) over
those real columns.

## Guiding constraints
- **Never regress a green parity.** Locked: ph200 210 (273/0 script_type), 520 GlobalDB XMLs, 600
  diagnosis/DiagList/SCL, **300 signals.csv (byte-locked)**, 400/510, 700/800/900, 100 (596/596).
- **Blast radius is ONE runtime caller** (audit-corrected): `rule_expr` is imported only by
  `domain/fillout/classify.py` (`test` @ `classify.py:51,:66`, `render` @ `:67`). `core/config.py` is **not** a
  caller — `core.rule_expr` is only a docstring (`config.py:373`). `domain/fillout/fill.py` is a **second-order**
  consumer via `classify.classify`, **value-coupled** to the `<input required>` sentinel (`fill.py:40,156,169`).
- **Author surface stays the 2-column CSV** (`when` predicate + `type` template); a fallback is a lower-priority
  rule, not a typed-out `else`.
- **Spec-review gate** (standing rule): this plan is the review; no code until the decisions below are signed off.

## Strategy: build alongside, port once, retire (green at every step)
1. Build `core/expr/` as a NEW package (the DB-refs-only grammar). `rule_expr` stays untouched and green as the fallback.
2. Reorder ph200 to stage→fill, port the rule CSVs to the new syntax **once** (`$`-columns + `clean()`/`join()` +
   slices), flip `classify.py` to `core/expr`; re-verify **273/0** AND **300 byte-parity**.
3. Retire `rule_expr` (delete or thin shim); `test_rule_expr` → `test_expr`.
The new grammar is **not** a pure superset (barewords→`$column`, `extract(...,last)`→`extract(...,-1:)`,
load-time schema validation, the scope swap to the staged `signals` table), so in-place mutation could not be
byte-transparent — alongside is the safe choice.

## The engine surface (M-E1 feature list)
- **`$` field refs = database columns only** + dotted `$obj.key` (silent-empty on miss) + load-time validation
  against the evaluation scope (current table ⋈ joined tables ⋈ iteration var). No derived fields, no aliases.
- `if(cond, then, else)` + `coalesce(a, b, …)` (first non-empty); nestable. *(Prospective — for 230/240 + `ml_value`.)*
- `let(a := e1, b := f($a); body)` — sequential **bind-once** bindings, per-eval scope chain. *(Prospective — 220/230/240 + `fl_value`.)*
- `extract($f, /re/, SLICE)` — Python slice (`-1:`, `:3`, `1:3`, `2`), implicit IGNORECASE. **Audit-verified:**
  `-1:` is byte-exact with PL3 `last` on all 7 shipped sites *and safer*; `:1` == `first`. **`group<N>` is NOT a
  slice** (variable-length capture, `rule_expr.py:136-140`) → **OPEN DECISION A**.
- Operators: `~ /re/` (ci search), `= !=`, `in [..]`, numeric `> >= < <=`, `and or not ( )`; preserve regex-token
  backslash survival (`/CELL.\d/`). Add a **`startswith`/prefix predicate** (or document `~ /^KEY/`) for
  `object_families` longest-prefix matching (PL3 `index_assign.py:40-46`, `'DI'` beats `'D'`).
- String/util funcs: **`clean($col)`** (the new cleaning host func), `concat`, `join(sep,…)`, predicates
  `numeric/isdigit/len/present/blank`.
- **Two surfaces over one core**: `eval(expr, ctx)` (predicates + computed values) and `render(template, ctx)`
  (`{expr}` holes). **RENDER carries:**
  - **(a) format-spec holes `{token:spec}`** with numeric coercion (`int(float())` for `d/x/X/o/b/n`, float for
    `e/E/f/F/g/G/%`, **blank stays blank**) — LIVE at 3 shipped sites (`datablock_definitions.csv`,
    `datablock_elements.csv`, `diagnosis_columns.csv`); `identity._format_value` + `dbtemplate._SafeFormatter`. **Core.**
  - **(b) THREE missing-key modes** per call: **silent-empty** (default `''`), **keep** (leave `{token}` intact when
    the column is absent from scope — `identity.interp_keep:39-49`, for `interface_tagname`'s two-stage fill),
    **strict-raise** (`dbtemplate:40`).
  - **(c) joined-table evaluation scope** (NOT arbitrary aliases): a template renders against the DB columns in
    scope — the current row's table ⋈ joined config/SSOT tables ⋈ the `for_each` iteration var. `{tag_name}`/
    `{db_element}` become the real columns `{name_in_tagtable}`/`{name_in_db}`; `{direction}`/`{member}` are
    columns of the joined `diagnosis_logic_rules`/`interface_elements` row; `{cabinet}` is the bound `unique($diag_cabinet)`.
  - **(d) empty-hole `{}`/`{ }` → `''`** preserved (`rule_expr.py:311`).
- Literal-text sentinels (`<input required>`, author-defined) are strings; a result cell carrying one is a
  **TEMPLATE, never a pure expression** (where `<` would tokenize as an operator). Guarantee the byte value
  `<input required>` (`classify.INPUT_REQUIRED`) for `fill.py` value-equality.
- **Arithmetic / ordered-allocation boundary:** integer arithmetic (`+ - * / % //`, `int()`), the 220 progressive
  per-family counter + row-adjacency, and the 230/240 offset math stay **NAMED stateful host passes the engine
  CALLS** (parallel to next-free-bit / byte-packing) — **NOT grammar**. Matches PL3 (`index_assign.py`, `diag_alloc.py`).
- Data funcs (`where/first/lookup/unique/count/node_of`) are host passes over DB tables; `'|'`-OR list cells
  (`required_types`, `member_types`) stay **loader pre-split** (`families.py:16`).
- Fail-loud located errors; compiled-expr cache; thorough **SYNTAX GUIDE**.

## Milestones (stage→fill foundational; each parity-gated)
| # | Milestone | Parity gate |
|---|---|---|
| **M-E1** | `core/expr/` engine core (alongside `rule_expr`; full surface above; DB-refs-only Scope; `clean()`; data funcs). **Re-establish a runnable 273-row parity harness** (audit found none committed). | data-independent unit suite green: `let` scoping, slice edges, **3 render modes**, `{token:spec}` coercion (blank-stays-blank), implicit-IGNORECASE on **both** `~` and `extract`, empty-hole `{}`→`''`, `if`/`coalesce`, `clean()`, schema-validation load errors, joined-scope resolution |
| **M-E2** | **stage→fill reorder** (foundational) + **make staging carry the full `column_map` IoList set + derived** (the agreed contract — currently incomplete) + migrate ph200 210 onto `core/expr` over the staged `signals` scope. Port `gate_rules.csv` + `script_type_rules.csv` to `$`-columns + `clean()`/`join()` + slices; flip the single caller `classify.py`; retire `rule_expr`. | **300 `signals.csv` byte-parity** for the **previously-present** columns (the staging change ADDS columns; assert no existing column/value drifts) **AND ph200 210 = 273/0** vs PL3; assert every fill-referenced `$column` is present in `signals`; assert catch-all rules emit byte-identical `<input required>`; assert **both** IGNORECASE sites ported; assert the staged-blank-then-typed two-pass converges (`script_type`-in-uid handled — see Risks) |
| **M-E3** | ph200 220 (index = object grouping) over the staged DB: `let` + grouping over `signals` + `object_families` + the named ordered-counter host pass + `startswith` family match; ungroupable → literal `<input required>`. | per-row `index` data-parity vs PL3 over the real doc |
| **M-E4** | ph200 230/240 (diag cabinet/bit) over the staged DB: `node_of` + `let` + nested `if`; cabinet/bit allocation + offset math stay idempotent seeded host passes. | per-row `diag_cabinet`/`diag_bit` + cabinet-set data-parity vs PL3 — **ph200 COMPLETE** |
| **M-E5** | convergence (LATER, opportunistic): move `dbtemplate` `for_each`/render + `identity.interp`/`interp_keep` onto `core/expr`, byte-gated **per site**. Needs format-specs + 3 render modes + joined-scope in place FIRST. | byte-parity per site: 520 GlobalDB XMLs, 600 DiagList/SCL, interface tagnames |

## Build status
- **M-E1 — DONE + verified (2026-06-29).** `pipeline4/core/expr/` package (7 modules, ~949 LOC): `$`-field refs
  (DB-refs) + dotted access + compile-time `Scope` validation; `clean()`/`concat`/`join`/`extract` (capture-first);
  `if`/`coalesce`/`let` (bind-once); `render` with format-specs + 3 missing-key modes + the slice-vs-spec
  disambiguation; data funcs over host tables. Built ALONGSIDE `rule_expr` (untouched fallback). **`test_expr`
  22/22 + `test_expr_adversarial` 23/23; full data-independent gate 334/334, 0 regressions**; adversarially
  verified (0 bugs, verdict sound). Two known non-blocking follow-ups: (1) `render` strict/keep modes only check
  missing-ness on a SIMPLE `$field` hole — a missing field inside a function-call hole isn't caught under `strict`
  (revisit at **M-E5** convergence, where `dbtemplate`'s raise-on-unknown needs full fidelity); (2) the compiled-expr
  cache keys on `(text, id(scope))` and pins each Scope — fine when callers reuse one Scope, a minor growth note.
- **M-E2 (classification port) — DONE + verified (2026-06-29).** Added single-quote string literals + `strip()`
  to `core/expr`; ported `gate_rules.csv` + `script_type_rules.csv` to `$`-columns (DB-refs) + `clean()`/`join()`/
  `strip()`/`-1:` slices + literal `<input required>` sentinels; rewrote `classify` to run over a STAGED signals
  row with the signals `Scope`; **retired `rule_expr`** (deleted). **Oracle parity EXACT: 0 mismatches / 269 rows**
  vs the pre-port classifier (captured before changes); full gate **329/329**. Independent verifier caught a
  `clean()`-vs-strip divergence on the `type_hw` RESULT (rules 10/30) — fixed: results use `strip()` (trim-only),
  matches use `clean()`. Confirmed: the staged `signals` already carries all 64 columns (34 `column_map` + 30
  derived) — no staging-schema change needed; the stale stub was the earlier confusion.
- **NEXT (M-E2 remainder):** wire the physical stage→fill→re-stage run order (`fill` reads the staged `signals`,
  writes `script_type` back to the doc, re-stage if changed) — 210 classifies correctly over raw OR staged rows
  (same canonical columns), so this is run-order plumbing, not a correctness gate. Then M-E3 (220).

## Resolved decisions
1. **Pipeline order** → **stage → fill → re-stage(if changed) → validate → generate → report** (the hard rule).
   The reorder is foundational (M-E2), 300-byte-parity gated; it is NOT decoupled/deferred.
2. **`$`-namespace** → **explicit database references only** — DB-table columns (+ config-CSV tables + joined
   tables + iteration vars). No derived bare fields, no aliases. Transforms (`clean`, `join`, `extract`) are functions.
3. **In-place vs alongside** → **alongside**, port the one caller, retire `rule_expr`.
4. **Convergence pace** → **engine + ph200 now, converge later** (M-E5, byte-gated per site).
5. **Name/home** → a **`core/expr/` package**; keep `eval`/`test`/`render` names.
6. **Cleaning** → a **`clean()` host function** over the raw column (not a persisted cleaned column).

## DECISION A — RESOLVED (user, 2026-06-29): (b) capture-first
`extract` keeps BOTH a whole-match slice AND variable-length capture, via **capture-first**: if the regex has a
capturing group, `extract` returns group 1 (an optional slice then applies to that capture); no capture group →
the slice applies to the whole match (**identical to today**). So `extract($desc_l1b, /CH./, -1:)` is unchanged
and `extract($desc_l1b, /CH(\d+)/)` yields the variable digits. `m.group(N)` is the mechanism (`rule_expr.py:136-140`).

**Plan signed off — build started at M-E1.**

## Risks (top, with mitigations)
- **The stage→fill reorder touches the locked 300 + the signals uid key includes `script_type`** (`SIGNAL_KEY_COLUMNS
  = combined_FLD, script_type, source_cell`). A staged-blank-then-typed two-pass would re-stamp uids when fill fills
  `script_type`. → Make **stage #1 ephemeral/in-memory** (the fill scope), **stage #2 (post-fill) the authoritative
  persisted `signals.csv`** that the byte-parity checks; confirm the two-pass converges to identical stage-#2 uids;
  re-run `_finalize_identity` + re-resolve the `type` object after fill; diff every identity column, not just file size.
- **Staging must carry the full `column_map` IoList set + derived** (the agreement; current output is incomplete,
  user-verified). Adding columns **changes `signals.csv`** (new columns appear), so the M-E2 300 gate is **"no drift
  on the previously-present columns/values + uids unchanged"**, not strict byte-identity. → Make the staging read
  emit every `column_map` IoList canonical + the enriched set; diff old-vs-new restricted to the prior column set.
- **Render half** (format-specs / 3 modes / joined-scope) → in M-E1 core with tests before any convergence; byte-gate
  each M-E5 site individually.
- **`extract` slice ≠ `group<N>`** → no production risk (all shipped use `,last`); resolve via Open Decision A.
- **230/240 arithmetic + 220 ordered counter** not in grammar → named host passes; named in M-E3/M-E4.
- **No committed 273-row parity harness** (audit) → (re)establish as an M-E1 deliverable before the M-E2 gate.
  Green baseline confirmed: `test_rule_expr` 8/8 + `test_fillout_classify` 5/5.
