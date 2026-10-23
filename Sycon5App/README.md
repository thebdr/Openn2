# Sycon5App — SYCON.net project automation (spike stage, 2026-10-23)

Layout of this folder:

- `README.md` — this brief (the handoff for the next session)
- `sycon5/` — **the driver package** (see "The driver" below): `session`, `drawing`, `catalog`, `dialog`,
  `controller`, `device`, `readback`, `driver` (the `SyconDriver` facade)
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
WARN, no controller a FAIL. `python -m pipeline5.systems.ipc_based.intervalzero_rtx.sycon_handoff --iolist <xlsx>
--out <folder>` stages the list with the builtin params and writes the folder; `tests/unit/test_sycon_handoff.py`.
The LOWER SORTER list (`8FVT_IO0010 ... LOWER SORTER_R1.2.xlsx`) gives 1 controller + 55 stations (3 PN/PN
Coupler X2, 6 ET200SP, 26 ServoOne Junior, 19 AL1202, 1 Anybus Communicator) + 22 module rows; skipped: the
backup cifX card, 5 SCALANCE switches (no XC216 in the catalog), 2 Vitronic controllers without a part number.

**Consumer** — `sycon5/handoff.py` (the reader, by position) + `sycon5/consumer.py` (`build`, `verify`) +
`scripts/build_from_handoff.py --handoff <folder> --out <project.spj> [--resume]` (`scripts/handoff_cut.py
--handoff <folder> --out <folder> --stations <names>` cuts a handoff down to a few stations for a smoke): new project, the controller
from the catalog and its network IP, every station from the catalog (SYCON names them `al1202`, `al1202-001`, ...),
ONE controller-dialog pass renaming every row and setting every IP (`ControllerDialog.rename_and_address`: the
Device Table read row by row - the name is read before it is written, the grids scrolled by wheel with the
pixel shift measured; the IPs in two phases, every row parked on 192.168.x.200+ first because a target IP may
still be auto-held by another row, each row's current IP checked before it is written), the modules of the
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
Reload the catalog (Network > Device Catalog > Reload) after any change to the folder.

**Catalog versions** (user 2026-10-23: "the pnpncoupler that was inserted was the wrong version"): the catalog shows
one same-named entry per GSDML file (five `PN/PN Coupler X2`, five `X1` before the reload), and nothing in the tree
tells them apart - the info pane under the catalog (RichEdit20W 59664, `Session.catalog_info`) does: its `Device:`
block cites the file in brackets, `[GSDML-V2.35-Siemens-PNPNIOC-20200924.xml]`. `catalog.catalog_item(session,
kind, item, gsdml)` selects the same-named entries one by one until the pane cites the wanted file (the index found
last is tried first), and refuses with the files it saw when none does; the device-types database's GSDML column
is that file, `hw/sycon-stations` carries it per station, and `verify` compares it with the saved device's
`deviceTypeInformation`. Without a GSDML the first entry is taken and its file logged.

**Cloning** (user: "once a device of a type was placed, Copy, Click, Paste in the left tab is a quick way to
replicate (see the .ahk script)"): `SyconDriver.clone_station(source, count)` selects the source node in the
netProject tree, posts the context menu's Copy (34503), selects it again and posts Paste (34504) - the keystrokes
Ctrl+C / Ctrl+V as the fallback - and reads the new node from the tree; SYCON.net names a clone `<source>-001`,
`-002` and the rename pass maps them like any auto name. The consumer adds only the first station of each
(kind, catalog item, GSDML) from the catalog and clones the rest. Written 2026-10-23 evening, to be verified on
the VM (the smoke build with cloning, then the 55-station build).

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
them (spacing collapsed), `SyconDriver.plug_submodules(station, slot, [(subslot, text)])` is a DRAFT (Add
Submodule under the expanded module row, Subslot combo 1901, submodule combo 1904 assumed like the module rows,
no scrolling yet) - `scripts/probe_submodules.py` is the probe to run on the VM first (nothing saved).

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
| `device.py` | `DeviceDialog`: `add_module`, `set_module(row, text)`, `resolve_module(row, "order:<no>")`, `set_slot`, `expand_row`, `select_row`, `dataset("Parameter")`, `set_param_visual`, `set_parameters({index: value})` (wheel scrolling with the pixel shift measured); drafts `add_submodule`, `set_subslot`, `set_submodule` |
| `readback.py` | `read_project(xml or spj)` → `Project` / `Device` (name, ip, mask, gateway, gsdml, `slots`, `submodules`, `records`, the controller's `network`), `describe` |
| `driver.py` | `SyconDriver`: `open(project)`, `new_project`, `add_controller`, `add_station(item, kind, gsdml)`, `clone_station(source, count)`, `set_controller_network`, `set_station_name_ip`, `rename_stations({old: (new, ip)})`, `plug_modules(station, specs)`, `plug_module(station, module, slot)`, `plug_submodules(station, slot, [(subslot, text)])` (draft), `set_parameters(station, slot, {index: value})`, `save_as`, `save`, `read_back`, `close` |

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
  project (it is launched on the scratch base project, then File > New). Drafted and not yet verified on the
  VM: station cloning, the submodule rows (an AL1202's ports). Done since: a second station of the same type
  (the rename pass maps SYCON's `-001` names), the PL5 handoff consumption (`consumer.py`).

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
