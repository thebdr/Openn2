"""xlsx_sheet_graft.py - copy a worksheet from another .xlsx INTO a workbook at the ZIP/XML level, leaving
every existing part of that workbook byte-identical ([[C-034]]).

Why not openpyxl: a `load_workbook` -> `save` round-trip re-serialises the WHOLE workbook, and on a modern
workbook that loses what openpyxl does not model ([[P-019]] measured it on FVT's I/O List: dynamic-array
formulas, threaded comments, add-in bindings, xl/metadata.xml, featurePropertyBag, printer settings, empty-text
cells). The graft never re-serialises the target. It ADDS the grafted sheet's own parts and APPENDS to the
four bookkeeping parts; every other part is copied byte-for-byte:
  - the worksheet XML, copied from the source with its cells re-pointed at the target: each style index
    remapped into the target's styles (a cell in the source's default format takes the target's default),
    each shared string written as an inline string (so xl/sharedStrings.xml is never rewritten), the grafted
    tables' names rewritten in its formulas (a name only - never inside a string literal, a quoted sheet
    name or a structured reference's [column] specifiers), `tabSelected` / `codeName` dropped,
    and optional cached values SEEDED into chosen formula cells;
  - its table parts, renamed `<name>_<title>` (unique in the workbook: tables + defined names, `_2`, `_3`...
    on a clash) with a fresh id - ref, header / totals row counts, autoFilter, the column ids + names and the
    table style kept; the per-column dxf / cell-style references and the calculated-column formulas dropped
    (they point into the SOURCE workbook / at the old name - Excel drops a table that carries them);
  - xl/workbook.xml (+ a <sheet> at the end, so every localSheetId stays valid; calcPr fullCalcOnLoad so
    Excel computes the grafted formulas the source left uncached), xl/_rels/workbook.xml.rels (+ a
    Relationship), [Content_Types].xml (+ Overrides), xl/styles.xml - APPEND-only: the number formats,
    fonts, fills, borders, cell formats and conditional-format dxfs the sheet uses are appended (an
    identical entry already there - or appended by an earlier graft - is reused) and only the collections'
    `count` attributes change.
Pure stdlib, Excel-independent. A source the graft cannot read, or cannot carry faithfully (a sheet part other
than tables / external hyperlinks, cell metadata - a dynamic array / rich value -, a prefixed spreadsheetml
namespace, a dangling style or string index), is REFUSED for that sheet - never half-copied, nothing of it
kept (not even a style); the others still graft.

Callers: src://pipeline5/systems/plc_based/siemens_s7/interface_xlsx_writer.py (phase 400e - the IF_ sheets
into the I/O List). Sibling of src://pipeline5/documents/xlsx_surgical_writer.py (cell edits / app-built
sheets), whose `_sheet_name_to_part` it reuses.
"""
from __future__ import annotations

import html
import io
import os
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from copy import deepcopy

from pipeline5.documents import xlsx_surgical_writer as xlsx_edit

_MAIN_URI = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_MAIN = "{" + _MAIN_URI + "}"
_REL_URI = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_XML_URI = "http://www.w3.org/XML/1998/namespace"
_T_TABLE = _REL_URI + "/table"
_T_HYPERLINK = _REL_URI + "/hyperlink"
_T_STYLES = _REL_URI + "/styles"
_T_SST = _REL_URI + "/sharedStrings"
_CT_TABLE = "application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml"
_BAD_TITLE = re.compile(r"[\\/?*\[\]:]")
_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


class GraftError(ValueError):
    """A source sheet the graft cannot carry faithfully (or a target it cannot extend) - refused."""


# --- XML text helpers ------------------------------------------------------------------------------ #
def _attr(v) -> str:
    return (str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
            .replace("\n", "&#10;").replace("\r", "&#13;").replace("\t", "&#9;"))


