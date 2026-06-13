# Safety DB — Power Query pipeline

Rebuild of the `3_Database` + `2_HwPlc` workbooks: same workflow, no formula
matrices, no copy-paste chains. All transformation logic lives in the `.pq`
files of this folder (M is plain text → reviewable, diffable, versioned in git);
Excel is the runtime and the UI.

```
documentation (I/O List + C&E matrix, untouched)
   │   PrepareInputs macro  → staged copies with the IsStruck column
   ▼
staging      StgIoList, StgCE          (canonical columns, corrections applied)
   ▼
validation   ValIoList / ValCE / ValCross → ISSUES   (the report for the owner)
   ▼
database     DbSignals, DbDevicesPaired, DbHardware, DbDiagnosis
   ▼
outputs      Openn2 csv (format 2) · I/O tags · block instances · custom DBs
             · diagnosis · machine interface          → ExportAll macro
```

Requires Excel with a current Power Query engine (Microsoft 365 / Excel 2021+).

### Power Query firewall — why the queries are split the way they are

Power Query's Formula Firewall forbids a single query from BOTH directly
accessing a data source AND referencing other queries. So the pipeline obeys
two rules and never needs "Ignore Privacy Levels":

- **Leaf queries** touch exactly one source and nothing else: `Cfg`,
  `SignalTypes`, `ColumnMap`, `Corrections`, `ValidationRules`, `MachineTypes`,
  `InterfaceData` (each reads one workbook table); `RawIoList`, `RawCE`,
  `RawDeviceTypes`, `RawInterfaceTemplate` (each opens one external file via a
  native parameter).
- **External-file paths are native parameters** (`pIoListStaged`, `pIoListSheet`,
  `pCEStaged`, `pCESheet`, `pDeviceTypesCsv`, `pInterfaceTemplate`) — the firewall
  treats parameters as constants, so a leaf may open a file named by a parameter.
  The PrepareInputs macro pushes the real paths into these parameters (from PARAMS
  / MACHINE_TYPES) before any refresh.
- **Everything else is reference-only**: staging, validation, database and output
  queries combine the leaves and call helper functions (which themselves only
  reference leaves), never reading a workbook table or file directly.

This is why config values are read through `fnParam` (which reads the `Cfg`
leaf), not via `Excel.CurrentWorkbook` scattered in each query.

## One-time wiring (≈30 min)

1. Create a macro workbook `SafetyDB.xlsm` in this folder.
2. Create the sheets/tables listed under **Tables** below (Insert → Table,
   then set the table name exactly — query lookups use the names).
3. Import the VBA modules: Alt+F11 → File → Import → `VBA\PrepareInputs.bas`
   and `VBA\ExportOutputs.bas`. Add two buttons (HOME sheet) calling
   `PrepareAllInputs` and `ExportAll`.
4. Import the queries: Data → Get Data → From Other Sources → Blank Query →
   Advanced Editor → paste the content of each `.pq` file; name the query
   **exactly like the file name** (without `.pq`). Order: `00_Config`,
   `01_Staging`, `02_Validation`, `03_Database`, `04_Output`.
   Functions (`fn*`) and intermediate queries: right-click → uncheck
   *Enable load* (connection only). Load to worksheets: `Issues` (sheet
   ISSUES) and every `Out*` query (one sheet each).
5. File → Options → Formulas: turn **R1C1 off**, and in Query Options disable
   *type detection* and set locale to en-US for deterministic parsing.

## Per-project workflow

1. **PARAMS**: fill project code, file paths, area list, nets, machine type.
2. **PrepareAllInputs** (button): snapshots the customer files →
   `Input\_staged\*.xlsx` with the `IsStruck` column. Strikethrough in the
   sources means *predisposition, not used* — Power Query cannot see
   formatting, which is exactly why this pre-pass exists.
3. **Refresh All**: staging + validation run. Read the **ISSUES** sheet:
   - send it (filtered) to the document owner, **or**
   - absorb a fix locally as a row in **CORRECTIONS** (auditable, survives
     re-imports; rule V906 flags corrections that became stale after a
     document revision).
