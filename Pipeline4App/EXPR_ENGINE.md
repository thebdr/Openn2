# PL4 Expr — a unified mini-formula engine (DESIGN PROPOSAL — not yet built)

Status (2026-06-29): **COMPLETE — the pause is lifted.** The unified engine (`core/expr`) is built and
retrofitted: all of ph200 (210 classify / 220 index / 230-240 diag) runs on it, the canonical stage→fill→
re-stage flow is operable end-to-end, and the duplicate render engines (`identity.interp` + `dbtemplate.render`)
are converged onto `core/expr.render` (byte-verified: 0 diffs on the locked 520/600 outputs). 8 commits, all
green + pushed (ef4fb86 engine · ee555c8 210 · 8deda92 220 · a314b14 230/240 · d8444af integration · 9799531 +
cff30ed convergence). The sequenced build record is in **`EXPR_BUILD_PLAN.md`**. Phase development can resume.
**UPDATE — FULL UNIFICATION DONE (M-E6, user-driven):** the native `$`-syntax was later retrofitted into EVERY
config-CSV expression column and the three legacy mini-languages retired — `dbtemplate.compile_for_each`'s predicate
now runs on `core/expr.test`, `identity.interp_keep` on `expr.render(mode="keep")`, and the `_dollarize` bridge is
deleted. One accepted byte-delta: `signals.csv` stores its embedded templates in native `{$token}` form; all
resolved outputs byte-identical. See `EXPR_BUILD_PLAN.md` (the M-E6 B–F record).

---
ORIGINAL framing (now satisfied): the user elevated the ph200 rule grammar into a first-class, reusable
"mini spreadsheet-formula engine" wired across the pipeline.

### DECISION RESOLVED (2026-06-29): **go_custom** — extend `core/rule_expr.py` → `core/expr` (NOT CEL)
A time-boxed **CEL/celpy 0.5.0 spike** on the 4 hardest real rules (§6 push-button join+slice, §6 reset-area
conditional, diagnosis `ml_value` nested-case, diagnosis `fl_value` host-lookup) settled it ON EVIDENCE
(`let` was dropped per the user — CEL evaluated on its native surface). Result: **all 4 ARE expressible in
native CEL and every test case passes when actually run**, but `config_author_readable` = **false on 4/4**
(an independent adversarial judge concurred on each). Why custom wins:
- CEL's only real edge ("find help online") covers ONLY the operator/ternary core — the *trivial* half. The
  load-bearing half (`extract`/`isdigit`/`present`/`node_of`/`where`/`lookup`) is a CUSTOM host function in
  BOTH worlds, and `rule_expr.py` already implements it (parity-green **273/0** on the real ph200 rules).
- CEL's native gaps contradict the decided grammar: **no `let`/`cel.bind`** at all; **no string slicing**
  (yet the grammar wants `extract(...,-1:)`); **missing-map-key access THROWS** (grammar wants silent `""`);
  `.matches` is **case-sensitive** (grammar wants implicit IGNORECASE).
- Dependency cost: `cel-python` pulls **8 transitive deps** incl. a native `google-re2` wheel + `pendulum`,
  on a **Beta** 0.5.0 lib — against PL4's explicit "light, no new dependency" value.
- `thin_custom_layer_over_CEL` is dominated (pays the full CEL tax AND still needs the custom parser layer).
**Next: a reviewed BUILD PLAN (`EXPR_BUILD_PLAN.md`) — feature order + parity gates — before any code.**
(Spike harnesses: `scratchpad/cel_R1..R4.py`; the workflow run synthesized the verdict with high confidence.)

### Build vs adopt — research conclusion (deep-research, 2026-06-29; full cited report in the session task output)
- **No off-the-shelf DSL is a clean fit, and `let()` is native to NONE of them.**
- **CEL (via cel-python / celpy)** — the ONLY single engine doing both predicates AND value/string-building in
  one sandboxed, non-Turing-complete syntax (strings via `+` concat → collapses our template-vs-predicate
  split into one expression language); host functions + an injected context fit our cross-table lookups;
  Apache-2.0; CPython 3.14 OK; an industry standard (K8s/Envoy/Elastic). RISKS: celpy 0.5.0 is **Beta**; CEL
  syntax is C-like, not Excel; `let` only via the `cel.bind` macro (unverified); the *Python* docs are thin
  (the *language* docs are strong). A Google-official `cel-expr-python` (announced Mar 2026) is one to watch.
