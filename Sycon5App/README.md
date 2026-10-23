# Sycon5App — SYCON.net project automation (spike stage, 2026-10-23)

Layout of this folder:

- `README.md` — this brief (the handoff for the next session)
- `spike/scripts/` — the pywinauto probe scripts (read-only on the project: nothing is ever saved), listed below
- `spike/references/` — the UI Automation dumps that are the **control maps** of the dialogs (tracked; the future
  skill's `references/`)
- `spike/scratch/` — gitignored: the working copy of the base project; `spike/*.txt` = probe outputs, gitignored
- `SyconProjects/AutomateSyconProj_BaseProj.spj` + `AutomateSyconProj_BaseProj/` — the **clean base project**
  (controller + 7 base devices), a tracked asset like `Openn5App\TiaProjects` — never open this one directly
- `reference_ahk/` — the old AutoHotkey partial automation and its parameter files, reference only

Goal: an AI skill (Claude Code) that creates Hilscher **SYCON.net** PROFINET projects from the same input
documents Pipeline5/Openn5 use for the TIA project — node list, submodules and DTM parameters per node —
by **driving the SYCON.net GUI** (user decision: GUI automation only; the AHK script only cloned nodes and
never configured submodules or parameters). Structure to mirror **PL5 ⇄ OP5**: PL5 produces a handoff
workspace with `#!openn` headers, a new **Sycon5App** (sibling of `Openn5App` in `C:\Source\Repos\_Openn5`,
same `.zen/contract.md` governance) consumes it and drives SYCON.net; the skill in `~/.claude/skills`
orchestrates and verifies. Driver technology: **pywinauto / UI Automation + win32** (decided); a colour scan of
the drawing only where it is custom-drawn (the bus lines).

## Status 2026-10-23 — the spike ran on the VM

VM `Win11-Test`, user `Administrator`, SYCON.net **1.500** (build 210311, installed 2026-10-22, exe 1.1100.7),
GSDML catalog rebuilt 2026-10-23 10:06. Python = the repo's `.venv` (3.12) + `pywinauto 0.6.9`, `comtypes`,
`olefile` (installed today). Defender did **not** flag pywinauto; no AV exclusion was needed. Screenshots of
SYCON.net are not available to the session (computer-use access declined) — everything below was observed
through UIA/win32 dumps and the netProject tree, which is the oracle for every action.

### Blocker found and worked around: the base project does not load on this SYCON.net

- Opening any device of `AutomateSyconProj_BaseProj` (Configuration..., or a double-click) fails with the modal
  `Error` "Internal error! Load DTM failed!" and the Output log "GSDML file <> not found in folder ... ->
  Device: ...", "Internal error! Function m_cPnIoDataModel.EventGetParameters(...) failed!", "The device is not
  installed."; the generic device DTM also reports "Could not load old ODM settings!" (one modal box per
  attempt, they stack). Dropping a catalog device into THAT project raises the ODM error and SYCON.net then
  **exits silently** (no crash dialog, no event-log entry, nothing written).
- Cause: the persisted DTM data in the project (the `BinData` blobs) was written by a different SYCON.net /
  DTM version than the VM's 1.500 (the work machine's one). Not the cause: the catalog (it lists AL1202, AC140x,
  IM 155-6 PN ST V4.2, SK CU4-PNT ...), the GSDML files, the ODMV3 service (running; it only fails to load the
  cifX hardware driver module, irrelevant without a cifX card).
- In a **new project everything works**: File > New, a `CIFX RE/PNM` controller from the catalog, `AL1202` and
  `IM 155-6 PN ST V4.2` slaves from the catalog, all their DTM dialogs open. → The driver builds every project
  **from scratch, from the catalog** (as already decided); the base project stays a reference for names/IPs
  and for the XML format, nothing more.

### What the GUI driver can do — proved on the real app

