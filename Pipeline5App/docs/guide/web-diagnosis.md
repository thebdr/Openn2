# The web diagnosis app

A read-only diagnosis page that the safety CPU's own web server serves at `https://<cpu>/~pl5/`. It shows
e-stops, safety breakers, doors, contactors, encoders, PROFINET nodes, diagnosis cabinets, areas, machine
interfaces and the users' own custom data, live, on desktop, tablet and phone. It never writes to the PLC
and is not a safety function.

## Generating it

- **650 Generate Web Application** (in phase 600, part of Run Pipeline) writes
  `Output/TiaPortalProjectInterface/BuilderData/<PLC>/Web applications/pl5/` (the folder and the page's
  address follow `app.name` in `webui_params.yaml`):
  - the fixed page, the same on every project (`index.html`, `app.js`, `app.css`, `icons.svg`, and
    `mock.js` for the local preview), from
    [Shared/Templates/WebServer/SafetyDiagnosis](src://../Shared/Templates/WebServer/SafetyDiagnosis);
  - `plant.json`, this project's devices, cabinets, areas and the exact variable names the page reads;
  - `webapp.manifest.csv`, the one headered file, which binds every file by its size and SHA-256.
- **660 Open Web Application Folder** opens that folder.
- What the page shows comes from the webui config, not from code: `device_kinds.csv` (one row per kind,
  its marker shape and its field I/O rule), `member_states.csv` (labels, healthy polarity and roles),
  `webui_params.yaml` (polling, the overview's tabs, the files below) and `webui_notes.csv` (the device
  notes), in the safety system's `config_project/webui/` folder.
- OP5 uploads the folder to the CPU (Workspace tab). The upload needs no TIA download and leaves the
  F-signature untouched.

## TIA checklist, once per safety CPU

- CPU properties, **Web server**: activate the web server and permit access with **HTTPS only**.
- **User management**, the anonymous user ("Everybody" on firmware V2.9, "Anonymous" from V3.1): tick
  **Read tags** and **Open user-defined web pages** only. The page logs in as this user with its empty
  password, so it carries no secret. On firmware V3.1 or later, also tick **Query diagnostics** for a node's
  diagnostics from the CPU (below).
- A **deploy user** for OP5's upload, with **Manage user-defined web pages**. Its password is typed at
  each upload and never stored.
- Download the hardware configuration, then check that the collective F-signature is unchanged.
- **PL5_CustomData** (optional, the Custom data view): create a **standard** global DB, not a fail-safe
  one, named `PL5_CustomData`. Keep **Accessible from HMI/OPC UA/Web API** ticked on every member you
  want to see. Build and change it freely in TIA: PL5 never generates or touches it, and the page
  discovers its structure when the view opens (Refresh structure after a download).

## Reading the page

- Green OK, amber Warning, red Alarm. A dashed grey chip is **Unknown**; "Unknown - node failed" means
  the device's PROFINET node is down, so its own state cannot be known.
- The polarity of the diagnosis bits (`diag.alarm_bit` / `diag.warning_bit` in `webui_params.yaml`) and of
  each member (`healthy` in `member_states.csv`) is config. The shipped values were confirmed live on the FVT
  1518F; a blank one shows Unknown, the raw value still shown.
- A violet border marks a PROFINET node flagged not installed in the program (`99_Commissioning`), and every
  device on it. The program then simulates those devices' members, so the page reads their field I/O instead
  (the kind's `field` rule) and the detail panel labels their members "(simulated)".
- A lost connection greys every state and retries. "No read right" means the anonymous user lacks
  **Read tags** on the CPU.
- **Configuration problems** lists the variables of `plant.json` the CPU does not know: the CPU runs
  another program than the one PL5 generated the page from. Run 650 again and upload.

## The overview

- One tab per entry of `layout.overview_tabs`. The shipped **Causes** tab shows the e-stops, doors, encoders
  and safety breakers, and only the PROFINET nodes they are wired to (`nodes: wired`); **Other devices** shows
  the rest and every node. A kind no tab names joins the last tab.
- **Filter** under the plant: regular expressions, one per line, matched without case against a device's FLD,
  PROFINET name, IP and description. The drawing and the schematic show only what matches one of them; the filter is kept in
  this browser.
- In the **Devices** lists, the locate button (**Show on layout**) opens the device's tab, zooms the drawing
  onto it and makes it pulse; a device without a position is shown in the schematic.

## Notes

- A device's detail panel has a **Note**. It is kept in this browser as it is typed.
- The **Notes** view lists every note and downloads them as `webui_notes.csv`. Save it over the project's
  `webui_notes.csv`, run **650** again and upload: the notes then show in every browser. The page itself writes
  nothing to the CPU.

## Node diagnostics from the CPU

- A PROFINET node's detail panel reads the node's diagnostics from the CPU when it opens, and again on
  **Refresh**; it is not polled.
- What it shows depends on the CPU's firmware (the Web API methods it has):
  - **V4.1 or later:** the node's status (good, error, not reachable, maintenance, deactivated), its diagnostic
    texts, its modules with their status, and its active alarms. The node is found by its device name in TIA.
  - **V3.1:** the node's active alarms only, matched by its name in the alarm text.
  - **Older** (the FVT 1518F runs V2.9.4): a note saying what is needed.

## The plant drawing

- A project can give the page a drawing of the plant: `webui_plant.svg`, `.png` or `.jpg` in the project's
  webui config (`config_project/systems/siemens_s7_safety/webui/`). The icon positions are
  `webui_positions.csv` beside it (`kind,fld,x,y`, in the drawing's own units).
- The overview then shows the drawing with one live icon per device. Drag to pan; zoom with the wheel, two
  fingers or the buttons; click an icon for its details. **Schematic** shows the automatic grouping instead.
- **Edit positions** moves icons: drag one, or pick a device under **Not placed** and tap the drawing. **Unplace
  selected** takes an icon off, **Discard changes** goes back. **Download webui_positions.csv** gives the file;
  save it over the project's `webui_positions.csv`, run **650** again and upload the application. The page
  itself changes nothing on the CPU.
- Phase 650 warns about a position that names no device of the plant, and notes the devices without a position
  (the edit mode lists them).

## Local preview

The page runs against a simulator, without a CPU. In the app folder:

```
python -m http.server 8765 --bind 127.0.0.1
```

Then open `http://127.0.0.1:8765/index.html?mock=1`. A striped banner says SIMULATED DATA on every view.
The simulator works only on a local address; on a CPU `?mock=1` is ignored. Options:

- `&polarity=plant` - the page as the CPU shows it before the polarity is confirmed;
- `&unknown=1` - one variable unknown to the CPU (Configuration problems);
- `&fail=lost` - the link drops from 6 s to 16 s;
- `&fail=rights` - every read refused (No read right);
- `&fw=3.1` / `&fw=2.9` - a CPU with the alarms only / with no diagnostics methods, for the node diagnostics
  (the default is V4.1).