- **Hybrid: simpleeval (predicates/values — MIT, Production/Stable, Excel-ish, best README) + python-liquid
  (string templates — MIT, Production/Stable, good docs, 3.14)** — but TWO syntaxes, still no `let`, and
  Liquid lookups are awkward pipe-filters.
- **Jinja2** — best docs/community but a sandbox-escape CVE history (CVE-2025-27516, `|attr`→`str.format`,
  fixed 3.1.6) that maps to our editable-config threat model → only with strict version pinning.
- **JSONLogic / Starlark / Excel-libs (formulas/PyCel/koala)** — poor fits: verbose JSON (not single-cell);
  Starlark is a developer-grade STATEMENT language (a single-line expression works, but `let` needs
  statements → not a clean operator single-cell formula); Excel libs evaluate spreadsheet FILES, not an
  embeddable per-row DSL (koala is GPL-3.0).
- **Custom (this doc)** — exact fit incl. `let` + unified predicate/template, but ZERO external docs/community
  (the opposite of the user's stated "users find help online" priority).

### DECISION (resolved — see the status block above): **go_custom**
The CEL spike was run and decided it on evidence (CEL functional but `config_author_readable`=false on 4/4;
8-dep Beta tax; native gaps vs the decided grammar). The hybrid was rejected up front (two syntaxes, no `let`,
awkward lookups). **Build path: extend `core/rule_expr.py` into `core/expr`** (keep its tokenizer + thunk
compiler + the host funcs it already has), add the decided grammar, re-verify parity, retrofit, THEN resume
the paused work (ph200 220 §7 index / 230-240 §8 diag, then M7 GUI polish). The sequenced, parity-gated build
plan lives in **`EXPR_BUILD_PLAN.md`** (under review before any code).

### Final grammar decisions reached in discussion (apply to whichever engine, or shape the custom one)
- Fields = **`$canonical`**, validated against the SCOPE's schema (post stage-before-fill that's the `signals`
  schema, not column_map). Unknown `$x` → load error. No magic barewords.
- The In/Out/Node **gate is rule-driven** (`gate_rules.csv`), not code; type rules filter by a `gate` column.
- **`join(sep, a, b, …)`** for joined-field matches, then `~` (replaces the earlier proposed `find(...)`).
- **`extract($col, /re/, SLICE)`** where SLICE is Python-style (`-1:`, `:3`, `1:3`, `2`) — not `last|first`.
- Result sentinels are **literal text** (`<input required>`, plus author-defined ones) — NOT a special token,
  so authors can invent placeholders for "kinda-matches / needs-review / ungroupable" cases.
- **`let(a := e1, b := f($a); body)`** sequential bindings (the spreadsheet-LET ask) — native to NO candidate;
  the strongest reason a thin custom layer may be needed atop an adopted expression core.
- Data access via host functions: `where($table, pred)`, `first`, `lookup`, `unique`, `node_of($bit)`; the
  stateful allocation (next-free-bit, byte packing, leftmost-DB) stays a code pass the engine CALLS.
- **ph200 reorder (decided): stage → fill** (staging tolerant of a blank `script_type`) so fill rules
  evaluate over the staged SSOT + cross-table lookups — this is what makes `$x`-against-a-real-schema and
  "reference any table/config/DB" work.

### Current committed state (still works; do not regress)
ph200 **210 is committed + pushed and operable** on the OLD `core/rule_expr.py` grammar (bareword fields,
`extract(...,last)`, `{INPUT_REQUIRED}`) + `gate_rules.csv`/`script_type_rules.csv`, parity 273/0. The grammar
decisions above SUPERSEDE that and will land when the engine is chosen + built; until then 210 runs as-is.
(PH200_SPEC.md describes 210 against the old grammar — treat THIS doc as the authority for the engine + grammar.)

---
(original proposal follows — superseded in places by the decisions above)