def _text(v) -> str:
    return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ser(el, prefix: str = "") -> str:
    """An ET element (from a parsed styles / table part) as XML text: spreadsheetml tags carry `prefix` (the
    target part's own - usually none), attributes are SORTED (so two equal entries serialise equal - the
    reuse key), any other namespace is declared on the element that uses it, whitespace-only text dropped."""
    decl: dict = {}

    def qn(name, attr):
        if name[0] != "{":
            return name
        uri, local = name[1:].split("}", 1)
        if uri == _MAIN_URI and not attr:
            return f"{prefix}:{local}" if prefix else local
        if uri == _XML_URI:
            return "xml:" + local
        return f"{decl.setdefault(uri, f'g{len(decl)}')}:{local}"

    tag = qn(el.tag, False)
    attrs = "".join(f' {qn(k, True)}="{_attr(v)}"' for k, v in sorted(el.attrib.items()))
    ns = "".join(f' xmlns:{p}="{_attr(u)}"' for u, p in decl.items())
    body = _text(el.text) if el.text and el.text.strip() else ""
    for child in el:
        body += _ser(child, prefix)
        if child.tail and child.tail.strip():
            body += _text(child.tail)
    return f"<{tag}{ns}{attrs}>{body}</{tag}>" if body else f"<{tag}{ns}{attrs}/>"


def _attr_of(start_tag_attrs: str, name: str):
    m = re.search(r'(?<![\w:])' + name + r'="([^"]*)"', start_tag_attrs)
    return html.unescape(m.group(1)) if m else None


def _set_attr(attrs: str, name: str, value) -> str:
    """Set (or, value None, remove) one attribute in a start tag's attribute text."""
    pat = re.compile(r'\s+' + name + r'="[^"]*"')
    attrs = pat.sub("", attrs, count=1)
    return attrs if value is None else f'{attrs} {name}="{_attr(value)}"'


def _root_prefix(xml: str, local: str):
    m = re.search(r"<(?:([A-Za-z_][\w.-]*):)?" + local + r"\b([^>]*)>", xml)
    return (m.group(1) or "", m.group(2)) if m else (None, "")


# --- the target's styles.xml, appended to (never rewritten) ---------------------------------------- #
class _Styles:
    _LISTS = ("fonts", "fills", "borders", "cellXfs", "dxfs")

    def __init__(self, data: bytes):
        self.text = data.decode("utf-8")
        self.prefix, _ = _root_prefix(self.text, "styleSheet")
        if self.prefix is None:
            raise GraftError("the workbook's styles part has no styleSheet")
        root = ET.fromstring(data)
        self.size, self.keys, self.new = {}, {}, {}
        for name in self._LISTS:
            kids = list(root.find(_MAIN + name)) if root.find(_MAIN + name) is not None else []
            self.size[name] = len(kids)
            self.keys[name] = {}
            for i, k in enumerate(kids):
                self.keys[name].setdefault(_ser(k), i)
            self.new[name] = []
        fmts = root.find(_MAIN + "numFmts")
        fmts = list(fmts) if fmts is not None else []
        self.size["numFmts"] = len(fmts)
        self.codes = {}                                    # formatCode -> numFmtId (existing + appended)
        self.ids = set()
        for f in fmts:
            self.ids.add(int(f.get("numFmtId")))
            self.codes.setdefault(f.get("formatCode"), int(f.get("numFmtId")))
        self.new["numFmts"] = []

    def snapshot(self):
        return ({k: dict(v) for k, v in self.keys.items()}, {k: list(v) for k, v in self.new.items()},
                dict(self.codes), set(self.ids))

    def restore(self, snap) -> None:
        self.keys, self.new, self.codes, self.ids = snap

    def index(self, name: str, el) -> int:
        """The target index of an entry equal to `el` in collection `name` - an existing / earlier-appended
        one when equal, else `el` appended."""
        key = _ser(el)
        hit = self.keys[name].get(key)
        if hit is None:
            hit = self.size[name] + len(self.new[name])
            self.new[name].append(_ser(el, self.prefix))
            self.keys[name][key] = hit
        return hit

    def numfmt(self, code: str) -> int:
        if code in self.codes:
            return self.codes[code]
        nid = max(self.ids | {163}) + 1                   # custom number formats start at 164
        self.ids.add(nid)
        self.codes[code] = nid
        p = f"{self.prefix}:" if self.prefix else ""
        self.new["numFmts"].append(f'<{p}numFmt numFmtId="{nid}" formatCode="{_attr(code)}"/>')
        return nid

    def changed(self) -> bool:
        return any(self.new.values())

    def render(self) -> str:
        text, p = self.text, (f"{self.prefix}:" if self.prefix else "")
        for name in ("numFmts",) + self._LISTS:
            if self.new[name]:
                text = _append_children(text, p, name, "".join(self.new[name]),
                                        self.size[name] + len(self.new[name]))
        return text


