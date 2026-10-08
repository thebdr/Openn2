# Openn5 — TIA Portal Openness automation tool

WPF app (.NET Framework 4.8, old-style csproj) that drives Siemens TIA Portal via the
Openness API: attaches to/creates TIA projects, generates PROFINET hardware from csv
files, imports/exports PLC blocks.

**OP5** is the Pipeline5 (PL5) counterpart, created 2026-10-07 as a copy of `Openn3App/` (OP3 - the stable,
shipped pair with PL3/PL4; **never edit OP3 for OP5 work**, it is the fallback and the reference). What OP5
changes: the **input contract** with PL5 - a VCI-shaped handoff workspace, a `#!openn` header on every file and
a kind taxonomy (`00_Contract/`, spec in `Shared\PL5_OP5_contract.md`) - and, next, a friendlier UI built on
that catalog instead of per-path buttons. Everything below that is not marked OP5 is inherited from OP3 and
still true. I/O controllers stay as they are (no existence tolerance; "Use existing IO controllers" mode).

## Build

- Requires `Siemens.Engineering.dll` **V18–V20**. The csproj resolves it automatically:
  repo `lib\Siemens.Engineering.dll` override → registry
  (`HKLM\SOFTWARE\Siemens\Automation\Openness`) → default install paths — lowest
  installed version first (max runtime compatibility).
