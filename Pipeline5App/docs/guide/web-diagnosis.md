# The web diagnosis app

A read-only diagnosis page that the safety CPU's own web server serves at `https://<cpu>/~safety/`. It shows
e-stops, safety breakers, doors, contactors, encoders, PROFINET nodes, diagnosis cabinets, areas, machine
interfaces and the users' own custom data, live, on desktop, tablet and phone. It never writes to the PLC
and is not a safety function.

## Generating it

- **650 Generate Web Application** (in phase 600, part of Run Pipeline) writes
  `Output/TiaPortalProjectInterface/BuilderData/<PLC>/Web applications/safety/`:
  - the fixed page, the same on every project (`index.html`, `app.js`, `app.css`, `icons.svg`, and
    `mock.js` for the local preview), from
    [Shared/Templates/WebServer/SafetyDiagnosis](src://../Shared/Templates/WebServer/SafetyDiagnosis);
  - `plant.json`, this project's devices, cabinets, areas and the exact variable names the page reads;
  - `webapp.manifest.csv`, the one headered file, which binds every file by its size and SHA-256.
- **660 Open Web Application Folder** opens that folder.
- What the page shows comes from the webui config, not from code: `device_kinds.csv` (one row per kind),
  `member_states.csv` (labels and healthy polarity) and `webui_params.yaml`, in the safety system's
  `config_project/webui/` folder.
- OP5 uploads the folder to the CPU (Workspace tab). The upload needs no TIA download and leaves the
  F-signature untouched.

## TIA checklist, once per safety CPU

- CPU properties, **Web server**: activate the web server and permit access with **HTTPS only**.
- **User management**, the anonymous user ("Everybody" on firmware V2.9, "Anonymous" from V3.1): tick
  **Read tags** and **Open user-defined web pages** only. The page logs in as this user with its empty
  password, so it carries no secret.
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
- Until the polarity of the diagnosis bits is confirmed for the plant (`diag.alarm_bit` /
  `diag.warning_bit` in `webui_params.yaml`, blank `healthy` cells in `member_states.csv`), device states
  show Unknown. The cabinet summaries and the raw bits are live already.
- A lost connection greys every state and retries. "No read right" means the anonymous user lacks
  **Read tags** on the CPU.
- **Configuration problems** lists the variables of `plant.json` the CPU does not know: the CPU runs
  another program than the one PL5 generated the page from. Run 650 again and upload.

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
- `&fail=rights` - every read refused (No read right).
