# Openn5 — TIA Portal Openness automation tool

WPF app (.NET Framework 4.8, old-style csproj) that drives Siemens TIA Portal via the
Openness API: attaches to/creates TIA projects, generates PROFINET hardware from csv
files, imports/exports PLC blocks.

**OP5** is the Pipeline5 (PL5) counterpart, created 2026-10-07 as a copy of `Openn3App/` (OP3 - the stable,
shipped pair with PL3/PL4; **never edit OP3 for OP5 work**, it is the fallback and the reference). What OP5
changes: the **input contract** with PL5 - a VCI-shaped handoff workspace, a `#!openn` header on every file and
a kind taxonomy (`00_Contract/`, spec in `Shared\PL5_OP5_contract.md`) - and the UI around it: the **Workspace
tab** (the first tab: scan, import and export of a whole handoff workspace), one **Files tab** for the single-file
tools, and a **collapsible TIA project row** (rarely used, collapsed by default). Since 2026-10-09 **legacy
acceptance is retired**: only files with a valid `#!openn` header in the VCI shape are imported; the legacy
BuilderData folders, the bare `#!format=2` tag and unheadered files are recognized only to say why they are
refused. Everything below that is not marked OP5 is inherited from OP3 and still true. I/O controllers stay as
they are (no existence tolerance; "Use existing I/O controllers" mode).

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
- **`TiaProjects\` is a tracked asset - never gitignore it** (grafted from OP3's history on 2026-10-09):
  `Openn2_Playground\Openn2_Playground.ap18` (TIA V18) is the playground project the block templates live
  in (block group `00_TEMPLATES` - the `TEMPLATE--vX.Y--…` blocks whose exports are the files under
  `Shared\Templates\Tia Portal Software Blocks`), and `Openn2_Playground_VCI\` is its TIA Version Control
  Interface export - the reference for the VCI-shaped workspace (`<PLC>\Program blocks\<group>`, `PLC tags`,
  `PLC data types`). Attach to the playground by path to edit or re-export a template. It keeps its
  historical name (renaming a TIA project needs TIA itself).

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
  consistency and `run` staleness. Statuses: **Ready is the only importable one** (valid header, consistent
  placement, current run); Legacy / NeedsHeader (recognized by legacy markers or extension, header missing),
  Invalid, Stale, Unclassified are never imported (since 2026-10-09 - the notes say why and how to fix);
  Ignored = config, sidecars, templates, documentation. "Log catalog" (Workspace tab) logs the summary;
  `CsvTable.Header` + `HardwareConfigLoader.CheckHeader` + `HardwareDeviceTypesDatabase.CheckHeader` consume
  the header (wrong kind, newer schema, bare `#!format=N` tag or no header = load error - the device-type csv
  must carry `kind: hw/device-types` too); `BlockXmlGenerator` resolves a relative `template=` via the
  csv folder, then `Templates\` at each level up to the workspace root, then `Shared\Templates\Tia Portal
  Software Blocks`. The spec (`Shared\PL5_OP5_contract.md`) and these three files change together. Test without
  TIA: `[Reflection.Assembly]::LoadFrom(".\bin\Debug\Openn5.exe")`, then
  `$asm.GetType("Openn._00_Contract.WorkspaceCatalog").GetMethod("Scan").Invoke($null, [object[]]@([string]$root))`
  and print `.Summary()` (no Siemens type is touched).
- **UI (OP5)** - `MainWindow.xaml`: a collapsible **TIA project row** (`Expander`, collapsed by default, state
  remembered in `Properties.Settings.ProjectPanelExpanded`; its header keeps the Attach/Detach toggle and a status
  text - Attach takes the selected open instance, expanding shows the instance dropdown, the path box and "TIA
  Version.."), the **Workspace tab** (first, the focus) and the **Files tab**, then the log. One I/O-controller
  mode: the radio pairs on both tabs mirror each other (`ControllerMode_Checked`). The log area starts six lines
  tall: `SetDefaultLogHeight(6)` at Loaded measures a rendered log line (first container, else font metrics),
  adds the toolbar, the list chrome and the horizontal scrollbar when showing, and sets `rowLog`'s pixel height;
  the splitter owns it afterwards (`rowTabs` takes the rest). The log toolbar: regex filter, "Log to file",
  "Cancel Operation" (visible while busy), "Clear Logs" and **"Pop out ↗"** = `LogWindow.cs` (code-only window):
  a second view of the same log. `LogsManager` (`10_StandardFunctions/StandardFunctions.cs`) feeds any number
  of attached `ListView`s from one history, each through its own filter (`SetFilter(view, …)`,
  `FilterFor(pattern)`); a view attached later is seeded with the whole history; `ClearLog()` empties all;
  `CopyLines(view, selectedOnly)` is the shared clipboard copy. The pop-out has its own filter, Copy all,
  Clear and "Keep on top" (Topmost); it is not owned by the main window (the two order freely) but closes
  with it; placement and the pin are remembered (`Properties.Settings.LogWindowPlacement` = "L,T,W,H",
  `LogWindowTopmost`).
  **Workspace tab** (`MainWindow.Workspace.cs` = the UI partial, `03_ApiManager/TiaPortalOpenness.Workspace.cs`
  = the import engine): root picker (default `AppPaths.BuilderDataDir`; Browse to a PL5 project's
  `Output[\<system>]\TiaPortalProjectInterface\BuilderData`; remembered in `Properties.Settings.WorkspaceRoot`,
  stored as "" for the default so it keeps following the exe) + Rescan; a `ListView`/`GridView` grouped PLC → TIA
  folder → group - three `GroupStyle` levels drawn as a tree: flat `ToggleButton` headers with a triangle glyph
  (right = collapsed, down = expanded), level 0 a blue band (`<workspace>` / `PLC  <name>`), level 1 a grey band
  with a blue left bar indented 18, level 2 italic indented 36, and the `(root)` group draws no header at all
  (its files sit right under the folder band) - one row per file with kind, status (Ready green; everything else
  red-tinted - Legacy/NeedsHeader amber text, Invalid/Stale/Unclassified red, Ignored grey), route,
  producer/generated/run from the header, notes, last import result; hover tooltip and a detail pane repeat the
  full header/placement/notes. An **Import** tick column (importable rows only; `WorkspaceRow.ImportEnabled`,
  two-way): unticked = listed, never imported - the row text turns grey, Action reads `import disabled (…)`, the
  tooltip and the detail pane say so, an `import disabled: K` chip (a filter) appears and the totals chip counts
  the unticked; right-click → "Tick / Untick Import for selected" for many rows; Stations.csv and Modules.csv of
  one folder move together (one generation run). Ticks persist per workspace in `.openn\import.openn5.config`
  (`00_Contract/WorkspaceImportSettings.cs`: `disabled: <relative path>` lines, `#` comments; written on every
  change, deleted when nothing is unticked; the catalog lists it Ignored with its own note; reloaded by every
  scan - a failed write keeps the ticks for the session and the next rescan of the same root).
  `ImportWorkspaceAsync` drops unticked items before queuing the engine and marks them `Skipped: import
  disabled by you`. Summary chips carry `WorkspaceCatalog.Summary()`'s counts (a legacy layout or
  unheadered files show red "not importable" chips) and the kind / attention / unheadered / importable chips are
  **filters**: click = only those rows (chip drawn filled), click again = all; one chip at a time, kept across a
  rescan while its chip exists. A **text filter** box above the grid narrows as you type (regex, case-insensitive,
  else plain substring; Esc clears) over name, path, kind, status, action, producer, generated, run and notes; it
  combines with the chip, "showing N of M rows" + Clear appear while filtering (`ListCollectionView.Filter`,
  group counts follow). After a scan the Files tab's hardware csv folder follows the
  workspace's single `Devices & networks` folder until edited, and the export header shows
  `AppPaths.ExportRootFor(root)` (the workspace's sibling `ExportedData`). "Import Selection" / Import
  Workspace queue ONE worker operation, `tia.ImportWorkspaceItems(catalog, items, createNew)`: items sorted by
  `WorkspaceCatalog.OrderForImport` (kind rank, PLC, path) and dispatched per `InputKindInfo.Route` -
  `HardwareGeneration` = `HardwareConfigLoader.LoadAll(<item folder>)` + `CreateDevices` once per folder
  (Stations+Modules are one run; the folder's hardware files must all be Ready), `Reference` = nothing by itself,
  `ImportTypeXml` / `ImportTagTableXml` / `ImportBlockXml` into the find-or-created type/tag/block group of the
  item's `GroupPath`, `CreateInstanceDbs` = `CreateInstanceDbsCore(path, GroupPath, plc)`, `GenerateThenImport`,
  `GenerateFromSource` (root - TIA limitation, logged). The PLC comes from the item's PLC folder
  (`FindPlcSoftware`, device or CPU name, groups included; a missing PLC fails its items - no fallback), null =
  `GetPlcSoftware` (the single PLC). Non-Ready items are never imported (logged with their notes); routes without
  internal handling get `AskFileDecision(..., "Workspace import")` (Retry/Abort/Ignore), instance DBs and hardware
  keep their own prompts; cancellation between items; nothing is saved. `CreateDevices` returns false when it stops
  early so the row result is honest.
  The tab's **Export** expander (`03_ApiManager/TiaPortalOpenness.Project.cs`) writes the attached project into the
  export root in the same VCI shape, every file stamped: `<PLC>\Program blocks\<group>\<Block>.xml` (code AND data
  blocks share the folder, kind by `block is DataBlock`), `<PLC>\PLC data types\…`, `<PLC>\PLC tags\…` (TIA XML +
  the header as the first comment after the declaration, BOM kept; keys kind/schema/producer/generated/run/
  project/plc/target/name/source), the hardware as CAx `Devices & networks\<project>.aml` + `.cax.log` +
  `.aml.openn` sidecar (doc/other), and `.openn\workspace.openn.config` with a fresh run id per export
  (`ExportRun`). The PLC folder = the CPU device item's name (`FirstPlc`, every device incl. groups). "Export full
  project" sweeps the PLC's three folders first; a single export only overwrites same-named files (the run id
  marks the rest as leftovers). Nothing in TIA changes.
  **Files tab**: the single-file tools - Search / Export Blocks (`BlockSearchWindow` → `AppPaths.ExportedBlocksDir`), "Import Block" routed by content (`ImportPlcBlock` + `DetectSingleFileRoute`, ported from the epitaxy line 2026-10-09: block XML, generation csv = generate + import, instance-DB csv, `.db/.scl/.awl` source = `GenerateFromExternalSource`; unrecognized files are refused with the list),
  Import Block (one XML), Generate Blocks (one block-gen csv → `GeneratedBlocksDir`, the XML path lands in the
  import box), Create Instance DBs (one csv), the hardware csv folder (Reload / Edit / Generate Hardware with the
  controller mode) and Dump Device Attributes. File dialogs start at the box's own path, else at the workspace
  root. The old Software / Hardware / Project tabs, the folder-based "Import Full Project" route and the import
  queue (`RunImportQueue`) are gone - the Workspace tab is the batch way in.
- **Hardware config** (`01_Constructor/`): csv "format 2" — `Stations.csv` +
  `Modules.csv` + `DeviceTypesDatabase.csv`; `,` delimited (`CsvTable` default; fields
  with a comma or `"` are `"`-quoted, and custom parameters use `|` internally so they
  never need quoting), `#` comments, the `#!openn` header (OP5 contract v1, **required**: a bare
  `#!format=2` tag - Excel-padded or not - or no header is a load error since 2026-10-09), parsed by `CsvTable`.
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
- **Hardware generation hardening** (ported 2026-10-09 from the `epitaxy` OP3 line - the Openn5 copy came from
  `main`'s OP3, which never had it; `TiaPortalOpenness.Hardware.cs`): the network editor is NEVER opened and a
  pre-generation OK/Cancel **checkpoint** (`ConfirmEditorsClosed`) has the user close ALL TIA editor tabs first
  (Openness has no close-editor API; generating under an open editor makes TIA post a per-device "device not
  assigned to an IO controller" / "IO device not connected to an IO system" warning that persists through every
  compile); Cancel logs `CANCELLED at the checkpoint`, cancels the operation (a workspace import reports the
  hardware run Cancelled and stops) and changes nothing. Stations.csv column 8 `Group` = a device-group path the
  generation find-or-creates (`ResolveDeviceGroup`, per-run cache; attach mode searches the groups too) and
  column 9 `Connector` (`X1`/`X2`; the verbatim I/O-List cell "X1-P1 R" is fine -
  `HardwareConfigLoader.ExtractConnector`) picks the interface by item name or PositionNumber and the IO
  connector by ordinal (`PickIoConnector`: the PN/PN coupler's X2 = its second connector, logged
  `<station>: Connector X2 -> IO connector 2 of 2`); without a designation the FIRST connector is used -
  X1 on a coupler - and an unmarked multi-connector station logs a WARNING (user decision 2026-10-09: the historical
  `Last()` came from the pre-AI single-connector version; PL5 emits the designation explicitly anyway). Association is the documented
  two-step (node `ConnectToSubnet`, then `ConnectToIoSystem`). A missing Ethernet interface skips the station /
  aborts the controller with file/line; the rack falls back to the first device item when the "Rack"/"Rail" name
  match fails (localized projects); "no free slot accepts the module" and a PlcCardCm with no slot pop the
  Retry/Abort/Ignore decision / abort instead of silently skipping; attach mode (`AdoptIoSystem`) guarantees the
  controller node ends on the registered subnet (cross-wired or shared-subnet base projects abort with a clear
  message). The loader rejects duplicate PROFINET device numbers per subnet (explicit PN Number, else the last IP
  octet). Every created station / plugged module / transfer area logs ONE line ending with
  `custom parameters: <path.Name=Value, …>` (the model defaults merged with the row, as written; `- N FAILED`
  when some did not apply; `no custom parameters` otherwise) - `CustomParameterApplier.Apply` returns that
  summary; module and transfer-area lines also carry the slot / position and the configured I/Q addresses.
- **TIA teardown** (`TiaPortalOpenness.Shutdown`, `MainWindow.TeardownTia`; same port): the Openness runtime keeps
  every imported/exported XML (and the project) locked until the `Project`/`TiaPortal` are disposed, so
  `Window_Closing` and the version-switch restart run `Shutdown()` on the TiaWorker (bounded 10 s): a project WE
  opened is closed, an attached user instance is left running (`ownsPortal`); re-attaching releases the previous
  portal first. `StartFileLog` disposes its writer when the seeding throws (no orphaned handle).
- **PROFINET port wiring** (`TiaPortalOpenness.Hardware.cs WirePorts`, 2026-10-10): Stations.csv column 10 `Topology`
  (optional; `01_Constructor/HardwareTopology.cs` parses `X1-P2 > <partner station>:X1-P1`, `|` separated, at load
  with file/line errors; the editor round-trips it) names the port links of the plant; with the "Wire PROFINET
  ports" box ticked (one choice mirrored on both tabs, `WirePorts_Changed`, remembered in
  `Properties.Settings.WireProfinetPorts`) the generation wires them after the stations exist through
  `NetworkPort.ConnectToPort`: the interface item by `Xn` (name token / PositionNumber), the port item by "Port n" /
  PositionNumber / order. A pair already connected is left alone, a port connected elsewhere is reported and never
  disconnected, a missing station/interface/port is reported; skipped (existing) stations are wired too. Unticked
  with links present = one log line saying so. The data source is OPEN: PL5 emits column 9 `Connector` from the
  I/O list's column I verbatim and nothing about partners yet.
- **Re-arrange devices** (`ArrangeDevicesWindow.cs`, `01_Constructor/NetworkViewLayout.cs`,
  `10_StandardFunctions/MouseRobot.cs`, 2026-10-10): Openness creates every station on ONE row of the network view
  and has no layout call; TIA's editors are invisible to UI Automation and keys do not move objects (verified
  2026-10-09) - only a mouse drag does. So the Files tab's "Re-arrange devices.." takes the last generation's
  stations in creation order (`TiaPortalOpenness.LastCreatedStations`; the loaded IO-device list stands in without
  a generation, with a warning), plans rows by the Stations.csv Group column (one row per group, at most 7 per row - the box in the
  window - a longer group wraps onto the next free row; rows in order of first appearance; the first row is
  compacted LAST, after the others moved away, so every drop lands on a free spot - `MovesInSafeOrder`), and
  after the user opens the view, zooms until the rows fit vertically and the first columns horizontally, and
  calibrates - in a step-by-step WIZARD (a coloured step strip, one card per step with a drawing of what to hover, a
  pulsing "then press F9" pill, the derived numbers on the side; colourful on purpose - it underlines the two numbers,
  X and Y, that Openness will not give) - with the global hotkey F9: the first station, the second, the first cell of
  row 2, the four scrollbar
  ARROW buttons (< > ^ v); the robot then clicks > 8 times and v 6 times and the user re-hovers the first station
  after each, which measures the scroll step in px per click. From then on the robot scrolls by COUNTED clicks
  (the user's model, 2026-10-10: exact, no pixel reading), brings TIA to the front (`AttachedProcessId`) and drags
  with SendInput, keeping every station's canvas position. A far station travels down in hops of one viewport at a
  free column (columns beyond "max per row" are free on every row - the lane is its target row, row 2 for the
  first row), then left in hops along that lane, then one drag into its cell. Requirements: at least "max per row
  + 1" columns and 2 rows visible (the zoom); the plan is refused otherwise. F12 or a foreground change stops it;
  the drags never run while another window is in front.
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
  read-only view of the model's default parameters, saves back to csv - each file opening with its
  `#!openn` header (the loaded header's keys such as `run` / `project` / `plc` carried forward, producer
  and generated the editor's) and the 9th `Connector` column preserved - and re-runs the validating
  loader. The document layer deliberately tolerates invalid
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
  errors, leftover-placeholder, well-formedness and EMPTY-symbol-component checks before writing (an empty cell
  or iterator slot landing inside a `<Component Name>` fails generation with the row's file/line - TIA would only
  reject it at import as a cryptic per-UID error; ported from the epitaxy line 2026-10-09).
- **Instance-DB creation** (`02_Converter/InstanceDbListParser.cs` +
  `TiaPortalOpenness.Blocks.cs CreateInstanceDbs`): bulk single-instance DBs via the
  direct `PlcBlockComposition.CreateInstanceDB` API — no template/XML, so none of the
  import pitfalls (IDs, namespaces, version, culture) apply; TIA auto-numbers when the
  csv leaves Number empty. Csv reuses the row-marker conventions but with NAMED
  columns (`%` key row: `Name`, `InstanceOf`/`FB`, `Number`, `Folder`) so column order
  is free. Folders are find-or-created (`Groups.Find ?? Groups.Create`); a name conflict with an instance DB of
  the SAME FB is replaced automatically (regeneration semantics, logged; start values are lost by design), any
  other conflict (checked program-wide - block names are unique) pops Retry/Abort/Ignore naming what occupies
  the name; cancellable between DBs; nothing saved. **Fail-safe FBs** (`F_ESTOP1` & co.) refuse
  `CreateInstanceDB` ("cannot create instance DBs for automatically generated blocks") -
  `IsFailsafeCreateRejection` + `TryImportFailsafeInstanceDb` fall back to importing a minimal
  `SW.Blocks.InstanceDB` XML with `ProgrammingLanguage` F_DB, which TIA accepts (ported from the epitaxy line
  2026-10-09; the direct call stays the first attempt). Preferred over the
  XML-template route for plain name+FB+number instance DBs.
- **Input/output paths** (`10_StandardFunctions/AppPaths.cs`): defaults are resolved from the exe
  location, never hardcoded. `AppPaths` walks up from the exe to the monorepo `Shared` folder (the
  one with `HardwareConfigBuilderData`/`OutputTree`) and hands back: `BuilderDataDir` = the default
  workspace (`…\TiaPortalProjectInterface\BuilderData`, VCI shape), `ExportedDataDir` = the default export
  root, `ExportRootFor(workspaceRoot)` = the sibling `ExportedData` of any workspace, `ExportedBlocksDir` =
  the single-block export sink (`…\ExportedData\SingleBlocks`), `GeneratedBlocksDir` (exe-local) and
  `DeviceTypesDatabasePath`. The legacy folders (`HardwareConfiguration`, `SoftwareBlocks\CreationInfo|
  ImportReady`, `PlcTags`, `UserDataTypes`) have no AppPaths entry any more.
  `DeviceTypesDatabase.csv` is a shared **input** under `Shared\HardwareConfigBuilderData` (not
  beside the generated Stations/Modules), so `HardwareDeviceTypesDatabase.ResolvePath` prefers a copy
  beside the config folder and otherwise falls back to the shared one. Openn5-internal working dirs
  (the default new-project folder `bin\Debug\TiaProjects`, `GeneratedBlocks`, `AttributeDumps`, `Logs`) stay
  next to the exe - not to be confused with the tracked repo `TiaProjects\` playground (see Build). `CsvTable`
  opens config files `FileShare.ReadWrite` and closes them before parsing, so a load never locks the
  csv against Pipeline5 regenerating it (or Excel).
- **Export** (`03_ApiManager/TiaPortalOpenness.Project.cs`, the Workspace tab's Export expander - details in the
  UI bullet): the attached project into the workspace's sibling `ExportedData`, VCI shape, every file stamped
  (contract v1 §5.4) - the producer side for Pipeline5's (deferred) phase **920** TIA project coverage. XML via
  each object's `Export` mirroring the TIA group tree, hardware via CAx (`project.GetService<CaxProvider>().Export`
  → `Devices & networks\<project>.aml`). Cancellable between objects; nothing is saved. UDTs and tag tables are
  **one XML per object** (`TypeGroup.Types.Import` / `TagTableGroup.TagTables.Import` on the way in; the
  `PLCTags.xlsx` stays a manual TIA aid - **no Excel library is used**). The folder-based whole-project IMPORT
  that used to live here is gone with the legacy layout; importing is the Workspace tab's job.

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
3. **Config load:** at startup the Files tab's hardware folder is the workspace's `Devices & networks`; the log
   shows `Hardware configuration loaded: N device types, M controller(s), K IO device(s), L module(s)`
   (the builtin PL5 workspace: 19 device types, 2 controllers, 7 IO devices, 18 modules). A folder whose csvs
   carry only `#!format=2` (or no header) is refused: `Hardware configuration NOT loaded - ... requires a #!openn
   header`. `Shared\HardwareConfigBuilderData\TestData\Passing` (stamped 2026-10-09, own database copy) loads.
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
   auto-created sub-items after module plugging — verify against a fresh dump. Before anything is created, the
   "Openn5 - Hardware Generation" OK/Cancel checkpoint asks to close ALL TIA tabs (Cancel: `Hardware generation
   CANCELLED at the checkpoint`, nothing changed; from Import Workspace the hardware row reads Cancelled and the
   run stops). Every created station / plugged module / transfer area line ends with `custom parameters: …` (or
   `no custom parameters`). A station with `Connector` X2 (the PN/PN coupler) is wired to its second IO connector
   (`<station>: Connector X2 -> IO connector 2 of 2` in the log) - before the port every coupler landed on the
   same connector.
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
9. **Workspace tab** (OP5, no TIA needed for the scan): at startup the tab is selected and lists the remembered
   root (default = the builtin BuilderData, PL5's VCI-shaped output). The chips read `layout: VCI shape`,
   `config: ok, contract 1, project 8XXX, run …`, `35 file(s): 32 classified, 0 unclassified, 3 ignored; 32
   importable`; every classified row is green Ready under `n0001-mc1-cc1-k65501 / Program blocks` (block-gen csvs,
   DB and FC XML, InstanceDBs.csv, .scl sources), `<workspace> / Devices & networks` and `Templates`; `PLC tags`
   holds PLCTags.xlsx grey Ignored with its sidecar. Browse to another root, Rescan, restart: the root is
   remembered. Hover / select a row: the notes and header appear; "Log catalog" writes the summary to the log.
   The groups read as a tree: `<workspace>` and `PLC  <name>` blue bands, the TIA folders grey bands indented
   under them, block groups indented further, files in a folder's root directly under the folder band; a
   collapsed band shows a right-pointing triangle, an expanded one a down-pointing triangle. Click the
   `sw/block-gen` chip: only those rows stay, the chip turns filled, "showing 7 of N rows" and Clear appear;
   click it again: all rows return. Type `estop` in the Filter box: the rows narrow as you type across any
   column (regex, e.g. `^0[0-4]_`); Esc empties the box; a chip plus text combine.
   Point the root at a pre-contract tree (legacy `HardwareConfiguration` / `SoftwareBlocks` / `PlcTags` folders)
   or at a folder with unheadered files: the rows are red-tinted (Legacy / NeedsHeader amber text, Invalid red),
   the chips say `layout: legacy BuilderData folders - not importable` / `without #!openn header: N - not
   imported`, and "Import Workspace" logs that nothing is importable. On the synthetic headered workspace
   (the "Contract layer" test pattern: `.openn\workspace.openn.config` with `run`, a file with another `run`, a
   file whose `target` contradicts its folder, a file directly under the PLC folder) the Stale / Invalid rows are
   red and `needs attention: N` is shown.
10. **Workspace import** (project attached): "Import Workspace" runs every Ready item in kind order
   (hardware → UDTs → tag tables → data blocks → instance DBs → block-gen → code blocks → sources), logging
   `=== Workspace import: N item(s) ...` and one line per item, and fills the "Last result" column (Imported
   green / Skipped amber / Failed red / NothingToDo, Cancelled grey); non-Ready rows are skipped with
   `SKIPPED <path> - not importable [...]`; "Cancel Operation" stops between items; a plug / import error pops the
   Retry/Abort/Ignore dialog; nothing is saved. "Import Selection" with only red rows selected logs that none is
   importable and touches nothing.
11. **Export** (project attached): expand "Export the attached TIA project → <sibling ExportedData>" and run
   "Export full project": the log shows the run id and the PLC folder; `ExportedData\<PLC>\Program blocks\…`,
   `PLC data types\…`, `PLC tags\…` hold TIA XML files whose second line opens the `#!openn` comment (kind
   sw/code-block or sw/data-block, run, plc, target, name), `Devices & networks\<project>.aml` + `.cax.log` +
   `.aml.openn` exist, and `.openn\workspace.openn.config` names contract 1, the run and the PLC. Point the
   Workspace root at that ExportedData folder and Rescan: every XML is Ready, the AML Ignored (doc/other).
12. **TIA project row**: starts collapsed (unless left open last time - `ProjectPanelExpanded`); the header reads
   `TIA project: not attached - Attach takes the selected open instance (N found) ...`; Attach works from the
   header without expanding when an instance is listed; expanding shows the dropdown, the path box and "TIA
   Version..". After attaching the header reads `TIA project: <name>` and the button turns steelblue "Detach".
13. **Files tab**: the hardware folder box follows the workspace (`Files tab: the hardware csv folder follows the
   workspace -> …` in the log); Reload / Edit / Generate Hardware work as before; the controller radios mirror the
   Workspace tab's; "Edit Hardware Config.." → Save + Reload writes both csvs with their `#!openn` header and the
   Connector column, and the loader accepts them. Browse buttons start at the workspace root.
14. **Log pop-out**: "Pop out ↗" on the log toolbar opens "Openn5 - Log" with the whole session log so far (same
   colors); new lines appear in both views; its filter is independent of the main one; "Clear Logs" in either
   empties both; "Keep on top" pins it; close and reopen restores the last placement and the pin; a second click
   while open brings it to the front; it closes with the main window.
15. **Import ticks**: untick a Ready row's Import box: the row turns grey, Action reads `import disabled (…)`, the
   chip `import disabled: 1` appears (click it: only that row), the totals chip says `(1 unticked)`, and
   `.openn\import.openn5.config` in the workspace holds `disabled: <relative path>`. Rescan, restart, or let PL5
   regenerate: the tick is still off. Untick Stations.csv: Modules.csv unticks with it (and back). Select rows,
   right-click → "Untick Import for selected" / "Tick Import for selected": all of them move, one file write.
   "Import Workspace" / "Import Selection" with an unticked row: the log says `N item(s) skipped - import
   disabled by you`, its Last result reads `Skipped: import disabled by you (Import box unticked)`, the rest
   imports; with every item unticked nothing is queued. Tick everything again: the file disappears.
16. **Fail-safe instance DBs** (project attached, safety library present): an `InstanceDBs.csv` row whose FB is
   `F_ESTOP1` (or any F-FB) creates without a Retry/Abort/Ignore dialog; the log reads `Created fail-safe instance
   DB <name> via F_DB xml import (instanceOf F_ESTOP1) - direct CreateInstanceDB is not allowed for
   auto-generated blocks`. Run the csv again: the same-FB DB is replaced (`already exists (same FB "…") -
   replaced with a fresh one`); a name taken by a different block still pops the dialog naming it.
17. **Port wiring**: add `X1-P2 > <next station>:X1-P1` to a station's Topology cell (editor or csv), tick "Wire
   PROFINET ports", generate: the log shows `Port link wired: …`, the topology view shows the line between the two
   ports; generate again: `already connected`; a malformed cell fails the load with file/line; unticked with links
   present logs `Topology links in Stations.csv NOT wired`.
18. **Re-arrange devices**: right after a generation, open the network view at its origin (fully left and up), zoom so that 8 columns fit, press
   "Re-arrange devices..", F9 on the first station, the second, one row below the first, the four arrow buttons,
   then F9 on the first station after the robot clicked > 8 times and again after it clicked v 6 times (the status
   shows the measured step and the viewport in columns x rows), Start: the view scrolls by arrow clicks, far stations
   hop down and left along their row's free columns (`after N hop(s)` in the log), then every
   Group gets its own row(s), at most 7 per row (the box in the window; a group of 9 fills row 1 with 7 and puts 2 on
   the next free row), logged `Re-arrange: <station> -> row r, column c (<group>)`; the first group's row is compacted
   last; F12 stops mid-way; alt-tabbing away stops with `lost the foreground`; a plan off-screen is refused.
