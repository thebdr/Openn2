# ph100 Before/After Document-Quality Report — Spec

A **standalone, non-pipeline** analysis wrapped under phase 100 (Documents Validation). It compares a
PRIOR document revision against the CURRENT one (the I/O List + C&E Matrix + AREA sheets) and classifies
every row **intact / corrected / upgrade / removed** to expose **human document-quality** problems — a
"what went wrong" review that helps spot workflow/skill weaknesses. It NEVER touches the SSOT or the
BuilderData, never gates/halts, and is not in `run_order`. It only reads two workbook revisions and
writes a graphical HTML dashboard + a CSV audit trail under `ProjectDocumentation/Reports/`.

## The central principle
Address (`bit`) is the single most important parameter — a re-addressing is the costliest correction to
apply on a built machine (re-read manuals, re-test, propagate to many devices; caught late = far worse).
So **structural / re-scheme changes (address, slot, pin, device-tag) are GROUPED BY NODE and COUNTED at
the field's weight — never hidden.** The bulk in the real 8FVX R0.0→R1.2 pair (a 310-row address re-map,
a re-slot, a re-pin) is detected as a *coordinated* re-map and shown as one-line CONTEXT, but every changed
row still counts — grouping by node only tames the per-row noise. (An earlier version wrongly netted these
out of the defect count; corrected per the user's feedback.) Other field changes are itemized per row.

## User decisions (locked)
- **Matching**: derived empirically from the real corrective-action pair (no single field is stable).
- **New rows**: node-aware split — a whole new node/block = **upgrade**; an isolated new row = correction.
- **Weights**: a `change_weights.csv`, 3 tiers (critical/major/minor), shipped default + per-project tunable.
- **Scope**: I/O List **and** C&E Matrix (+ AREA sheets).
- **Excluded columns**: the `preliminary_check_exclude` (pipeline-owned AA–AH) columns are not compared.
- **Re-schemes** (address/slot/pin/device): **grouped by node and COUNTED** at the field's weight (never
  hidden) — a re-addressing is the costliest fix on a built machine. The coordinated pattern is shown as context.
- **Direction**: corrections are ONE bucket, each tagged `gap-fill` / `value-change` / `value-loss`;
  value-losses surface as a sub-count (a tag), not a separate category.
- **Channel doubt**: ambiguous multichannel blocks collapse to one block-level change.

## Matching cascade (node-scoped, address-blind, deterministic) — `match.py`
Validated: 883/883 old rows matched, 0 false buckets, on the real pair.
- **normalize** — strip a leading text-guard apostrophe, collapse whitespace, uppercase.
- **partition** — carry `profinet_name` down to form node blocks (the stable structure).
- keys: `fld` = functional_unit|location|device; `desc` = desc_l1|desc_l1b; `cp` = connector|pin_no.
  Address/slot/pin are NEVER identity keys (they are exactly what gets re-schemed).
- **T1** exact fld+desc unique → **T2** dup-group (multichannel) by connector+pin then position →
  **T3** within-node connector+pin (recovers device-tag renames) → **T4** within-node fuzzy desc/fld
  (rename safety-net) → **T5** within-node positional spacer fill (hard guard: never pair blank→named).
- Unmatched non-blank old = **removed**; unmatched new = **added**. (Leftovers force-match within a node,
  so removed≈0 unless a node has only an old-side leftover — by design.)
- Confidence per pair: T1/T2cp/T3 = high; T2pos = channel-uncertain; T4 = fuzzy; T5pos = positional.
- C&E cause rows match by **CONCATENATE ID**; AREA rows match by line+description across the pooled
  sheets (areas get reorganized, so a row can move sheet — `moved` is flagged).

## Classification — `classify.py`
- **Structural / re-scheme fields** (`_GROUP_BY_NODE` = bit/slot/pin/connector, + a bulk device-tag rename
  when `__rename__` fires) are **grouped by node** into `grouped_changes` (per node+field) + `structural`
  (per-field rollup: address X rows / Y nodes), COUNTED at the field's weight. The report leads with them.
- **Other (semantic) fields** are itemized per row (`corrections`). Every changed row is bucketed ONCE in
  `by_tier` by its highest-tier change — so an address-only row reads **critical**. `changed = matched −
  intact`. Each itemized diff is direction-tagged; a value-loss on critical/major = a **regression** tag.
- **Coordinated-re-map detection** (`detect_address_event` byte-bijection / `detect_value_event`
  low-cardinality) is kept ONLY as `systematic_events` context (a "looks like a re-base" one-liner) + to
  set the bulk-rename flag — it never hides a row.
- **Channel-uncertain** corrections aggregate to one block-level change per (node, fld).
- **Upgrade** (added rows): a contiguous block of ≥4 in a node = upgrade; an isolated row = forgotten
  signal; a 2–3 row cluster = flagged for review.
- **C&E effects**: a lost effect (X→blank in an existing area) = critical regression; a whole new effect
  column rolled across rows = upgrade roll-out. A coherent contiguous added cause block = upgrade.
- **AREA**: per-area row counts, how many rows moved sheet, device-tag/address/line corrections, and a
  structural-reorganization flag. Read **with formulas** (`data_only=False`) — the cells are `=...`
  strings; a cached read fabricates phantom deletions.

## Output — `report.py` + `run.py`
- `io_documents_quality_report.html` — a self-contained, light/dark-aware, print-friendly dashboard
  (KPI cards, composition bar, systematic-events panel, corrections-by-tier/direction, tables of
  corrections / upgrades / regressions / removals). No dependency; every data value HTML-escaped.
- `io_documents_quality_report.csv` — the per-correction audit trail.
- **First-issue mode**: a missing/identical prior revision degrades to a "no prior revision" notice.

## Config / GUI
- `config_project/input_docs/change_weights.csv` — {document, field, tier}; `config.load_change_weights()`.
- `config.changes_report_dir()` + `config.CHANGES_REPORT_STEM`.
- Reads `iolist_path`/`iolist_previous_path` + `matrix_path`/`matrix_previous_path` from `project_params.yaml`.
- GUI: phase-100 sub-button **145** `pb_change_report` (PL4-native, EN/IT) → `_run_change_report`
  (opens the HTML when done). Never halts.

## Expected breakdown (8FVX R0.0→R1.2, the validation pair; tiers per the current change_weights.csv)
- **I/O List**: 883 matched, 514 intact, 369 changed (by_tier critical 338 / major 13 / minor 18).
  Structural (grouped by node, COUNTED): **I/O address re-map 310 rows / 20 nodes [critical]**, module
  re-slot 72 / 3 [critical], connector re-pin 51 / 3 [major]. Itemized corrections 41, channel-uncertain
  blocks 3, +32 upgrade rows (UL1/UL2 telescopic-belt feedback), 0 removed.
- **C&E**: 101 matched, **93 address changes [critical]** (counted), 0 other isolated corrections, AREA-2
  effect roll-out (97 rows = upgrade), +26 contiguous cause rows (upgrade block), 0 effects deleted, 0 removed.
- **AREA**: a real reorganization — AREA-1 43→4, AREA-2 0→37, 37 rows moved sheet, 2 removed (NOT a
  cache artifact; surfaced, not suppressed).

## Tests — `tests/unit/test_changes.py` (16, hermetic)
norm/keys, node carry-down, the cascade (incl. force-match), address-event (prefix-flip stays genuine),
value-event (low-card vs high-card), systematic netting, direction+regression, node-aware upgrade,
channel-block aggregation, HTML render smoke, first-issue mode.
