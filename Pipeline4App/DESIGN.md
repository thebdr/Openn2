# Pipeline4App (PL4) — design: an SSOT database pipeline

**Status:** DRAFT for review. No phase code yet. This document is the thing to agree on first.

PL4 is a clean-room rebuild of **PL3** (`Pipeline3App`) — which works and stays shipped — around a **single source of truth (SSOT) database**. Its matched importer is **OP4** (`Openn4App`); the PL4⇄OP4 `BuilderData/` contract is co-designed (see `Shared/PL4_OP4_coordination.md`). Naming: **PLn / OPn**.

---

## 1. Why (the thesis)

PL3 stages a flat `IODatabase.csv` (`ctx.rows` = `list[dict]`) and each phase reads it and writes its own private output files. That works, but it forces a set of **workarounds that exist only because cells are flat scalars**:

- **7 `|`-joined columns** (`datablocks`, `matrix_areas`, `areas_description`, `interface_mapping`, + config `db_names`/`required_types`/`member_types`) split-and-rejoined at **~20 sites**.
- The **"leftmost db name"** hack (`plc_binding`, builder 03) — `datablocks.split('|')[0]`.
- **`_type` is dropped on persist** — staging computes the resolved type dict but writes only `type_id_resolved`/`type_category`, so the persisted DB **can't be read back** without re-deriving `_type`; consumers depend on it being live in RAM.
- **`plc_binding` is never stored** — re-derived on every call from flat cells.
- The **created data lives only in export files** — DB members exist only in the XML, diagnosis entries only in the DiagList CSVs, tags only in PLCTags.xlsx. There is no one place that holds "everything the pipeline retrieved, inferred, or created."

**PL4's principle (the user's directive):** *every phase, every transform — every datum retrieved from the documents, inferred, or created — is written into the database. The database holds it all: every io signal, every db_element, every diagnosis element.* The export files (for OP4) become **projections** of the database, not separate truths.

This is **not** a SQL engine. It is **CSV files with JSON cells** + an in-memory `Database` object. Light, file-based, git-diffable, GUI-grid-able, no new dependency — but structured (real lists/objects) and comprehensive (every entity, queryable).

## 2. The shape: one `Database`, many tables

```
Database
 ├─ signals            one row per I/O signal (+ node/metadata rows)   ← the fact table
 ├─ db_members         every generated DB member (db_element)          ← 520 writes
 ├─ instance_dbs       FB instance DBs                                  ← 520/800 writes
 ├─ diagnosis_entries  every diagnosis element (cabinet/bit/binding)   ← 600 writes
 ├─ plc_tags           every PLC tag (io + interface sources)          ← 510 writes
 ├─ interfaces         interface instances + their mirrored signals    ← 400 writes
 ├─ hardware_stations  one per station head                            ← 700 writes
 ├─ hardware_modules   one per card slot                               ← 700 writes
 ├─ software_blocks    builder outputs / CreationInfo rows             ← 800 writes
 ├─ coverage           per-signal trace across outputs (derived)       ← 900 writes
 └─ validation_issues  findings + treatments                           ← 100 writes
```

- Each table persists to one **CSV-with-JSON-cells** file under the **Database directory** — its own top-level folder: **`Shared/Database/`** (builtin) or **`<project>/Database/`** (project), parallel to `Output/`, NOT inside the output tree (§10.3). The `signals` table is the successor of today's `IODatabase.csv`.
- **Every created/inferred entity references its source** (a foreign key): `db_members.source = signal_id | cabinet | "seed" | "cumulative"`, `diagnosis_entries.source = signal_id | rule_id`, `plc_tags.source = signal_id | interface_id`, etc. So coverage/trace is a **join**, not a re-read of files.
- **Row order is data** (hardware station grouping, member order in a DB). Each table has an integer **`id`** primary key that preserves order across re-runs.

### Why tables, not one big JSON-per-signal blob
Several created entities **don't map 1:1 to a signal**: DB seed members (`Always FALSE/TRUE/No Operation`), the per-cabinet `DiagnosticTags` members, the `02_COM` AREA cumulatives, rule-generated diagnosis logic rows. They are first-class records with their own provenance. A `signals`-only model would have to bolt them on awkwardly; separate tables keep each entity honest and the projections clean.

## 3. The `signals` table (the fact table)

One row per IoList row kept by staging (signals + node/metadata). Columns by **provenance**:

- **RETRIEVED** (from the documents, verbatim): all IoList canonical columns (via `column_map`), plus C&E-derived `matrix_areas` **(JSON list)**, `areas_description` **(JSON list, parallel to matrix_areas)**, `ce_functional_unit/location/device`, `numerazione_linea`; DiagnosisBlocks-derived `diag_block_name/template`, `swp_cabinet`.
- **INFERRED** (computed at staging): the **resolved type** `type` **(JSON object — the former `_type`, now PERSISTED)**; `iol_FLD`/`ce_FLD`/`combined_FLD`; `IsSorterArea`; identity `name_in_db`, `name_in_tagtable`, `tagtable`, `datablocks` **(JSON list)**, `diag_desc`, `interface_tagname`; **`plc_binding` (STORED, not re-derived)**; `subnet_name`; the positional node ranges `I/Q_startByte/endByte`.
- **PROVENANCE**: `source_sheet`, `source_row`, `source_cell` — and a **stable `uid`** = `sha1` of the row's identifying content (the universal key, §10.1; generalizes PL3's finding-uid `sha1(phase|type|location|detail)`, **excluding** volatile bits — workbook/seq/level — so it survives a document revision). Created entities FK to this `uid`.