def _append_children(text: str, p: str, name: str, body: str, total: int) -> str:
    """Append `body` at the END of the styleSheet collection `name` (expanding a self-closing one, creating
    a missing one in its schema place) and set its count - nothing else of the text changes."""
    m = re.search(r"<" + re.escape(p) + name + r"\b([^>]*?)(/?)>", text)
    if m:
        attrs = m.group(1)
        attrs = (re.sub(r'(?<![\w:])count="\d*"', f'count="{total}"', attrs, count=1)
                 if re.search(r'(?<![\w:])count="', attrs) else f'{attrs} count="{total}"')
        if m.group(2):
            return text[:m.start()] + f"<{p}{name}{attrs}>{body}</{p}{name}>" + text[m.end():]
        close = text.index(f"</{p}{name}>", m.end())
        return text[:m.start()] + f"<{p}{name}{attrs}>" + text[m.end():close] + body + text[close:]
    el = f'<{p}{name} count="{total}">{body}</{p}{name}>'
    if name == "numFmts":                                   # the styleSheet's first child
        root = re.search(r"<" + re.escape(p) + r"styleSheet\b[^>]*>", text)
        return text[:root.end()] + el + text[root.end():]
    if name == "dxfs":                                      # after cellStyles (or cellXfs)
        for after in ("cellStyles", "cellXfs"):
            i = text.find(f"</{p}{after}>")
            if i >= 0:
                i += len(f"</{p}{after}>")
                return text[:i] + el + text[i:]
    raise GraftError(f"the workbook's styles part has no <{name}> to append to")


# --- the source workbook (the sheet to graft) ------------------------------------------------------ #
def _rels_of(z, part: str) -> list:
    """[(Id, Type, resolved target or raw external target, TargetMode)] of a part's .rels ([] when none)."""
    rp = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
    if rp not in z.namelist():
        return []
    out = []
    for r in ET.fromstring(z.read(rp)):
        tgt, mode = r.get("Target") or "", r.get("TargetMode")
        if mode != "External":
            tgt = (tgt.lstrip("/") if tgt.startswith("/")
                   else posixpath.normpath(posixpath.join(posixpath.dirname(part), tgt)))
        out.append((r.get("Id"), r.get("Type"), tgt, mode))
    return out


class _Source:
    """The FIRST worksheet of a source .xlsx + what grafting it needs: its rels, its tables' XML, its
    styles (parsed) and its shared strings (the raw inner XML of each <si>, in order)."""

    def __init__(self, path: str):
        with open(path, "rb") as fh:
            data = fh.read()
        parts = xlsx_edit._sheet_name_to_part(data)
        if not parts:
            raise GraftError("the source workbook has no worksheet")
        part = next(iter(parts.values()))
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.sheet = z.read(part).decode("utf-8")
            self.rels = _rels_of(z, part)
            self.tables = {rid: z.read(t) for rid, typ, t, _ in self.rels if typ == _T_TABLE}
            book = {typ: t for _, typ, t, _ in _rels_of(z, "xl/workbook.xml")}
            styles = book.get(_T_STYLES)
            self.styles = ET.fromstring(z.read(styles)) if styles else None
            sst = book.get(_T_SST)
            self.sst = []
            if sst:
                text = z.read(sst).decode("utf-8")
                if _root_prefix(text, "sst")[0] != "":
                    raise GraftError("the source's shared strings use a prefixed namespace")
                self.sst = [m.group(1) or "" for m in
                            re.finditer(r"<si(?:\s[^>]*)?(?:/>|>(.*?)</si>)", text, re.DOTALL)]

    def style_list(self, name: str) -> list:
        el = self.styles.find(_MAIN + name) if self.styles is not None else None
        return list(el) if el is not None else []


