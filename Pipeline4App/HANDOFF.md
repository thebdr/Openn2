# PL4 — HANDOFF (next session)

You are continuing **Pipeline4App (PL4)** — the SSOT-database clean-room rebuild of PL3. Read **`CLAUDE.md`**
(live architecture) and **`DESIGN.md`** (rationale + the locked decisions) first. This file is where we are
and what's next.

## Working agreement (the cadence that's been running)
PROPOSE/explore → SHOW/confirm → implement → keep the data-independent gate green → **commit only on the
user's word**, push only when asked. Each phase is committed with its gate **and** its parity verified.
Commit messages end with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## Where we are
- **Branch `pl4`** (off `tia181920`, remote `origin` = github.com/thebdr/Openn2.git). **`acc8734` is the
  latest local commit and is UNPUSHED** — `origin/pl4` is at `0469039`. Push when the user asks.
- **Gate: 44 tests green** (data-independent). Run from `Pipeline4App/`:
  `for t in tests/unit/test_*.py; do python "$t"; done`
- **`python launch_gui.py`** opens the window; **"300 Documents Staging" stages the real I/O List** → 269
  signals → `Shared/Database/signals.csv`. (sv-ttk present; window builds + runs.)

### Commits so far (oldest → newest)
1. `8a8b9a6` design + the OP4 coordination brief (`Shared/PL4_OP4_coordination.md`)
2. `b1fd380` core spine — `keys` / JSON-cell `Table` / `Database` (adversarially reviewed)
3. `96e9f2e` the `signals` table schema (the fact table)
4. `e45bdd5` config skeleton (paths + sheet resolution) + the shared workbook reader
5. `93363a7` runnable GUI shell
6. `408f339` the nested `project_params` schema + `load_params`/`get_param`
7. `b9ae1b2` restructured `config_project/` (the CSV review)
8. `918a62c` config-CSV loaders (`column_map`, `signal_types`, `resolve_type`)
9. `0469039` **staging** — read the I/O List → the `signals` table (ph300, GUI-wired)
10. `acc8734` **C&E enrichment** (`matrix.annotate`) — `matrix_areas`/`ce_*`/descriptions as list cells

## What's DONE (verified)
- **The spine** (`core/`): the content-hash `uid`, the JSON-cell `Table` (deterministic, fail-loud,
  schema-declared json columns), the `Database` (folder save/load). 21 spine tests; the adversarial review's
  9 findings all fixed (notably the determinism + fail-loud guards).
- **Config**: the nested `project_params.yaml` + `load_params`/`get_param`; the restructured `config_project/`
  (input_docs / datablocks / diagnosis / chain_reactions); the `column_map`/`signal_types`/`resolve_type`
  loaders over `core.table`.
- **Staging direct fields** (ph300): IoList columns + resolved `type` (object cell) + the FLDs + the **full
  C&E enrichment**. **Parity: 269 signals == PL3, 0 dup uids, 0 mismatches on `matrix_areas`/`combined_FLD`/
  `ce_functional_unit`** (matched by `source_cell`). GUI-wired.

