# Sycon5App — SYCON.net project automation (spike stage, 2026-10-23)

Layout of this folder:

- `README.md` — this brief (the handoff for the next session)
- `sycon5/` — **the driver package** (see "The driver" below), its modules in dependency order (law L1 of
  `tests/test_architecture_contracts.py`): `log` < `handoff`, `readback` (the PL5 tables, the read-back oracle)
  < `canvas`, `workspace` (the XML / folder side) < `session`, `drawing` < `catalog`, `dialog`, `exports` <
  `controller`, `device` < `driver` (the `SyconDriver` facade) < `consumer` (the build) < `gui` (the users' window)
- `tests/test_readback.py` — the read-back on the two fixtures (no GUI); `scripts/e2e_driver_round3.py` — the
  driver end to end on the VM (writes one project into `spike/scratch`)
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

## The PL5 handoff and its consumer (2026-10-23 afternoon)

**PL5 side** — `Pipeline5App/pipeline5/systems/ipc_based/intervalzero_rtx/sycon_handoff.py` (the cPCI hardware of
the IPC-based sorter: its cifX PROFINET controller and IO devices), three kinds with the contract-v1 header
(`openn_header.SCHEMAS` knows them, `target: SyconNetProjectInterface`), written into `SyconNetProjectInterface/`:

| kind | file | columns |
|---|---|---|
| `hw/sycon-device-types` | `SyconDeviceTypesDatabase.csv` (hand-maintained original: `Shared/HardwareConfigBuilderData/`, shipped beside the tables with its `source`) | Model Id (the I/O List Part No. without spaces), Role (controller / slave / gateway / ignore), Catalog Item (the SYCON.net catalog entry under PROFINET IO > Master / Slave / Gateway), Modules (`iolist` = the I/O List cards are plugged, `iolink-ports` = the IO-Link ports are configured from the connector rows, `default` = the catalog defaults stay), GSDML (the file whose catalog entry is taken - the catalog lists one same-named entry per GSDML version; checked by read-back), Comment |
| `hw/sycon-stations` | `SyconStations.csv` | Role, Station Name (the PROFINET name), Catalog Kind, Catalog Item, Model Id, GSDML (the file of the catalog entry to take; column added 2026-10-23 pm - the reader tells by the `#` column line), IP Address, Subnet Mask, Gateway, Device Number (col F), Description, Comment |
| `hw/sycon-modules` | `SyconModules.csv` | Station Name, Slot (plug order), Subslot (empty = a module row; a submodule row's subslot - column added 2026-10-23 pm, the reader tells by the `#` column line), Module Id (the card's order number; empty for a port), Module Text (empty = resolved by the consumer from the order number the catalog shows in brackets; a port's submodule text), Parameters (index=value), Comment (the slot tag; a port's connector, footprint and devices) |

Rules: the staging's head rule (`profinet_name` opens a node), phase 700's card rule (each distinct slot tag under
the head that is not the head's own is a card); a card's model is its Part No. unless that is a Fives code
(`14C_00051`) - this I/O List shifts the card rows one column (the order number in `Manufacturer`); the second
controller of a redundant pair (same IP) and `ignore` models are INFO findings, a head without a mapped model a
WARN, no controller a FAIL. One project = one PROFINET network, the controller's (2026-10-24: the conveyor list
`IO0013` has two cabinet sheets, R1.S2.C1 on 192.168.2.x and R1.S2.C2 on 192.168.3.x, each with its own cifX
pair, and the second repeats the first's station names - `n0055-enc04-aec1-k11`, `n0078-enc06-aec1-k11`,
`n0085-enc04-aec1-k11`; merged into one project they blocked the controller dialog's IP Address Table page):
a controller on another network than the first is an INFO (`sycon_second_controller`, "another PROFINET
network"), every station on another network than the controller's an INFO `sycon_other_network`, left out -
`--sheet R1.S2.C2` exports that network's own project. A station name or IP repeated WITHIN the network is a
document error: `sycon_duplicate_name` / `sycon_duplicate_ip` FAIL, the second left out (PL5's 110 now also
raises `pname_duplicated` on a PROFINET name used twice). `python -m pipeline5.systems.ipc_based.intervalzero_rtx.sycon_handoff --iolist <xlsx>
--out <folder>` stages the list with the builtin params and writes the folder; `tests/unit/test_sycon_handoff.py`.
The LOWER SORTER list (`8FVT_IO0010 ... LOWER SORTER_R1.2.xlsx`) gives 1 controller + 55 stations (3 PN/PN
Coupler X2, 6 ET200SP, 26 ServoOne Junior, 19 AL1202, 1 Anybus Communicator) + 22 module rows; skipped: the
backup cifX card, 5 SCALANCE switches (no XC216 in the catalog), 2 Vitronic controllers without a part number.

**Consumer** — `sycon5/handoff.py` (the reader, by position) + `sycon5/consumer.py` (`build`, `verify`) +
`scripts/build_from_handoff.py --handoff <folder> --out <project.spj> [--resume]` (`scripts/handoff_cut.py
--handoff <folder> --out <folder> --stations <names>` cuts a handoff down to a few stations for a smoke): new project, the controller
from the catalog and its network IP, every station from the catalog (SYCON names them `al1202`, `al1202-001`, ...),
ONE controller-dialog pass renaming every row and setting every IP (`ControllerDialog.rename_and_address`: the
Device Table read row by row - the name is read before it is written, the grids scrolled by wheel HALF a view
at a time with the pixel shift measured and, after every scroll, re-synchronised on a row already read (a grid
of alike rows aliases at a row's pitch: 2026-10-24 17:19 two IPs landed three rows off); the IP Address Table
has its OWN order - the stations sorted by IP, not the Device Table's rows (found 2026-10-24 17:30: two new
stations with the auto IPs .3 / .4 sat at rows 1 / 2) - so it is scanned read-only once, a station's row is the
row of its current IP (the saved one on a resume, else the unclaimed auto-assigned ones ascending in Device Table
order), then ONE pass writes the targets straight away (user: duplicate IPs are refused at OK only, so no
parking on .200+), each row's current IP checked before it is written), the modules of the
`iolist` stations in one dialog each (`plug_modules`: 'Add Module' pressed again when a first press only closed
an open editor, the module text resolved from the order number in the combo's brackets, the plain variant
preferred), checkpoint saves, `read_project` compared with the tables (`<project>.verification.txt`). SYCON.net
lower-cases every name of station: all comparisons are case-insensitive. Grid geometry: an 18 px header and
16 px rows in the controller grids AND the Modules grid (row n centre at y+27+16n / y+26+16(n−1)).
Smoke (3 stations, 7 modules, 15:38): 22 PASS, 0 FAIL in 172 s (`spike/references/LowerSorter/`).

**GSDML folder hygiene** (`scripts/gsdml_dedupe.py`, dry run by default, `--apply` moves): the catalog listed every
version of a family (3 PN/PN coupler files, 2 ET200SP, ...); the script keeps the newest date per vendor + family
and moves the rest to `GSDML_superseded_<date>` beside the folder. **Never move the installer's own files**
(the Hilscher GSDMLs, 2020-10-21 timestamp): the Windows Installer then re-runs SYCON.net's self-repair at every
start, which fails without its source folder ("Configuration failed" 1603, 2026-10-23 16:04) - put them back
and SYCON.net starts again. The `#Siemens-PreConf_` per-node exports and the `_MOD_` SCALANCE files are left to
the user; a project saved against a moved GSDML loses its DTM (the spike fixtures reference the 2021 ET200SP).
Reload the catalog (Network > Device Catalog > Reload) after any change to the folder. **The newest file is not
always the usable one**: with the 2024 `GSDML-V2.43-Siemens-ET200SP-20240425.xml` SYCON.net 1.500 logs
`CreateSubModule failed` / `GetIOProperties failed` in the Output window and the first DI module ended "without
submoduls" on Apply (two builds, 17:21 and 17:36, the 2024 file alone in the folder); the afternoon smoke with
the 2021 V2.35 file had plugged them fine. The user re-imported the 2021 file and the database names it (user
2026-10-23: "use the 2021 gsdml"); the dedupe script never moves a file the database names (`--database`,
default `Shared/HardwareConfigBuilderData/SyconDeviceTypesDatabase.csv`). **One file per device identity**: with
both ET200SP files installed (17:57 build) the catalog shows two `IM 155-6 PN ST V4.2` entries, the driver
dragged the one whose pane cites the 2021 file, the 7 modules plugged with their submodules - and the saved
device still records `deviceTypeInformation` = the 2024 file: the generic DTM resolves the GSDML by vendor /
device / DAP identity, not by the catalog entry, so the verification's GSDML check fails (48 PASS, 1 FAIL) until
the 2024 file leaves the folder (moved by hand to `GSDML_superseded_<date>`, catalog reloaded). The DAP suffix
of the catalog item still works where the DAPs differ (the coupler: the V4.2 DAP saved from entry 2 of 5).

**Catalog versions** (user 2026-10-23: "the pnpncoupler that was inserted was the wrong version"): the catalog shows
one same-named entry per GSDML file AND per DAP of a file, and nothing in the tree tells them apart - the info pane
under the catalog (RichEdit20W 59664, `Session.catalog_info`) does: its `Device:` block cites the DAP and the file
in brackets, `firmware V4.2 [0x00010006] [DAP X2 V4.2] [GSDML-V2.35-Siemens-PNPNIOC-20200924.xml]`. Probed 17:00:
the five `PN/PN Coupler X2` entries all come from that one file and are its DAPs V1.0 (`DAP V2.1 X2`, order
6ES7 158-3AD00), V2.2, V3.0, V4.0 and V4.2 (entry 5, order 6ES7 158-3AD10 = the I/O List's part; the smoke project
of 15:38 had taken entry 1, the V1.0 DAP). So the device-types database names the catalog item with the DAP as a
bracketed suffix, `PN/PN Coupler X2 [DAP X2 V4.2]`, beside the GSDML column; `catalog.catalog_item(session, kind,
item, gsdml)` splits the suffix (`split_item`) and selects the same-named entries one by one until the pane cites
the wanted file and DAP (the index found last is tried first), refusing with the tokens it saw when none does
(a wrong file was refused, 16:57). `read_project` now reads the saved DAP id and its order number (slot 0's
`PNIOModuleBasic`), and `verify` checks the GSDML, the type name, the DAP and the order number against the
model id - the oracle of the version. Without a GSDML or a variant the first entry is taken and its info logged.
Speed: `_kind_node` / `catalog_item` look at the direct children of a tree node only - walking the whole catalog
tree cost 15-30 s per lookup; `Session.project_tree` likewise looks at each tree's root item only (it used to walk
the catalog tree looking for `Project:` - that was most of the ~50 s per station of the afternoon).

**Cloning** (user: "once a device of a type was placed, Copy, Click, Paste in the left tab is a quick way to
replicate (see the .ahk script)"): `SyconDriver.clone_station(source, count)` selects the source node in the
netProject tree, sends Ctrl+C, selects it again, sends Ctrl+V and reads the new node from the tree; SYCON.net
names a clone `<source>-001`, `-002` (the AL1202 cloned twice, 17:00) and the rename pass maps them like any
auto name. The context menu's Copy / Paste command ids (34503 / 34504) posted to the main window produce
nothing - they stay as the fallback. The consumer adds only the first station of each (kind, catalog item,
GSDML) from the catalog and clones the rest.

**IO-Link ports (AL1202)** (user 2026-10-23: "how to configure the modules for the iolink devices, rules in the
file" = `TAG_IFM_PROFINET_AL1202_R0.17.xlsm`, the Fives IO creator tool: its sheet `Tab` and the `DATA INSER`
macro, extracted from the VBA). An AL1202 has 8 ports `X01`..`X08`, each with pin 4 (IO-Link, DI, DO or unused)
and, on the class-A ports X01-X04, pin 2 (a DI); its SYCON.net `8 Ports` module (slot 1, there by default) holds
the `IO-Link Master` in sub 1 and one port submodule per port after it, fixed by the port's device: `Disabled`,
`Digital Input + PQI` (a pin-4 or a pin-2 DI: 1 input byte), `Digital Output + PQI` (1 in, 1 out), `IO-Link In
2 Byte + PQI` (3 in), `IO-Link In/Out  2/ 2 Byte + PQI` (3 in, 2 out), `IO-Link Out  2 Byte + PQI` / `Out 16
Byte` (stack lights: 1 in), `IO-Link In 32 Byte + PQI` / `In/Out 32/32` (33 in = 32 data + the PQI byte). The
I/O List addresses follow the ports in order (a port's PQI bit = bit 7 of its last input byte, `DIAGNOSTIC OF
PORT Xnn (PQI)`; a DO reserves an input byte without a row; a 32-byte device lists its output start only). PL5
reads that backwards - `sycon_handoff.port_rows / port_footprint / port_submodule`, policy `iolink-ports` in
the device-types database: a port's rows are those with its connector plus the connector-less rows after them
(a stack light's lamps), its footprint the span of their `I.<node>.<byte>.<bit>` / `Q...` addresses, the
submodule from the footprint table (`sycon_port_footprint_unknown` WARN and no row when none fits);
`hw/sycon-modules` carries one row per port: Slot 1, Subslot = port + 1 (the IO-Link Master being sub 1 - to be
verified on the VM), Module Text = the submodule. LOWER SORTER (19 AL1202, 152 port rows): 73 Disabled, 33
In/Out 32/32 (the modulators), 21 Digital Input, 14 Out 2 Byte (stack lights), 10 In 2 Byte, 1 Digital Output.
Consumer side: `read_project` lists the submodules (`STLSubModuleMap/<sub>/PNIOSubModuleBasic`; the smoke
project's AL1202 shows slot 1 `8 Ports` / sub 1 `IO-Link Master` only), `verify` compares every port row with
them (spacing collapsed), `SyconDriver.plug_submodules(station, slot, [(subslot, text)])` plugs them - verified
17:12 (`scripts/probe_plug_ports.py`: the 8 ports of n0035 plugged in 200 s, saved as `Smoke_ports.spj`, 8 of
8 read back as wanted; 81 s for 8 ports in the 17:57 build after the grid rectangle was cached and the texts
read through win32).
**ET200SP potential groups** (user 2026-10-23 evening: "first module and first output module of the IM155-6 nodes
should have the parameter PotentialGroup" = `Enable new potential group (light BaseUnit)`): PL5 writes it into
the module row's Parameters cell as `potential_group=Enable new potential group (light BaseUnit)` for the first
module and the first output module (a card is an output module by its signals' addresses, `Q.` and no `I.`,
else by its order-number family 6ES7132 / 6ES7135); the Parameters cell is `name=value | ...` where a numeric
name is the index within the module's first record and `potential_group` the module's LAST parameter row - the
one parameter of the `Potential group` record that closes every ET200SP module's parameter grid.
`SyconDriver.set_module_parameters(station, slot, [(name, value)])` opens the module's submodule, Dataset =
Parameter, wheels the grid to its end, finds the last text row by its pixels (`param_rows_y`, alignment-free)
and chooses the combo item (`set_param_at_y`, the value read back from the re-opened editor); `verify` reads the
submodule's record 243 (first byte 01 = a new group). LOWER SORTER: 12 rows on the 6 ET200SP.

**Stations timing** (user: "station timiming 8ms for all nodes"; then "nodes that acquire: control zones, check
position photocells of sorter; load accuracy, check position, synchronism on induction lines -> Station Timing
= 2ms"; then the recentering sensors, "DISTANCE SENSOR / LEFT SIDE RECENTERING 2, PHOTOCELL / BETWEEN CELLS
RECENTERING 2 -> 2ms"): `hw/sycon-stations` carries an Update Time (ms) column - PL5 writes 8 for every slave
(`--update-time-ms`) and 2 for a station whose signal descriptions mention one of `FAST_SIGNAL_KEYWORDS`
(control zone, check position, load accuracy, synchronism, recentering; the station's Comment says which).
The consumer runs one pass of the controller's Stations Timing page after the rename pass
(`ControllerDialog.set_stations_timing`: the station picked in the 'Name of station' combo 220, the updating
time chosen in combo 223, the watchdog Edit 224 follows at 3x - verified 18:23, 4 stations at 8 / 24 ms), and
the read-back decodes each slave's `sendClockFactor x 31.25 us x reductionRatio` from the controller's
`SlaveDTMsGetParameters/DTMProxy<n>` text (the default was 16 ms / watchdog 48 ms). `ConfigDialog.combo(cid)`
takes the VISIBLE combo only: every page of a dialog is instantiated at once and the ids repeat across pages
(220 is also a port-speed combo of another page - the first pass picked that one, 18:22).

**SCALANCE switches** (user 2026-10-23: "let's also add the scalance switches, with the following parameters" -
the XC206-2 dialog's PN-IO Parameter dataset): policy `scalance-pnio` in the device-types database
(6GK5216-4BS00-2AC2 = `SCALANCE XC216-4C V4.4`; the folder's V4.4 DAPs live in three hand-modified `_MOD_`
XC200 GSDMLs - user: "no modified gsdml files, just the official ones", the latest official SCALANCE XC-200
file to be downloaded and named in the database, the catalog item following its newest DAP; the GSDML cell
stays empty until then). PL5 writes ONE row for the device's own
PN-IO submodule (Slot 0, Subslot 32768, Module Text PN-IO): never plugged (a Slot-0 row is the DAP's), its
Parameters `2=Off | 4=Off` (Loop Detection `Interface Mode` and Port Mirroring `Mirroring Mode`, parameter grid
rows 3 and 5 - the GSDML defaults are `Local configuration` = 255; `Not by STEP7` Off, Monitor Barrier Off,
Monitor Port 1 are the defaults) plus `record:<index>=<hex>` entries, the verification-only form: the saved
records 3 / 12309 / 12312 (`00 03 00 06 01 00 00 00 00 00`, `30 19 00 08 01 01 00 01 01 00 00 02`, `30 1C 00
08 01 01 00 00 00 01 00 00` - the dialog shows the bytes in decimal) compared by `verify`. The driver reaches
the PN-IO as the DAP's second submodule row (`set_module_parameters(..., subslot=32768)`). Not yet run on the
VM (the user's SYCON.net was open); LOWER SORTER: 5 switches (n0010, n0015, n0040, n0070, n0100).
**Combo ports and SFPs** (the I/O Lists say nothing; the cabinet drawings' parts lists do - `8FVT_Q0012` p.73:
`6GK5991-1AD00-8GA0` x4 for the XC216-4C -K26501; `8FVT_P1001` p.94: x1 for its XC216-4C -K26501-AE01 and
`6GK5991-1AD00-8AA0` for the XC206-2SFP -K28001; the SUM_BOM workbooks list the switches and C-PLUGs only):
the transceiver is always the SFP991-1 (100 Mbit/s multimode, LC). In the official XC-200 GSDML
(`GSDML-V2.45-Siemens-002A-SCALANCE_XC200-20260302.xml`, the user's download) the XC216-4C's combo ports 1-4
are PLUGGABLE port submodules (subslots 32769-32772): `RJ45 1 GBit`, `SFP 991-1 A`, `SFP 991-1 LD A`,
`SFP 992-1`, ... - the project must say which; the XC208's 8 ports are fixed, the XC206-2 SFP's ports 7-8 are
pluggable like the combo ports. User: "Configure all four combo ports of every XC216-4C as SFP 991-1 A" - PL5
writes one row per such port (Slot 0, Subslot 32768 + port, Module Id the SFP's order number, Module Text
`SFP 991-1 A`; `SCALANCE_COMBO_PORTS`), the consumer's `set_dap_submodules` chooses them, `verify` compares.
**Probed 21:10** (`scripts/probe_switch.py`, a new project, the switch dragged from the single catalog entry of
the official 2026 file - SYCON.net 1.500 takes that V2.45 GSDML): the DAP row expanded lists its submodules in
subslot order - row 2 the device, row 3 `PN-IO` (32768), rows 4-7 the combo ports (default `RJ45 1 GBit`, the
in-place combo 1904 offering the 16 port submodules), rows 8-19 the fixed ports 5-16; the PN-IO row enables the
Dataset combo and its Parameter grid shows 8 rows at 16 px (record, Not by STEP7, record, Interface Mode,
record, Mirroring Mode, Monitor Barrier, Monitor Port). The SUM_BOM workbooks name the switches and their
C-PLUGs only; the SFPs are in the cabinet drawings' parts lists (pypdf, `scratchpad/pdf_sfp.py`).

**The four FVT test projects** (user 2026-10-23 evening, going to dinner: "do a sycon project for us to test
for each machine type: 1 sorter, 1 induction lines, 1 upstream, 1 chutes (1 card only); vitronic i will provide
later"): `scripts/build_fvt_tests.sh` exports and builds, in sequence, `FVT_Sorter_Lower` (IO0010),
`FVT_Induction_LowerGR1` (IO0011), `FVT_Upstream_ConveyorsLower` (IO0013) and `FVT_Chutes_Card1` (IO0030,
sheet R5.S1.C1 only - the list has one cabinet sheet per cifX card, `--sheet`) into `spike/scratch/`; the models
without a GSDML yet (KEBA, NORD, SEW, Interroll, Inovance, Vitronic, Balluff) are skipped with the exporter's
`sycon_model_not_in_dtd` WARN. Summary in `spike/scratch/dinner_builds.log`.
Results (2026-10-24 morning, all four verified by read-back, `<name>.verification.txt`): Sorter_Lower 60 stations
(3 PN/PN couplers, 6 ET200SP with their modules and potential groups, 26 ServoOne Junior, 19 AL1202 with 8 ports
each, 5 SCALANCE XC216-4C with 4 SFP ports and the PN-IO parameters, 1 Anybus) 601 PASS / 0 FAIL, 27 notes (the
order-number patterns below); Induction_LowerGR1 107 PASS / 0 FAIL (565 s); Upstream_ConveyorsLower, the first
network (192.168.2.x) of the two the list holds, 23 stations, 265 PASS / 0 FAIL (2283 s); Chutes_Card1 528 PASS /
0 FAIL (~48 min with the load). What the sorter's 60 stations taught the driver: the Device Table / IP Address
Table passes visit the table's LAST row - at the end of the scroll its centre sits inside the 10 px bottom margin
(a 3 px margin there, the click capped: `sweep(at_end)`); the IP cell's in-place editor is opened with up to
three clicks (`_open_ip_editor` - one verify click of 120 opened none in 0.8 s and the whole pass was lost); a
failure in the IP pass keeps the names and the IPs written so far (Cancel + Yes; `ControllerDialog.phase`) and
a resume re-addresses the named stations whose saved IP is not the table's, a failed names pass is still
checkpointed; the verification notes, instead of failing, a DAP whose GSDML order number is a pattern or a
placeholder (`13xx.xx7x.xxxx.x` the LTi ServoOne Junior, `T_ID_DAP_DESCRIPTION` the Anybus Communicator:
`order_is_pattern`). `scripts/verify_saved.py --handoff <folder> --out <project.spj>` re-runs the verification
of a saved project without SYCON.net (the module texts judged by order number, the table's updating times).

**PL5 project types for the hardware alone** (user 2026-10-24: "generic hardware (Siemens Tia Portal), generic
hardware (Hilscher Sycon.Net) (only validation + hardware generation enabled)"): PL5 now offers, beside the
safety system, `siemens_tia_generic_hw` and `hilscher_syconnet_generic_hw` (`pipeline5/systems/generic_hw.py`,
registered in `systems/catalog.py`) - phases 0 / 100 / 700 only; 100 runs the 110 I/O List checks alone, 700
writes the TIA tables (hw/stations, hw/modules) or this handoff (hw/sycon-*, into `<output>/SyconNetProjectInterface/`,
params `sycon_device_types_db` / `sycon_update_time_ms`). The column map's `mandatory_in` names the project types
a column must be filled for on a node row (Part No., PROFINET name, IP for both) - a 110 FAIL `mandatory_missing`
otherwise; a PROFINET name used twice is a 110 FAIL `pname_duplicated`. Contract C-043.

**Maximized dialogs, geometry** (user: "you could maximize the configuration windows ... some systems may
have 100+ nodes"): every configuration dialog is maximized when it opens (`ConfigDialog.maximize`, SW_MAXIMIZE)
so the grids show dozens of rows; the custom grids' columns scale with the width, so the column offsets
measured on the control maps are scaled by the grid's width (`DeviceDialog.sx` from 571, `psx` for the
parameter grid from 561, `ControllerDialog.cx` from 661); the row heights stay 16 px. The Modules grid's
first column does not scale: a row's expand box sits at x 11-20 and is READ from its pixels (`_glyph_columns`:
the '+' / '-' strokes - the box border is black on the current row and light elsewhere, 18:56), so
`row_expanded`, `has_glyph` (a submodule row has no box), `collapse_all` (SYCON.net reopens a dialog with the
rows expanded as they were left: slot n is on row 1 + n only when none is) and `ensure_expanded` are exact
and a double-click (a toggle) is never blind. The parameter grid's Value column is not proportional to its
width either: `open_param_editor_at` tries a few fractions of the width and keeps the one that opens an editor.
`fit()` (resize the dialog back to the control maps' size) stays as a tool but is not used.

**Smoke 4 stations** (17:47-17:57, `spike/references/LowerSorter/smoke4_*`): controller, coupler [DAP X2 V4.2],
ET200SP with 7 modules, AL1202 + its clone with 8 ports each - 598 s, 48 PASS, 1 FAIL (the ET200SP GSDML path,
see "one file per device identity" above). Per station: a catalog add ~25 s, a clone 12 s, the rename / IP pass
~1 min for 4, 7 modules 58 s, 8 ports 81 s. The module pass of the 17:21 / 17:36 builds was refused ("Slot [1]
contains a module without submoduls") - the recovery now selects the row of each slot the error names before
`Add Submodule` (pressed with another row current it answers "No possible submodule found"), and the module
combo is never re-opened on a row where it is already open (`_open_combo_on`); the 17:57 build needed neither. The Modules grid, probed with `scripts/probe_submodules.py` (17:05): the AL1202's
`8 Ports` row (row 2) shows its `IO-Link Master` sub row from the start (`is_expanded` counts the text bands
against `Use of slots`, so `expand_row` is only double-clicked when needed); `Add Submodule` with the module row
selected appends a row at the END with the next subslot assigned by SYCON.net (2, 3, ... - its Sub Slot cell opens
no editor, so the table's subslots must be exactly 2..9) and the GSDML's first submodule preselected (`IO-Link
In/Out 32/32 Byte + PQI`; the `State of data length` text changes - the proof the press worked, pressed again when
an in-place editor swallowed it); its Submodule cell (x+150) opens the in-place ComboBox 1904 with the 22 port
submodules, texts verbatim the Fives tool's. The grid shows 8 rows: before every press the grid is wheeled to the
top (the module row at its place), after it to the end, and the new row is the last text band.

## The production folder (2026-10-24 afternoon)

User: "each hilscher card gets its own, separate project", "name the projects as HilscherPnCard_n", "use
`Z:\Work\0 Commesse\FVZ_Intermarche\3 Software\9_Backup\20261020_1731\FVZ_MSC_20261020_1731\PRODUCTION` as the folder
structure reference, so the output can be easily pasted in the folder". The reference holds, per cifX card,
`HilscherIOCard1\HilscherPNCard1.spj` (+ `HilscherPNCard1\_S129\SYCON_net.xml`, the card's `HilscherIO.xml` process-data
export, a pre-configured coupler GSDML, `nWid\` firmware batches, `_FakeIO.*`) and `IODriver\BusField.csv` for all the
cards. What we produce, `scripts/build_production.sh "<list.xlsx>" "<out>"` (`RESUME=1` to resume, `EXPORT_ONLY=1`
for the handoff alone):

```
<out>/                                  = PRODUCTION
  HilscherIOCard1/
    SyconNetProjectInterface/           the PL5 handoff of card 1 (hw/sycon-* tables + the device-types database)
    HilscherPnCard_1.spj + HilscherPnCard_1/   the SYCON.net project of card 1, built by the driver
    HilscherPnCard_1.verification.txt   the read-back verification
    build.log
    HilscherIO.xml                      the process-data export (the IO driver's input)
    nWid/config.nxd + UpdateCardV5.bat  the configuration export and the card-update batch (Shared/HardwareConfigBuilderData/nWid)
  HilscherIOCard2/ ...                  one per card (one per PROFINET network of the list)
  IODriver/BusField.csv                 every card's nodes
    _PL_Logs/                           build[_resume].log, HilscherPnCard_<n>.verification.txt (user: "keep the
                                        _logs folder in the card folder. also, name it _PL_Logs")
  _PL_Logs/                             export.log, build.log (the list)
```

`UpdateCardV5.bat` is the FVZ reference's `UpdateCardV4.bat` with one change, hence V5 (user 2026-10-25: "this is V5 now
since it was edited. The header should follow PL5 format (hand maintained script)" - the `#!openn` header in the
batch's own comment syntax, each directive line prefixed `::`, kind `tool/nwid-update-card`): the card chosen - the serial number
that names its folder under `C:\Program Files\cifX Device Driver
80100_*` - is remembered in `card.txt` beside
the batch; a later run reports the remembered card and uses it when present, else the normal workflow (none /
one / several to choose from) runs and remembers the choice. `CIFX_DRIVER_PATH` overrides the driver folder;
`tests/test_update_card_bat.py` runs it three times against a fake one. The batch copies `config.nxd` AND
`nwid.nxd` (renamed from `config_nwid.nxd`) into the card's `Channel0`. The DBM/nxd export writes TWO files
(user: "the sycon export DBM/NXD function exports 2 files. i name them config or c, one has to be renamed"):
`config.nxd` and `config_nwid.nxd`; the verification checks both are there after the export.

**One project per card** — PL5's `sycon_handoff.cards_of` lists the cifX cards of the list: one per PROFINET
network in document order (the redundant second card on a network is not a card); `build(rows, dtd, card=n)` keeps
card n's controller and the stations on its network (the others are INFO findings `sycon_second_controller` "card
m's controller" / `sycon_other_network` "card m's project"); `project()` writes every card into
`HilscherIOCard<n>/SyconNetProjectInterface/` (`--card n` for one). The driver builds `HilscherPnCard_<n>.spj` beside
it. A saved project can be RENAMED by renaming its `.spj` and its folder together (the sorter's `Sorter_Lower.spj`
copied as `HilscherPnCard_1.spj` + `HilscherPnCard_1\` opened and resumed on 2026-10-24 17:07).

**Symbolic names and canvas positions** (`sycon5/canvas.py`; user: "i edited the sorter lower project in
`FVT_Sorter_Lower - Modified Canvas Positions`, we need to replicate positioning rules and symbolic name edits.
maybe this can be done on the .xml"): the two projects' XMLs diffed device by device gave the rules. The symbolic
name (the label before `[type]<station>`) follows the device type, now a column of the device-types database
(`Symbolic Name`: `fld` = functional unit + the location's first segment, `=TRIB-AEP01`, for ET200SP and SCALANCE;
`variable` = the description's variable part, `SORTER (=TRIB) / INDUCTION LINES GR1 (=TRIB-AEC01)`, for a coupler;
`description` = the Description Module, `ANTENNA CELL TEST`, for an Anybus; `default` for drives, AL1202 and the
controller) - and, since the user's edit of 2026-10-25 (`088_=TRIB-CA01`, `087`), the label is `nnn[_Custom
Description]`: nnn the node number (the IP's last octet, three digits), then `_` and the rule's text when it gives
one (`sycon_handoff.symbolic_name`; the controller keeps SYCON.net's). PL5 writes it into the stations table
(`Symbolic Name` column, with `FLD`), and the canvas: the
controller top-left, rows per group (ET200SP, couplers, gateways, IO-Link masters, switches, drives) in FLD order
(user: "the canvas rows should sort by FLD"; the project's own order is by PROFINET name), each row a stair of up to 8 (70 px right - 90 for the 70 px wide switch and gateway boxes, user 2026-10-25: "a few pixels further apart horizontally so the text does not get covered" - and 22 px down), the next row of a group 200 px lower,
the next group below. The bus is VERTICAL (the user's second edit, 2026-10-25 08:59, `PROD_Sorter_Lower_fresh -
Modified added vertical busline`, an XML edit: a Device-less `<BusLine>` at x 8..12 from y 72 down past the last
device as the channel's last BusLine, the channel's own line a stub from x 8 to the controller's left edge, every
device's drop line a horizontal branch from x 8 to its left edge at its vertical centre; SYCON.net keeps a gateway's
box 40 x 70 like a switch's). Written into `SYCON_net.xml` with the project CLOSED (`canvas.apply`: the `syc:symbolicName`
attribute and the device's `PositionRect` + its BusLine's drop line, edited in place by regex - no
re-serialisation), after the last save of the build; read back (`Device.symbolic`, `rect`, `line_rect`) and
verified. Dry run on a copy of the sorter: 60 of 61 labels equal to the user's (the 61st was the location's full
tag, since shortened to its first segment as the user did).

**BusField.csv** (`scripts/busfield.py --production <out>`): the IO driver's node table, the reference's columns
(`#;Board Number;Physical Node Address;Node Type;...;# Description`), one row per node of every card: Board Number
= the card, Physical Node Address = the IP's last octet, Node Type = `0x<VendorID><DeviceID>` of the device's GSDML
identity as the saved project records it (`fdt:manufacturerId` / `fdt:deviceTypeId` on the Device element, decimal:
the ET200SP 42 / 787 = 0x002A0313, the cifX master 286 / 515 = 0x011E0203, the PN/PN coupler 0x002A0604, the
SCALANCE 0x002A0A0B, the AL1202 0x0136AC55, the ServoOne 0x017C4E21, the Anybus Communicator 0x010C0020 - user:
"Node Type eg 0x011E0203 is 0xVendorIDDeviceID", the GSDML Viewer's DeviceIdentity), the description `[station]
DESCRIPTION (MANUFACTURER) FLD (ip)`. `@` = the node is in the configuration; `#` = commented out: the master's
own station under the master row (user 2026-10-25: the FVZ reference's `#` switches were switches not in that
configuration - ours are configured, so they are `@`); a station missing from the project gets `#` and
0x00000000. The file opens with the PL5 `#!openn` header in csv form (kind `hw/iodriver-busfield`; the IO driver
reads `#` lines as comments).

**The Anybus Communicators and the couplers' modules** (device-types database, policy `fixed` + the `Fixed Modules`
column): the cell test antenna's ABC3013-A plugs `IN 0016` + `OUT 0012` (user's screenshot 2026-10-24), the
Vitronic camera system's PROFINET controller is an HMS Anybus Communicator with `IN 0064` + `OUT 0064` - its I/O
List head has no Part No., so the database row `VITRONIC` is keyed by the head's Manufacturer (`head_model`, INFO
`sycon_model_by_manufacturer`); a PN/PN coupler plugs `*OUT 128 Byte` + `*IN 128 Byte` on its X2 side and the mirror
on X1 (user: "couplers have no defined I/O modules, let's default to 128Byte IN + OUT; X1 will need to have the
module positions mirrored") - the Fixed Modules column holds one list per connector (`X2: ... ; X1: ...`), the
head row's Connector column picks it (a connector without a list: WARN `sycon_connector_unknown`). The database's
column 9, `DAP Parameters` (2026-10-25), sets the device's own submodule (slot 0, subslot 1) through its Parameter
dataset like a module's: the coupler's `4=0 | record:1=00 0C 00 02 00 00` - user: "on the PNPN couplers: Diagnostics
data validity = 0", the 5th bit parameter of the General head parameters record (GSDML DDV, byte 1 bit 1, default
1), the record's bytes `00 0C 00 02 00 00` afterwards the read-back oracle (`00 0E ...` before). A built project
takes a database change of this column without a full build: `scripts/apply_dap_params.py --handoff <folder>
--out <project.spj>` (one device dialog per station with DAP rows, save, read back).

## Recording the user's actions, and the exports they taught (2026-10-24 evening)

User: "we need to log the ui interactions. a few sycon functions that change and export data" - the process-data
export among them. `scripts/ui_recorder.py --out spike\scratch
ecordings\<name> [--minutes 30]` records the
desktop while the user works (no hook library in the venv: the mouse buttons and every virtual key are polled at
15 ms through GetAsyncKeyState's "pressed since the last check" flag): one line per click with the control under
the cursor and its parent chain through UI Automation (a MenuItem in its Menu, a Button in its named dialog, the
dialog's Edit / ComboBox / CheckBox values when a button is pressed), the keys typed and, when the typing pauses,
the focused field and its value, every top-level window opening or closing, and a PNG of the active window after
each click (pure-Python PNG, zlib). It stops on a `STOP` file in the folder, the time limit, or Ctrl+Alt+Q. One
thing a log cannot name is the entry of a menu that closed under the click; `scripts/probe_context_menu.py` reads
such menus afterwards (the controller node's context menu and every nested level - a hover opens no submenu
there, the item's own `click_input` does).

The first recording (`spike/scratch/recordings/process_data_export`, 96 events, 34 screenshots, 2026-10-24 19:11)
gave four functions, now in the driver and at the end of every build (`consumer.build` step 4):

1. **Auto addressing** - controller Configuration > Address Table > the `Auto addressing` check box (id 201) >
   Warning "Enabling Auto Addressing causes all manually edited addresses to be lost. Proceed anyway?" > Yes >
   Apply > OK (`ControllerDialog.set_auto_addressing`, idempotent: the box's state is read first).
2. **Process-data export** - right-click the controller > Additional Functions > Export > `XML...` > Save As (XML
   Files) > `<project folder>\HilscherIO.xml` (the IO driver's input; SYCON.net: "XML export of process data
   succeeded with device ..."). `sycon5/exports.py`: the popup menus found at the Win32 level (class #32768) and
   their items clicked through UI Automation, the Win32 Save As driven by its File name edit (id 1148) and Save
   (id 1), a `Confirm Save As` answered Yes, the file's rewrite awaited; `process_data_devices` reads the export
   back (`ProcessData/Controller/Channel/Device` display names `label[type]<station>`) and the verification checks
   every station of the table is listed.
3. **Configuration export** - the same menu > `DBM/nxd...` > `<project folder>
Wid\config.nxd` ("Export of
   DBM/nxd database succeeded") - two files come out, `config.nxd` and `config_nwid.nxd`.
4. **Save** - the toolbar's Save.

The Additional Functions submenu, for the record: Offline Compare..., Online Compare..., Setpoint Value...,
Service > (Start Communication, Stop Communication), License, Export > (CSV..., DBM/nxd..., XML...), Print >
(Configuration). The Controller Settings page the user showed: start of bus communication automatically by
device, watchdog 1000 ms, process image big endian, module alignment byte boundaries, ports AUTO.

Run on the sorter (2026-10-24 19:40-20:03, the desktop left alone, 1387 s): the resume re-confirmed the ET200SP
parameters and the ports, found Auto addressing already on, exported HilscherIO.xml (657 KB, UTF-16, every one of
the 62 stations listed) and nWid/config.nxd + config_nwid.nxd, shipped the card-update batch, wrote 17 symbolic names
and 63 positions, regenerated BusField.csv (the Vitronic and cell-test nodes 0x010C0020): verification 775 PASS /
0 FAIL, 29 notes (`spike/references/FVT_tests/HilscherPnCard_1.verification.txt`; the recording's log in
`spike/references/recordings/process_data_export/events.log`).

The same folder built FROM SCRATCH (2026-10-25 00:13-01:23, `PROD_Sorter_Lower_fresh`, 4161 s + the 28 min of the first
attempt): 775 PASS / 0 FAIL (`HilscherPnCard_1_fresh.verification.txt`). The project holds its 62 devices grouped by
type, each type once, the names in natural order within a type (3 Anybus, 6 ET200SP, 3 couplers, 5 switches, 26
ServoOne, 19 AL1202 - the clones added twelve at a time); the IP Address Table scan put the 62 stations at rows
0..61 and one pass addressed them all. The first attempt died in the names pass on the resync anchor: after a
scroll the pass looked for the last row by the name it had just REPLACED - it now uses the name the row shows.

## Faster, same output (2026-10-25, the user's four observations)

User: "now, we can reduce the time without impacting the output" - four observations on the 89-minute fresh build of
the sorter (22 min adding 62 stations, 5 names, 2 + 4 IPs, 2 timing, 52 module dialogs, 2 exports):

1. **Cloning by doubling** - "i usually double the existing stations (1->2->4->8->...) by selecting and copy-pasting
   more than one station at a time". The netProject tree extends its selection with Shift+Down from the keyboard
   (not with Shift+click or Ctrl+click: `scripts/probe_multiselect_clone.py` found those select one node; the user's
   way recorded in `spike/references/recordings/clone_multiselect_events.log`). `SyconDriver.clone_station(source,
   count, after_batch)`: the first clone from the source, then the clones made so far - contiguous at the end of the
   tree - selected from the first one with Shift+Down, Ctrl+C, a click on the source, Ctrl+V: 1, 2, 4, 8 ..., the last
   batch the remainder, a checkpoint every 8 or so. The 25 drive clones in 97 s (six pastes), the 18 AL1202 in 111 s.
2. **"The profinet name assignment was done twice"** - the first fresh build's names pass died after 47 rows (the resync
   anchor) and, all-or-nothing, the resume named all 62 again. A failed pass now keeps what it wrote (Cancel, the
   data kept); a resume pairs only the still auto-named nodes, in the order the pass renames. The per-row read-back
   of every name stays (user: "readback is important").
3. **No IP table scan** - "a remaining from when the addresses were being set to 200+": the IP pass orders the rows from
   the IPs it knows (a resumed station's saved IP; a new station's auto-assigned one = the next free address at its
   add, ascending in Device Table order), reads two sentinel rows before writing, checks every row's current IP as it
   writes, and keeps the full scan as the fallback when a sentinel disagrees.
4. **Type-common setup before cloning** - "stations that share parameters or number of modules/submodules may be set
   up before cloning (eg: on the AL1202 all the 8 submodules could be created with default values on first station,
   then the final run would only set the specific types)". The stations are added by type and, within a type, by
   MODEL; the first station of each model is configured with what all its stations share before it is cloned (the
   couplers' two modules and head parameter, the switches' SFP ports and PN-IO parameters, each Anybus model's two
   modules, the AL1202's eight ports with that station's types - `consumer.clone_safe`: every station of the model
   has the head's structure; the ET200SPs differ in their cards and stay per station); step 3 reads the saved
   project ONCE and opens a dialog only for what is missing or differs: a clone's port whose type differs is re-typed
   in place (`SyconDriver.set_submodules`, no Add Submodule), a parameter only when its record oracle is not met
   (`consumer.params_satisfied`: the potential group's record 243, the `record:<idx>` entries), modules already there
   are left alone. `tests/test_build_plan.py` pins the planning against fake read-backs.

The timed fresh build with all four (`PROD_Sorter_Lower_fast`, 10:57-11:55): 823 PASS / 0 FAIL in 3446 s - 57
minutes against 89 - the same project order (the types once each, the names natural within each), 41 device dialogs
instead of 56 (the 12 AL1202 re-typings in ~30 s each instead of 8 Add Submodules in ~80 s; the switches, couplers
and Anybus skipped by the read-back). What is left: the six ET200SPs (two dialogs each, ~15 min) and the two
controller passes (names ~5 min, IPs ~6 min).

## Cloning in the XML: no (probed 2026-10-25 23:00)

User: "we can maybe go even further by adding one station per type, saving and closing sycon; doing the cloning +
other parameters assignment (i see profinet name) in the .xml". What the saved project says (`scripts/probe_xml_clone.py`,
its log in `spike/references/recordings/probe_xml_clone.log`): a station's DTM blob is an OLE compound document (a
4-byte length, then `d0cf11e0...`; `olefile` reads it, pywin32's structured storage could rewrite its streams) and two
identical drives differ in 168 of 13 828 bytes only - the name of station (three UTF-16 occurrences), the IP, one
GUID in `DeviceType` and a repeated 3-byte value - so copying the element and patching those is mechanical. But the
CONTROLLER's blob (2.5 MB, 2985 streams for 62 stations) holds, per child, a `SlaveDTMsGetParameters/DTMProxyNNN`
stream of 17-23 KB and a `pn:DeviceList` entry (name, IP, mask) with the child's GUID, and SYCON.net does NOT rebuild
them from the device elements: a station cloned in the XML of a throwaway project (the name, IP and GUIDs patched,
the controller untouched) shows in the netProject tree, but the controller's Device Table keeps its two rows, an OK
on the controller dialog changes nothing, the project saves as unmodified, the blob keeps its two proxies. A clone
made in the file is a device without a controller - not addressed, not in the process-data export. Making it one
would mean fabricating the DTM's own proxy stream and list entry per clone, with no oracle short of a card: not done.
The names and IPs alone would be rewritable (the device blob and the controller's DeviceList, by structured storage)
but the GUI pass writes both consistently in ~11 minutes per 62 stations - not worth the risk either.

Learnt the hard way the same evening: `SyconDriver.open` used to ATTACH to a SYCON.net already running - the first probe
run attached to the user's own instance (the fast sorter project open in it), opened and cancelled the controller
dialog there and closed it (the files were untouched: nothing was saved). A running instance is the user's: `open`
now refuses it unless `open(attach=True)` says so on purpose.

## The users' GUI (2026-10-25 evening)

User: "sycon5app needs a basic gui for the users. buttons to retrieve the workspace data and a log viewer." One tkinter
window, PL5's dark palette (`Pipeline5App/pipeline5/workbench/theme.py`) so the two apps look alike:

```
C:\Source\Repos\_Openn5\.venv\Scripts\python.exe launch_gui.py [<PRODUCTION folder>]
```

A double-click on `launch_gui.py` works too: started with any other Python the launcher re-launches itself with the
repo venv (user 2026-10-25: "launch_gui.py opens nothing" — the system Python had no pywinauto and the console closed
on the traceback; now `sycon5/__init__.py` loads the driver lazily, the GUI needs no pywinauto, the steps always run
with the venv's python, and a startup error is shown in a message box).

- `sycon5/workspace.py` — **the workspace data, no tkinter**: `scan(root)` reads a PRODUCTION folder as PL5 writes it
  (`HilscherIOCard<n>/SyconNetProjectInterface/` per card) and Sycon5App fills it: per card the handoff's `#!openn`
  header (generated, source), its station / module rows and controller, the project (`HilscherPnCard_<n>.spj`, saved
  time), the verification report (`_PL_Logs/<name>.verification.txt`: PASS / FAIL / NOTE counts), the four exports
  (`HilscherIO.xml`, `nWid/config.nxd`, `nWid/config_nwid.nxd`, `nWid/UpdateCardV5.bat`), the card's `_PL_Logs` files;
  the root's `IODriver/BusField.csv` and `_PL_Logs`. `Card.status()` says what the card still needs (`no handoff`,
  `not built`, `built, not verified`, `1 FAIL`, `verified before the last save`, `exports 3/4`) or `complete`. The
  `*_command` builders give the command lines of the steps — the same scripts `scripts/build_production.sh` runs,
  the same `_PL_Logs` files — for the GUI's runner; `note_summary` appends the bash script's time-stamped lines to
  the root `_PL_Logs/build.log`. `level_of(line)` colours a log line (PASS / FAIL / NOTE of a report, the verdicts
  RSLT, tracebacks ERRR, warnings, INFO). Tests: `tests/test_workspace.py` on a fake production folder.
- `sycon5/gui.py` — **the window**: the workspace row (`Open...` remembers the last folder in
  `%APPDATA%\Sycon5App\gui.json`, `Reload`, `Explorer`, `I/O List > handoff...` = PL5's `sycon_handoff` into the
  workspace); the cards table (green = built, verified after the save, 0 FAIL, exports 4/4; red = a FAIL or a
  handoff problem; yellow = something to do; double-click opens the card folder); the step buttons of the selected
  card — `Build card` (`build_from_handoff.py`, SYCON.net driven), `Resume build` (`--resume`), `Verify card`
  (`verify_saved.py`: the saved project against its handoff without SYCON.net — it REWRITES the report with fewer
  checks, the module texts chosen in the GUI and the device-limited update times are not known any more), `Card
  folder`; `Build all cards + BusField` (every card with a handoff, then `busfield.py`), `BusField`, `Stop`; the log
  viewer: `run output` (the running step live) or any log / report of the workspace from the dropdown, re-read with
  `Reload`, PASS / NOTE / INFO hideable (`Show`), `Follow` keeps the end in view.
- **A step is a subprocess**, never run in the GUI's process: SYCON.net is driven from the script, and while it runs
  the desktop must be left alone — the yellow banner says so and the buttons are disabled until it ends. The
  output streams into the viewer and into the step's log file (`build.log` / `build_resume.log` / `verify.log` in
  the card's `_PL_Logs`, `export.log` / `busfield.log` in the root's), the table reloads after every step.
- **Stop**: the step is sent a CTRL_BREAK (`build_from_handoff.py` turns it into a KeyboardInterrupt, its `finally`
  closes SYCON.net without saving); a terminate follows after 120 s, or at once when the signal cannot arrive —
  probed 2026-10-25: it reaches a child of a console parent (`python.exe launch_gui.py`), never one spawned
  without a console (`pythonw.exe`: the child gets its own hidden console). So launch with `python.exe`; after a
  terminate, close SYCON.net by hand without saving.
- Tests: `tests/test_gui.py` (the window withdrawn, a fake workspace): the table, the buttons' enabling, the viewer's
  levels and filter, a real step through the runner and its log file, a batch, a stop. Tried on the VM on
  `spike/scratch/PROD_Sorter_Lower_fast`: `Verify card` ran `verify_saved.py` (758 PASS, 0 FAIL — the saved-project
  subset of the build's 823), streamed and coloured, the table refreshed.

## The Zen contract (2026-10-25 night)

User: "we did not use the zen contract for the sycon5app, I'm afraid. Is it too late to implement it?" then
"implement the zen method to align with the repo rules". Sycon5App now follows `.zen/contract.md` the way PL5 does:

- **The clauses.** P-019 (the delta the app lived under since 2026-10-23) is promoted into three `C-` clauses,
  each with its oracle: **C-046** the driver, its read-back oracle and the structure laws; **C-047** the PL5
  handoff built into a project and verified by read-back (the FVT numbers); **C-048** the user's functions
  recorded and replayed (auto addressing, the two exports). C-043 (the generic-hardware types), C-044 (the
  production folder, the canvas, BusField, the speed-ups) and C-045 (the users' GUI) were already clauses. The
  scope line of the contract names Sycon5App.
- **The oracle scripts.** `scripts/verify_c046.sh`, `verify_c047.sh`, `verify_c048.sh` - exit code = verdict, run
  from Git Bash with the repo venv (`PY=` overrides the interpreter). They run the automated oracles only: the
  driver itself is verified on the VM by the FVT builds, whose reports are kept under
  `spike/references/FVT_tests/`.
- **The recorded runs.** `scripts/zen_record.py --clause C-046 -- bash Sycon5App/scripts/verify_c046.sh` runs
  the oracle and writes `.zen/evidence/runs/C-046.json` in the repo's shape (the command, its exit code, the
  sha256 and tail of its output, the commit, the test files with their sha256). The repo had no in-tree
  recorder; this one is generic (any clause, any command).
- **The evidence notes.** `.zen/evidence/C-046.md` (the oracle, the laws and what taught them, the P-019 log as
  it stood when promoted), `C-047.md` (the builds' table, the timed fast build, the XML-clone probe declined, the
  table rules), `C-048.md` (the recordings, the replays, the fixture).
- **The structure laws** (`tests/test_architecture_contracts.py`, the shape of PL5's): L1 one dependency
  direction (`log < handoff, readback < canvas, workspace < session, drawing < catalog, dialog, exports <
  controller, device < driver < consumer < gui`); L2 the oracle apart (`readback`, `handoff`, `log` import
  nothing of the package; the XML / folder side never imports pywinauto, pywin32 or comtypes, directly or through
  the package - `log` became its own module for this, re-exported by `session`); L3 the GUI sealed (tkinter only
  in `gui`, which imports `workspace` alone); L4 one facade (`Session`, `attach_if_running` and the dialogs only
  behind `driver`, `SyconDriver` constructed only by `consumer`); L5 the tests never drive SYCON.net. A ratchet
  (empty) quarantines known violations - adding an entry is an architecture decision.
- **Status.** The three clauses are `verified` (2026-10-26): the recorded runs under `.zen/evidence/runs/`, the
  refute round under `.zen/evidence/refutes/` - round 1 (`tests/test_refute_c046.py` .. `c048.py`) refuted all
  three and was fixed (a blob cut in half read as a device, the loader's gates, the bat's endless prompt - the
  evidence notes list every finding), round 2 held. `zen_record.py --refute held --round 2 -- <command>` records a
  round (the tests with the sha256 of the test names they define).
- **C-043, C-044, C-045 followed on 2026-10-26** (`verify_c043.sh` .. `verify_c045.sh`, the runs and refutes
  recorded): round 1 refuted all three - eleven gaps fixed, among them a controller IP that emptied the handoff
  as INFO, a `;` in a description shifting BusField's columns, a device without identity written as node type
  0x00000000, two card folders numbered alike, a report that is no verdict shown as "not verified" - round 2
  held; C-044's wording about `#` switches corrected to the user's rule. Every Sycon5App-related clause is
  `verified`; the evidence notes list every attack, what fell and what held.

## Couplers 4 x 128 bytes a side, the X1 entry, SCALANCE V4.3 (2026-10-26)

User: "scalance v4.3 instead of 4.4" (the VM's catalog: `SCALANCE XC216-4C V4.3`, firmware V4.3 [DAP 5C] of the same
`GSDML-V2.45-Siemens-002A-SCALANCE_XC200-20260302.xml`) and "pnpn couplers updated: added missing ones, added new
custom modules management: 4[*OUT 128 Byte] | 4[*IN 128 Byte] - 4 is a multiplier (4 modules of the [] type, which
is to be set verbatim); | is the separator".

- `Shared/HardwareConfigBuilderData/SyconDeviceTypesDatabase.csv`: the three switch rows name the catalog's V4.3
  entries; the coupler row's Fixed Modules are `X2: 4[*OUT 128 Byte] | 4[*IN 128 Byte]; X1: 4[*IN 128 Byte] |
  4[*OUT 128 Byte]` (512 bytes each way, slots 1-8) and its Catalog Item names one entry per side, `X2: PN/PN
  Coupler X2 [DAP X2 V4.2]; X1: PN/PN Coupler X1 [DAP X1 V4.2]` - the "missing one" read as the X1 side: an I/O
  List row whose Connector is X1 takes the catalog's X1 entry (the X1 DAP's name is by symmetry with X2, not yet
  dragged on the VM; the driver refuses an entry whose info pane does not cite the DAP, so a wrong name fails
  loudly). The older coupler generations (6ES7 158-3AD00 / -3AD01) are not rows: no FVT list names them.
- PL5 `sycon_handoff.module_items` expands `N[text]` (N >= 1, the text verbatim) in a plain or a per-connector
  Fixed Modules cell; `by_connector` reads the `X2: ...; X1: ...` form of either column; `catalog_item_for` picks
  the head row's entry by its Connector (none named: the first - X2 - with the WARN `sycon_connector_unknown`, as
  the modules do). The stations table carries the resolved item, so the consumer and its clone grouping
  (`type_key` holds the catalog item) see X1 and X2 couplers as two types. Tests:
  `Pipeline5App/tests/unit/test_sycon_fixed_multiplier.py`; the sorter list re-exported: its three couplers eight
  module rows each, the switches at V4.3.
- Not done on the VM yet: a build with eight coupler modules and the V4.3 switches - the next production build
  verifies them by read-back (the switch PN-IO records of the V4.3 DAP may differ: the verification says).

## Update mode and the controller's name of station (2026-10-26)

User: "is it possible to update an already existing sycon project, like OP5 did by skipping existing nodes with
matching pn name. also, no pn name was set for the controller".

- **The controller's name.** The controller dialog's `Controller Network Settings` page has a `Name of station`
  edit (control 211) beside the IP controls; `set_network` filled the IP, mask and gateway and never the name, so
  every project's controller stayed `controller` and the process-data export showed `<controller>` where the FVZ
  reference shows `<n0001-mc1-cc1-a1001>`. `ControllerDialog.set_network(ip, mask, gateway, name=...)` fills it
  (`SyconDriver.set_controller_network(..., name=)`); a fresh build names the controller as the table does. The
  read-back parses the controller's own stream (`CachedController/PNIOControllerDataModelBasic`: name, IP, mask)
  and `verify` checks the controller's name of station and IP; `verify_exports` checks the export's controller
  display name. The projects built before 2026-10-26 fail that check until updated.
- **Update mode** (`build_from_handoff.py --update`, `UPDATE=1 build_production.sh`, the GUI's `Update card`):
  OP5's rule - a station whose PROFINET name the project already has is skipped whole, never completed or
  compared (a NOTE each in the report); the project's other nodes are kept and noted; the new stations are added
  by type, cloned, named, addressed, configured and laid out by the rule on the canvas while every other box, the
  controller's and the user's hand-placed ones, stays where it is (the vertical bus still reaches the lowest
  device); the controller's name of station is set when it is still the default, else kept with a NOTE (its IP
  likewise); the exports and BusField run as always over the whole project. `--resume` keeps its own meaning (an
  interrupted build of the same handoff: the auto-named nodes paired and renamed, wrong IPs re-addressed).
- Tests: `tests/test_update_mode.py` (the checks, the NOTEs, the canvas of an update, the command and the
  button), `tests/test_readback.py` (the controller's stream). Not done on the VM yet: a fresh build (the name
  edit filled and read back) and an update of the fast sorter project with a station added to the list.

## The ServoOne's module, a station left without one, Davi1's fixes (2026-10-29/30)

User: "the servo one junior were missing their module on the sorter. Davi1 should have committed the update".

- **Why.** The ServoOne Junior's DAP (`DAP 2` of `GSDML-V2.3-LT-i-ServoOne-20130515.xml`) takes one module in slot 1
  and fixes none, so a catalog drop plugs nothing; its database row said `default`, the handoff had no module rows
  for it, and the verification - which compared only the modules the table names - had nothing to compare: the
  sorter's 26 ServoOne verified clean with their DAP alone.
- **Davi1's update** (f7f26fc, IO0011 LOWER GR1) sat on the branch `sycon/io0011-lower-gr1-fixes`, never merged; merged
  2026-10-30 with: the controller's `Name of station` edit looked up as a page control (`min_id=0` - the lookup's
  default skips ids below the in-place editors' 1900, so a fresh build on main stopped right after the controller)
  and read back case-insensitively (SYCON.net lower-cases names); the SCALANCE V4.3 DAPs' PN-IO grid (no record 3:
  `0=Off | 2=Off`, `scalance_pnio_params`); the KEBA D3-DU 330 row (its DAP fixes its module: `default` is right);
  the ServoOne's module text `PPO 3, 4 bytes IO` - in the Fixed Modules column while the policy stayed `default`,
  which never plugs it. The row's policy is `fixed` now: every ServoOne gets slot 1 `PPO 3, 4 bytes IO` (the sorter
  list re-exported: 26 rows, the ServoOne clone-safe - the first configured, the clones inherit).
- **The oracle.** `sycon5/gsdml.py` reads a DAP's module slots from its GSDML (SYCON.net's catalog folder
  `C:\ProgramData\SYCONnet\PROFINET\GSDML`): `verify` checks every station the table gives no module rows - when
  its DAP takes modules (`AllowedInSlots` / `FixedInSlots` / `UsedInSlots` >= 1) one must be plugged. A SCALANCE DAP
  lists none (not checked), the AL1202 and the KEBA fix theirs (checked, plugged by the catalog), a GSDML or DAP not
  found is a NOTE. On the saved fast sorter project the check fails exactly the 26 ServoOne.
- **Resume names the controller** (`controller_action`): a saved project's unnamed controller is named by a resume
  as by an update; a resume also writes the table's name over another one (this handoff's own build), an update
  keeps a named controller (OP5's rule).
- **The fast sorter project needs a resume, not an update** (an update skips existing stations whole, the ServoOne
  included). Found 2026-10-30: its saved XML was rewritten on 2026-10-26 13:27 outside the build and holds 55 devices
  - no PN/PN coupler, no SCALANCE switch; a resume on a re-exported handoff re-adds those eight (4 x 128-byte
  modules a coupler side, the V4.3 switches), plugs the ServoOne modules, names the controller.
- Tests: `tests/test_module_expectation.py`, `Pipeline5App/tests/unit/test_sycon_fixed_multiplier.py`
  (`test_the_servoone_plugs_its_ppo3_module`), Davi1's `test_scalance_pnio_row_v43_has_no_media_redundancy_record`.

## The driver — `sycon5` (2026-10-23, round 3 verified)

The proven mechanisms as a package; `SyconDriver` is the facade the skill / the PL5 consumer will call. Run
everything with the repo venv (`C:\Source\Repos\_Openn5\.venv\Scripts\python -I`), from `Sycon5App\`.

| module | holds |
|---|---|
| `session.py` | the process (launch on a project, login, close without saving, kill), the main window, the top-level windows enumerated through win32 (owned dialogs, message boxes), `dismiss_errors`, `answer_box(title, button)`, `post_command` (File commands as WM_COMMAND, refused while a modal dialog is open), popup menus, `safe_click`, the netProject tree (`nodes`, `station_item`), the catalog tree, the Output log |
| `drawing.py` | the BitBlt capture of the netDevice pane, the bus lines by colour (`locate_lines` → grey root dy, green line), the drop-point candidates, `text_bands` for custom grids |
| `catalog.py` | `add_device(session, kind, item, gsdml)`: the catalog tree item (PROFINET IO > Master / Slave / Gateway, the same-named entry whose info pane cites the GSDML file), the drag-drop with the tree as oracle, `parse_node` of a tree label |
| `dialog.py` | `ConfigDialog`: open from the context menu, `select_page` (UIA), win32 `controls()` (ids ≥ 1900), `press` (BM_CLICK), `apply`, `close(keep)` (Cancel → Question Yes/No, Warning Yes/No, Error → raise), `ok` |
| `controller.py` | `ControllerDialog`: `set_network(ip, mask, gw)` (+ the subnet Warning), `device_rows` / `find_row` / `set_station_name`, `set_station_ip` |
| `device.py` | `DeviceDialog`: `add_module`, `set_module(row, text)`, `resolve_module(row, "order:<no>")`, `set_slot`, `expand_row`, `is_expanded`, `select_row`, `visible_rows` / `scroll_to_end` (text bands of the Modules grid), `add_submodule(module_row)` → the new row, `set_submodule(row, text)`, `dataset("Parameter")`, `set_param_visual`, `set_parameters({index: value})` (wheel scrolling with the pixel shift measured) |
| `readback.py` | `read_project(xml or spj)` → `Project` / `Device` (name, ip, mask, gateway, gsdml, `dap`, `order_no`, `slots`, `submodules`, `records`, the controller's `network`), `describe` |
| `driver.py` | `SyconDriver`: `open(project)`, `new_project`, `add_controller`, `add_station(item, kind, gsdml)` (item = `name [DAP]`), `clone_station(source, count)`, `set_controller_network`, `set_station_name_ip`, `rename_stations({old: (new, ip)})`, `plug_modules(station, specs)`, `plug_module(station, module, slot)`, `plug_submodules(station, slot, [(subslot, text)])`, `set_parameters(station, slot, {index: value})`, `save_as`, `save`, `read_back`, `close` |

- **Verification**: every operation checks the GUI (the tree label, the reopened cell, the editor's text) and
  the round ends with `read_back` on the saved file — `tests/test_readback.py` pins the parser on the two
  fixtures (run the file directly; pytest is not installed in the venv), `scripts/e2e_driver_round3.py` is the
  whole chain on the VM: new project → controller → ET200SP → controller IP 192.168.2.1 → `n0005-ms1-k2501` @
  192.168.2.5 → `DI 8x24VDC HF V2.0` in slot 1 → Wire break = 1, Input delay = 0.4 ms → `Save as` → read back →
  assertions (names, IPs, the controller's list, slot 1, record bytes `10 83`). Verified 14:38, 5 minutes;
  log in `spike/references/E2E_Round3/`.
- **Parameters are addressed by index** within the submodule's record (0 = the first parameter row): the names
  are not readable from the custom grid, the order comes from the GSDML; the record bytes are the proof.
- **Module commit**: after choosing the module leave its in-place editor open (dropdown closed) and press Apply —
  closing the editor with a click elsewhere left the module without its submodule ("Slot [1] contains a module
  without submoduls" on Apply); the driver also recovers from that message with `Add Submodule` + Apply.
- **Not yet in the driver**: Remove, the base project's other device types, SYCON.net launched without a
  project (it is launched on the scratch base project, then File > New). Done since round 3: a second station
  of the same type (the rename pass maps SYCON's `-001` names; cloning), the PL5 handoff consumption
  (`consumer.py`), the submodule rows (an AL1202's ports), the catalog entry by GSDML file and DAP.

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
