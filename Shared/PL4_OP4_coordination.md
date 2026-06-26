# PL4 ⇄ OP4 — coordination brief (for the Openn / importer Claude session)

**Audience:** the Claude session working on **OP3** (`Openn3App/`) that will go on to build **OP4**.
**Author:** the PL session (building **PL4**, the new pipeline). This is a heads-up + a coordination protocol so the two v4 apps land as a matched pair. Read it before changing the import format.

---

## Naming (house convention)
- **PLn** = the Python pipeline (`Pipeline2App` → `Pipeline3App` → **`Pipeline4App`**). Emits the TIA `BuilderData/`.
- **OPn** = the C# TIA-Openness importer (`Open2App` → **`Openn3App`** → **`Openn4App`**). Reads the `BuilderData/`.
- **PL3 + OP3 both WORK today** — they are the stable, shipped pair. v4 (PL4 + OP4) is built **in parallel**, in new directories; PL3/OP3 stay untouched and shippable as the fallback + the reference.
- (Note: PL3's `CLAUDE.md` still says "Open2App" everywhere — that is **stale**; it means OPn. Worth fixing on the OP side's docs too.)

## What PL4 is
A clean-room rebuild of PL3 around a **single source of truth (SSOT) database**. Instead of a flat `IODatabase.csv` with `|`-joined cells and per-phase private output files, PL4 keeps **one in-memory `Database`** of typed **tables** (signals, db_members, diagnosis_entries, plc_tags, hardware_stations/modules, …), persisted as **CSV-with-JSON-cells**. Every phase reads from and **writes its results back into** the database; the `BuilderData/` files become **projections** of those tables. (Full design: `Pipeline4App/DESIGN.md`.)

## The key point for OP4: the contract is CO-DESIGNED
Because OP4 is **new too**, the `BuilderData/` format between PL4 and OP4 is **no longer frozen**. We are free to define whatever import contract maps cleanest onto PL4's tables and onto the TIA Openness API — instead of OP4 being bolted to OP3's legacy import format.

**But we evolve it deliberately, not eagerly.** The agreed strategy:

1. **PL4 starts format-preserving.** Its first builds emit `BuilderData/` **byte-identical to what PL3 emits today**, so:
   - OP3 (and OP4, initially) import PL4's output **unchanged** — a free cross-check that PL4's SSOT spine is correct.
   - The regression oracle is a cheap **byte-diff** of PL4's output vs PL3's.
2. **Then we improve the contract one surface at a time** — only when there's a concrete reason (a cleaner block-import, richer metadata, fewer Excel round-trips). Each change is **proposed in the contract spec, agreed on both sides, implemented on both sides together, and verified end-to-end** (OP4 imports PL4's new output → the resulting TIA project equals what PL3→OP3 produced).

So the **parity gate** has two regimes:
- **Unchanged surface** → PL4 bytes == PL3 bytes (byte-diff).
- **Deliberately-changed surface** → end-to-end equivalence: PL4 → OP4 → TIA project ≡ PL3 → OP3 → TIA project (OP4 import tests + a TIA smoke import).

## What OP4 should do now
- **Keep OP3 working and shippable.** Don't pre-emptively change OP3's import format for PL4 — PL4 will match the current format first.
- **Don't invent a new `BuilderData` format unilaterally.** The format is the shared interface; changes go through the contract spec (below) and are agreed before either side implements.
- **Tell the PL side** if OP3's import format is *already* changing under you (the active edits in `Openn3App/03_ApiManager/TiaPortalOpenness.Blocks.cs` suggest it might be). If the block-import contract is in flux, the PL side needs to know what the target shape is so PL4 aims at OP4's real expectations, not PL3's legacy bytes.

## The shared artifact: the contract spec
The interface between PL4 and OP4 is the **`BuilderData/` contract** — the exact files, locations, and byte formats OP4 imports. Today (PL3 → OP3) that surface is (under `…/TiaPortalProjectInterface/BuilderData/`):

| Surface (PL `OUTPUT_PATHS` key) | Files | Format (current PL3) |
|---|---|---|
| `hardware_dir` | `Stations.csv`, `Modules.csv` | format-2 CSV, **no BOM**, CRLF, `#!format=2` tag + comment header |
| `blocks_import_dir` | `<DB>.xml` (SW.Blocks.GlobalDB), `Diagnostic_for_OPC.scl`, `02_COM.xml`, `03_*` FC-XML | UTF-8 **BOM**, CRLF |
| `blocks_creation_dir` | `CreationInfo/*.csv`, `InstanceDBs.csv` | comma CSV |
| `io_tags_dir` | `PLCTags.xlsx` | TIA "PLC Tags" workbook (PLC Tags + TagTable Properties sheets; %-prefixed addresses) |

PL4 will publish a **versioned contract spec** (per surface: schema + exact byte format + the OP4-side import expectations). When a surface is improved, the spec change is the proposal; both sides implement against the new version.

## Coordination protocol
1. PL side proposes a contract-surface change in the spec (what/why/new bytes).
2. OP side reviews against the TIA Openness API (is it importable? cleaner?).
3. Agree → implement on both sides in the same cycle.
4. Verify end-to-end (OP4 import test + TIA smoke). Until verified, the previous format stays the gate.
5. PL3/OP3 remain the working fallback the whole time.

## Pointers
- PL3's contract details (formats, BOM/CRLF, format-2, the GlobalDB XML shape, the SCL shape) are documented in `Pipeline3App/CLAUDE.md` (Phases 500/600/700/800 + "Conventions & gotchas"). Treat every "Open2App" there as "OPn".
- The import surface = PL's `config.OPEN2APP_KEYS` (rename pending) → `…/BuilderData/`. Nothing outside `BuilderData/` is an import contract (the `ProjectDocumentation/` + `Reports/` trees are PL-internal documentation).
- The PL4 data model + how each table projects to these surfaces: `Pipeline4App/DESIGN.md`.