# --- the per-sheet rewrite ------------------------------------------------------------------------- #
_CELL = re.compile(r"<c(?=[\s/>])([^>]*?)(/>|>(.*?)</c>)", re.DOTALL)
# a formula's text: a cell's <f>, a conditional format's <formula>, a validation's <formula1|2>, x14's <xm:f>
# (never a self-closing one - a shared formula's follower <f t="shared" si="0"/> has no text)
_FORMULA = re.compile(r"(<((?:\w+:)?(?:f|formula|formula1|formula2))(?:\s[^>]*)?(?<!/)>)(.*?)(</\2>)", re.DOTALL)
_V = re.compile(r"<v\s*/>|<v(?:\s[^>]*)?(?<!/)>.*?</v>", re.DOTALL)


def _skip_quoted(text: str, i: int, q: str) -> int:
    """The index just past the quoted run that opens at text[i] (a doubled quote is an escaped one)."""
    j = i + 1
    while j < len(text):
        if text[j] == q:
            if text[j + 1:j + 2] == q:
                j += 2
                continue
            return j + 1
        j += 1
    return j


def _skip_brackets(text: str, i: int) -> int:
    """The index just past the bracketed run that opens at text[i] - a structured reference's specifiers
    (`[@[Data Type]]`, `[[#This Row],[Col]]`, nested) or an external-workbook index; `'` escapes the next
    character inside it (`[a'[b']]`)."""
    depth, j = 0, i
    while j < len(text):
        c = text[j]
        if c == "'":
            j += 2
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return j


def _table_renamer(renames: dict):
    """(pattern, {old casefolded: new}) for `_rename_in_formula` - a whole NAME, case-insensitively (Excel's
    rule), never part of a longer one (`DT` is not in `DT2` / `X.DT`) nor a sheet name (`DT!A1`); None when
    nothing is renamed."""
    if not renames:
        return None
    alt = "|".join(re.escape(k) for k in sorted(renames, key=len, reverse=True))
    return (re.compile(r"(?<![\w.\\])(" + alt + r")(?![\w.!])", re.IGNORECASE),
            {k.casefold(): v for k, v in renames.items()})


def _rename_in_formula(text: str, rx) -> str:
    """Rename the grafted tables' references in one formula's text. Only a NAME is renamed - never inside a
    "string literal", a 'quoted sheet name' or the [bracketed] column specifiers of a structured reference
    (a column may share a table's spelling: `Data[@[Data Type]]` keeps its column)."""
    if rx is None:
        return text
    out, start, i = [], 0, 0
    while i < len(text):
        c = text[i]
        if c in "\"'[":
            out.append(rx[0].sub(lambda m: rx[1][m.group(1).casefold()], text[start:i]))
            j = _skip_brackets(text, i) if c == "[" else _skip_quoted(text, i, c)
            out.append(text[i:j])
            start = i = j
        else:
            i += 1
    out.append(rx[0].sub(lambda m: rx[1][m.group(1).casefold()], text[start:]))
    return "".join(out)


