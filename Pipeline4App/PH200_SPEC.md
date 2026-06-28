# PH200 — Documents Fill Out (STEP 4) — SPEC + PLAN

Status: **spec reviewed by the user 2026-06-28** (corrections folded in); **4 decisions LOCKED**; the
**rule grammar below is PROPOSED, pending sign-off** before any code. Built **one sub-phase at a time**
(210 → 220 → 230 → 240), each parity-checked vs PL3 (`Pipeline3App/pipeline3/domain/iolist_diag/`).

PL3's ph200 turns a RAW I/O List into a CLASSIFIED one: it computes `script_type` (AB), `index` (AD),
`diag_cabinet` (AE), `diag_bit` (AF) per row and generates the **DiagnosisBlocks** sheet. PL4 never built
it (PL4 staging assumes a pre-filled doc). ph200 is the missing front end.

## Locked decisions (user, 2026-06-28)
1. **Dedicated rules CSV** — `config_project/input_docs/script_type_rules.csv` (classification rules kept
   separate from the type SCHEMA in `signal_types.csv`).
2. **Full, expressive rule grammar now** — not a minimal one. The plan is to expand the fill to many more
   types via config, so the grammar gets "all the due effort" (see §6).
3. **Doc-only write:** ph200 **mutates the source I/O List in place** (PL3-faithful: a timestamped backup
   first, deleted if the fill changed nothing). It does **NOT** write the SSOT database — **staging (300)
   reads the now-filled doc and builds the tables**, so the data lands in the DB via the existing path
   (1:1 with PL3). (Revised from the earlier "doc + DB": staging already gets all the info.)
4. **Full implementation**, incrementally **one sub-phase at a time** (210, then 220, then 230, then 240).
5. **`project_params.yaml` must carry `diag_bit_min` / `diag_bit_max`** (PL3 reads them; defaults 0 / 62).

## Corrected understanding (the two review corrections)
- **Sub-phases are STANDALONE.** Each sub-phase runs on its own and respects PRE-FILLED data: it reads its
  upstream columns from the document (operator-filled, or written by an earlier sub-phase) and computes +
  writes ONLY its own column. 1:1 with PL3. (NOT "one monolithic compute that only gates the emit".)
- **`index` = OBJECT IDENTITY / the grouping mechanism.** An object is one device that may own ONE OR MORE
  signals; all signals of an object share the SAME index. §7's job is to decide which signals form one
  object and give that object a contiguous per-family index. The channel-pair / KQ↔KI series / door-FLD /
  Z-pattern rules are *how* objects are recognized — grouping is the purpose.

## The phase shape
| Button | Computes/writes | Reads (upstream, from the doc) |
|---|---|---|
| 210 Fill Script Type | `script_type` AB (+ `suggested_type` AC, always) | description, address, id_node, type (col R) |
| 220 Fill Index | `index` AD | script_type (+ FLD/device for object grouping) |
| 230 Fill Diag Cabinet | `diag_cabinet` AE (+ DiagnosisBlocks) | script_type, index, FLD, node |
| 240 Fill Diag Bit | `diag_bit` AF (+ DiagnosisBlocks) | script_type, index, diag_cabinet |
| header | all four + DiagnosisBlocks | — |

Each sub-phase is independently runnable; numbering/allocation is GLOBAL across all matched sheets; column
letters/headers resolve from `column_map.csv` (no hardcoding).

---

## §6 — Script-type classification (210) + the PROPOSED rule grammar

### Inputs (per row)
`d1` = description col K, `d2` = description col L, both **cleaned** (control chars → space, whitespace
collapsed, stripped); `desc` = `d1 + " " + d2`; `addr` (col G); `id_node` (col F); `type_hw` (col R).
Matching is **case-insensitive regex search** (substring/anywhere).

### The In/Out/Node gate — ALSO rule-driven (decision: rule-driven, not code)
The gate is computed by its own small ruleset `config_project/input_docs/gate_rules.csv`
(`priority, when, gate`), first-match-wins over the raw fields, using the SAME expression engine. The
shipped default reproduces PL3:
```
priority, when,                    gate, comment
10,       addr ~ /i/,              In,   address carries an I
20,       addr ~ /O|Q/,            Out,  address carries an O/Q
30,       id_node > 0,             Node, a positive node id
```
(No match → blank gate → the row stays unclassified.) The computed `gate` is then a field the
`script_type_rules` filter on. Making it rule-driven keeps every classification input in config.

### `config_project/input_docs/script_type_rules.csv` — schema
| column | meaning |
|---|---|
| `priority` | int; ascending eval order **within a gate**; **first match wins** |
| `gate` | `In` \| `Out` \| `Node` \| `any` — the rule applies only under this IO class |
| `when` | a predicate expression over the fields (empty = always true) — grammar below |
| `type` | the resulting script_type: literal text + `{token}` interpolation |
| `comment` | human note |