## Why (the problem it solves)
PL4 today has **three overlapping mini-languages** + a pile of hand-written "formulas over the data":
1. `domain/identity.py` `interp`/`interp_keep` — `{token}` / `{token:spec}` string templates (current-row).
2. `domain/dbtemplate.py` — PEP-3101 `{name:spec}` render + the `for_each` DSL (`row where P` /
   `<var> in unique(col) where P`) with a predicate sub-grammar (`numeric/=/!=/~/in` + `and/or/not/()`).
3. `core/rule_expr.py` (ph200) — predicates + `{expr}` result templates + `extract/len/present/...`.
   Plus config CSV expression columns (diagnosis_columns `expression`, *_logic_rules `member`/`required_types`,
   interface_tagnames, signal_types `tag_name`/`io_comment`, datablock `member`/`for_each`) — all resolved by
   one of the three above. Plus **code-level lookups that are conceptually formulas**: `plc_binding`
   (signals ⋈ db_members, leftmost-DB), `node_of` (positional I/Q-range → node), `ml_value`/`fl_value`
   (case + node lookup), `resolve_logic` (chained cabinet join + next-free-bit), the interface `io_address`
   LET. Three grammars + N hand-rolled joins = drift risk + every new "compute X on condition" is code.

**Vision:** ONE small engine, authorable in config, that (a) tests conditions, (b) builds strings AND
objects, (c) reads the current row + other tables/config/the SSOT, with `let` bindings — used everywhere a
phase conditionally derives a value. Greenfield for ph200 now; the older DSLs converge onto it later.

## The language (proposed)
**Values are typed:** string · number · bool · list · (object/record — a later extension; ph200 needs none).

**Field references:** `$name` (resolved in the current SCOPE), and dotted `$name.key` into an object cell
(e.g. `$type.category`, `$type.diag_logic`). Only names in the scope's schema are valid (validated at load).

**`let`** — sequential local bindings, then a body (spreadsheet LET):
```
let(area := extract($desc_l1b, /AREA ./, -1:);          # one binding
    if(isdigit($area), concat("R", $area), "R*"))        # body uses $area
let(n := node_of($bit), name := $n.profinet_name; ...)   # later bindings see earlier ones
```

**Conditionals:** `if(cond, then, else)` and `coalesce(a, b, …)` (first non-empty).

**Operators:** `~ /re/` (ci search), `= != in [..]`, numeric `> >= < <=`, `and or not ( )`.

**Functions (a registry — extensible; the one place to add capability):**
- strings: `concat(…)`, `join(sep, …)`, `strip`, `upper`, `lower`, `replace`, `extract($f, /re/, SLICE)`
  where SLICE is Python-style (`-1:`, `:3`, `1:3`, `2`).
- predicates/util: `numeric`, `isdigit`, `len`, `present`, `blank`.
- data access (read the SSOT/config): `where($table, <pred>)`, `first($table, <pred>)`,
  `unique($col [over $table])`, `lookup($table, key, value)`, `count(…)`, and domain helpers like
  `node_of($bit)` (the positional range join). `$table` names a Database table or a config CSV.

**Two surfaces over one core** (so the existing `{token}` cells still work):
- `eval(expr, ctx) -> value` — predicates + computed values (incl. objects later).
- `render(template, ctx) -> str` — a string with `{expr}` holes, each `eval`-d (e.g. `E{extract(...)}/2`).
A result column may be a **template** (`{…}` holes, the common case) OR a **pure expression** (when it needs
`if`/`let`/`concat` — e.g. the `R{area}` vs `R*` choice). The author picks per column.

## Data / context model
`ctx` carries: the **scope** (the current row — a staged signal) + a **data handle** (the `Database` tables +
the loaded config). Field refs hit the scope; `where/first/lookup/unique/node_of` hit the data handle. The
**stateful** parts (next-free-bit allocation, per-direction byte packing, leftmost-DB-by-seq) stay as engine
PASSES / built-in functions in code — the language CALLS them but doesn't re-implement the loop. So:
expressible = "the value of this cell given the data"; not-expressible = "the allocation algorithm."