- **Session**: `launch_sycon(project)` → `SYCON.net User Login` → `login_default()` (OK, empty credentials) →
  main window `SYCON.net - [<name>.spj]`; `close_sycon_no_save()` (Alt+F4, answers No, kills if stuck).
  File menu = MFC command ids posted as `WM_COMMAND` to the main window (no menu timing): 57600 New, 57601
  Open..., 57602 Close, 57603 Save, 57604 Save as..., 57665 Exit. File > New proved → `SYCON.net -
  [Untitled.spj]`, tree `Project: Untitled`. View / Help menus dumped in `references/uia_menus_kbd.txt`.
- **Add a device from the catalog = drag-drop** (pywinauto `mouse.press` / stepped `move` / `release`) from
  the catalog tree (SysTreeView32 ctrl 40000, `PROFINET IO > Master | Slave | Gateway / Stand-Alone Slave >
  <item>`; expand with the UIA pattern, no clicks) onto a bus line of the **netDevice drawing** (pane auto 3000,
  custom-drawn): a Master onto the grey root line, a Slave onto the controller's **green** network line.
  `find_buslines.py` locates both by colour (one BitBlt of the pane; grey row ≈ 150–200 grey, green ≈
  RGB(80,160,128)): in the new project the root line was at pane y≈51 and the green line at y≈71 to the right
  of the controller icon; in the base project the green line is vertical at x≈37 — layout-dependent, so always
  locate. Success = a new item in the netProject tree: `CIFX_RE_PNM[CIFX RE/PNM]<controller>(#1)`,
  `AL1202[AL1202]<al1202>` (a second one `<al1202-001>`), `IM_155-6_PN_ST_V4.2[IM 155-6 PN ST V4.2]<et200sp>`.
  A drop on empty canvas does nothing (harmless). A catalog item has no context menu.
- **Node context menu** (right-click in the netProject tree; it can take seconds → `wait_menu`): Connect
  35500, Disconnect 35501, Download 35502, Upload 35503, Cut 34502, Copy 34503, Paste 34504,
  Configuration... 35553, Measured Value... 35557, Simulation... 35555, Diagnosis... 35554, Additional
  Functions, Delete 34505, Symbolic Name... 35509. `Symbolic Name...` → `netProject - Change Symbolic Name`:
  Edit 121 (writable), OK 1, Cancel 2.
- **DTM configuration dialogs** are `#32770` windows OWNED by the main window: UIA lists them under the main
  window, not on the desktop → enumerate with the win32 backend (`top_windows`, `config_dialogs`). Title
  `netProject - Configuration <tree label>`. Buttons (descendants, not children): OK 1, Cancel 2, Apply 2204,
  Help 9. Navigation tree SysTreeView32 auto 2199 — pages selected with the UIA `select()` pattern (no mouse);
  page host pane auto 59649. Cancel after a change → `Question` "Configuration data has been changed. Do you
  want to save the data?" Yes 6 / No 7 / Cancel 2 → No. Esc anywhere in the dialog = Cancel.
- **Controller dialog** (`references/uia_ctrl_pages.txt`): Settings > Driver > netX Driver, Device Assignment
  (Scan 1002, SysListView32 1001), Firmware Download, Licensing, Ethernet Devices; Configuration >
  *Controller Network Settings* (Edit 'Name of station' 211, Description 212, SysIPAddress32 IP 213 / mask 214 /
  gateway 215), *Device Table* (custom grid `CDeviceTableGridCtrl` 210: a cell click opens an in-place editor —
  row 1 at y+30: x+20 CheckBox 1900 activate, x+120 Edit 1901 device number, x+200 Edit 1902 **Name of
  station**, writable), *IP Address Table* (custom grid `CIPAddressTableGridCtrl` 212: x+260 opens a
  SysIPAddress32 1901, Field0..3 = the slave's **IP**), Process Data, Address Table (`CIOAddressGridCtrl` 204 /
  205, CSV Export 202, Auto addressing 201), FSU-/Port- Settings, Stations Timing (combos 220 / 223, Edit 224),
  Controller Settings (radios 2224.., Edit 2230, combos 220–223).
