# ph100 Before/After Document-Quality Report — Spec

A **standalone, non-pipeline** analysis wrapped under phase 100. It compares the PRIOR revision of the
project's documents (the I/O List + C&E Matrix + AREA sheets) with the CURRENT one and **summarizes the
effort that went into bringing the project to its current state** — completions, corrections, address
re-mapping, and changes to the safety logic, with the items costliest to apply on a built machine
highlighted first. It is **not** a blame tool (it does not judge who produced what) and **not** a
right/wrong verdict; it is a neutral measure of the work done. It NEVER touches the SSOT or the
BuilderData, never gates/halts, is not in `run_order`, and reads only the two workbook revisions → a
self-contained HTML dashboard + a CSV audit trail under `ProjectDocumentation/Reports/`.

The report is **viewer-facing**: no references to the pipeline, the producing software, or internal field
keys / coined acronyms. Field keys render as readable labels; the device identity renders as a bare
reference designation (`=S1+DL1.CC1`), never the internal pipe-joined `=S1|+DL1.CC1|`.

## Central principle — cost, not blame
Address (`bit`) is the costliest parameter to change on a built machine (re-read manuals, re-test,
propagate to many devices; caught late = far worse). So **structural / re-scheme changes (address, slot,
pin, device-tag) are GROUPED BY NODE and COUNTED at the field's weight — never hidden.** A coordinated bulk
re-map is detected and shown as one-line CONTEXT, but every changed row still counts — grouping by node
only tames the per-row noise. Everything sorts most-impacted-first.

## What is and isn't a defect (the non-defect categories)
The analysis separates real signal changes from things that are not defects:
- **Unused channels** = rows with NO description (nothing wired). Kept OUT of the defect counts: unchanged
  → **unused** (light grey); changed → **complementary review** (mid grey, shown LAST, faded). A
  re-addressed free slot is not a defect today, but if a signal is wired into it later a wrong address would
  reproduce the original class of mistake — so it is tracked.
- **Noise** = a change to the device-identity fields (FunctionalUnit+Location-Device) that is only
  punctuation or AT MOST ONE alphanumeric character (a stray text-guard apostrophe, a `--K`→`-K`, a one-char
  typo/renumber). Split PER DIFF into a listing-only **Noise** category; the severity counts are unchanged.
  `_fld_noise` = alphanumeric-stripped Levenshtein ≤ 1; `_lev_le1` the cheap ≤1 check. (Operator's rule —
  applied to the I/O List FLD fields and the AREA `device_tag`; C&E has no itemized identity field.)