class _SheetRewrite:
    def __init__(self, src: _Source, styles: _Styles, renames: dict):
        self.src, self.styles = src, styles
        self.xfs = src.style_list("cellXfs")
        self.default = _ser(self.xfs[0]) if self.xfs else None
        self.xf_cache: dict = {}
        self.rx = _table_renamer(renames)

    def xf(self, i: int):
        """The target cellXfs index for source xf `i`; None = the source's default format (the cell then
        takes the target's default, like an unstyled cell)."""
        if i in self.xf_cache:
            return self.xf_cache[i]
        if i >= len(self.xfs):
            raise GraftError(f"a cell names style {i}, the source has {len(self.xfs)}")
        if _ser(self.xfs[i]) == self.default:
            self.xf_cache[i] = None
            return None
        xf = deepcopy(self.xfs[i])
        for attr, coll in (("fontId", "fonts"), ("fillId", "fills"), ("borderId", "borders")):
            if xf.get(attr) is not None:
                items = self.src.style_list(coll)
                j = int(xf.get(attr))
                if j >= len(items):
                    raise GraftError(f"style {i} names {coll[:-1]} {j}, the source has {len(items)}")
                xf.set(attr, str(self.styles.index(coll, items[j])))
        nf = int(xf.get("numFmtId") or 0)
        if nf >= 164:
            codes = {int(f.get("numFmtId")): f.get("formatCode") for f in self.src.style_list("numFmts")}
            if nf not in codes:
                raise GraftError(f"style {i} names number format {nf}, the source does not define it")
            xf.set("numFmtId", str(self.styles.numfmt(codes[nf])))
        xf.set("xfId", "0")
        self.xf_cache[i] = self.styles.index("cellXfs", xf)
        return self.xf_cache[i]

    def restyle(self, attrs: str, name: str) -> str:
        v = _attr_of(attrs, name)
        return attrs if v is None else _set_attr(attrs, name, self.xf(int(v)))

    def cell(self, m, seeds: dict, seeded: list) -> str:
        attrs, body = m.group(1), m.group(3)
        if re.search(r'(?<![\w:])(?:cm|vm)="', attrs):
            raise GraftError(f"cell {_attr_of(attrs, 'r')} carries cell metadata (a dynamic array / rich "
                             "value) the graft does not copy")
        attrs = self.restyle(attrs, "s")
        if body is None:
            return f"<c{attrs}/>"
        if _attr_of(attrs, "t") == "s":                      # a shared string -> an inline string
            v = re.search(r"<v>\s*(\d+)\s*</v>", body)
            idx = int(v.group(1)) if v else -1
            if not 0 <= idx < len(self.src.sst):
                raise GraftError(f"cell {_attr_of(attrs, 'r')} names shared string {idx}, the source has "
                                 f"{len(self.src.sst)}")
            body = f"<is>{self.src.sst[idx]}</is>"
            attrs = _set_attr(attrs, "t", "inlineStr")
        body = _FORMULA.sub(lambda f: f.group(1) + _rename_in_formula(f.group(3), self.rx) + f.group(4), body)
        ref = _attr_of(attrs, "r")
        if ref in seeds and re.search(r"<f\b", body):        # seed a formula cell's cached value
            t, value = seeds[ref]
            v = f"<v>{_text(value)}</v>"
            body = _V.sub(v, body, count=1) if _V.search(body) else re.sub(
                r"(<f\b[^>]*/>|</f>)", lambda f: f.group(1) + v, body, count=1)
            attrs = _set_attr(attrs, "t", t)
            seeded.append(ref)
        return f"<c{attrs}>{body}</c>"

    def rewrite(self, seeds: dict) -> tuple:
        xml = self.src.sheet
        prefix, _ = _root_prefix(xml, "worksheet")
        if prefix != "":
            raise GraftError("the source worksheet is not plain spreadsheetml (a prefixed namespace)")
        xml = re.sub(r"(<sheetView\b[^>]*?)\s+tabSelected=\"(?:1|true)\"", r"\1", xml)
        xml = re.sub(r"(<sheetPr\b[^>]*?)\s+codeName=\"[^\"]*\"", r"\1", xml)
        xml = re.sub(r"<col\b([^>]*?)(/?)>", lambda m: f"<col{self.restyle(m.group(1), 'style')}{m.group(2)}>", xml)
        start, end = xml.find("<sheetData"), xml.find("</sheetData>")
        seeded: list = []
        if start >= 0 and end >= 0:
            data = xml[start:end]
            data = re.sub(r"<row\b([^>]*?)(/?)>", lambda m: f"<row{self.restyle(m.group(1), 's')}{m.group(2)}>", data)
            data = _CELL.sub(lambda m: self.cell(m, seeds, seeded), data)
            xml = xml[:start] + data + xml[end:]
            end = start + len(data)
        else:                                               # an empty <sheetData/>: the rest follows it
            m = re.search(r"<sheetData\s*/>", xml)
            end = m.end() if m else 0
        tail = xml[end:]
        dxfs = self.src.style_list("dxfs")

        def cf(m):
            v = _attr_of(m.group(1), "dxfId")
            if v is None:
                return m.group(0)
            if int(v) >= len(dxfs):
                raise GraftError(f"a conditional format names dxf {v}, the source has {len(dxfs)}")
            return f"<cfRule{_set_attr(m.group(1), 'dxfId', self.styles.index('dxfs', dxfs[int(v)]))}{m.group(2)}>"

        tail = re.sub(r"<cfRule\b([^>]*?)(/?)>", cf, tail)
        tail = _FORMULA.sub(lambda f: f.group(1) + _rename_in_formula(f.group(3), self.rx) + f.group(4), tail)
        return xml[:end] + tail, seeded