4. Iterate 2–3 until no `Error` rows remain (`Warning` rows are allowed).
5. **ExportAll** (button): writes the outputs. The macro **refuses to export
   while Errors exist** — Openn2's validating loader is the second net.

New revision of a customer document = drop the file, run steps 2–4 again.

## Tables (sheet PARAMS unless noted)

**PARAMS** (`Name | Value | Note`) — rows:
`ProjectCode`, `MachineType`, `AreaList` (`;`-separated), `SafetyNets`
(e.g. `192.168.50;192.168.51`), `StrikeHandling` (`Exclude` or `Flag`),
`IoListSourcePath`, `IoListSheetName`, `IoListHeaderRow`, `IoListStagedPath`,
`CESourcePath`, `CESheetName`, `CEHeaderRow`, `CEStagedPath`,
`DeviceTypesCsvPath` (→ Openn2 `HardwareConfig\DeviceTypesDatabase.csv`),
`OutputFolder`.

**SIGNAL_TYPES** (`TypeId | Description | Category | PairKey | Channel | BlockTemplate | InDiagnosis | IsPattern`):

| TypeId | Description | Category | PairKey | Channel | BlockTemplate | InDiagnosis | IsPattern |
|---|---|---|---|---|---|---|---|
| A | Alarm | Diag | | | | TRUE | FALSE |
| W | Warning | Diag | | | | TRUE | FALSE |
| PA | Fieldbus Alarm | Diag | | | | TRUE | FALSE |
| PW | Fieldbus Warning | Diag | | | | TRUE | FALSE |
| E1/2 | Emergency Push Button | Safety | E | 1 | 02_EM Push Button | FALSE | FALSE |
| E2/2 | Emergency Push Button | Safety | E | 2 | 02_EM Push Button | FALSE | FALSE |
| B1/2 | Safety Breaker | Safety | B | 1 | 04_ESTOP | FALSE | FALSE |
| B2/2 | Safety Breaker | Safety | B | 2 | 04_ESTOP | FALSE | FALSE |
| ENC1/2 | Safety Encoder | Safety | ENC | 1 | 07_Speed Control | FALSE | FALSE |
| ENC2/2 | Safety Encoder | Safety | ENC | 2 | 07_Speed Control | FALSE | FALSE |
| DI1/2 | Door Closed Safety Input | Safety | DI | 1 | 08_Gate Manager | FALSE | FALSE |
| DI2/2 | Door Closed Safety Input | Safety | DI | 2 | 08_Gate Manager | FALSE | FALSE |
| DD | Door Closed Diag Input | Diag | | | 08_Gate Manager | TRUE | FALSE |
| DR | Door Reset Input | Std | | | 08_Gate Manager | FALSE | FALSE |
| DL | Door Lamp Output | Std | | | 08_Gate Manager | FALSE | FALSE |
| DQ | Door Unlock Output | Std | | | 08_Gate Manager | FALSE | FALSE |
| KI | Contactor Feedback Input | Safety | | | 06_Feedback Error | FALSE | FALSE |
| KQ | Contactor Output | Safety | | | 05_Output Feedback | FALSE | FALSE |
| RES | Emergency Reset | Safety | | | | FALSE | FALSE |
| FA# | Emergency Status Feedback Area # | Safety | | | | FALSE | TRUE |

`FA#` matches FA1, FA2, FA10… (`#` = digits). **Verify the BlockTemplate
column** — the mapping above is a best guess from the template names in
`1_SwPlc\XML Templates`; correct it in the table, no code changes needed.

