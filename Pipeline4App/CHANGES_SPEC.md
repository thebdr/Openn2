# ph100 Before/After Document-Quality Report — Spec

A **standalone, non-pipeline** analysis wrapped under phase 100 (Documents Validation). It compares a
PRIOR document revision against the CURRENT one (the I/O List + C&E Matrix + AREA sheets) and classifies
every row **intact / corrected / upgrade / removed** to expose **human document-quality** problems — a
"what went wrong" review that helps spot workflow/skill weaknesses. It NEVER touches the SSOT or the
BuilderData, never gates/halts, and is not in `run_order`. It only reads two workbook revisions and
writes a graphical HTML dashboard + a CSV audit trail under `ProjectDocumentation/Reports/`.

## The central risk it solves
A naive column-by-column diff of a real revision pair (8FVX R0.0→R1.2) reports **~369** I/O "corrections"
and **~97** C&E ones — but the genuine human-defect residue is **~14–40 rows**. The bulk is a handful of
**deliberate, deterministic re-schemes** (a 310-row address re-map = 36 byte-rules; a confined re-slot; a
cyclic re-pin; a device-tag rename). Counting those as hundreds of "mistakes" buries the real ones. The
whole design exists to **net systematic re-schemes out of the defect count** and surface the small real
residue + regressions clearly.

## User decisions (locked)
- **Matching**: derived empirically from the real corrective-action pair (no single field is stable).
- **New rows**: node-aware split — a whole new node/block = **upgrade**; an isolated new row = correction.
- **Weights**: a `change_weights.csv`, 3 tiers (critical/major/minor), shipped default + per-project tunable.
- **Scope**: I/O List **and** C&E Matrix (+ AREA sheets).
- **Excluded columns**: the `preliminary_check_exclude` (pipeline-owned AA–AH) columns are not compared.
- **Re-schemes**: shown as their own section, as churn, **kept out of the defect count** (confirm-intentional).
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
- **Systematic events** (netted out of the defect count): address byte-level bijection (a prefix flip
  I↔Q is NEVER systematic — it stays a genuine critical defect); low-cardinality value re-map for the
  STRUCTURAL fields {slot, pin_no, connector}; the T3-matched device-tag rename. Semantic fields
  (type_hw, normal_condition, descriptions, ts_ref, mnemonic) are never systematic.
- A pair is **corrected** iff it has ≥1 changed compared field NOT explained by a systematic event;
  **intact** otherwise. Row tier = the max tier of its genuine changed fields. Each diff is direction-
  tagged; a value-loss on critical/major = a **regression**.
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

## Expected breakdown (8FVX R0.0→R1.2, the validation pair)
- **I/O List**: 883 matched, 514 intact, ~39 genuine corrections (incl. 14 value-losses — the 2 CPU
  `Type` drops + DL `normal_condition` losses), 3 systematic re-schemes (address 310 / slot 72 / pin 51)
  netted out, +32 upgrade rows (UL1/UL2 telescopic-belt feedback), 0 removed, 3 channel-uncertain blocks.
- **C&E**: 101 matched, 0 isolated corrections, address re-map (1 event), AREA-2 effect roll-out (97
  rows = upgrade), +26 contiguous cause rows (upgrade block), 0 effects deleted, 0 removed.
- **AREA**: a real reorganization — AREA-1 43→4, AREA-2 0→37, 37 rows moved sheet, 2 removed (NOT a
  cache artifact; surfaced, not suppressed).

## Tests — `tests/unit/test_changes.py` (11, hermetic)
norm/keys, node carry-down, the cascade (incl. force-match), address-event (prefix-flip stays genuine),
value-event (low-card vs high-card), systematic netting, direction+regression, node-aware upgrade,
channel-block aggregation, HTML render smoke, first-issue mode.
