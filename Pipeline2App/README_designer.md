# I/O List Checker (for electrical designers)

A small tool to **validate your documents before sharing them**. It runs the same checks as the
old Excel "IOList check" tool **plus** the cross-check against the Cause & Effect matrix.

## Running it
Open the **`IOListChecker`** folder and launch **`IOListChecker.exe`**. No install, no Python needed.
(Your projects and settings are saved outside the app folder, so it's fine to move/update it.)

> **If antivirus blocks or removes it:** that's a false positive on the unsigned bundled runtime,
> not actual malware. Ask IT to **allow-list** the exe (by its SHA-256 hash — `build_designer.bat`
> prints it) or to **code-sign** it. See "Building" below.

## First time / per job: create a project
A *project* is a folder that keeps your settings (and, optionally, copies of your input files).

1. **File ▸ New project** → pick/create an empty folder. It gets a `project.yaml` plus `Inputs/`
   and `Output/` subfolders.
2. Fill in the form:
   - **I/O List file** + its sheet name and header row.
   - **Cause & Effect file** + the matrix/AREA header & data rows.
3. *(optional)* tick **File ▸ Copy input files into project on save** so that **Save** copies the
   I/O List + C&E into the project's `Inputs/` folder and points the project at those copies. The
   project folder is then self-contained — you can zip and send it.
4. **Save**.

Next time, **File ▸ Open project** and pick the folder (the app also reopens your last project).

## Running the checks
The buttons on the left run top-to-bottom:

- **Run all** — everything below, in order.
- **Validation** — the I/O List on its own (column names, addresses, Profinet nodes/IPs, the
  "permanent part" descriptions, T.S. refs, duplicate IPs / devices, node counts).
- **C&E in I/O List** — every Cause & Effect / AREA reference exists in the I/O List.
- **I/O List in C&E** — every mandatory I/O signal appears in the Cause & Effect matrix.

Results show in the log, colour-coded:
- red **[FAIL]** = an error to fix, amber **[WARNING]** = check it, the rest is information.
- Click a **[open SHEET!CELL]** link to jump straight to that cell in Excel (Excel must be installed).

A full report is written to the project's **`Output/`** as `validation_log.txt` and
`validation_log.html` (the `.html` is the one to share).

## Other
- **File ▸ Archive project…** zips the whole project into a single `.zip` (optionally with a
  date/time stamp) — handy for sending or keeping a snapshot.
- **Language** menu: English / Italiano.

## Building the .exe (for the maintainer)
```
pip install pyinstaller
build_designer.bat
```
Produces **`dist/IOListChecker/`** (one-folder, no UPX, with version metadata — the AV-friendliest
unsigned build); ship that folder (zip it to send). The script prints the exe's SHA-256 for IT
allow-listing.

**Corporate antivirus:** even a clean PyInstaller exe can be quarantined on managed PCs. The reliable
fixes, in order: (1) **code-sign** it with the company certificate — uncomment the `signtool` step in
`build_designer.bat` (also clears the SmartScreen warning); (2) have IT **allow-list** it by SHA-256
hash or path; (3) submit it to the AV vendor as a false positive (e.g. Microsoft's submission portal).
One-folder + no UPX (this build) minimises the false positives but signing/allow-listing is the cure.