**COLUMN_MAP** (`Document | SourceHeader | CanonicalName | Required`) — maps the
customer headers to the canonical names the queries use. IoList canonical names:
`Module, Manufacturer, PartNo, CodFives, Slot, IdNode, Bit, NormalCondition,
Connector, PinNo, DescriptionL1, DescriptionL1b, DescriptionL2, DescriptionL2b,
FunctionalUnit, Location, Device, Type, DrawingName, Sheet, TsRef, ProfinetIp,
ProfinetName, Mnemonic, AlarmFilter, TagFilter, DiagCabinet, DiagBit,
DescriptionModule`. CE canonical names: `PlcF, Validated, Position, Note,
ModuleAddress, BitAddress, SlotDevice, PinNo, Description, FunctionalUnit,
Location, Device, Area`. When the customer renames a column, fix this table.

**VALIDATION_RULES** (`RuleId | Description | Severity | Enabled`) — prefill:
V101 unknown type=Error · V102 duplicate identity=Error · V103 node/bit
collision=Error · V104 device-tag pattern=Warning · V105 IP outside nets=Error
· V106 diag data without type=Warning · V107 struck row with type=Warning ·
V108 Diagnosis Bit outside 0..63=Error ·
V201 malformed address=Error · V202 bad validation status=Error · V203 BYPASS
without note=Error · V204 duplicate address in matrix=Error · V301 C&E device
missing in I/O List=Error · V302 safety device missing in matrix=Warning ·
V303 unknown area=Warning · V906 stale correction=Warning.
Unknown rule ids default to enabled Errors.

**CORRECTIONS** (`Document | RowKey | Column | NewValue | Reason | Author | Date | Status`)
— copy the RowKey from the ISSUES sheet; `Status=Active` applies, `Resolved`
keeps it as history.

**MACHINE_TYPES** (`MachineType | InterfaceTemplate`) — one interface template
text file per machine type (in `Templates\`), `{Token}` placeholders.
**INTERFACE_DATA** (`Token | Value`) — project-specific token values.

**EXPORTS** (`Source | FileName | Format`) — what `ExportAll` writes:

| Source | FileName | Format |
|---|---|---|
| OutStations | Stations.csv | Format2Csv |
| OutModules | Modules.csv | Format2Csv |
| OutIoTags | IoTags.csv | Csv |
| OutDiagnosis | Diagnosis.csv | Csv |
| OutBlockInstances | BlockInstances.csv | Csv |
| OutCustomDb | (per row) | TextPerRow |
| OutInterface | (per row) | TextPerRow |

## Where each PLC-project part comes from

- **I/O Tags** → `OutIoTags` (one tag per channel, TIA tag-table layout).
- **Custom DBs** → `OutCustomDb` (SCL DATA_BLOCK source per signal category,
  written as plain text to `Output\Blocks\`).
- **Software blocks LAD/FBD** → `OutBlockInstances` is the instance feed (one
  row per *physical device*, both channel addresses paired) for the XML
  template engine (`1_SwPlc` flow) and Openn2 block import. SCL/STL blocks
  stay plain text via `OutCustomDb`/`OutInterface`.
- **Diagnosis** → `OutDiagnosis`: documented part from the I/O List
  (`DiagCabinet`/`DiagBit`) + generated part (`DbDiagnosis`, extend the
  `Generated` step per machine type).
- **Interfaces** → `OutInterface`: machine-type template + `INTERFACE_DATA`.
- **Hardware for Openn2** → `OutStations`/`OutModules` in csv **format 2**
  (`;` columns, `|` parameters, `#!format=2`, Group column) — loaded and
  fully validated again by Openn2 before generation.

## Notes & known seams

- The staged snapshot also acts as the import record (what was processed,
  including what was struck) — the old C&E CRC column becomes obsolete.
- `OutModules` leaves I/Q start addresses and custom parameters empty in v1:
  decide whether addressing comes from the I/O List columns or stays
  TIA-assigned, then fill the two fields in the query.
- `DbHardware` resolves Part No. → ModelId by removing spaces; non-Siemens
  devices (GSD ids like `55556`) may need a mapping row in COLUMN_MAP-style —
  extend `DbHardware` when the first such project lands.
- `DbDiagnosis`'s generated part is intentionally minimal (one entry per
  cabinet) — the real generation rules are machine-type-specific.
