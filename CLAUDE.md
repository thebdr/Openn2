# Openn2 — TIA Portal Openness automation tool

WPF app (.NET Framework 4.8, old-style csproj) that drives Siemens TIA Portal via the
Openness API: attaches to/creates TIA projects, generates PROFINET hardware from csv
files, imports/exports PLC blocks.

## Build

- Requires `Siemens.Engineering.dll` **V18–V20**. The csproj resolves it automatically:
  repo `lib\Siemens.Engineering.dll` override → registry
  (`HKLM\SOFTWARE\Siemens\Automation\Openness`) → default install paths — lowest
  installed version first (max runtime compatibility).
- On machines without TIA Portal, drop a V18 dll into `lib\` (see `lib/README.md`).
  Never commit that dll, never copy it next to the exe (the reference is
  `Private=False` — an Openness requirement; a copied dll would break version selection).
- Build with Visual Studio (`Openn.sln`) or `msbuild Openn.csproj /p:Configuration=Debug`.
- V21+ is deliberately unsupported (breaking Openness changes).

## Architecture — key invariants

- **Version selection** (`03_ApiManager/OpennessSetup.cs`): installed Openness versions
  (V18–V20) are discovered from the registry + install-folder scan; the user picks one at
  startup (`App_Startup`) and an `AppDomain.AssemblyResolve` hook loads that version's
  assemblies. No Siemens type may be touched before the hook is registered; once loaded,
  the version is fixed until restart.
- **TIA facade** (`03_ApiManager/TiaPortalOpenness*.cs`): one partial class split by
  feature area — `TiaPortalOpenness.cs` (portal/project lifecycle),
  `.Blocks.cs` (block listing/export/import), `.Hardware.cs` (hardware generation).
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
- **Hardware config** (`01_Constructor/`): csv "format 2" — `Stations.csv` +
  `Modules.csv` + `DeviceTypesDatabase.csv`; `;` delimited, `#` comments, `#!format=2`
  tag, parsed by `CsvTable`. `HardwareConfigLoader` validates the whole folder before
  publishing anything (all-or-nothing, every error with file/line). **No legacy
  support by design**: pre-format-2 folders (`IoControllersList.csv` + wide
  `IoDevicesList.csv`) are handled by the old stable application version, not here —
  do not re-add converters or fallbacks.
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
  `[Item(i).][Ch(i).]Name=Value`, separated by `|` (`,` is rejected with an error —
  it collides with Excel's csv delimiter), one `(a-b)` range per entry, `IP[i]`
  placeholder = octet i of the station IP. Applied in `TiaPortalOpenness` either via
  the explicit path or by discovering the owning object through `GetAttributeInfos`
  (first writable match in the module tree); values are converted to the attribute's
  actual type. No hardcoded attribute names — keep it that way.

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
2. **Startup:** version dialog lists all installed versions, newest preselected; the
   chosen version appears in the window title and the first log line.
3. **Config load:** log shows
   `Hardware configuration loaded: 14 device types, 2 controller(s), 87 IO device(s), 336 module(s)`.
4. **Project handling:** attach to a running TIA instance (dropdown) and by path.
   Open "Search / Export Blocks" — the list must include blocks inside block-group
   subfolders (shown as `[Type] Folder/Name`), the search box filters as you type
   (regex, case-insensitive), and exporting a block that lives in a subfolder must
   work. Import a block.
5. **Generate Hardware** on a fresh project: devices created, IPs and PN numbers set,
   and custom parameters land where the old hardcoded code put them — Murrelektronik FS
   Data module: `Failsafe_FDestinationAddress`/`FMonitoringtime`/`FParameterSignature…`
   on the module's first sub-item; F-DI cards: `Failsafe_DiscrepancyTime` per channel;
   `PotentialGroup` on the module itself. The UI must stay responsive (spinner over the
   log area) during generation. "Cancel Operation" must stop the run between devices
   with a "N of M created" log line; a plug error must pop the Retry/Abort/Ignore
   dialog and honor each choice.
6. **Negative test:** select V18 at startup, try attaching to a running V19 instance —
   expect an error in the log, not a crash.