- **Slave dialog** (`references/uia_dev_pages_*.txt`): Configuration > *General* (Name of station 243,
  Description 281, IP 278, mask 279, gateway 280 — all **read-only**, "set by the controller of the network":
  station name and IP are written in the controller's Device Table / IP Address Table; CheckBoxes Shared
  Device 325, Enable Bit-Signals 326), *Modules*; Description > Device Info (SysListView32 2301 name/value),
  Module Info (combo 287 + SysListView32 319), GSDML Viewer (an IE control, dumps the whole GSDML — skipped in
  the references).
- **Modules page**: grid `CModulesGrid` 321 (header ≈20 px, rows ≈18 px → row n centre at y ≈ 20 + 18·(n−1) +
  9), Add Module 307 / Add Submodule 308 / Remove 309, 'Alpha-sorted module selection' 325, 'Use of slots: n/m'
  310, 'State of data length ...' 293, Dataset combo 311 (items `Parameter`, `I/O data`), Display mode 312,
  lower grid `CIOGrid` 322 ('IOs'). **Add Module** appends a row with the first GSDML module preselected.
  A click on the new row's Slot cell (x+60) opens an in-place ComboBox 1901; on its Module cell (x+150) an
  in-place ComboBox 1904 whose dropdown lists every module of the GSDML (`DI 8x24VDC HF V2.0  [6ES7
  131-6BF00-0CA0]` ..., 526 for the ET200SP; `references/uia_modules_grid_et200sp.txt`). Select it with the
  **win32** backend: `ComboBoxWrapper.select(text)` (CB_SETCURSEL + notify) — the editor closes = committed.
  UIA pattern calls (select / expand / selected_text) on that editor destroy it.
