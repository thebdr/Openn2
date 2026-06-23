"""Preserve formula CACHES across an openpyxl re-save.

openpyxl drops the cached `<v>` of every formula cell when it saves a workbook (it can't recompute
them), so a `data_only` reader (staging/validation) would then see `None` for e.g. the I/O List's
Profinet IP/name `_xlfn.LET` formulas. `restore(original_bytes, target_path)` captures those cached
values from the PRE-save bytes and patches them back into the just-saved file at the ZIP/XML level
(atomic temp + os.replace). Lifted from `interfaces.insert_sheets_into_iolist`'s cache machinery so
phase 200 Fill (which re-saves the source in place) no longer degrades it.
"""
from __future__ import annotations
import io
import os
import re
import zipfile
import xml.etree.ElementTree as ET

_MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _sheet_name_to_part(zbytes) -> dict:
    """{sheet display name -> worksheet part path} from a workbook's workbook.xml + rels."""
    out = {}
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rid = {r.get("Id"): r.get("Target")
               for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        sheets_el = wb.find(_MAIN_NS + "sheets")
        for sh in (sheets_el if sheets_el is not None else []):
            t = rid.get(sh.get(_REL_NS + "id"), "")
            out[sh.get("name")] = (t.lstrip("/") if t.startswith("/")
                                   else t if t.startswith("xl/") else "xl/" + t)
    return out


def capture(zbytes) -> dict:
    """{sheet name -> {cell ref -> (t_attr, cached value text)}} for every formula cell carrying a
    cached value."""
    caches = {}
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        present = set(z.namelist())
        for nm, part in _sheet_name_to_part(zbytes).items():
            if part not in present:
                continue
            cc = {}
            for c in ET.fromstring(z.read(part)).iter(_MAIN_NS + "c"):
                f, v = c.find(_MAIN_NS + "f"), c.find(_MAIN_NS + "v")
                if f is not None and v is not None and v.text is not None:
                    cc[c.get("r")] = (c.get("t"), v.text)
            if cc:
                caches[nm] = cc
    return caches


def _patch(xml: str, ref: str, t, value: str) -> str:
    """Restore one formula cell's cached value (+ result-type t) in an openpyxl-written sheet XML
    (openpyxl emits an empty <v/> for formula cells)."""
    esc = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    pat = re.compile(r'(<c r="' + re.escape(ref) + r'")([^>]*)(>)(.*?)(</c>)', re.DOTALL)

    def repl(m):
        attrs = re.sub(r'\s+t="[^"]*"', "", m.group(2))
        if t:
            attrs += f' t="{t}"'
        body = m.group(4)
        if re.search(r"<v\s*/>|<v>.*?</v>", body, re.DOTALL):     # has a (possibly empty) <v> -> replace
            body = re.sub(r"<v\s*/>|<v>.*?</v>", f"<v>{esc}</v>", body, count=1, flags=re.DOTALL)
        elif "</f>" in body:                                       # formula, no cached <v> -> add one
            body = body.replace("</f>", f"</f><v>{esc}</v>", 1)
        else:
            body = body + f"<v>{esc}</v>"
        return m.group(1) + attrs + m.group(3) + body + m.group(5)

    return pat.sub(repl, xml, count=1)


def restore(original_bytes, target_path: str) -> bool:
    """Patch the formula caches from `original_bytes` into the openpyxl-saved `target_path`, in place
    (atomic). Best-effort: returns False (and leaves the file untouched) on any error or when there is
    nothing to restore."""
    try:
        caches = capture(original_bytes)
        if not caches:
            return False
        with open(target_path, "rb") as f:
            data = f.read()
        tparts = _sheet_name_to_part(data)
        repl = {}
        for nm, cc in caches.items():
            part = tparts.get(nm)
            if not part:
                continue
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                xml = z.read(part).decode("utf-8")
            for ref, (t, v) in cc.items():
                xml = _patch(xml, ref, t, v)
            repl[part] = xml.encode("utf-8")
        if not repl:
            return False
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as zin, \
                zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for it in zin.infolist():
                zout.writestr(it, repl.get(it.filename) or zin.read(it.filename))
        tmp = target_path + ".tmp_cache"
        with open(tmp, "wb") as f:
            f.write(out.getvalue())
        os.replace(tmp, target_path)
        return True
    except (OSError, zipfile.BadZipFile, ET.ParseError):
        return False