A row with no matching rule in its gate yields `""` (unclassified, left blank — same as PL3).

### The expression engine — its OWN reusable module (decision: standalone + expandable)
`pipeline4/core/rule_expr.py` — a self-contained recursive-descent expression engine, NOT tied to ph200,
with a **thorough syntax guide in its module docstring** (so it's the one place to learn/extend the
grammar). It exposes `test(predicate, ctx) -> bool` (for `when` / `gate_rules.when`) and
`render(template, ctx) -> str` (for `type`). `ctx` is a dict of row fields. Reusable by future phases; the
existing `dbtemplate.py` predicate DSL stays as-is for now (we can converge it onto this later).

### The predicate grammar (`when`)
- `field ~ /regex/` (case-insensitive search), `field = "x"`, `field != "x"`, `field in ["a","b"]`.
- `field > N` / `>= <= < =` numeric comparisons (numeric-coerced) — e.g. `id_node > 0`, `len(desc) > 3`.
- functions: `numeric(field)`, `len(field)`, `isdigit(EXPR)`, `extract(field, /regex/, part)` where
  `part ∈ { last, first, group<N> }` (`last` = last char of the first match — PL3's `_last`).
- `and` / `or` / `not` / `(...)`.
- Fields available: `d1 d2 desc addr id_node type_hw functional_unit location device gate`.

### The result template (`type`)
Literal text + `{...}`: `{field}` (e.g. `{type_hw}`), `{extract(field,/re/,part)}`, and `{INPUT_REQUIRED}`
(the `<input required>` sentinel). A fallback is just a **lower-priority rule** (first-match-wins), so the
two-way conditionals (`R{area}` vs `R*`) and the catch-alls become ordered rule pairs.

### The full §6 ladder mapped to CSV rows (proves coverage — this IS the shipped default)
```
priority, gate, when,                                                              type,                          comment
10,  Node, ,                                                                       {type_hw},                     node -> Type col R verbatim
20,  In,  desc ~ /EMERGENCY PUSH.BUTTON PRES/,                                     E{extract(d2,/CH./,last)}/2,   emergency push-button
21,  In,  desc ~ /FEEDBACK.*SAFE.*(RELAY|CONTACTOR)/,                              KI,                            safety relay/contactor feedback
22,  In,  desc ~ /DOOR.*OPEN/ and d2 ~ /CH/,                                       DI{extract(d2,/CH./,last)}/2,  door channel input
23,  In,  desc ~ /DOOR.*OPEN/ and d2 ~ /RESET/,                                    DR,                            door reset
24,  In,  desc ~ /DOOR.*OPEN/,                                                     DD,                            door (plain)
25,  In,  desc ~ /SAFETY ENCODER.*PHOTO/,                                          N{extract(d2,/CELL.\d/,last)}/2, encoder photocell
26,  In,  desc ~ /SWITCH DISCONNECTOR.*OPEN/,                                      B{extract(d2,/CH./,last)}/2,   switch-disconnector/breaker
27,  In,  desc ~ /FIRE ALARM/,                                                     F{extract(d2,/CH./,last)}/2,   fire alarm
28,  In,  desc ~ /EMERG.*RESET/ and isdigit(extract(d2,/AREA ./,last)),           R{extract(d2,/AREA ./,last)},  emergency reset (area n)
29,  In,  desc ~ /EMERG.*RESET/,                                                   R*,                            emergency reset (no area)
30,  In,  len(desc) > 3 and type_hw != "",                                         {type_hw},                     IN catch-all -> Type col R
31,  In,  len(desc) > 3,                                                           {INPUT_REQUIRED},              IN catch-all -> sentinel
40,  Out, d1 ~ /(SAFE.*(RELAY|CONTACTOR)|CUT.OFF.*AREA)/,                          KQ,                            safety relay/cut-off (desc1)
41,  Out, d1 ~ /DOOR.*OPEN$|SOLENOID.*CONTROL/,                                    DQ,                            door open / solenoid (desc1)
42,  Out, d2 ~ /(SAFE.*(RELAY|CONTACTOR)|CUT.OFF.*AREA)/,                          KQ,                            safety relay/cut-off (desc2)
43,  Out, desc ~ /DOOR.*LAMP/,                                                     DL,                            door lamp
44,  Out, d2 ~ /EMERGENCY AREA \d/,                                               Z{extract(d2,/AREA ./,last)},  emergency-area output
45,  Out, len(desc) > 3,                                                           {INPUT_REQUIRED},              OUT catch-all -> sentinel
```
Notes: OUT has NO Type-col fallback (only IN does). The `d1`-then-`d2` KQ ordering (40 before 42) is
load-bearing. Adding a new type = adding a row.

### AB vs AC
`suggested_type` (AC) is the app-owned column — **always rewritten** with the computed value each run. AB
(`script_type`) is written only when blank/sentinel (Mode-1); a genuine human AB value is **preserved**
(Mode-2) and propagates downstream + is audit-logged.

---

## §7 — Index = object grouping (220) — detail at build
The index is the OBJECT id; all signals of one object share it. Per-family contiguous numbering
(4-digit), driven by `object_families.csv` (PL4 already has it) — `link` strategy decides object membership:
channel-pair (E/B/N/F), KQ↔KI series (K), door-FLD (D), Z-pattern (Z), reset (R), standalone. A genuine
numeric pre-filled index is preserved (idempotent). Members that can't be grouped → `<input required>`
(reasons: channel_fld_mismatch / door_member_unlinked / manual_member / ki_without_kq). Exact mechanics
re-confirmed against PL3 when 220 is built.

## §8 — Diagnosis cabinet/bit (230/240) — detail at build
`cap = diag_bit_max - diag_bit_min + 1`. Only `in_diag` non-skipped rows. Type-1 **node cabinets** (one per
node FL; non-P bits up from min, P bits down from max; a lone PA/PW → the shared `+FieldIODevices` block);
Type-2 **family blocks** (`+SafetyDoors/...`; bit a deterministic function of index+channel). **Idempotency:
stable `ID_Local` reused by `full_name`; bit allocation seeded from existing `ex_diag_bit` so a re-run never
duplicates a `(cabinet,bit)`.** DiagnosisBlocks sheet = identity columns (append-only) + derived columns
(Count/unused_bits/non_unique_bits, recomputed). Exact mechanics re-confirmed when 230/240 are built.

## Write mechanics (decision 3 — doc only)
1. **Doc, in place, surgical** via `io/xlsx_edit` (PL4 already ported it): edit only filled cells, append
   DiagnosisBlocks rows, rebuild `_UnresolvedIndex`, byte-copy the rest, drop calcChain, freeze array
   spills. Timestamped `.bak_` first; **deleted if the workbook is value-identical** afterward.
2. **No DB write.** Staging (300) reads the now-filled doc and builds signals / diagnosis_cabinets — the
   data reaches the SSOT via the existing staging path (1:1 with PL3).
3. **HALT** downstream when any non-skipped row stays `<input required>` → a blocking Finding (severity
   model), plus the `_UnresolvedIndex` sheet for the operator.

## Parity oracle
PL3's populator over the same raw doc → compare computed `script_type`/`index`/`diag_cabinet`/`diag_bit`
per row + the cabinet set. Each sub-phase committed with its gate + this parity green.

## Progress
- **210a — classification core DONE.** `core/rule_expr.py` (the reusable expression engine + syntax guide)
  + `config_project/input_docs/gate_rules.csv` + `script_type_rules.csv` (the full §6 ladder) +
  `config.load_gate_rules`/`load_script_type_rules` + `domain/fillout/classify.py` (+ `reader.py`). Gate
  green (`test_rule_expr` 8, `test_fillout_classify` 5). **PARITY: 273 rows, 0 mismatches vs PL3's
  `script_type.suggested_type`** on the real doc.
- **210b — fill write-back + GUI DONE (210 operable).** `domain/fillout/fill.py` - `fill_script_type`:
  per row compute the type, write AC always + AB Mode-1 (blank/sentinel only), preserve AB Mode-2 (a human
  value) + a `fill_type_mismatch` WARN audit; surgical write via `io/xlsx_edit` (output-col headers if blank,
  the `_UnresolvedIndex` sheet with cell hyperlinks); timestamped backup, DELETED on a value-identical no-op;
  an unresolved row (`<input required>`, not skipped) -> a blocking `fill_unresolved` finding. **Doc only, no
  DB write.** GUI: phase 200 added to the registry (210 enabled; 220/230/240 greyed; 250 Open I/O List) +
  `_run_fill` handler (gated/halt-capable); excluded from Run-all until the full fill lands. Tests:
  `test_fillout_fill` (2: Mode-1/2 + unresolved + `_UnresolvedIndex`; idempotent no-op drops the backup);
  `test_gui_phases` updated. **Real-data smoke (non-destructive scratch copy):** filled=0 / mismatch=8 (the
  doc's 8 hand-overrides vs the ladder - PL3 flags the same) / unresolved=0; a re-run is a no-op. GUI-verified
  on screen (the 200 dropdown: 210 enabled, 220-240 greyed, 250 open).
- **NEXT:** 220 (§7 index = object grouping) · 230/240 (§8 diag cabinet/bit). Each: re-confirm the PL3
  mechanics, build, parity-check, add to the fill + the Run-all once complete.