def _table_xml(src: bytes, tid: int, name: str) -> str:
    """A grafted table part: the source table renamed + re-identified, its references into the SOURCE
    workbook (dxfs, cell styles) and its calculated-column / totals formulas dropped."""
    root = ET.fromstring(src)
    if root.get("tableType") not in (None, "worksheet"):
        raise GraftError(f"table {root.get('displayName')}: a {root.get('tableType')} table (its query part "
                         "is not copied)")
    attrs = f' id="{tid}" name="{_attr(name)}" displayName="{_attr(name)}"' + "".join(
        f' {k}="{_attr(root.get(k))}"' for k in ("ref", "headerRowCount", "totalsRowCount", "totalsRowShown")
        if root.get(k) is not None)
    af = root.find(_MAIN + "autoFilter")
    cols = root.find(_MAIN + "tableColumns")
    cols = list(cols) if cols is not None else []
    tsi = root.find(_MAIN + "tableStyleInfo")
    body = ((_ser(af) if af is not None else "")
            + f'<tableColumns count="{len(cols)}">'
            + "".join(f'<tableColumn id="{_attr(c.get("id"))}" name="{_attr(c.get("name"))}"/>' for c in cols)
            + "</tableColumns>" + (_ser(tsi) if tsi is not None else ""))
    return f'{_DECL}<table xmlns="{_MAIN_URI}"{attrs}>{body}</table>'


