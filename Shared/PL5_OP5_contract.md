# PL5 ⇄ OP5 — the input contract (v1, draft)

**Audience:** the PL session (`Pipeline5App/`, PL5) and the OP session (`Openn5App/`, OP5).
**Status:** contract **1, draft**. OP5 side implemented (classification, header parsing, legacy acceptance,
scan command); PL5 side implemented 2026-10-08 (migration steps 2 + 3: the header on every surface, the run
id + workspace config, the VCI shape — the legacy layout and the `#!format=2` tag are no longer written).
Open: step 1 (TIA's acceptance of the XML header comment before `<Document>`) is still unverified on a real import.
**Supersedes** the "format-preserving" regime of `PL4_OP4_coordination.md` for the v5 pair only: PL3/PL4 + OP3
stay untouched and shippable; OP5 reads today's PL5 output **with warnings**; PL5 adopts v1 one surface at a time.

The change protocol is unchanged: propose here → review against the TIA Openness API → agree → implement on
both sides in the same cycle → verify end-to-end (OP5 import + TIA smoke). Until verified, the previous
format stays the gate.

---

## 1. Principles

1. **A file says what it is.** Every managed file opens with a header that declares its `kind`. OP5 never
   guesses a kind from a file name, an extension or a folder when a header is present.
2. **Location says where it lands.** The workspace is shaped like a TIA Version Control Interface (VCI)
   workspace: `<PLC>/Program blocks/<group>/…`. The folder decides the TIA target; the header may repeat it
   (`plc`, `target`) and then **must agree** — a mismatch is an error, not a hint.
3. **Nothing silent.** Unknown, invalid, misplaced or stale files are listed and **skipped**, never imported.
   Every skip is logged with the reason and the fix.
4. **Legacy is accepted for one version, with a warning.** OP5 v1 still imports the legacy BuilderData layout and
   the `#!format=2` tag (status `Legacy`). OP5 v2 will require the header.
5. **No host paths in the handoff.** Template references are relative (`Templates/…`); the workspace is
   relocatable (a project's `Output/`, `Output/<system>/`, or the builtin `Shared/OutputTree/…`).
6. **Hardware stations are never completed or compared.** A station already in TIA is skipped with its modules
   (OP3 rule since 2026-10-07, kept); refresh = delete in TIA + regenerate.

---

## 2. What OpennN manages — the kinds

The kind id is written in the header (`kind: hw/stations`). `schema` is the per-kind column/shape version
(hardware csvs continue the format-2 numbering; everything else starts at 1); it bumps only on a breaking
change — a trailing added column (the 9th `Connector`) does not bump it.

| kind | what | file | lives in (TIA folder) | OP5 route | order | schema | producer |
|---|---|---|---|---|---|---|---|
| `hw/device-types` | model database (order no → type identifier, device type, default custom parameters) | `DeviceTypesDatabase.csv` | `Devices & networks` (or `Shared/HardwareConfigBuilderData`) | reference data for hardware generation | 0 | 1 | hand-maintained |
| `hw/stations` | one row per station: `Plc` / `PlcCardCm` / `IoDevice`, IP, PN number, subnet, custom parameters, group, connector | `Stations.csv` | `Devices & networks` | hardware generation | 10 | 2 | PL5 phase 700 |
| `hw/modules` | one row per plugged module of a station: slot order, model, I/Q address, custom parameters | `Modules.csv` | `Devices & networks` | hardware generation | 11 | 2 | PL5 phase 700 |
| `sw/udt` | one PLC data type | `<Name>.xml` (`SW.Types.PlcStruct`) | `<PLC>/PLC data types/…` | `TypeGroup.Types.Import` | 20 | 1 | PL5 (not emitted yet) |
| `sw/tag-table` | one PLC tag table | `<Table>.xml` (`SW.Tags.PlcTagTable`) | `<PLC>/PLC tags/…` | `TagTableGroup.TagTables.Import` | 30 | 1 | PL5 (today: xlsx only, see §9) |
| `sw/data-block` | one global DB (F-DBs included) | `<Name>.xml` (`SW.Blocks.GlobalDB`) | `<PLC>/Program blocks/<group>/…` | `Blocks.Import` | 40 | 1 | PL5 phase 520 |
| `sw/instance-db` | list of single-instance DBs created through the API | `InstanceDBs.csv` (`%` key row `Name, InstanceOf, Number, Folder`) | `<PLC>/Program blocks/<group>/…` | `CreateInstanceDB` per row | 50 | 1 | PL5 phase 830 |
| `sw/block-gen` | template-driven block generation list (`$ template=`, `%` keys, `@` rows) | `<Block>.csv` | `<PLC>/Program blocks/<group>/…` | `BlockXmlGenerator` → `Blocks.Import` | 60 | 1 | PL5 phase 820 |
| `sw/code-block` | one OB / FB / FC | `<Name>.xml` (`SW.Blocks.OB|FB|FC`) | `<PLC>/Program blocks/<group>/…` | `Blocks.Import` | 61 | 1 | PL5 phase 820 (`fc_xml`) |
| `sw/source` | text source compiled by TIA (SCL / STL / DB / UDT) | `.scl .awl .db .udt .st` | `<PLC>/Program blocks/<group>/…` | external source → `GenerateBlocksFromSource` (blocks land in the Program blocks **root** — TIA limitation) | 62 | 1 | PL5 phases 400/620/820 |
| `sw/block-template` | template export referenced by `sw/block-gen` csvs (`TEMPLATE--vX.Y--Name`) | `.xml .scl .db` | `Templates/` (workspace root) or `Shared/Templates/Tia Portal Software Blocks` | never imported by itself | 90 | 1 | hand-maintained (PL5 ships copies) |
| `doc/plc-tags-workbook` | TIA "PLC Tags" workbook for manual GUI import | `PLCTags.xlsx` (+ sidecar) | `<PLC>/PLC tags/` | none (listed) | 100 | 1 | PL5 phase 510 |
| `doc/other` | anything for humans (reports, builder workbooks, readme) | any | anywhere | none (listed) | 101 | 1 | any |

Reserved, not implemented: `sw/technology-object`, `sw/watch-table`, `sw/software-unit` (the remaining VCI
folders `Technology objects`, `Watch and force tables`, `Software units`, `External source files`).

The same kinds describe OP5's **exports** (TIA → PL5 coverage report), with `producer: Openn5 …`.

### 2.1 Model ids in `hw/device-types` (DeviceTypesDatabase.csv)

The Model Id (column 1) is the key both sides share: PL5 writes it into the `Model Id` column of `hw/stations`
and `hw/modules`, OP5 resolves it to the TIA type identifier (column 3) and the model's default custom
parameters (column 5, applied by OP5 only — PL5 never copies them). Three id shapes exist:

| id shape | example | meaning | PL5 (producer) | OP5 (consumer) |
|---|---|---|---|---|
| plain | `55556`, `6ES7131-6BH01-0BA0` | a head (`IoDevice`/`Plc`/…) or a card (`IoDeviceCard`) that appears in the I/O list | emitted where the I/O list names it: the head as a station row, a card as a module row per Slot tag | plugs / creates it by its TIA identifier |
| **default card** `<PARENT>:SUFFIX` | `<55556>:DefaultCard`, `<55556>:STATE_DATA` | a submodule every station of model `PARENT` needs but which neither TIA nor the I/O list provides (e.g. the Murrelektronik FS Data and STATE_DATA submodules) | appends one module row per station of `PARENT`, **after** the I/O-list cards, in database order: `Module Name` = `Model Id` = the full id, `Slot` = next plug position, I/Q Addr and Custom Parameters empty, Comment from the database (`load_device_types_db` → `default_cards`) | no special handling: an ordinary `IoDeviceCard` plugged by name — the TIA module is literally named `<55556>:DefaultCard`; its F-parameters come from the model's column-5 defaults |
| **transfer area** (type `TransferArea`) | `TransferArea-IN`, `TransferArea-OUT`, `TransferArea-IN_OUT` | a PN/PN coupler / I-device transfer area; column 3 holds the Openness `TransferAreaType` name instead of a TIA identifier | a module row per area: `Module Name` = area name, `Slot` = position, I/Q Addr = start addresses in the station's IO controller, lengths as custom parameters (`PartnerToLocalLength=<in bytes>`, `LocalToPartnerLength=<out bytes>`). **PL5 (phase 700, 2026-10-08):** an interface = an `IOC` row under the coupler's head in the I/O list (Index `<TYPE>-<NN>`; base = its Bit, else the coupler head's start column the project maps as `coupler_start`) → two rows, `<TYPE>-<NN>_IN` (`TransferArea-IN`, I Addr = base) and `<TYPE>-<NN>_OUT` (`TransferArea-OUT`, Q Addr = base), positions 1..n per coupler after its cards; the default length is the model's column 5 here (`PartnerToLocalLength=128` / `LocalToPartnerLength=128`, applied by OP5 like any default), a different size is the `IOC` row's Hardware Parameters entry, written on its own area's row | created on the station's PROFINET interface (`NetworkInterface.TransferAreas`), consumes no rack slot |

**Submodules TIA plugs by itself** (e.g. the Lumberg 935023006 F-DI submodule on slot 2) get **no row**
anywhere: PL5 drops the I/O-list card whose Slot tag equals the device's own tag, and its parameters and
addresses are written through the head's station row with explicit paths (`Item(1).Item(3).Item(0).…` in the
head model's column 5 / column 7, exactly as the OP attribute dump prints them). The former documentation-only
`<model>_AutoPluggedCard` database rows were retired on 2026-10-08 — never add them back; a plain id must
always be pluggable.

Default-card ids are case-insensitive on the PL5 side (`PARENT` is matched upper-cased) and must be unique
like any Model Id; a default card's own column 5/6/7 behave like those of any other card.

---

## 3. The header

### 3.1 Shape

A block of `#!` directive lines — the `#!format=2` idea, made complete:

```
#!openn
#! kind: hw/stations
#! schema: 2
#! producer: Pipeline5 5.0 (phase 700)
#! generated: 2026-10-07T18:00:00Z
#! run: 20261007-180000-7f3a
#! project: 8XXX
#! plc: n0001-mc1-cc1-k65501
#! target: Devices & networks
#! source: hardware_stations
#!end
```

- `#!openn` opens, `#!end` closes. Between them `#! key: value` lines — key lower-case `[a-z0-9-]`,
  the first `:` separates key and value, value trimmed, no line breaks. Keys are case-insensitive, duplicates
  are an error, unknown keys are tolerated (remark) so the contract can grow.
- **The header is the first thing in the file** (after the UTF-8 BOM / the XML declaration). Plain `#`
  comment lines may sit between header lines (the csv column-comment line stays where it is, after `#!end`).
- **Excel tolerance (csv):** trailing delimiters (`#! kind: hw/stations,,,,`) and Excel's quoting of a line that
  contains the delimiter (`"#! producer: Pipeline5 5.0, phase 700",,,`) are undone before parsing. Therefore a
  value must not **end** with the csv delimiter.
- A file whose header is a bare `#!format=N` is `Legacy`; no `#!` line at all is `Missing`.
- **PL5 (2026-10-08):** writes the csv lines unpadded and no `#!format=2` line any more (`schema: 2` carries the
  format number). A template file name holds `--`, which an XML comment cannot, so an XML header never names a
  template file: a template copy's `source` is the hand-maintained original's folder
  (`Shared/Templates/Tia Portal Software Blocks`), a code block's `source` names its template as `<name> v<version>`.

### 3.2 Keys

| key | required | meaning |
|---|---|---|
| `kind` | yes | a kind id from §2 |
| `schema` | yes | integer; must not be newer than the schema OP5 supports for that kind |
| `producer` | yes | free text: tool + version (+ phase) |
| `generated` | yes | ISO 8601 date-time (UTC `Z` preferred) |
| `run` | recommended | the producer's run id. OP5 compares it with the workspace config's `run`: a different run = **stale** leftover, not imported. PL5 (user decision 2026-10-08): one fresh id per **generation** = one button press — Run-all is one id for every phase of its chain, a single phase button mints its own, so after a lone phase the other phases' files are Stale until regenerated (nothing is swept); the id is `YYYYMMDD-HHMMSS-xxxx` |
| `project` | recommended | the PL5 project (`project_code`) |
| `plc` | optional | TIA PLC device name; must equal the `<PLC>` folder the file sits in |
| `target` | optional | TIA folder path (`Program blocks/00_Safety`); must equal the file's location |
| `name` | optional | the TIA object name when it differs from the file name |
| `source` | optional | provenance: SSOT table / phase / rule that produced the file |
| `id` | optional | stable identity across regenerations (SSOT row uid or content hash) |
| `depends` | optional | comma list of TIA object names that must exist first (replaces the `01_` prefix convention when both sides support it) |
| `comment` | optional | free text |

### 3.3 Wrapping per file type

| file type | wrapping | example |
|---|---|---|
| csv, txt, config | lines as they are (`#` is the csv comment char) | see §3.1 |
| XML (`.xml`, `.aml`) | the **first comment after the declaration**, one directive per line | `<?xml …?>` ⏎ `<!--` ⏎ `#!openn` ⏎ `#! kind: sw/data-block` ⏎ … ⏎ `#!end` ⏎ `-->` ⏎ `<Document>` |
| sources (`.scl .awl .db .udt .st`) | each line prefixed `//` | `//#!openn` ⏎ `//#! kind: sw/source` ⏎ … ⏎ `//#!end` |
| binary / foreign (`.xlsx .xlsm .pdf …`) | sidecar text file `<file>.openn` with the csv form | `PLCTags.xlsx.openn` |

An in-file header wins over a sidecar. XML comments cannot contain `--` (OP5's writer replaces it by `- -`).
The XML header does **not** use the strings `<!--Begin Template-->` / `<!--End Template-->` (template markers).

### 3.4 The workspace config

`<workspace>/.openn/workspace.openn.config` — the header of the workspace itself (csv form, no `kind`):

```
#!openn
#! contract: 1
#! project: 8XXX
#! producer: Pipeline5 5.0
#! generated: 2026-10-07T18:00:00Z
#! run: 20261007-180000-7f3a
#! plcs: n0001-mc1-cc1-k65501
#! templates: Templates
#!end
```

Required: `contract`, `producer`, `generated`. `run` enables stale detection. `plcs` lists the PLC folders.
PL5 writes it at the start of every generation, before the first BuilderData write (`output_layout.begin_generation`);
`plcs` = the `Plc` station name(s) of Stations.csv.

---

## 4. The workspace (folder shape)

```
BuilderData/                                   ← the workspace (name kept; PL5 may rename it later)
  .openn/workspace.openn.config                ← §3.4
  Devices & networks/                          ← project-level hardware (TIA tree node; VCI has no hardware)
    Stations.csv                               hw/stations
    Modules.csv                                hw/modules
    [DeviceTypesDatabase.csv]                  hw/device-types (optional local override of the Shared one)
  Templates/                                   ← sw/block-template copies referenced by block-gen csvs
  <PLC name>/                                  ← one per Plc row of Stations.csv; name = the station name
    Program blocks/<group>/…/<Block>.xml       sw/code-block, sw/data-block
    Program blocks/<group>/…/<Block>.csv       sw/block-gen
    Program blocks/<group>/…/InstanceDBs.csv   sw/instance-db (the Folder column is relative to this folder)
    Program blocks/<group>/…/<Source>.scl|.db  sw/source
    PLC data types/<UDT>.xml                   sw/udt
    PLC tags/<Table>.xml                       sw/tag-table
    PLC tags/PLCTags.xlsx (+ .openn sidecar)   doc/plc-tags-workbook
```

- Exactly the shape TIA's VCI writes (`Openn3App/TiaProjects/Openn2_Playground_VCI` is a real export:
  `<PLC>/PLC data types`, `PLC tags`, `Program blocks/<group>/…`). A workspace in this shape can be added
  to TIA as a VCI workspace *and* imported by OP5.
- Groups are folders. A file at the category root lands in the root group (today's flat `ImportReady/`).
- Reserved root folders: `.openn`, `.vci`, `Devices & networks`, `Templates`. Every other root folder is a PLC.
- OP5 **exports** into the same shape (`ExportedData/<PLC>/…`, hardware as `Devices & networks/<project>.aml`).
- Multi-system PL5 projects produce one workspace per system (`Output/<system>/TiaPortalProjectInterface/BuilderData`).
  OP5 lets the user pick the workspace root; the default stays `Shared/OutputTree/TiaPortalProjectInterface/BuilderData`.
- **PL5 writes this shape only** (user decision 2026-10-08: no legacy copy beside it — a legacy root folder would make
  the scan's layout verdict "legacy"). The PLC folder = the `Plc` station's name, taken from the `hardware_stations`
  table or, before phase 700 ran, from the I/O List's PLC head row (the same rule phase 700 applies); no PLC head = a
  pointed error, no workspace. PL5 never sweeps: an existing legacy tree (`HardwareConfiguration/`, `SoftwareBlocks/`,
  `PlcTags/`) must be deleted once by hand — OP5 v1 still reads it, with warnings, until then.
- `Templates/` holds PL5's copies of the hand-maintained templates, each stamped `sw/block-template` with the
  generation's `run` (a copy an older generation left behind is Stale) and `source` = the original's folder; the
  block-gen csvs keep `$ template=Templates/<file>.xml`, which OP5 resolves by walking up to the workspace root (§7.3).
  A `DeviceTypesDatabase.csv` copy (a project's own database, placed beside Stations.csv) stays byte-exact: it carries
  a header once the hand-maintained original does (§6.7).

### 4.1 Legacy layout → workspace mapping (OP5 v1 reads both)

| legacy folder | mapped to | PLC |
|---|---|---|
| `HardwareConfiguration/` | `Devices & networks/` | — |
| `SoftwareBlocks/CreationInfo/*.csv` | `<PLC>/Program blocks/` (block-gen, instance DBs) | the project's single PLC |
| `SoftwareBlocks/CreationInfo/Templates/` | `Templates/` | — |
| `SoftwareBlocks/ImportReady/*` | `<PLC>/Program blocks/` | the project's single PLC |
| `PlcTags/` | `<PLC>/PLC tags/` | the project's single PLC |
| `UserDataTypes/` | `<PLC>/PLC data types/` | the project's single PLC |
| `DataBlocks/` | `<PLC>/Program blocks/` | the project's single PLC |

---

## 5. What OP5 does with the catalog

1. **Scan** the workspace → every file gets a kind and a status:
   `Ready` (valid header) · `Legacy` (recognized by legacy markers: format tag, `$ template=`, `%` key row,
   XML root object) · `NeedsHeader` (extension / location only) · `Invalid` (bad header, header ≠ location,
   kind in the wrong TIA folder, no usable location) · `Stale` (run ≠ workspace run) · `Unclassified` ·
   `Ignored` (config, sidecars, documentation, templates by themselves).
2. **Import** only `Ready`, `Legacy` and `NeedsHeader` items, in kind order (§2 column *order*), then PLC, then
   path (the `00_`, `01_` prefixes keep working inside a kind). `Invalid`, `Stale`, `Unclassified` are logged and
   skipped — never imported.
3. **Existence policy per kind** (unchanged from OP3): stations already in TIA are skipped with their modules
   (warning); block / UDT / tag-table XML imports `Override`; instance DB name clashes prompt
   Retry/Abort/Ignore; a plug error prompts Retry/Abort/Ignore. Nothing is ever saved by OP5.
4. **Export stamping** (planned, OP5 v1.x): OP5 inserts the header comment into every XML it exports and writes
   `.openn/workspace.openn.config` for `ExportedData`, so PL5's coverage report (phase 920) can classify exports
   the same way.

---

## 6. Producer obligations (PL5)

1. Write the header (§3) on **every** BuilderData file, in the file type's wrapping; the sidecar for `PLCTags.xlsx`.
2. Write `.openn/workspace.openn.config` with a fresh `run` id per generation, and stamp the same `run` into every
   file written in that run. Files not rewritten in a run keep their old `run` and OP5 reports them stale —
   this replaces the missing sweep (today the builtin tree still holds PL3-era `.db` files and absolute
   template paths).
3. Emit into the VCI shape (§4): PLC folder = the `Plc` station name from Stations.csv; `Templates/` at the
   workspace root; `template=Templates/<name>.xml` stays relative.
4. Keep the csv column layouts of schema 2 (hardware) and schema 1 (others) unchanged; bump `schema` only on a
   breaking change, and propose it here first.
5. Update the parity oracle (`scripts/parity_vs_pl4.py`): the header block becomes an allowed difference, like
   the generator comment line already is.
6. The Files tab grid uses a csv's first row as its header: a `#!openn` first row shows as the column header.
   Either skip `#` rows in the grid or accept the cosmetic effect.
7. Templates (`Shared/Templates/Tia Portal Software Blocks`, hand-maintained) and `DeviceTypesDatabase.csv` get a
   header when next edited (PL5's loaders already skip `#` lines).

**PL5 status (2026-10-08):** 1–5 done — `pipeline5/systems/plc_based/siemens_s7/openn_header.py` renders the header
in its three wrappings + the sidecar, holds the run id and writes the workspace config; `output_layout.py` is the
workspace (the VCI dirs, the PLC folder, `begin_generation`); every writer stamps its surface; the host
(`workbench/app_main.py`) mints one generation id per button press and hands it in as `PhaseContext.run`;
`scripts/parity_vs_pl4.py` strips the header and maps the shape onto the frozen PL4 reference (a workspace file
without a header is a difference; the PL5-only transfer-area rows of `Modules.csv` are its one sanctioned row
allowance); `scripts/run_pipeline.py` generates a workspace headless. Transfer areas (§2.1) are emitted since
2026-10-08 (`.zen/contract.md` C-031). 6: the `#!openn` row
in the Files-tab grid is accepted as cosmetic. 7: not started (the hand-maintained files are unchanged).

## 7. Consumer obligations (OP5)

1. Classify before importing; log the catalog summary; never import `Invalid` / `Stale` / `Unclassified`.
2. Accept the legacy layout and `#!format=2` with warnings in v1; require the header in v2 (announced here).
3. Resolve a relative `template=` against: the csv folder → a `Templates/` folder at each level up to the
   workspace root → `Shared/Templates/Tia Portal Software Blocks`.
4. Keep the hardware existence policy (skip existing stations with modules); keep I/O controllers as they are.
5. Reflect every contract change in `Openn5App/00_Contract/` (`InputKind.cs` = §2, `OpennHeader.cs` = §3,
   `WorkspaceCatalog.cs` = §4-5) and in this document, in the same commit.
6. A template copy in `Templates/` opens with its `sw/block-template` header comment; `BlockXmlGenerator` copies the
   template head verbatim, so a generated block XML would inherit that comment — OP5 must drop it (or re-stamp the
   generated XML `sw/code-block`, producer Openn5) before `Blocks.Import`. Same gate as step 1 of §8.

---

## 8. Migration plan

| step | side | what | verification |
|---|---|---|---|
| 0 | OP5 | contract layer + "Scan BuilderData" command (done) | scan of today's tree: 29 files, 27 classified, 0 unclassified, 2 ignored, all `Legacy`/`NeedsHeader` |
| 1 | **TIA** | **verify that `Blocks.Import` / `Types.Import` / `TagTables.Import` accept an XML comment before `<Document>`** (and that a VCI workspace does) | import one headered DB XML into the playground project. If TIA refuses: XML headers move to the sidecar form (§3.3 last row), the rest of the contract is unchanged |
| 2 | PL5 | **done 2026-10-08** — headers on every surface + workspace config + run id (the legacy layout is NOT kept beside the new shape: user decision) | OP5 scan: `Ready` everywhere (Appendix A); parity oracle green with the header + shape as allowed differences |
| 3 | PL5 | **done 2026-10-08** — VCI shape (PLC folder = the Plc station, `Devices & networks`, `Templates/`, `<PLC>/PLC tags` + sidecar) | OP5 scan: layout "VCI shape" (Appendix A); OP5 full import ≡ OP3 import of the legacy tree (TIA smoke) — still to run |
| 4 | OP5 | workspace-driven import (catalog → routes) replaces the per-folder buttons; workspace root selectable; export stamping | import of a PL5 workspace from a project `Output/` folder |
| 5 | both | retire legacy acceptance (OP5 v2) | OP5 refuses an unheadered file with a pointed message |

---

## 9. Open questions (decide here)

1. **Tag tables:** PL5 emits only `PLCTags.xlsx`; OP5 imports tag-table XML. Who converts? (OP3 on the unmerged
   `epitaxy` branch converted the xlsx; PL5 could emit `SW.Tags.PlcTagTable` XML directly — preferred: one
   format, no Excel dependency in OP.)
2. **UDTs:** PL5 emits none today; the `sw/udt` kind is ready when it does.
3. **`.db` sources vs `GlobalDB` XML:** both exist for the same blocks in the builtin tree (PL3 leftovers). With
   `run` stamping the leftovers become `Stale`; until then OP5 imports both — decide whether `sw/source` `.db`
   files are still a PL5 surface at all.
4. **Multi-PLC projects:** the VCI shape supports several PLC folders; PL5 has one `Plc` row today.
5. **Block groups:** PL5 writes everything flat; the shape allows groups whenever PL5 wants them (folder = group).

---

## Appendix A — the builtin tree (OP5 scan)

**After the PL5 implementation (2026-10-08** — `scripts/run_pipeline.py` over the builtin config, then the Appendix B
scan**):**

```
Workspace scan: Z:\Source\Repos\_Openn5\Shared\OutputTree\TiaPortalProjectInterface\BuilderData
  layout: VCI shape (<PLC>/Program blocks | PLC tags | PLC data types + Devices & networks)
  workspace config: Ok, contract 1, project 8XXX, producer Pipeline5 5.0, run 20261008-120906-e378
  35 file(s): 32 classified, 0 unclassified, 3 ignored
  hw/stations              1 file(s)   ready 1, legacy 0, needs-header 0, invalid 0, stale 0
  hw/modules               1 file(s)   ready 1, legacy 0, needs-header 0, invalid 0, stale 0
  sw/data-block           11 file(s)   ready 11, legacy 0, needs-header 0, invalid 0, stale 0
  sw/instance-db           1 file(s)   ready 1, legacy 0, needs-header 0, invalid 0, stale 0
  sw/block-gen             7 file(s)   ready 7, legacy 0, needs-header 0, invalid 0, stale 0
  sw/code-block            1 file(s)   ready 1, legacy 0, needs-header 0, invalid 0, stale 0
  sw/source                3 file(s)   ready 3, legacy 0, needs-header 0, invalid 0, stale 0
  sw/block-template        7 file(s)   ready 7, legacy 0, needs-header 0, invalid 0, stale 0
```

The 3 ignored files are the workspace config, `PLCTags.xlsx` (`doc/plc-tags-workbook`, its header read from the
sidecar - listed, never imported) and the sidecar itself. The PL3-era `.db` leftovers are gone with the legacy tree
(a fresh workspace; an old project tree keeps them as Legacy until it is cleaned once, §4).

**Before (2026-10-07, the legacy tree):** 29 files, 27 classified, 0 unclassified, 2 ignored — every kind `Legacy`
(the `#!format=2` tag / the csv and XML markers) or `NeedsHeader` (the five `sw/source` files: the PL3-era `.db`
leftovers plus the two `.scl`), layout "legacy BuilderData folders", workspace config missing.

## Appendix B — reference implementation

- `Openn5App/00_Contract/InputKind.cs` — the taxonomy (§2), one `InputKindInfo` per kind.
- `Openn5App/00_Contract/OpennHeader.cs` — parser + writer (§3): `OpennHeader.Read(path)`,
  `OpennHeader.Create(kind, producer, utcNow).Render(HeaderSyntax.Csv|Xml|Source)`.
- `Openn5App/00_Contract/WorkspaceCatalog.cs` — scan + classification + consistency + stale detection (§4-5).
- No Siemens dependency: the three classes load from `Openn5.exe` by reflection without TIA, so PL5 can be checked
  against the real parser from a script (see the OP5 `CLAUDE.md`, "Contract layer").
- PL5 side: `Pipeline5App/pipeline5/systems/plc_based/siemens_s7/openn_header.py` (§3: the three wrappings, the
  sidecar, the run id, the workspace config, and a parser mirroring `OpennHeader.cs` for the round-trip tests),
  `output_layout.py` (§4: the workspace, the PLC folder, `begin_generation`), `tests/unit/test_openn_header.py`
  (the key rules, the Excel-padding round trip, the layout) and `tests/unit/test_siemens_main_handlers.py`
  (`run_all_writes_a_ready_op5_workspace`: the whole chain, headers checked file by file, the lone-button
  staleness). `scripts/run_pipeline.py` regenerates a workspace headless; the parity oracle
  `scripts/parity_vs_pl4.py` strips the header and maps the shape onto the frozen PL4 reference.
