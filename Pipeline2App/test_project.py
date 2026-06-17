#!/usr/bin/env python3
"""Tests for project.py (the folder-based project manager).

new/open/save round-trip, copy-inputs-on-save (xlsx copied into Inputs/ + paths rewritten,
resolved back by config.load_params), and archive (with/without a date/time suffix).

Run: python test_project.py
"""
import os
import sys
import tempfile
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from openpyxl import Workbook

from pipeline2.gui import project
from pipeline2.core import config

failures = 0


def check(name, ok, detail=""):
    global failures
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        failures += 1


def _xlsx(path):
    wb = Workbook()
    wb.active["A1"] = "x"
    wb.save(path)


def main():
    tmp = tempfile.mkdtemp(prefix="projtest_")

    # --- new project ---
    folder = os.path.join(tmp, "MyProject")
    ppath = project.new_project(folder)
    check("new_project creates project.yaml", os.path.exists(ppath))
    check("new_project creates Inputs/ + Output/",
          os.path.isdir(os.path.join(folder, "Inputs")) and os.path.isdir(os.path.join(folder, "Output")))
    doc = project.load_doc(ppath)
    check("default doc blanks io_list/ce paths",
          doc["io_list"]["path"] == "" and doc["ce"]["path"] == "")
    # default_doc inherits the template's values (blanks only the input paths), so assert the
    # project knobs are PRESENT + well-typed rather than coupling to the template's language.
    check("default doc has project knobs",
          isinstance(doc.get("copy_inputs_on_save"), bool) and doc.get("language") in ("en", "it"))

    # --- open project ---
    check("open_project resolves the folder", project.open_project(folder) == ppath)
    try:
        project.open_project(os.path.join(tmp, "nope"))
        check("open_project raises on missing", False)
    except FileNotFoundError:
        check("open_project raises on missing", True)

    # --- save round-trip (no copy) ---
    src_io = os.path.join(tmp, "src", "io.xlsx")
    src_ce = os.path.join(tmp, "src", "ce.xlsx")
    os.makedirs(os.path.dirname(src_io), exist_ok=True)
    _xlsx(src_io)
    _xlsx(src_ce)
    doc["io_list"]["path"] = src_io
    doc["ce"]["path"] = src_ce
    doc["project_code"] = "TEST123"
    project.save_project(doc, ppath, copy_inputs=False)
    reopened = project.load_doc(ppath)
    check("save round-trips a scalar edit", reopened.get("project_code") == "TEST123")
    check("no-copy leaves absolute input paths", reopened["io_list"]["path"] == src_io)
    check("no-copy did NOT create Inputs copies",
          not os.path.exists(os.path.join(folder, "Inputs", "io.xlsx")))

    # --- save WITH copy-inputs ---
    project.save_project(doc, ppath, copy_inputs=True)
    saved = project.load_doc(ppath)
    check("copy-inputs copies the I/O List into Inputs/",
          os.path.exists(os.path.join(folder, "Inputs", "io.xlsx")))
    check("copy-inputs copies the C&E into Inputs/",
          os.path.exists(os.path.join(folder, "Inputs", "ce.xlsx")))
    check("copy-inputs rewrites paths to Inputs/<name>",
          saved["io_list"]["path"] == "Inputs/io.xlsx" and saved["ce"]["path"] == "Inputs/ce.xlsx")
    # config.load_params resolves the relative paths against the project folder
    params = config.load_params(ppath)
    check("config.load_params resolves project-relative inputs",
          os.path.isfile(params["io_list"]["path"]) and
          os.path.normpath(params["io_list"]["path"]) == os.path.normpath(os.path.join(folder, "Inputs", "io.xlsx")))

    # --- save_as ---
    folder2 = os.path.join(tmp, "Copy2")
    ppath2 = project.save_project_as(project.load_doc(ppath), folder2, copy_inputs=False)
    check("save_project_as writes a new project.yaml", os.path.exists(ppath2) and ppath2 != ppath)

    # --- archive (no datetime) ---
    z1 = project.archive_project(ppath, base_name="MyProject", add_datetime=False)
    check("archive creates a .zip beside the project", os.path.exists(z1) and z1.endswith("MyProject.zip"))
    with zipfile.ZipFile(z1) as zf:
        names = zf.namelist()
    check("archive contains project.yaml under the project root",
          any(n.replace("\\", "/") == "MyProject/project.yaml" for n in names))
    check("archive contains the copied input", any("Inputs/io.xlsx" in n.replace("\\", "/") for n in names))

    # --- archive (with datetime) ---
    from datetime import datetime
    fixed = datetime(2026, 6, 16, 9, 30, 0)
    z2 = project.archive_project(ppath, base_name="MyProject", add_datetime=True, now=fixed)
    check("archive datetime suffix applied", z2.endswith("MyProject_20260616_093000.zip") and os.path.exists(z2))

    # --- last-project state round-trip (redirect state dir so we don't touch real APPDATA) ---
    os.environ["LOCALAPPDATA"] = tmp
    project.set_last_project(ppath)
    check("last project round-trips", project.get_last_project() == os.path.abspath(ppath))

    print("ALL CHECKS PASS" if failures == 0 else f"{failures} CHECK(S) FAILED")
    raise SystemExit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