# --- the target workbook --------------------------------------------------------------------------- #
class _Book:
    """The target's bookkeeping parts (as text, appended to) + what a graft allocates (parts, ids, names)."""

    def __init__(self, z, data: bytes):
        self.orig = {p: z.read(p).decode("utf-8") for p in
                     ("xl/workbook.xml", "xl/_rels/workbook.xml.rels", "[Content_Types].xml")}
        self.wb, self.rels, self.ct = (self.orig["xl/workbook.xml"], self.orig["xl/_rels/workbook.xml.rels"],
                                       self.orig["[Content_Types].xml"])
        self.p, root_attrs = _root_prefix(self.wb, "workbook")
        if self.p is None or f"</{self._p}sheets>" not in self.wb:
            raise GraftError("the workbook part has no <sheets>")
        m = re.search(r'xmlns:([\w.-]+)="' + re.escape(_REL_URI) + '"', root_attrs)
        self.rp = m.group(1) if m else None
        styles = {typ: t for _, typ, t, _ in _rels_of(z, "xl/workbook.xml")}.get(_T_STYLES)
        if not styles:
            raise GraftError("the workbook has no styles part to append to")
        self.styles_part = styles
        self.styles = _Styles(z.read(styles))
        self.taken = {n.lower() for n in z.namelist()}
        self.sheet_names = {n.casefold() for n in xlsx_edit._sheet_name_to_part(data)}
        self.names = {html.unescape(n).casefold() for n in re.findall(r'<(?:\w+:)?definedName\b[^>]*\bname="([^"]*)"', self.wb)}
        self.table_ids = [0]
        tables = {n for n in z.namelist() if n.lower().startswith("xl/tables/") and n.lower().endswith(".xml")}
        tables |= {p.lstrip("/") for p in re.findall(r'PartName="([^"]+)"[^>]*ContentType="' + re.escape(_CT_TABLE), self.ct)}
        for t in tables:
            if t in z.namelist():
                tr = ET.fromstring(z.read(t))
                self.table_ids.append(int(tr.get("id") or 0))
                self.names |= {(tr.get(k) or "").casefold() for k in ("name", "displayName")}
        self.added: dict = {}

    @property
    def _p(self) -> str:
        return f"{self.p}:" if self.p else ""

    def snapshot(self):
        return (self.wb, self.rels, self.ct, self.styles.snapshot(), set(self.taken), set(self.sheet_names),
                set(self.names), list(self.table_ids), dict(self.added))

    def restore(self, s) -> None:
        (self.wb, self.rels, self.ct, st, self.taken, self.sheet_names, self.names, self.table_ids,
         self.added) = s
        self.styles.restore(st)

    def _free(self, pattern: str) -> str:
        """The first `pattern.format(n)` part name not in the package - and whose .rels name is not either
        (an orphan rels part would otherwise be written twice). Part names compare case-insensitively."""
        def rels(p):
            return posixpath.join(posixpath.dirname(p), "_rels", posixpath.basename(p) + ".rels").lower()
        n = 1
        while pattern.format(n).lower() in self.taken or rels(pattern.format(n)) in self.taken:
            n += 1
        self.taken |= {pattern.format(n).lower(), rels(pattern.format(n))}
        return pattern.format(n)

    def _unique(self, base: str) -> str:
        name, n = base, 1
        while name.casefold() in self.names:
            n += 1
            name = f"{base}_{n}"
        self.names.add(name.casefold())
        return name

    def _override(self, part: str, content_type: str) -> None:
        if "</Types>" not in self.ct:
            raise GraftError("[Content_Types].xml has no </Types>")
        self.ct = self.ct.replace("</Types>", f'<Override PartName="/{part}" ContentType="{content_type}"/></Types>', 1)

    def graft(self, title: str, source: str, seeds: dict) -> list:
        if not title or len(title) > 31 or _BAD_TITLE.search(title) or title[0] == "'" or title[-1] == "'":
            raise GraftError(f"{title!r} is no valid sheet name")
        if title.casefold() in self.sheet_names:
            raise GraftError("a sheet of that name is already in the workbook")
        src = _Source(source)
        rels, renames = [], {}
        suffix = re.sub(r"[^A-Za-z0-9_]", "_", title)
        for rid, typ, target, mode in src.rels:
            if typ == _T_TABLE:
                old = ET.fromstring(src.tables[rid])
                old = old.get("displayName") or old.get("name")
                new = self._unique(f"{old}_{suffix}")
                renames[old] = new
                self.table_ids.append(max(self.table_ids) + 1)
                tpart = self._free("xl/tables/table{}.xml")
                self.added[tpart] = _table_xml(src.tables[rid], self.table_ids[-1], new).encode("utf-8")
                self._override(tpart, _CT_TABLE)
                rels.append(f'<Relationship Id="{_attr(rid)}" Type="{_T_TABLE}" Target="../tables/{posixpath.basename(tpart)}"/>')
            elif typ == _T_HYPERLINK and mode == "External":
                rels.append(f'<Relationship Id="{_attr(rid)}" Type="{_T_HYPERLINK}" Target="{_attr(target)}" TargetMode="External"/>')
            else:
                raise GraftError(f"the sheet carries a {(typ or '?').rsplit('/', 1)[-1]} part the graft does not copy")
        xml, seeded = _SheetRewrite(src, self.styles, renames).rewrite(seeds)
        part = self._free("xl/worksheets/sheet{}.xml")
        self.added[part] = xml.encode("utf-8")
        if rels:
            rpart = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
            self.added[rpart] =(f'{_DECL}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                                 f'relationships">{"".join(rels)}</Relationships>').encode("utf-8")
        self._override(part, xlsx_edit._WS_CT)
        self._register(title, part)
        self.sheet_names.add(title.casefold())
        return seeded

    def _register(self, title: str, part: str) -> None:
        ids = [int(i) for i in re.findall(r'\bId="rId(\d+)"', self.rels)]
        rid = f"rId{max(ids + [0]) + 1}"
        while f'Id="{rid}"' in self.rels:
            rid = f"rId{int(rid[3:]) + 1}"
        if "</Relationships>" not in self.rels:
            raise GraftError("the workbook's relationships part has no </Relationships>")
        target = posixpath.relpath(part, "xl")
        self.rels = self.rels.replace(
            "</Relationships>", f'<Relationship Id="{rid}" Type="{xlsx_edit._WS_REL}" Target="{target}"/></Relationships>', 1)
        sid = max([int(s) for s in re.findall(r'<(?:\w+:)?sheet\b[^>]*\bsheetId="(\d+)"', self.wb)] + [0]) + 1
        rel = f'{self.rp}:id="{rid}"' if self.rp else f'xmlns:r="{_REL_URI}" r:id="{rid}"'
        el = f'<{self._p}sheet name="{_attr(title)}" sheetId="{sid}" {rel}/>'
        self.wb = self.wb.replace(f"</{self._p}sheets>", el + f"</{self._p}sheets>", 1)

    def _full_calc_on_load(self) -> None:
        """Ask Excel to compute every formula on open - the grafted sheet's formulas carry no cached value
        (only the seeded ones do), and Excel shows an uncached formula as empty until it recalculates."""
        p = re.escape(self._p)
        m = re.search(r"<" + p + r"calcPr\b([^>]*?)(/?)>", self.wb)
        if m:
            attrs = _set_attr(m.group(1), "fullCalcOnLoad", "1")
            self.wb = self.wb[:m.start()] + f"<{self._p}calcPr{attrs}{m.group(2)}>" + self.wb[m.end():]
            return
        for after in ("definedNames", "externalReferences", "functionGroups", "sheets"):
            i = self.wb.find(f"</{self._p}{after}>")
            if i >= 0:
                i += len(f"</{self._p}{after}>")
                self.wb = self.wb[:i] + f'<{self._p}calcPr fullCalcOnLoad="1"/>' + self.wb[i:]
                return

    def replaced(self) -> dict:
        self._full_calc_on_load()
        out = {}
        for part, text in (("xl/workbook.xml", self.wb), ("xl/_rels/workbook.xml.rels", self.rels),
                           ("[Content_Types].xml", self.ct)):
            if text != self.orig[part]:
                out[part] = text.encode("utf-8")
        if self.styles.changed():
            out[self.styles_part] = self.styles.render().encode("utf-8")
        return out


def graft_sheets(path: str, grafts: list, *, dest: str | None = None) -> list:
    """Graft each {"title", "source" (an .xlsx path - its FIRST sheet), "seeds" ({cell ref: (t, cached
    value)}, optional)} into the workbook at `path`, as a new LAST sheet named `title`. Every existing part
    stays byte-identical except xl/workbook.xml, xl/_rels/workbook.xml.rels, [Content_Types].xml and the
    styles part (appended to). Returns one {"title", "error" (None = grafted, else why that sheet was
    refused - it adds nothing), "seeded" ([cell refs given their cached value])} per graft, in order. ONE
    atomic write (temp + os.replace) to `dest` (default: in place); nothing is written when no sheet
    grafts. Raises OSError / zipfile.BadZipFile / ET.ParseError / GraftError on a target it cannot read or
    extend (nothing written)."""
    dest = dest or path
    with open(path, "rb") as fh:
        data = fh.read()
    results = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        book = _Book(z, data)
        for g in grafts:
            snap = book.snapshot()
            try:
                seeded = book.graft(g["title"], g["source"], g.get("seeds") or {})
                results.append({"title": g["title"], "error": None, "seeded": seeded})
            except Exception as e:  # noqa: BLE001 - whatever ONE source does (a damaged deflate stream, a
                # malformed attribute, an index out of range ...), it refuses itself, never the whole run
                book.restore(snap)
                results.append({"title": g["title"], "error": f"{type(e).__name__}: {e}"
                                if not isinstance(e, GraftError) else str(e), "seeded": []})
        if not book.added:
            return results
        repl = book.replaced()
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for it in z.infolist():
                zout.writestr(it, repl.get(it.filename) or z.read(it.filename))
            for part, content in book.added.items():
                zout.writestr(part, content)
    tmp = dest + ".tmp_graft"
    try:
        with open(tmp, "wb") as fh:
            fh.write(out.getvalue())
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return results