- **Struck-through rows** = rows carrying a struck-through cell (any text-bearing cell, via the workbook
  view's `cell_struck`). Counted (just a count) and flagged as a formatting practice to avoid — strike-through
  carries no reliable meaning. Shown in the Noise section with a live strike-through demo.

## User decisions (locked)
- **Matching**: derived empirically from the real corrective-action pair (no single field is stable).
- **New rows**: node-aware split — a whole new block = **upgrade**; an isolated new row = forgotten signal.
- **Weights**: a `change_weights.csv`, 4 tiers (critical/major/minor/exclude), shipped default + per-project tunable.
- **Scope**: I/O List **and** C&E Matrix (+ AREA sheets).
- **Excluded columns**: the `preliminary_check_exclude` (pipeline-owned AA–AH) columns are not compared.
- **Re-schemes** (address/slot/pin/device): grouped by node and COUNTED (never hidden).
- **Direction**: corrections are ONE bucket, each tagged `gap-fill` / `value-change` / `value-loss`.
- **Channel doubt**: ambiguous multichannel blocks collapse to one block-level change.
- **No opinions**: the summary states *what changed*, by field — not whether it was right or wrong.

## Matching cascade (node-scoped, address-blind, deterministic) — `match.py`
Validated: 883/883 old rows matched, 0 false buckets, on the real 8FVX pair.
- **normalize** — strip a leading text-guard apostrophe, collapse whitespace, uppercase.
- **partition** — carry `profinet_name` down to form node blocks (the stable structure).
- keys: `fld` = functional_unit|location|device; `desc` = desc_l1|desc_l1b; `cp` = connector|pin_no.
  Address/slot/pin are NEVER identity keys (they are exactly what gets re-schemed).
- **T1** exact fld+desc unique → **T2** dup-group (multichannel) by connector+pin then position →
  **T3** within-node connector+pin (recovers device-tag renames) → **T4** within-node fuzzy desc/fld →
  **T5** within-node positional spacer fill (hard guard: never pair blank→named).
- Unmatched non-blank old = **removed**; unmatched new = **added**. (Leftovers force-match within a node,
  so removed≈0 by design.) Confidence per pair: T1/T2cp/T3 = high; T2pos = channel-uncertain; T4 = fuzzy.
- C&E cause rows match by **CONCATENATE ID**; AREA rows match by line+description across the pooled sheets.

## Classification — `classify.py`
- No-description rows leave the defect flow (→ `unused` / `complementary_entries` → `complementary_blocks`).
- **Structural / re-scheme fields** (`_GROUP_BY_NODE` = bit/slot/pin/connector, + a bulk device-tag rename)
  grouped by node into `grouped_changes` + `structural` (per-field rollup), COUNTED at the field's weight.
- **`by_tier`** — every described changed row bucketed ONCE by its highest tier (critical/major/minor).
- **`by_nature`** — every described changed row bucketed ONCE by its COSTLIEST change: I/O address re-map >
  completion (all changes are blank→filled gap-fills) > other (value change / rename / re-scheme).
- **`by_field`** — per-field count of described changed rows (the neutral "what was changed" inventory);
  `comp_addr` = the count of unused-channel rows whose change includes an address.
- **`struck_rows`** — current-revision rows with a struck-through cell.
- **FunctionalUnit+Location-Device noise** diffs split out PER DIFF (a row may keep a real correction AND
  contribute a noise diff); `noise_blocks` grouped by node. Counts unchanged.
- **Corrections** (non-structural, non-noise) itemized + grouped by node, direction-tagged; a value-loss on
  critical/major = a **regression** tag; channel-uncertain blocks aggregate + carry a flag.
- **Upgrade** (added rows): contiguous ≥4 in a node = upgrade; isolated = forgotten; 2–3 = review.
- **C&E**: address changes counted (critical); a lost effect (X→blank) = critical regression; a whole new
  effect column rolled across rows = upgrade roll-out; a coherent contiguous added cause block = upgrade.
- **AREA — device-centric membership**: group rows by device (normalized `device_tag`) and compare the SET
  of AREA sheets it belongs to, old vs new → `membership` (+ `membership_summary`): **extended** (areas
  added, none removed = the safety logic grew, the original design did not cover that zone) / **moved** /
  **reduced**. Read **with formulas** (`data_only=False`) — the cells are `=...` strings; a cached read
  fabricates phantom deletions. Device-tag noise split out as for the I/O List.

## Output — `report.py` + `run.py`
Self-contained, light/dark-aware HTML; every value HTML-escaped. Effort-framed intro (no pipeline/software
reference). Readable field labels (singular, `_FIELD_LABELS`); reference designations via `_designation`
(drops the `|` separators). First-issue mode: a missing/identical prior revision degrades to a notice.
- **I/O List** section order: KPI cards → **composition bar** (the new revision's rows, by highest-severity:
  unused · complementary · intact · critical · major · minor · added) → **"What was changed"** (a thin
  stacked bar by correction TYPE / by field, sequential decorative colours, summing to the field-change total
  in used rows, + a per-field legend) → **Structural changes — grouped by node** (+ address callout +
  by-node old→new) → **Corrections — by node** (direction-tagged; channel-uncertain flag) → **Noise —
  FunctionalUnit+Location-Device cleanup** (punctuation/1-char identity changes + the struck-through-rows
  count, with a live strike-through demo) → **Upgrades and Retrofits** (orange) → **Complementary reviews**
  (LAST, faded).
- **C&E** section: cards → I/O address changes (counted, critical) → **New effect column** (upgrade, orange
  badge) → Effects removed (safety-critical) → Cause-row corrections.
- **AREA** section: **Area membership — from → to** (device-centric; added areas orange, removed red, most
  growth first; banner counts the extensions) → Per-area row counts → AREA corrections → Noise (device-tag).
- **CSV** audit trail: structural changes + itemized corrections + AREA membership changes + AREA noise.

## Config / GUI
- `config_project/input_docs/change_weights.csv` — {document, field, tier}; `config.load_change_weights()`.
- `config.changes_report_dir()` + `config.CHANGES_REPORT_STEM`.
- Reads `iolist_path`/`iolist_previous_path` + `matrix_path`/`matrix_previous_path` from `project_params.yaml`.
- GUI: phase-100 sub-button **145** `pb_change_report` (PL4-native, EN/IT) → `_run_change_report` (opens the
  HTML when done). Never halts.

## Expected breakdown (current)
- **8FVX R0.0→R1.2** (the I/O List validation pair): 883 matched; **172 intact, 382 changed, 185 unused,
  144 complementary**. *What was changed* (used rows): 238 I/O addresses (+72 on unused channels), 182 normal
  conditions, 60 slots, 45 pins, 13 hardware types, 13 TS refs, … ; **102 struck-through rows**. C&E: a new
  effect-column roll-out (upgrade) + a coherent added cause block.
- **8FSN R9.3→R14.8** (the C&E/AREA pair): **46 devices changed AREA membership — 15 extended, 31 moved,
  0 reduced** (e.g. a safety relay AREA 6 → AREA 1, AREA 3, AREA 6); 0 struck rows.

## Tests — `tests/unit/test_changes.py` (27, hermetic)
norm/keys, node carry-down, the cascade (incl. force-match), address/value events, systematic netting,
direction+regression, node-aware upgrade, channel-block aggregation, `by_nature` partition, struck-rows
count, FunctionalUnit+Location-Device noise predicate + per-diff split (I/O List + AREA), AREA membership
(extended/moved/reduced, multi-area-not-moved, genuine-move), HTML render smoke, read-error degrade.