## ph200 reorder: stage → fill (resolves "what names exist")
Instead of fill→stage, we **stage first** (tolerant: build the `signals` rows from the raw doc; rows whose
`script_type` is blank stay untyped), then the **fill rules evaluate over the staged signals + the DB**, then
write `script_type`/`index`/`diag_*` back to the DOC; a re-stage completes the typed rows. So a rule's `$names`
are the **signals schema** (rich, declared) + table lookups — not the narrow raw column_map. (This is the
user's "we solve it by staging before filling.") Requires: staging tolerates untyped rows (mostly already
true); a declared `signals` schema for `$`-validation.

## What it subsumes (and when)
| surface | today | converge |
|---|---|---|
| ph200 gate/script_type/index/diag rules | (greenfield) | **build on the engine now** |
| `identity.interp` `{token}` templates | identity.py | later (byte-parity re-verified) |
| `dbtemplate` render + `for_each` | dbtemplate.py (520, parity-locked) | later — `where/unique` already map |
| diagnosis_columns / *_logic_rules / interface_tagnames / signal_types templates | identity.interp | later |
| `plc_binding` / `node_of` / `ml_value` / `fl_value` | hand-written | expose as data functions; optional |

## Phasing (proposed)
1. **Build `core/expr`** — the engine: values, `$field`/dotted, `let`, `if`/`coalesce`, operators, the
   function registry (string/predicate/data), `eval` + `render`, schema-validated `$names`, fail-loud,
   thorough syntax guide + tests. (Supersedes `rule_expr`.)
2. **ph200 on the engine** — stage-before-fill; gate + script_type rules (re-verify the 273-row parity),
   then 220 index / 230-240 diag (which NEED the data functions: object grouping, cabinet lookup, node_of).
3. **Converge** identity + dbtemplate onto it opportunistically, re-verifying byte-parity each time.
4. **Later** — object/record values; the in-app expression editor.

## Hard cases expressed (proof the model is enough)
```
# §6 push-button (template result)
when:  join(" ", $desc_l1, $desc_l1b) ~ /EMERGENCY PUSH.BUTTON PRES/
type:  E{extract($desc_l1b, /CH./, -1:)}/2

# §6 reset area (expression result — needs the conditional + let)
type:  let(a := extract($desc_l1b, /AREA ./, -1:); if(isdigit($a), concat("R", $a), "R*"))

# diagnosis ml_value (nested case)
if($type.diag_logic = "mirror", "TRUE",
   if($type.diag_logic = "invert", "FALSE",
      if(present($normal_condition), "FALSE", "TRUE")))

# diagnosis fl_value (let + range-join lookup + string build)
if(present($profinet_name), "false",
   let(n := node_of($bit); concat('"PROFINET_NODES_ALARM"."', $n.profinet_name, ' ', $n.profinet_ip, '"')))
```
(Stateful allocation — next-free diag bit, byte packing, leftmost-DB — stays a code pass; the engine supplies
the per-row value once inputs are resolved.)

## Open decisions (for the user)
1. **Typed values incl. objects?** ph200 needs only string/number/bool; objects are the bigger "custom
   objects" ask. Build typed-with-objects now, or string/number/bool now + objects later? (Lean: latter.)
2. **Template sugar kept?** Keep `{expr}` template strings alongside pure expressions (recommended — it's
   what every existing cell uses), with the object-literal syntax deferred so `{}` stays "a hole" for now?
3. **Data-access syntax** — `where($table, <pred>)` / `first` / `lookup` / `node_of` as functions; the
   stateful allocators stay code passes. OK with that boundary, or push more into the language?
4. **Scope/validation** — declare a `signals` schema (the column list) as the validated `$`-namespace
   (today it's implicit across staging + write-back). Add it?
5. **Convergence pace** — build engine + ph200 now, converge dbtemplate/identity later (recommended), or
   converge eagerly (riskier — they're parity-locked)?
6. **ph200 stage-before-fill** — confirm staging becomes tolerant of unresolved `script_type` so fill can
   evaluate over staged rows + the DB.
7. **Name / home** — `core/expr.py` (or a `core/expr/` package); a name for it ("PL4 Expr"?).