**This kills the shenanigans outright:** `datablocks` is a real list (`[0]` is the leftmost, typed); `type` round-trips so nothing re-attaches it; `plc_binding` is stored so nothing re-derives it; `matrix_areas`/`interface_mapping` are lists so no `.split('|')`.

## 4. Serialization: CSV with JSON cells (schema-driven)

- The container stays **CSV** (one file per table) — so git diffs, the GUI grid, and Excel still work.
- Each table **declares which columns are JSON** (lists/objects). The reader `json.loads` those columns; the writer `json.dumps` them. Scalar columns stay plain text. **No in-cell markers** (a column is JSON by schema, not by guessing).
- CSV quoting: `QUOTE_MINIMAL` quotes a JSON cell (it contains `,`/`{`/`"`); round-trips cleanly. Delimiter sniffing is unaffected (JSON commas are inside quotes).
- **No legacy reader** (§10.6) — PL4 is a clean skeleton; there is no `|`-list back-compat path. The config CSVs use the same JSON-cell format. PL3/OP3 own legacy data.

The single serialization point is `core/table.py` (read/write a typed table) — the successor to PL3's `io/csv_tables`.

## 5. The `Database` object (the access layer)

In-memory, holds all tables; the one API every phase uses (generalizes PL3's phase-800 `Database`):

- **Query:** `db.signals.where(pred)`, `.by_type(t)`, `.by_db(name)`, `.by_area(a)`, `.first(...)`, `.areas()` — now over **native lists** (no parsing).
- **Write-back:** `db.db_members.add(...)`, `db.diagnosis_entries.add(...)`, … — each phase appends its created records.
- **Relations:** `db.db_members.for_signal(sig.id)`, `db.diagnosis_entries.by_cabinet(c)`, etc.
- **Persist / load:** `db.save(dir)` / `Database.load(dir)` — each table to/from its CSV-with-JSON-cells. A run can resume from a saved DB (all tables, fully typed, no re-derivation).

`ctx` carries the `Database` instead of a bare `rows` list.

## 6. Per-phase mapping (read → write)

Same phase numbers/registry as PL3. Each phase READS the DB and WRITES its table(s); the **export projection** (§7) is a separate, swappable step.

| Phase | Reads | Writes (table) | Export projection (for OP4) |
|---|---|---|---|
| 200 Fill | source docs | (writes the populated IoList in place — unchanged) | — |
| 300 Stage | populated IoList + C&E + DiagnosisBlocks | **`signals`** (retrieved + inferred, JSON cells, stored `type`/`plc_binding`) | `signals.csv` (internal doc) |
| 100 Validate | `signals` | **`validation_issues`** | validation reports (internal) |
| 400 Interfaces | `signals` (`interface_mapping` list) | **`interfaces`** (+ mirror records) | `IF_*.xlsx` (internal); inserted IF sheets |
| 510 I/O Tags | `signals` + `interfaces` | **`plc_tags`** | `PLCTags.xlsx` (**contract**) |
| 520 Data Blocks | `signals` + the datablock registry CSVs | **`db_members`**, **`instance_dbs`** | `<DB>.xml` (**contract**) |
| 600 Diagnosis | `signals` + DiagnosisBlocks + rules | **`diagnosis_entries`** | `DiagList_*.csv` (internal), `Diagnostic_for_OPC.scl` (**contract**) |
| 700 Hardware | `signals` + DeviceTypesDB | **`hardware_stations`**, **`hardware_modules`** | `Stations.csv`/`Modules.csv` (**contract**) |
| 800 Software | `signals` + editable shells | **`software_blocks`**, `instance_dbs` | CreationInfo `*.csv`, `02_COM.xml`, `03` FC-XML (**contract**) |
| 900 Coverage | **all tables** (a join) | **`coverage`** | coverage report (internal) |

**900 becomes a query, not a re-read.** Today coverage re-opens every output file on disk; in PL4 it joins `signals ← {plc_tags, db_members, diagnosis_entries, hardware_*, software_blocks}`. ORPHAN = a signal no table references; UNPLACED = a binding referencing a `db_members` row that doesn't exist. Fast, auditable, no Excel round-trip.

## 7. The export-projection layer (the OP4 contract)

Each `BuilderData/` file is **generated FROM a table** by a small projector. In the **format-preserving** regime, every projector reproduces **PL3's exact bytes** (BOM/CRLF/format-2/the GlobalDB XML shape) → byte-diff vs PL3 is the regression oracle, and OP3 can import PL4's output unchanged.

Projectors (table → bytes):
- `hardware_stations`+`hardware_modules` → `Stations.csv`/`Modules.csv`
- `db_members` (grouped by `db_name`) → `<DB>.xml`; `instance_dbs` → `InstanceDBs.csv`
- `diagnosis_entries` (+ cabinets) → `Diagnostic_for_OPC.scl`
- `plc_tags` → `PLCTags.xlsx`
- `software_blocks` → CreationInfo `*.csv`, `02_COM.xml`, `03` FC-XML

When a surface is **deliberately improved** with OP4, only its projector + OP4's importer change; everything upstream (the tables) is untouched. This is the seam that makes the contract co-evolvable.

## 8. What carries over from PL3 (~60–70% reuse)

Reused largely as-is (architecture-independent), adapted only at the data-access boundary:
- `io/workbook` (the one workbook reader), the **whole GUI** (`gui/*` — grid gains JSON-cell handling + multi-table view), `domain/validation/*`, the **templates + `Shared/` handoff**, the **config CSVs + loaders**, **`dbtemplate` + `datablocks`** (already config-driven — they become `db_members` producers), the phase **registry / numbering / i18n / context** machinery, the **Project Manager**, the treatment registry.

Genuinely new (the spine):
- `core/database.py` (the `Database` + tables), `core/table.py` (JSON-cell CSV), staging rewritten to populate `signals`, every phase rewired to read/write tables, the **export-projection layer**, stored `type`/`plc_binding`, the write-back tables.

## 9. Build sequencing (each step keeps a green gate + byte-parity)

1. **Spine:** `core/table.py` (JSON-cell codec, round-trip tests) + `core/database.py` (tables + query + persist).
2. **`signals`:** port staging → populate `signals` with native lists + persisted `type` + stored `plc_binding`. **Verify:** the `signals.csv` content is equivalent to PL3's `IODatabase.csv` data (modulo JSON cells), and `signals` round-trips losslessly.
3. **Per phase, in dependency order** (700 → 510 → 520 → 600 → 400 → 800 → 900 → 100): build the write-back table + the projector, **byte-diff the projected `BuilderData/` against PL3** on the same inputs. Hardware first (smallest contract), then tags/blocks/diagnosis.
4. **Cutover:** when all phases are on the `Database` and byte-parity holds across `BuilderData/`, PL4 is at parity with PL3. PL3 stays the fallback.
5. **Contract evolution (later, with OP4):** improve surfaces one at a time, end-to-end verified.

Throughout, the **data-independent gate** (PL3's discipline) is rebuilt per module, and the **parity oracle** (PL4 bytes == PL3 bytes) guards every projector.

## 10. Decisions

**RESOLVED**

1. **Keys/idempotency** ✓ — every entity (and every finding) carries a **`uid` = `sha1` of its stable identifying content**, generalizing PL3's finding-uid `sha1(phase|type|location|detail)[:10]` (`core/model.py:78`). It **excludes volatile bits** (workbook name, sequence, level) so it survives a document revision — that exclusion is the whole point. Treatments key on it (as today); every created entity FKs to its source's `uid`. (Confirmed PL3's uid already works this way.) *Design detail to specify per table:* the exact identifying fields hashed (e.g. a signal = `combined_FLD` + `type_id` + `channel`, with a tiebreak for genuine duplicates).
2. **Table granularity** ✓ — the §2 table set stands as proposed.
3. **DB on disk** ✓ — the Database is its **own top-level main folder**: **`Shared/Database/`** (builtin) or **`<project>/Database/`** (project), parallel to `Output/`, NOT inside the output tree. One CSV-with-JSON-cells file per table.

4. **GUI inspection** ✓ *(deferred — "for later", after the core arc)* — a JSON cell renders in a **distinct font colour**; **hover shows a tooltip with the JSON content**; **click opens a popup** (JSON viewer/editor). Per-table grid + a table switcher as the frame; relation-following (signal → its `db_members`/`diagnosis_entries`/`plc_tags`) a later enhancement.
5. **Raw vs structured** ✓ — keep the IoList raw columns verbatim in `signals` **alongside** the structured cells.
6. **Clean skeleton — NO legacy management** ✓ — PL4 is built end-to-end on the new skeleton: **config CSVs also use JSON cells** (no `|`-list legacy), and there is **no backward-read / migration** of PL3-format artifacts. **Legacy data is processed by PL3/OP3** (the working pair). PL4 reads the same *source documents* (I/O List, C&E) fresh and emits byte-identical `BuilderData/` for OP4, but never ingests PL3 intermediates. *(This removes the migration/dual-format code a refactor would have needed — a real simplification.)*
7. **Naming/structure** ✓ — **verbose, explicit structure and naming preferred**; reuse a PL3 module name only where the carryover is genuinely the same concept.

---

*All decisions locked. Next: build the spine (`core/table.py` + `core/database.py`), then the `signals` port, against the PL3 parity oracle.*
