# Sycon5App — SYCON.net project automation (spike stage, 2026-10-23)

Layout of this folder (everything the VM session needs is in the repo; untracked, nothing committed yet):

- `README.md` — this brief
- `spike/scripts/` — the pywinauto probe scripts + `netproject_tree_dump.txt` (a UIA dump from the first machine)
- `spike/scratch/` — gitignored: put the working copy of the base project here and open only that in SYCON.net
- `SyconProjects/AutomateSyconProj_BaseProj.spj` + `AutomateSyconProj_BaseProj/` — the **clean base project**
  (controller + 7 base devices); a tracked asset like `Openn5App\TiaProjects` — never open this one directly
- `reference_ahk/` — the old AutoHotkey partial automation and its parameter files, reference only

Goal: an AI skill (Claude Code) that creates Hilscher **SYCON.net** PROFINET projects from the same input
documents Pipeline5/Openn5 use for the TIA project — node list, submodules and DTM parameters per node —
by **driving the SYCON.net GUI** (user decision: GUI automation only; the AHK script only cloned nodes and
never configured submodules or parameters). Structure to mirror **PL5 ⇄ OP5**: PL5 produces a handoff
workspace with `#!openn` headers, a new **Sycon5App** (sibling of `Openn5App` in `C:\Source\Repos\_Openn5`,
same `.zen/contract.md` governance) consumes it and drives SYCON.net; the skill in `~/.claude/skills`
orchestrates and verifies. Driver technology: **pywinauto / UI Automation** (decided), screenshot-driven
fallback only for custom-drawn DTM pages.

The local spike stopped because the antivirus flagged the pywinauto script (click injection); it continues
on a VM with SYCON.net installed. **On the VM, first add an AV exclusion for the driver folder.**

## Inputs on this machine