- On machines without TIA Portal, drop a V18 dll into `lib\` (see `lib/README.md`).
  Never commit that dll, never copy it next to the exe (the reference is
  `Private=False` — an Openness requirement; a copied dll would break version selection).
- Build with Visual Studio (`Openn5.sln`) or `msbuild Openn5.csproj /p:Configuration=Debug` (output
  `bin\Debug\Openn5.exe`; old-style csproj - a new .cs needs its own `<Compile Include>` entry). The NuGet
  `packages\` folder is gitignored; copy it from `Openn3App\packages` or restore it when it is missing.
- V21+ is deliberately unsupported (breaking Openness changes).

## Architecture — key invariants

- **Version selection** (`03_ApiManager/OpennessSetup.cs`): installed Openness versions
  (V18–V20) are discovered from the registry + install-folder scan; selection at
  startup (`App_Startup`), in order: `--tiaversion=NN` arg (written by the in-app
  "TIA Version.." switch, which restarts the app), the version of the running TIA
  Portal process(es) when they all agree (detected from process paths — no Siemens
  type touched), single installed version, else the dialog. An
  `AppDomain.AssemblyResolve` hook loads that version's assemblies. No Siemens type
  may be touched before the hook is registered; once loaded, the version is fixed
  until restart.
- **TIA facade** (`03_ApiManager/TiaPortalOpenness*.cs`): one partial class split by
  feature area — `TiaPortalOpenness.cs` (portal/project lifecycle),
  `.Blocks.cs` (block listing/export/import), `.Hardware.cs` (hardware generation),
  `.Project.cs` (whole-project import/export — the "Project" tab, see below),
  `.AttributeDump.cs` (attribute-tree dump of project devices into `AttributeDumps\`
  next to the exe — discovery aid for custom parameter names; paths printed in
  `Item(i)/Ch(i)` syntax; `::` sections additionally dump the service-based surfaces
  invisible to `GetAttributeInfos`: `Addresses` composition (I/O start addresses),
  `NetworkInterface` nodes/connectors (IP, PN name/number), `NetworkPort`, and raw
  GSD `PrmData` records probed 0–255 — GSD module parameters are bit-packed there,
  layout in the GSDML `<ParameterRecordDataItem>`, writable via
  `GsdDeviceItem.SetPrmData`).
  Custom-parameter writing is the separate stateless `CustomParameterApplier`.
  Keep new TIA functionality in the matching file.
- **Threading** (`03_ApiManager/TiaWorker.cs`): the Openness API is **not thread-safe**.
  ALL Siemens calls (and hardware-config loading) must go through `TiaWorker.Run(...)` —
  one dedicated worker thread with a serial queue. UI code awaits the returned Task via
  `MainWindow.RunBackend`; never call `tia.*` directly on the UI thread.
  Cancellation is **cooperative**: single Openness calls cannot be interrupted, so long
  loops check `TiaWorker.CurrentCancellation` between calls (per station/module); the
  "Cancel Operation" button trips the token. Never `Thread.Abort` the worker. Nothing
  is ever auto-saved — a cancelled/aborted generation is rolled back by closing the
  project in TIA without saving.
- **Contract layer (OP5)** (`00_Contract/`, Siemens-free): `InputKind` = the taxonomy of everything OpennN
  manages (`hw/device-types`, `hw/stations`, `hw/modules`, `sw/udt`, `sw/tag-table`, `sw/data-block`,
  `sw/instance-db`, `sw/block-gen`, `sw/code-block`, `sw/source`, `sw/block-template`, `doc/*`), each with its
  TIA folder, import route, import order and supported schema; `OpennHeader` = the `#!openn ... #!end` header
  every handoff file opens with (`kind`, `schema`, `producer`, `generated` required; `run`, `plc`, `target`, ...
  optional; csv lines / XML first comment / `//` source lines / `<file>.openn` sidecar; Excel padding tolerated;
  a bare `#!format=N` = `Legacy`); `WorkspaceCatalog.Scan(root)` = classifies every file of a workspace
  (header first, legacy markers second), places it from the VCI-shaped path (`<PLC>/Program blocks/<group>`,
  `Devices & networks`, `Templates`; the legacy BuilderData folders are mapped too), checks header vs location
  consistency and `run` staleness. Statuses: Ready / Legacy / NeedsHeader (importable) vs Invalid / Stale /
  Unclassified (never imported) / Ignored. "Scan BuilderData" (Project tab) logs the catalog; `CsvTable.Header`
  + `HardwareConfigLoader.CheckHeader` consume it (wrong kind or newer schema = load error; legacy / missing
  header = warning until PL5 stamps its output); `BlockXmlGenerator` resolves a relative `template=` via the
  csv folder, then `Templates\` at each level up to the workspace root, then `Shared\Templates\Tia Portal
  Software Blocks`. The spec (`Shared\PL5_OP5_contract.md`) and these three files change together. Test without
  TIA: `[Reflection.Assembly]::LoadFrom(".\bin\Debug\Openn5.exe")`, then
  `$asm.GetType("Openn._00_Contract.WorkspaceCatalog").GetMethod("Scan").Invoke($null, [object[]]@([string]$root))`
  and print `.Summary()` (no Siemens type is touched).
- **Hardware config** (`01_Constructor/`): csv "format 2" — `Stations.csv` +
  `Modules.csv` + `DeviceTypesDatabase.csv`; `,` delimited (`CsvTable` default; fields
  with a comma or `"` are `"`-quoted, and custom parameters use `|` internally so they
  never need quoting), `#` comments, the `#!openn` header (OP5 contract v1; the legacy
  `#!format=2` tag, Excel-padded `#!format=2,,,,` or not, is still accepted with a warning), parsed by `CsvTable`.
  `HardwareConfigLoader` validates the whole folder before
  publishing anything (all-or-nothing, every error with file/line). **No legacy
  support by design**: pre-format-2 folders (`IoControllersList.csv` + wide
  `IoDevicesList.csv`) are handled by the old stable application version, not here —
  do not re-add converters or fallbacks.
- **Hardware regeneration** (`TiaPortalOpenness.Hardware.cs CreateIoDevices`): a station whose
  name already exists anywhere in the project (ungrouped or in a device group, case-insensitive)
  is skipped with a `WARNING` together with all its modules; the run continues and ends with a
  `N of M IO device(s) created, K SKIPPED (already in project)` summary line. Correction workflow
  by design: delete the stations to refresh in TIA, generate again with "Use existing IO
  controllers". Modules are only plugged on the run that creates their station - an existing
  station is never completed, compared or slot-matched (a module change = delete + regenerate
  its station). Do not add tolerance/compatibility checks. Controllers are not covered: in
  "Create new IO controllers" mode an existing Plc still fails the run.
- **Transfer areas** (PN/PN coupler 6ES7158-3AD10 V4.x, I-devices): NOT device items - they live in
  `NetworkInterface.TransferAreas` of the station's PROFINET interface, so a `DeviceItems` walk never
  sees them (the dump prints them as `::TransferArea(i)` with `.Addr(j)` local / `.PartnerAddr(j)`
  partner address objects). Generated from Modules.csv rows whose model (DeviceTypesDatabase.csv) is
  of type `TransferArea`: that model's Tia Identifier column is the Openness `TransferAreaType` name
  (`IN`, `OUT`, `IN_OUT`, `PROFISAFE_IN12_OUT6`, ...), Module Name = area name, Slot = position
  number, I/Q Addr = start addresses in the station's IO controller, custom parameters relative to the
  area (`PartnerToLocalLength=128`, `Addr(0).StartAddress=100`). Created by `CreateTransferArea`
  (`TiaPortalOpenness.Hardware.cs`) with the module Retry/Abort/Ignore handling; no rack slot is
  consumed. Semantics verified on a GUI-configured coupler dump (2026-10-08): on the connected
  interface `PartnerAddresses` is the controller side (carries `AddressControllers`; I/Q Addr are
  written there; an IN area exposes one partner Input, an OUT area one partner Output),
  `LocalAddresses` is the coupler's other side (stays -1 until that side gets a controller);
  `IN` ⇒ `PartnerToLocalLength`, `OUT` ⇒ `LocalToPartnerLength`; `Direction` is read-only; positions
  are 1..n; the same areas appear mirrored (IN⇄OUT, no partner addresses) on the X2 interface.
- **Hardware config editor** (`HardwareConfigEditorWindow.cs` +
  `01_Constructor/HardwareConfigDocument.cs`): tree explorer with regex search,
  add/duplicate/delete/edit of stations and modules (Ctrl+Click multi-select,
  right-click context menu, Del key), unsaved objects highlighted bold blue,
  read-only view of the model's default parameters, saves back to format-2 csv and
  re-runs the validating loader. The document layer deliberately tolerates invalid
  rows (so broken configs can be fixed in the editor) — keep validation in the
  loader, not in the editor. Stations.csv has an optional 8th column `Group`
  (`folder/subfolder/...`) — organizational only for now, generation ignores it.
- **Custom parameters** (`01_Constructor/CustomParameterParser.cs`): syntax
  `[Item(i).]…[Ch(i).|Addr(i).]Name=Value` or `[Item(i).]…PrmData(n)=<hex bytes>`,
  separated by `|` (`,` is rejected with an error — it collides with Excel's csv
  delimiter), one `(a-b)` range per entry, `IP[i]` placeholder = octet i of the
  station IP. Module rows resolve paths relative to the plugged module; station rows
  (Stations.csv custom-parameters column, applied **after** module plugging) relative
  to the device root — both exactly as the attribute dump prints them. Applied via
  the explicit path or by discovering the owning object through `GetAttributeInfos`
  (first writable match in the tree); values are converted to the attribute's actual
  type. Apply order: model defaults (DeviceTypesDatabase.csv) first, then row
  parameters — identical targets are deduplicated (row wins), and the order makes
  the row win on overlapping-but-differently-keyed targets too. `Addr(i)` = the item's I/O address objects (e.g. `StartAddress`); `PrmData(n)`
  = byte-exact GSD parameter record write via `GsdDeviceItem.SetPrmData` — only for
  records identical across stations (F-records contain per-module F-addresses/CRCs,
  keep those on the `Failsafe_*` attribute route). No hardcoded attribute names —
  keep it that way.
  To find the attribute name behind a TIA GUI parameter (GUI shows localized display
  names, the API wants internal names): set a distinctive value manually in the GUI,
  "Dump Device Attributes", search the dump for the value — or dump twice around one
  GUI change and diff. Strip the module's own path prefix to get the csv path.

- **Block generation** (`02_Converter/BlockXmlGenerator.cs`): csv-driven generator of
  block XML from template exports (C# port of the legacy Excel/VBA motor;
  templates in `EditedBlocks\XML Templates V18`. Marker-less templates = plain TIA
  exports, auto-templated: each `SW.Blocks.CompileUnit` (network) becomes
  `Network Type #1..#N` in document order, DB exports use the single block object;
  literal section `ID="hex"` attrs are renumbered per generated instance, so raw
  exports only need `!!key$$` value placeholders. Multi-network variants are
  authored in TIA via delimiter networks (empty network titled `Template #NN`
  opens variant NN, `Template End` closes; delimiters dropped, networks before the
  first delimiter stay fixed). Template blocks are version-named
  `TEMPLATE--v1.0--Block Name`; the prefix is stripped from generated block names
  (or replaced by the UI "as:" override; empty = strip logic). Hand-marked
  templates — markers
  `<!--Begin/End Template-->` + `Network Type #NN` variants, placeholders
  `!!COLUMN_n$$`, `!!Iterator$$` = document-global hex ML-ID seeded above the
  envelope's literal IDs, `!!ITERATOR_STRINGS$$` = next value of the row's value
  list, which starts at the column whose KEY-ROW cell is `!!ITERATOR_STRINGS$$` —
  everything right of that marker is values, not headers; slots beyond the row's
  cells fill empty because the `Network Type` sections are capacity-sized).
  Csv rows are typed by their first cell: `$` directive (`$,template=<path>`
  relative to the csv, `?CsvName?` = csv name without extension and `.xml` is
  appended when no extension is given — `template=.\TEMPLATE-?CsvName?` pairs
  csv and template by name; `$;separator=";"`, default `,`, before the key row — the
  char after `$` delimits the directive row itself, and the value must be quoted
  when it equals that delimiter because Excel pads trailing separators), `#`
  comment, `%` key row (exactly
  one, aligned column-for-column with data rows; key cells empty or starting with
  `#` = ignored column), `@` data row (`@;TemplateType;values…`, TemplateType
  selects the variant), `&END` stop — also usable as a CELL in `%`/`@` rows to
  terminate that row's columns; unmarked rows are ignored. The generator owns
  the envelope: `<Engineering version>` is stamped from the running Openness
  version (V17→V18 lesson: V18+ additionally requires `<Namespace />` after
  `<Name>` in every block's AttributeList — already fixed in the V18 template set).
  Output to `GeneratedBlocks\` next to the exe; all-or-nothing with file+line
  errors, leftover-placeholder and well-formedness checks before writing.
- **Instance-DB creation** (`02_Converter/InstanceDbListParser.cs` +
  `TiaPortalOpenness.Blocks.cs CreateInstanceDbs`): bulk single-instance DBs via the
  direct `PlcBlockComposition.CreateInstanceDB` API — no template/XML, so none of the
  import pitfalls (IDs, namespaces, version, culture) apply; TIA auto-numbers when the
  csv leaves Number empty. Csv reuses the row-marker conventions but with NAMED
  columns (`%` key row: `Name`, `InstanceOf`/`FB`, `Number`, `Folder`) so column order
  is free. Folders are find-or-created (`Groups.Find ?? Groups.Create`); name conflicts
  pop Retry/Abort/Ignore; cancellable between DBs; nothing saved. Preferred over the
  XML-template route for plain name+FB+number instance DBs.
- **Import queue** (`TiaPortalOpenness.Blocks.cs RunImportQueue`): one-shot batch over
  an intake folder (default `ImportQueue\` next to the exe). Files processed in
  relative-path order (prefix `01_`,`02_`,… to sequence FBs before their instance DBs —
  no dependency graph by design). Route auto-detected per file (`DetectQueueRoute`):
  `.csv` with a `template=` directive → `BlockXmlGenerator.Generate` then import; `.csv`
  with `%` key columns `Name`+`InstanceOf`/`FB` → `CreateInstanceDbs`; `.xml` → direct
  import. Subfolders mirror into TIA block groups (`GetOrCreateBlockGroup`); an
  instance-DB file's effective group is `join(subfolder, Folder column)`. Per-file
  Retry/Abort/Ignore (`AskFileDecision`) for routes without internal handling;
  instance-DB files keep their own per-DB prompt (no double-prompt); cancellable
  between files; nothing saved.
- **Input/output paths** (`10_StandardFunctions/AppPaths.cs`): defaults are resolved from the exe
  location, never hardcoded. `AppPaths` walks up from the exe to the monorepo `Shared` folder (the
  one with `HardwareConfigBuilderData`/`OutputTree`) and hands back the Pipeline5↔Openn5 surface:
  hardware config `…\BuilderData\HardwareConfiguration` (Stations+Modules), block-gen / instance-DB
  csv `…\BuilderData\SoftwareBlocks\CreationInfo`, import-ready blocks + the import-queue intake
  `…\BuilderData\SoftwareBlocks\ImportReady`, the block-export sink `…\ExportedData\SoftwareBlocks`.
  `DeviceTypesDatabase.csv` is a shared **input** under `Shared\HardwareConfigBuilderData` (not
  beside the generated Stations/Modules), so `HardwareDeviceTypesDatabase.ResolvePath` prefers a copy
  beside the config folder and otherwise falls back to the shared one. Openn5-internal working dirs
  (the TIA project, `GeneratedBlocks`, `AttributeDumps`, `Logs`) stay next to the exe. `CsvTable`
  opens config files `FileShare.ReadWrite` and closes them before parsing, so a load never locks the
  csv against Pipeline5 regenerating it (or Excel).
- **Project round-trip** (`03_ApiManager/TiaPortalOpenness.Project.cs` + the "Project" tab): whole-project
  import/export against the Shared tree, the consumer/producer for Pipeline5's (deferred) phase **920** TIA
  project coverage. **Import** (BuilderData → TIA), fixed order with a button each + "Import Full Project":
  hardware (loads `HardwareConfigDir` then the existing `CreateDevices`) → UDTs → IO tags → data blocks →
  instance DBs → software blocks. UDTs/IO-tags are **one XML per object** imported via
  `TypeGroup.Types.Import` / `TagTableGroup.TagTables.Import` (Pipeline5 emits the XML; the `PLCTags.xlsx`
  stays only for manual TIA tag import — **no Excel library is used**). Data vs software blocks are split by the
  first `<SW.Blocks.*>` element of each ImportReady xml (`GlobalDB` ⇒ data block), `.db`/`.scl` go through
  `ExternalSourceGroup.ExternalSources.CreateFromFile` + `GenerateBlocksFromSource`. **Export** (TIA →
  `ExportedData/{SoftwareBlocks,DataBlocks,UserDataTypes,TagTables}`) is XML via each object's `Export`,
  mirroring the TIA group tree; **hardware exports via CAx** (`project.GetService<CaxProvider>().Export` → one
  `HardwareConfiguration/<project>.aml`). Every phase is cancellable (`TiaWorker.CurrentCancellation`) and the
  new folder-imports are continue-on-error (per-file logged); instance-DB/hardware keep their own
  Retry/Abort/Ignore. Nothing is saved.

## Runtime requirements

- The Windows user must be in the local group **"Siemens TIA Openness"** (sign out/in
  after adding), or every `TiaPortal.GetProcesses()` call throws.
- The first connection per TIA version pops the Openness access prompt — answer
  "Yes to all" to whitelist the exe.
- TIA project file extensions are version-bound (`.ap18`/`.ap19`/`.ap20`);
  `AttachToProject` locates the right file automatically.

## Verification checklist (on a machine with TIA V18–V20)

1. **Build.** Verified: compiles and runs against TIA Portal **V18** (tested
   incrementally during development, 2026-06). Note the dev machine has no TIA Portal —
   changes made there are only syntax-checked, so always rebuild and retest on a TIA
   machine after pulling.
2. **Startup:** with a running TIA instance the matching version is auto-selected
   (log line, no dialog); with none (or mixed versions) the dialog lists all
   installed versions, newest preselected, Enter confirms. The chosen version
   appears in the window title and the first log line. "TIA Version.." reopens
   the selection; picking a different version prompts and restarts the app.
   With exactly one instance + one open project, the project is auto-attached
   (button shows "Detach Project", steelblue).
3. **Config load:** log shows
   `Hardware configuration loaded: 14 device types, 2 controller(s), 87 IO device(s), 336 module(s)`.
4. **Project handling:** attach to a running TIA instance (dropdown) and by path.
   Open "Search / Export Blocks" — the list must include blocks inside block-group
   subfolders and UDTs (shown as `[Type | Language] Folder/Name`, e.g. `[FB | SCL] …`,
   `[UDT] …`), the search box filters as you type (regex, case-insensitive), and
   exporting a block that lives in a subfolder must work. The format dropdown picks
   the output: XML (any object) or a source format (scl/awl/db/udt) that only applies
   where the object's language matches — non-matching selections are skipped with a
   logged reason (XML via `Export`, source via `ExternalSourceGroup.GenerateSource`).
   Import a block.
5. **Generate Hardware** on a fresh project: devices created, IPs and PN numbers set,
   and custom parameters land where the old hardcoded code put them — Murrelektronik FS
   Data module: `Failsafe_FDestinationAddress`/`FMonitoringtime`/`FParameterSignature…`
   on the module's first sub-item; F-DI cards: `Failsafe_DiscrepancyTime` per channel;
   `PotentialGroup` on the module itself. The UI must stay responsive (spinner over the
   log area) during generation. "Cancel Operation" must stop the run between devices
   with a "N of M created" log line; a plug error must pop the Retry/Abort/Ignore
   dialog and honor each choice. Station rows with custom parameters (e.g. Lumberg
   `Item(..)…Addr(i).StartAddress=…` / `PrmData(n)=<hex>`) must land on the
   auto-created sub-items after module plugging — verify against a fresh dump.
6. **Regenerate on the same project** ("Use existing IO controllers"): every station already in
   the project logs `WARNING: IoDevice <name> (...) already exists in the project - station SKIPPED
   with its N module(s)`, nothing is created and the summary line reads
   `0 of M IO device(s) created, M SKIPPED (already in project)`. Delete one station in TIA and
   generate again: exactly that station comes back with all its modules, IP/PN number and
   parameters, the others stay untouched.
7. **Negative test:** select V18 at startup, try attaching to a running V19 instance —
   expect an error in the log, not a crash.
8. **Attribute dump:** on an attached project, "Dump Device Attributes" with an empty
   filter writes a file under `AttributeDumps\` (log shows path + device/node/attribute
   counts); a name filter limits the dumped devices; an invalid regex logs an error;
   "Cancel Operation" stops between devices and marks the file `# CANCELLED`.
9. **Scan BuilderData** (OP5, no TIA needed): on today's PL5 tree the log shows `layout: legacy BuilderData
   folders`, `workspace config: missing`, `29 file(s): 27 classified, 0 unclassified, 2 ignored` and every kind
   Legacy / NeedsHeader. On a headered tree the files show Ready; a header whose `target` contradicts the
   folder shows `[Invalid]`; a file whose `run` differs from the workspace config shows `[Stale]`; a file
   directly under a PLC folder or in a non-TIA folder shows `[Invalid]`.