## What's NEXT (in order)
1. **Finish staging's direct fields** (the immediate next chunk the user approved):
   - **Node address ranges** — port PL3's `staging._add_node_address_ranges`: a Profinet node owns the rows
     beneath it (positional, in I/O-List order, until the next node / sheet end — NOT keyed by FLD) → the
     `I_/Q_startByte/endByte` columns. (This was a real PL3 bug-fix; keep it positional.)
   - **`IsSorterArea`** — the user changed `sorter_areas` to **numbers** (`matrix_params.sorter_areas: [1]`),
     so map area NUMBER → area NAME (`1` → "AREA 1") and set `IsSorterArea` when `matrix_areas` intersects.
   - Re-run the data-parity (add these fields to the source_cell comparison vs PL3's IODatabase).
2. **Phase 520 — data blocks + the registry-derived signal fields.** Port `datablocks.generate` (PL3's exists)
   over the new `datablock_definitions`/`datablock_elements`(real templates)/`datablock_types`. This produces
   the **`db_members` table**, and **`name_in_db` / `datablocks` / `plc_binding`** derive from the registry
   (decide: compute at staging by evaluating the registry per signal, so 400/600 don't need to wait; or write
   them back after 520). Project `db_members` → the GlobalDB XML (`BuilderData/`). **NOTE**: the real-template
   relocation changes member declaration order (grouped-by-type) — functionally identical for Optimized DBs +
   OP4 co-design, so 520 parity is **functional/end-to-end, not byte-identical to PL3** (user accepted).
3. **The other phases**, each: port → write its table → project to `BuilderData/` → parity. 400 interfaces,
   510 tags, **600 diagnosis** (the unified trigger-driven DiagList + `source` io|logic + **tristate** — to be
   IMPLEMENTED this run, per the user: the 3rd alarm state, "alarm was on", via the warning UDInts), 700
   hardware, 800 software, 900 coverage (a join over the tables), 100 validation. Wire each into its GUI button.

## Deferred relocations (data still lives in PL3's `signal_types`, pull it when the phase ports)
PL4's `signal_types.csv` was stripped of `db_names`/`db_element` (→ `datablock_elements`, done) AND
`in_diag`/`diag_logic`/`diag_desc`/`tristate_desc`/`diag_container_check` (→ diagnosis, **ph600**) AND
`interface_tagname` (→ chain_reactions, **ph400**). The latter two are NOT yet in their PL4 homes — build them
when those phases port, verifying against PL3's `signal_types`. Also pending: convert the registry CSVs'
`|`-list columns to **JSON cells** (DESIGN 10.6) when their loaders are written.

## Locked decisions (DESIGN §10 + the reviews) — don't relitigate
- **Keying**: every entity carries a content-hash `uid` excluding volatile bits (survives a doc revision).
- **DB on disk**: the `Database/` is a **top-level folder** (`Shared/Database/` or `<project>/Database/`).
- **GUI inspection** (deferred): JSON cells get a distinct colour + tooltip + click-to-popup.
- **Raw kept alongside structured** in `signals` (10.5). **No legacy management** (10.6) — PL4 reads source
  docs fresh, never PL3 intermediates; config is the JSON-cell skeleton. **Verbose naming** (10.7).
- **Diagnosis mirrors the datablocks model**: one trigger-driven creation point → one unified DiagList with a
  `source` (io|logic) column. **`datablock_elements` fully supersedes** the old follower role.
- **Identity reads `row["type"]`** (the object cell), not `_type`.

## Parity tooling (reuse it)
Match PL4 signals to PL3's frozen IODatabase by `source_cell` and diff fields. The PL3 reference is
`Shared/OutputTree/ProjectDocumentation/InformationDatabase/IODatabase.csv`. The pattern that's been used:
```python
from pipeline4.domain import staging
db = staging.stage(); pl4 = {r['source_cell']: r for r in db['signals'].rows if r.get('source_cell')}
# load PL3 IODatabase.csv by source_cell; compare the field (PL4 list vs PL3 '|'-split, scalars direct)
```

## OP4 coordination
`Shared/PL4_OP4_coordination.md` briefs the OP-side session: PLn/OPn naming, that PL3/OP3 stay the working
pair, that the `BuilderData/` contract is **co-designed** (build format-preserving first, evolve per-phase,
verify end-to-end). When a `BuilderData/` surface lands (520/600/700/800), keep it byte-stable to PL3 first;
contract changes go through that spec and are agreed both sides.

## Gotchas
- **openpyxl turns a leading `=` into a formula** (cached value None under `data_only`) — in synthetic test
  xlsx use non-`=` values; real IoLists store FU/Loc/Dev as text so `stage()` reads them.
- The `Table.read_csv` is **strict** (ragged/duplicate-header/bad-JSON → located error) — good for machine
  tables; config uses `read_config_csv` (tolerant: skips blank/all-empty rows).
- Staging runs **inline on the GUI thread** for now (a few seconds on a real workbook) — a worker thread
  comes with the engine.
- `acc8734` is **unpushed**.