| what | where |
|---|---|
| clean base project (controller + 7 base devices, no clones) — **use a copy of this one** | `Sycon5App\SyconProjects\AutomateSyconProj_BaseProj.spj` + folder `AutomateSyconProj_BaseProj\_S129\SYCON_net.xml` (original: `OneDrive - FIVES\Work\3 Programmi\0_Scripts\AutoHotKey\AutomateSyconProj_Data - Backup - Copy\`; the un-suffixed `AutomateSyconProj_Data` holds an AHK run with 36 clones) |
| AHK partial automation (reference only) | `Sycon5App\reference_ahk\AutomateSyconProj.ahk` (+ `_lib.ahk`); params in `reference_ahk\Parameters\` (`Quantities.csv`, `NodesList.csv`, `_SyconBaseDevices.csv`, `__SyconNodes.xlsm`) |
| TIA counterpart (the structure to mirror) | `C:\Source\Repos\_Openn5` — `Openn5App\CLAUDE.md`, `Shared\PL5_OP5_contract.md`, `Pipeline5App\pipeline5\systems\plc_based\siemens_s7\{profinet_hardware,hardware_csv_export,openn_header,output_layout}.py` |
| PL5 hardware handoff the SYCON side should consume | `hw/stations` (`Stations.csv`: role, station name, model id, IP, PN number, subnet, custom params, group, connector) + `hw/modules` (`Modules.csv`: station, slot, module name, model id, I/Q addr, custom params) + `hw/device-types` (`DeviceTypesDatabase.csv`) |
| project input docs (FVT La Poste) | `...\0 Commesse\FVT_LaPoste\0 Documenti Elettrici\_IOLists\*.xlsx`, `Cxxxx Configuration Summaries\8FVT_C0002_ADDRESS TABLE FIVES - PROFINET_R0.0 ...xls` |

Python on this machine: `C:\Users\bogdan.dragoi\AppData\Local\Python\bin\python3.exe` (3.14) with pywinauto
0.6.9, comtypes, pywin32, openpyxl, olefile (no xlrd).

## What the SYCON.net project file is (for verification, not for writing)

- `<name>.spj` is a 40-byte OLE stub; the project is `<name>\_S129\SYCON_net.xml`.
- One `<Device …>` per node: attributes `syc:symbolicName` (`VENDOR#Model: description`, the catalog name the AHK
  matched on), `deviceNo` (= PROFINET station name), `fdt:manufacturerId`, `fdt:deviceTypeId`,
  `fdt:deviceTypeInformation` (the GSDML path under `C:\ProgramData\SYCONnet\PROFINET\GSDML\`), plus a
  `<BinData>` hex blob.
- The blob (after a 4-byte length prefix) is an OLE compound file — the DTM's persisted data: stream
  `PNIODeviceDataModelBasic` holds the station name and IP as length-prefixed UTF-16 strings; `STLModuleMap/<slot>/
  STLSubModuleMap/<n>/…` holds the plugged modules/submodules and `STLRecordParamDataMap/<index>` the parameter
  records. The controller's blob carries a `<pn:Network nameOfStation=… ipAddress=…>` list of every slave.
- Reading this XML after a save = the cheapest **read-back verification** of what the GUI driver did
  (names, IPs, module counts per station). Python `olefile` opens the blobs.

## What UI Automation exposes (proved on the real app, this machine)

- Login dialog `SYCON.net User Login` (`#32770`): ComboBox `User Name:` (auto 1008), Edit `Password:` (1009),
  Button `OK` (auto 1). Default credentials are empty → just press OK.
- Main window title `SYCON.net - [<project>.spj]`, MFC (`Afx:…`). Menu bar is a `ToolbarWindow32` (drive menus
  with Alt-keys / `menu_select`, or the context menu).
- **netProject** pane: a real `SysTreeView32` (auto 158). Items read `Symbolic[DeviceName]<station-name>`, e.g.
  `IFM#AL1202: IOLink 8xM12[AL1202]<n0030-rc1-xn1>`, the controller `CIFX_RE_PNM[CIFX RE/PNM]<n0001-mc1-a2501>(#1)`.
  → every node is element-addressable by station name; no pixel offsets needed (the AHK's weak point).
- **netDevice** pane: left = the network drawing (custom `AfxFrameOrView70su`, auto 3000 — not UIA-readable, avoid),
  right = the **device catalog**: search Edit (auto 227) + `CatalogSearch` button (auto 226) + a real tree whose
  top level is the fieldbus list (AS-i, CANopen, CC-Link, …, PROFINET …) → add-from-catalog can be element-driven
  (the AHK copied base nodes instead because it could only see pixels).
- Output window: `SysListView32` (auto 1004) — the message log, readable for verification.
- Full tree dump: `spike\scripts\netproject_tree_dump.txt`.

Convention seen in the base project: a GUI copy/paste of a node yields `<base-name>-001`, `-002`, … with the next
free IPs — i.e. cloning needs a rename + IP step per node anyway, so **adding from the catalog is not worse
than cloning** and gives the right device type without a base node per model.

## Next steps on the VM (the unknowns)

1. `pip install pywinauto openpyxl olefile`; add an AV exclusion for `Sycon5App\`; copy `SyconProjects\*` into
   `spike\scratch\` (gitignored) and open only that copy. Run the scripts from `Sycon5App\` (their `.txt`
   outputs land in `spike\` and are gitignored).
2. `python -I spike\scripts\uia_dump.py spike\scratch\AutomateSyconProj_BaseProj.spj` → login dialog;
   `python -I spike\scripts\uia_login_dump.py 7` → presses OK, dumps the main window.
3. `python -I spike\scripts\uia_probe.py n0030-rc1-xn1` → context menu of a slave, catalog tree, win32 control classes,
   then double-clicks the slave and dumps its **DTM configuration dialog** to `uia_dtm_dialog.txt`.
   This dump is the decision point: which pages/controls set **station name, IP, modules/submodules
   (slot table), parameters**, and whether they are standard Win32 (Edit/ComboBox/SysListView32/grid) or
   custom-drawn. Repeat for a NORD `sk-cu4-eth` (a drive with record parameters) and the controller.
4. Probe the catalog: type a model in the search Edit, dump the tree, find how a catalog item is added under the
   controller (drag-drop onto the bus line vs. context menu "Add"/"Insert").
5. Probe the menus: `Network` (Device Assignment / Download / Export), `Project`, and the slave context menu
   (`Configuration…`, `Symbolic Name…`, `Cut/Copy/Paste`, `Delete`) — the AHK used Shift+F10 → Up → Enter to reach
   "Symbolic Name" of the previous row.
6. Record each dialog's control map in `references/` of the future skill; then write the driver as
   `Sycon5App` operations: `open_project`, `add_station(model, name, ip)`, `plug_module(station, slot, model)`,
   `set_parameters(station, slot, {name: value})`, `save_as`, `read_back()` (parse `SYCON_net.xml`).

## Decisions already taken (do not re-ask)

- GUI automation only (pywinauto/UIA); no file-level generation of `SYCON_net.xml`.
- Consumer lives in `_Openn5` as `Sycon5App`, under the repo's `.zen` contract; PL5 gains SYCON handoff kinds
  (proposed `hw/sycon-stations`, `hw/sycon-modules`, `hw/sycon-device-types` = model id → SYCON catalog
  `VENDOR#Model` + GSDML + slot/submodule map + DTM parameter names).
- Input = the PL5 hardware tables (same source of truth as the TIA project), not a separate parser.
- Nothing is ever auto-saved by the driver; the user saves after review (OP5 rule).