- **Output window** = SysListView32 1004 / 1005: the message log (the errors above, "Any duplicate
  signal/module tags are detected..." from the controller DTM).
- SYCON.net works on a temp copy of the open project (`%LOCALAPPDATA%\Temp\Sycon\<name>\`), written only on save.

### End-to-end round 1 — written, saved and read back (2026-10-23, `scripts/e2e_round1.py`)

The whole chain ran as one staged script (`--from N --to M`) and the result is the tracked fixture
`spike/references/E2E_Round1/` (the saved `.spj` + `SYCON_net.xml` + the run logs): a new project, the
controller `CIFX RE/PNM` from the catalog (grey line), `IM 155-6 PN ST V4.2` and the NORD `SK CU4-ETH` (its
GSDML V2.46 imported by the user that day, catalog rebuilt 12:25) from the catalog (green line), the controller's
IP 192.168.2.1, the ET200SP renamed `n0005-ms1-k2501` at 192.168.2.5 through the controller grids, the module
`DI 8x24VDC HF V2.0` plugged into its slot 1, `Save as` into `spike/scratch`, and the XML read back: `deviceNo`
per device, each slave's `PNIODeviceDataModelBasic` (name, IP, mask, GSDML path), the slot table from
`STLModuleMap/<slot>/PNIOModuleBasic` (ET200SP: slot 0 DAP + slot 1 `DI 8x24VDC HF V2.0`; NORD: its default
`Dig-IN (1 word)` slot 2 + `PPO 4 (4 words)` slot 3) and the controller's own device list
(`FdtChannelColl/PROFINET_IO/SlaveDTMsGetParameters/DTMProxy00n`: name + IP of every slave). Learned on the way:

- **Writing works through plain Win32**: `Edit.select()` + typed text for the Device Table's Name-of-station
  cell, `set_edit_text` on the four `Field0..3` edits of a `SysIPAddress32` (both in-place grid editors and the
  Controller Network Settings page), commit = click a read-only cell; `ComboBoxWrapper.select(text)` for the
  module cell. All verified by reopening the cell.
- **Order matters for the IP**: set the controller's IP first (`Controller Network Settings`, SysIPAddress32
  213), answer the `Warning` "Changing subnet will automatically modify IP addresses ..." with Yes (id 6), then
  the slave IPs; a slave IP outside the controller's subnet makes OK refuse with an `Error` that re-fires at
  every dismissal, and after such a loop every UIA pattern call on that dialog times out (2 min each) — back
  out with Win32 messages only (Cancel id 2, Question No id 7) or restart.
- **Dialog buttons by Win32 `BM_CLICK`** (`press()` in the script), never by mouse: the controller dialog's OK
  closes it; a **slave dialog's OK never closes it** (proved three times, no message anywhere) — use **Apply**
  (2204) to commit, then **Cancel** (2); if a `Question` "save the data?" follows, Yes (6) keeps the data.
- **Never post a command to the main window while a modal dialog is open** (PostMessage bypasses modality):
  a `Save as` posted behind an open slave dialog was followed by a silent exit of SYCON.net.
- **Silent exits**: SYCON.net exited four times today without any crash dialog, WER record or event-log entry —
  twice in the base project (the unreadable DTM data), once after the modal-bypass above, once while a driver
  process stuck in a UIA call was killed. The user is investigating; the driver must check `sycon_pids()` after
  every dialog close and drop.
- **The `Save As` dialog** (Windows common dialog, title `Save As`): the file name box is the Edit with
  automation id 1148 (the folder view's items are Edits too — pick by id), `set_edit_text(path)` + Enter; the
  main window title then becomes `SYCON.net - [<name>.spj]`. SYCON.net's Save needs a named project.
- The win32 TreeView item API (`get_item`) hangs from 64-bit Python on the 32-bit navigation tree — select pages
  with the UIA pattern only.
- The subnet `Warning` and the DTM messages also land in the Output window log.

### Open on the VM (next session)

1. **Module parameters — mechanism found** (14:05, with computer use for supervision; `probe_params_e2e4.py`,
   `probe_grid_pixels.py`, then by hand on screen):
   - The Modules grid (header 18 px, rows 18 px: row n centre at y+27+18·(n−1)) hides each module's **submodule
     rows**: **double-click the row's glyph at x+17** expands them (single clicks, spacebar, keypad +, Right do
     nothing). **Select a submodule row through the icon column at x+9** — a click in the Module column opens
     the module combo, a click at the far right selects the module row instead.
   - The **Dataset combo 311 enables only for a selected submodule that has parameters** (the ET200SP DAP's own
     submodule 1 has none; the DI module's submodule 1 has the record "Inputs"). Win32 `select("Parameter")`
     replaces the IOs grid 322 by the **`CParamGrid` (auto id 320)**: one row per record ("Inputs", expanded,
     Value = the raw record bytes) and one row per parameter (Name / Value / Data type / Data range, ~12 px rows,
     mouse-wheel scrolling).
   - **Double-click the Value cell's text** (right-aligned) → a Win32 editor, child of the CParamGrid, ctrl id
     **1902**: an `Edit` for numbers / bits (Wire break: `select()` + typed `1`, read back `1`) or a `ComboBox`
     for enumerations (Input delay: `None, 0.05 ms … 20 ms`; win32 `select("0.4 ms")` closes the editor =
     committed, the cell shows 0.4 ms). Single clicks, F2, Space and Down do nothing in that grid.
   - Parameter names are not readable (custom grid): the driver addresses a parameter by its **row index = the
     order of the record's parameters in the GSDML**, and verifies through the saved XML
     (`STLRecordParamDataMap/<n>/PNIORecordParamDataBasic`).
   - **Proved (round 2, 14:12)**: Wire break = 1 (Edit) and Input delay = 0.4 ms (ComboBox, committed by a click
     on the row's Name cell), **Apply** (2204, then disabled), **Cancel closes without a question** once applied,
     `Save` (WM_COMMAND 57603, the project is named) rewrote the XML, and the DI module's record
     `STLModuleMap/1/STLSubModuleMap/1/STLRecordParamDataMap/128` changed in exactly two bytes of channel 0:
     diagnostics byte `00 → 10` (the Wire break bit) and delay byte `86 → 83` (code 6 = 3.2 ms → code 3 =
     0.4 ms, bit 7 "channel activated" kept); the other seven channels and record 243 untouched. The grid's
     "Inputs" byte string never refreshes on screen — verify in the file. Fixture: `spike/references/E2E_Round2/`
     (the saved project + `records_n0005-ms1-k2501.txt` from `read_records.py`).
2. Submodules: `Add Submodule` on a module with one fixed submodule raises the modal `Error` "No possible
   submodule found for insertion!" (blocks everything until dismissed); Remove, slot numbering (combo 1901, SYCON
   numbers new rows 1, 2, …); the coupler / ServoOne / AC140x catalog names; a second slave of the same type
   (`-001` suffix) renamed.
3. Then the driver API as `Sycon5App` operations — `new_project`, `add_station(catalog, name, ip)`,
   `plug_module(station, slot, module)`, `set_parameters(station, slot, {name: value})`, `save_as`,
   `read_back()` (the stage functions of `e2e_round1.py` are their first draft) — and the PL5 handoff kinds
   (decisions unchanged, below).

### Scripts (`spike/scripts/`, run from `spike\` with the repo venv: `..\..\.venv\Scripts\python -I scripts\<name>.py ...`)

| script | what it does (read-only unless said) |
|---|---|
| `_probe_lib.py` | the shared helpers: `sycon_main`, `safe_click` (refuses to click while a popup menu is open or when the pixel belongs to another process — the Claude window can overlap), `wait_menu` / `close_menus`, `top_windows` / `config_dialogs` (win32 enumeration), `new_dialog`, `dismiss_errors`, `launch_sycon` / `login_default` / `close_sycon_no_save` |
| `sycon_restart.py` | close without saving, refresh `spike/scratch` from `SyconProjects`, launch, login |
| `uia_dump.py`, `uia_login_dump.py` | the first-machine dumps (launch + login + main window tree) |
| `probe_dtm_open.py <station>` | context menu → Configuration... (fallback double-click), dumps the dialog, leaves it open |
| `probe_dialog_pages.py <title-sub> <out> [--cancel]` | walks every page of the open dialog (UIA select), dumps each, Cancel |
| `probe_cancel_dialog.py`, `probe_question_no.py`, `probe_close_dialog.py` | clean-up: Cancel dialogs, answer No, dismiss Error boxes, print the Output log |
| `probe_catalog_menus.py`, `probe_menus_kbd.py` | catalog trees (PROFINET IO expanded) and the main menus by Alt+letter |
| `find_buslines.py` | the bus lines of the drawing by colour (BitBlt), as pane offsets for the drops |
| `probe_add_device.py [--new-project] "<PROFINET IO/Slave/AL1202>" dx dy` | File > New (optional), drag-drop a catalog item to a drop point, liveness check after every mouse action |
| `probe_catalog_add.py`, `probe_catalog_add2.py`, `probe_slave_open.py` | earlier versions, kept for the record |
| `probe_grid_cells.py <title-sub> <page> <grid id> <y> <xs>` | clicks cells of a custom grid, reports the in-place editors and their values |
| `probe_modules_page.py`, `probe_modules_grid.py` | Modules page: editability, Add Module, cell clicks with dropdown detection |
| `probe_parameters.py`, `probe_parameters2.py`, `probe_parameters3.py` | module selection via the in-place combo (v3 = win32, the one that works) and the Dataset / lower grid probe |
| `probe_symbolic_name.py <station>` | the Symbolic Name dialog |
| `read_records.py <SYCON_net.xml> <deviceNo>` | the parameter records of one slave from a saved project (the blob's `STLRecordParamDataMap` streams, hex) - the read-back oracle for `set_parameters` |
| `probe_params_e2e.py`, `probe_params_e2e2.py`, `probe_params_e2e3.py`, `probe_params_e2e4.py`, `probe_grid_pixels.py` | the module-parameter probes on the saved round-1 project (row scans, expansion keys, pixel bands of the Modules grid, the DAP/submodule rows, the CParamGrid); the mechanism they found is written up above |
| `e2e_round1.py [--from N] [--to M]` | **writes** (in memory + one `Save as` into `spike/scratch`): the 8-stage end-to-end round above — restart + New, controller, ET200SP, controller IP + station name + slave IP (controller grids), NORD, module plug (Apply, Cancel), Save as, XML read-back; its stage functions are the first draft of the driver operations |

## Inputs

| what | where |
|---|---|
| clean base project (controller + 7 base devices, no clones) — reference only on this VM (see the blocker) | `Sycon5App\SyconProjects\AutomateSyconProj_BaseProj.spj` + folder `AutomateSyconProj_BaseProj\_S129\SYCON_net.xml` (original: `OneDrive - FIVES\Work\3 Programmi\0_Scripts\AutoHotKey\AutomateSyconProj_Data - Backup - Copy\`; the un-suffixed `AutomateSyconProj_Data` holds an AHK run with 36 clones) |
| AHK partial automation (reference only; it read symbolic names via Shift+F10 → Up → Enter and cloned by copy/paste) | `Sycon5App\reference_ahk\AutomateSyconProj.ahk` (+ `_lib.ahk`); params in `reference_ahk\Parameters\` |
| TIA counterpart (the structure to mirror) | `C:\Source\Repos\_Openn5` — `Openn5App\CLAUDE.md`, `Shared\PL5_OP5_contract.md`, `Pipeline5App\pipeline5\systems\plc_based\siemens_s7\{profinet_hardware,hardware_csv_export,openn_header,output_layout}.py` |
| PL5 hardware handoff the SYCON side should consume | `hw/stations` (`Stations.csv`: role, station name, model id, IP, PN number, subnet, custom params, group, connector) + `hw/modules` (`Modules.csv`: station, slot, module name, model id, I/Q addr, custom params) + `hw/device-types` (`DeviceTypesDatabase.csv`) |
| project input docs (FVT La Poste) | `...\0 Commesse\FVT_LaPoste\0 Documenti Elettrici\_IOLists\*.xlsx`, `Cxxxx Configuration Summaries\8FVT_C0002_ADDRESS TABLE FIVES - PROFINET_R0.0 ...xls` |

## What the SYCON.net project file is (for verification, not for writing)

- `<name>.spj` is a 40-byte OLE stub; the project is `<name>\_S129\SYCON_net.xml`.
- One `<Device …>` per node: attributes `syc:symbolicName` (`VENDOR#Model: description`, the catalog name the AHK
  matched on), `deviceNo` (= PROFINET station name), `syc:progId` (`Hilscher.PNIOGenDevDTM2.1` for GSDML slaves,
  `Hilscher.PNIOControllerDTM2.1` for the controller), `fdt:manufacturerId`, `fdt:deviceTypeId`,
  `fdt:deviceTypeInformation` (the GSDML path under `C:\ProgramData\SYCONnet\PROFINET\GSDML\`), plus a
  `<BinData>` hex blob.
- The blob (after a 4-byte length prefix) is an OLE compound file — the DTM's persisted data: stream
  `PNIODeviceDataModelBasic` holds the station name and IP as length-prefixed UTF-16 strings; `STLModuleMap/<slot>/
  STLSubModuleMap/<n>/…` holds the plugged modules/submodules and `STLRecordParamDataMap/<index>` the parameter
  records. The controller's blob carries a `<pn:Network nameOfStation=… ipAddress=…>` list of every slave.
- Reading this XML after a save = the cheapest **read-back verification** of what the GUI driver did
  (names, IPs, module counts per station). Python `olefile` opens the blobs.

## Decisions already taken (do not re-ask)

- GUI automation only (pywinauto/UIA + win32 for the in-place editors); no file-level generation of `SYCON_net.xml`.
- Projects are built from scratch from the device catalog (the base project is a reference; it does not load on
  the VM's SYCON.net 1.500 anyway).
- Consumer lives in `_Openn5` as `Sycon5App`, under the repo's `.zen` contract; PL5 gains SYCON handoff kinds
  (proposed `hw/sycon-stations`, `hw/sycon-modules`, `hw/sycon-device-types` = model id → SYCON catalog
  `VENDOR#Model` + GSDML + slot/submodule map + DTM parameter names).
- Input = the PL5 hardware tables (same source of truth as the TIA project), not a separate parser.
- Nothing is ever auto-saved by the driver; the user saves after review (OP5 rule).
