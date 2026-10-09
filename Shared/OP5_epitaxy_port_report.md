# The `epitaxy` branch: trace and port report (2026-10-09)

Written by the OP session after the port. Read with `Shared/OP5_status.md` (state), `Shared/PL5_OP5_contract.md`
(the contract) and `Openn5App/CLAUDE.md` (the app's invariants).

## 1. What the branch is

| | |
|---|---|
| Ref | `epitaxy`, one commit `1b37518` "WIP: epitaxy pre-switch from pl5" (2026-09-24, Co-Authored Opus 5.5) |
| Where it lived | a local branch of the host's `Z:\Source\Repos\_Openn2` repo only - never pushed, never merged; fetched into the `C:\Source\Repos\_Openn5` clone on 2026-10-09 (tag `op3-frozen` came along) |
| Base | `31b5ec7` - the same commit `main`'s OP3 freeze (`bf9b1eb`) was built on |
| Content | the non-PL5 remainder of an earlier WIP squash: Openn3App work (July-September), `Shared/` data, PL3/PL4 config edits, a Claude settings file, the `Openn2App` gitlink. The PL5 half had already been moved to `pl5` as "step 6b". |
| Why it matters | **Openn5App was copied from `main`'s Openn3App**, which never received any of it. Every OP3 fix made on this line after the base was therefore missing from OP5: the close-tabs checkpoint, the connector pick, the fail-safe instance DBs, the TIA teardown, and more. |
| Other branches | every other branch (`pl4`, `pl4-fvt`, `pl5*`, `tia181920`, `upgrade_refactor_1`, `v17_firstDevelopment`, the two `claude/*` branches) has **zero** OP-app commits missing from `main`. `epitaxy` is the single source of lost OP work. |

Size of the branch vs the base: 112 files; OP3 sources 21 files, +2911/-242 lines; the rest is data (TIA playground
project files, `Shared/`, PL3/PL4 config).

## 2. How it was traced and ported

- `git diff --stat 31b5ec7 epitaxy` for the inventory; `git log main..<branch> -- Openn3App Openn5App Openn2App` on every branch.
- OP5 files that still share lineage with OP3 were merged three-way (`git merge-file`, LF-normalized, base `31b5ec7`,
  ours = Openn5App, theirs = epitaxy's Openn3App); the four real conflicts (station creation vs the skip-existing rule,
  the transfer-area rows vs the new plug loop, two doc blocks) were resolved by hand. Files OP5 had rewritten
  (`Project.cs`, `MainWindow.*`, `StandardFunctions.cs`) got the epitaxy hunks ported by hand.
- The port compiles clean (0 warnings). **Nothing of it has run against TIA yet** - see §6.
- Scripts kept in the session scratchpad: `port_epitaxy.pl` (phase 1, shipped), `port_epitaxy2.pl` (phase 2, staged, not applied).

## 3. Ported into Openn5 - shipped in `4623711` (2026-10-09)

| # | Improvement | Where (Openn5App) | Why it matters | State |
|---|---|---|---|---|
| 1 | **Close-tabs checkpoint** before every hardware generation; the network editor is never opened (`ShowHwEditor` removed) | `TiaPortalOpenness.Hardware.cs` `ConfirmEditorsClosed` | the per-device "device not assigned to an IO controller" / "IO device not connected to an IO system" warnings that persist through every compile; Cancel also cancels a workspace import's hardware run | compiled; needs a TIA run |
| 2 | **Connector column** (`X1`/`X2`, verbatim I/O-list cell accepted) picks the interface (item name / PositionNumber) and the IO connector (ordinal) | loader `ExtractConnector`, `FindNetworkInterface(…, connector)`, `PickIoConnector` | OP5 ignored column 9 entirely - every PN/PN coupler landed on the same connector ("all the couplers are wired to X1") | compiled; needs a TIA run |
| 3 | **Group column** -> the station is created inside that device group (find-or-create, per-run cache); attach mode searches the groups | `ResolveDeviceGroup`, `FindDeviceInGroups` | grouped stations were ignored by attach and always created at the root | compiled |
| 4 | `First()` nodes, documented two-step association (`ConnectToSubnet` then `ConnectToIoSystem`), WARNING when a multi-connector device has no Connector | `CreateIoDevices` | V18/V19 refuse the single-call variant; `Last()` for nodes was a historical accident | compiled |
| 5 | Rack fallback to the first device item (localized projects); "no free slot accepts the module" and a PlcCardCm with no slot now prompt / abort instead of silently skipping; a missing Ethernet interface skips the station / aborts the controller with file+line | `PlugSubmodules`, `CreateIoControllers` | silent skips produced half-built stations | compiled |
| 6 | `AdoptIoSystem` guarantees the controller node ends on the registered subnet; cross-wired or shared-subnet base projects abort with a clear message; `CreateIoControllers` returns false on failure and the run stops | `AdoptIoSystem`, `CreateIoControllers` | devices could join a subnet whose IO system lived elsewhere | compiled |
| 7 | Loader rejects duplicate PROFINET device numbers per subnet (explicit PN Number, else the last IP octet) | `HardwareConfigLoader` | TIA rejected the duplicate only mid-generation | compiled; covered by the loader harness pattern |
| 8 | **Fail-safe instance DBs**: when TIA refuses `CreateInstanceDB` for an auto-generated F-block (F_ESTOP1 & co.), a minimal `SW.Blocks.InstanceDB` XML with `ProgrammingLanguage` F_DB is imported instead; a same-FB name conflict is replaced automatically; other conflicts are checked program-wide and named | `TiaPortalOpenness.Blocks.cs` `IsFailsafeCreateRejection`, `TryImportFailsafeInstanceDb`, `FindBlock` | the Retry/Abort/Ignore dialog of the screenshot ("You cannot create instance DBs for automatically generated blocks") | compiled; needs a TIA run |
| 9 | A stale external source object is deleted before `CreateFromFile` | `TiaPortalOpenness.Project.cs` `GenerateFromExternalSource` | "The name is not unique" on the second run of a `.scl`/`.db` source | compiled |
| 10 | `BlockXmlGenerator` refuses an empty `<Component Name="">` slot with the row's file/line and the key/slot that produced it | `02_Converter/BlockXmlGenerator.cs` | TIA only rejected it at import as a cryptic per-UID error | compiled |
| 11 | **TIA teardown**: `TiaPortalOpenness.Shutdown` (closes a project we opened, disposes the portal, leaves an attached user instance running - `ownsPortal`), re-attach releases the previous portal, `MainWindow.TeardownTia` on `Window_Closing` and on the version switch | `TiaPortalOpenness.cs`, `MainWindow.xaml(.cs)` | imported/exported XMLs stayed locked by the Openness runtime until the process died | compiled |
| 12 | `StartFileLog` disposes its writer when the seeding throws | `StandardFunctions.cs` | an orphaned handle kept the fresh `.log` write-locked | compiled |
| 13 | Debug builds carry the "D"-badged icon | `Openn5.csproj`, `Roberto-64x64-Debug.ico` | tell the two exes apart | done |

Alongside the port, the same commit added (not from epitaxy): the custom parameters on every created station /
plugged module / transfer-area log line, the Workspace tab's Import ticks (per-workspace `.openn/import.openn5.config`),
the Import Selection / Import Workspace labels, the log pop-out window and the grid retouch.

## 4. Not ported - the candidates, with a recommendation

The branch was a playground. Each remaining piece is listed with what it would bring, how it fits the PL5 contract,
and whether the official version should have it. Phase 2 (`port_epitaxy2.pl`) is written and staged for the items
you pick; nothing of it is applied.

| # | Piece | Size | What it brings | Fit with the PL5 line | Recommendation |
|---|---|---|---|---|---|
| A | **Device-types database as xlsx** - `DeviceTypesDatabase.xlsx`, one sheet per manufacturer, named columns, the validation/GSDML columns (Input/Output Bytes, IO Distribution, Max Channels, Failsafe, Max Modules, Vendor/Device Id, Module Ident, GSDML File) form-checked at load; `HardwareDeviceTypesDatabase.ReadModels` (xlsx + csv), `XlsxWorkbook` reader | ~280 + 193 lines | a richer, Excel-friendly model database; the only target the GSDML importer can write | **conflicts**: on the PL5 line the csv with its `#!openn` header is the master and the only file Pipeline5 reads; an xlsx beside it makes the two apps read different databases. The validation columns were PL4-era inputs - PL5 references none of them | **port the reader, keep the csv the master** (the xlsx is read only when someone puts one there; the load log names the file used). Switching the master is a contract decision with PL5. |
| B | **GSDML importer** - writes every DAP / module of a GSDML library into the xlsx (new rows on the manufacturer's sheet, empty cells of existing rows filled, hand values never overwritten, rolling backup, duplicate detection); `XlsxInPlaceEditor` (format-preserving zip surgery) | 584 + 273 lines | adding a device family becomes "drop the GSDML in the library and press Import" instead of hand-typing TIA identifiers | needs A; writes only the xlsx (never the csv) | **port, dormant until an xlsx exists**; or re-target to the csv later if the csv stays the master |
| C | **PLCTags.xlsx -> tag-table XML converter** - one `SW.Tags.PlcTagTable` per Path, TIA V18 export shape, stale tag XMLs swept | 388 lines | regenerate the tag-table XMLs after an operator hand-edits the workbook | **superseded for generation** (§9.1: PL5 emits the XMLs itself); still useful after hand edits. The port stamps the `#!openn` header (kind sw/tag-table, the workspace's run) so the Workspace tab lists the result Ready | **port as an explicit Files-tab button** (no automatic "workbook wins" at import - that would contradict PL5 being the producer) |
| D | **Content-routed single-file import** (`Import Block` accepts a block XML, a generation csv, an instance-DB csv or a `.db/.scl/.awl` source) | ~90 lines | the by-hand tool handles every file type | the Workspace tab routes by header kind already; this is the Files tab only | **port** (cheap, no contract impact) |
| E | **Default workspace = Pipeline5's last opened project** (OP3 had "Project tab: redirect the output tree", persisted in `state.json`) | ~120 lines (adapted) | a first run opens on the project PL5 is working on | the OP3 redirect itself is superseded by the Workspace root picker; only the first-run default is worth keeping (PL5 writes `%LOCALAPPDATA%\Pipeline5\state.json` `last_opened`) | **port the first-run default only** |
| F | OP3 "Project" tab output-tree redirect (`AppPaths.UseProjectFolder`, `%LOCALAPPDATA%\Openn2\state.json`) | ~160 lines | - | superseded by the Workspace root picker + sibling `ExportedData` | **skip** |
| G | OP3 `ImportIoTags` preferring a found workbook over the XMLs at import time | ~40 lines | - | contradicts PL5 as the XML producer | **skip** (C covers the hand-edit case explicitly) |
| H | `.claude/settings.local.json` permission allowlist, `Openn3App/.claude/settings.local.json` | - | tooling | - | **skip** |

## 5. Data and non-OP changes on the branch

| Item | What | Recommendation |
|---|---|---|
| `Shared/HardwareConfigBuilderData/DeviceTypesDatabase.xlsx` (505 KB) + `.pre-import.xlsx` | the migrated database (17 models, "verified 1:1") plus the GSDML import backup | **do not bring in while the csv is the master** - it would silently become OP5's database the moment A is ported. Keep it reachable on the branch; bring it in with the contract decision. |
| `Shared/HardwareConfigBuilderData/DeviceTypesDatabase.csv` | epitaxy added two Pipeline columns (`signals_count`, `pairs_mapping`) and `<DR>`/`<DD>` signal-type parameter blocks on the F-DI rows; `main`'s csv has the contract header, the TransferArea models and the Item(…) parameters of the Schmersal/Lumberg heads | PL4-era inputs: Pipeline5 references neither column (grep). **PL5 decision**; nothing for OP5. |
| `Shared/HardwareConfigBuilderData/ADE94000` (15 KB) | an Office zip without extension (a stray workbook save) | **skip** |
| `Shared/Database/*.csv` (14 files) | a PL4 database dump (coverage, signals, instance DBs, …) | PL5 writes its own `Shared/Database` / `<project>/Database` (truth/database.py). **skip** |
| `Shared/PL4_OP4_coordination.md` | the epitaxy copy appends a 74-line "Update log" (OP-side entries of July: the in-app PLCTags.xlsx import, the connector agreement, ...) that `main`'s copy lacks | PL4 is frozen and the entries describe the OP3 features listed above; **skip** (history stays on the branch) |
| `Shared/Templates/.../TEMPLATE_INTERFACES_v0.0.xlsx` | changed binary | PL side; **skip unless PL5 wants it** |
| `Pipeline3App` / `Pipeline4App` config edits, `Pipeline4App/scratchpad/oracle_510.py`, `config_project/app_config.yaml` | PL3/PL4-era configuration and a validation oracle | frozen lines; **skip** |
| `Openn2App` gitlink | a submodule pointer to the legacy app | **skip** |
| `Openn3App/lib/Siemens.Engineering*.xml`, `Openn3App/TiaProjects/...` | the Openness API docs (143k lines) and playground project churn | already handled on main (`lib/` is gitignored for the dll; the xml is dev convenience) - **skip** |

## 6. Verification status and risks

- Phase 1 compiles with 0 warnings; the TIA-free harness covers the loader and the catalog. **Not yet exercised on
  TIA**: the checkpoint flow (OK / Cancel from the Files tab and from Import Workspace), the Connector X2 pick on a
  real coupler, the device-group creation, the fail-safe F_DB import, the created-line parameters. First real run:
  the FVT project with the PN/PN coupler rows - expect `<station>: Connector X2 -> IO connector 2 of 2` in the log.
- Risk in #2: `PickIoConnector` takes the n-th IO connector in TIA's enumeration order; on the coupler that order
  matched X1/X2 on the epitaxy line ("working correctly before"). If a device enumerates differently, the log line
  shows which ordinal was taken.
- Risk in #8: the F_DB import builds the XML for the running Openness version; a block whose interface TIA cannot
  derive from the FB would fail with the importer's message - the Retry/Abort/Ignore dialog still appears then, with
  the fallback's reason appended.
- The checkpoint cancels the whole workspace import run (hardware is first in import order, so nothing else ran).

## 7. Decisions for you

1. Phase 2 items A-E: port as recommended (A reader-only, B dormant, C explicit button, D, E), or only D and E?
2. The database master: stay with the csv (PL5 reads it) or move both apps to the xlsx (a contract change, then
   bring in the epitaxy workbook)?
3. The PL4-era csv columns (`signals_count`, `pairs_mapping`, `<DR>`/`<DD>` blocks): for the PL5 session to rule on.
