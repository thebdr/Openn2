"""The netDevice canvas of a SAVED project: the symbolic names and the positions of its devices, written into
`SYCON_net.xml` with the project closed (user 2026-10-24: "we need to replicate positioning rules and symbolic
name edits. maybe this can be done on the .xml"). The rules come from the user's edited sorter project
(`spike/scratch/FVT_Sorter_Lower - Modified Canvas Positions`, diffed against the built one):

- the symbolic name (the label before `[type]<station>`) is the handoff's `symbolic_name` column (PL5 fills it by
  the device-types database's rule: the location `=TRIB-AEP01` for cabinet devices, the description's variable
  part for a coupler, the description for an Anybus, SYCON.net's default for drives and IO-Link masters);
- the controller sits at the top-left corner; the devices are rows per GROUP (ET200SP, couplers, gateways,
  IO-Link masters, switches, drives - top to bottom), each row a gentle stair of up to 8 devices (the next one
  ~60 px right and ~22 px down, so the long labels stay readable), the next row of the same group ~200 px lower,
  the next group below the last row; a device's drop line runs from y 36 down to its top at x left + 15.

A device element: `<Device syc:deviceName=".." syc:symbolicName=".." ... deviceNo="n0005-...">` with its
`<PositionRect top left bottom right/>` right after it, inside a `<BusLine>` whose own first `<PositionRect/>` is
the drop line. The text is edited in place (regex, no re-serialisation) so SYCON.net reads back exactly what it
wrote plus the few attributes changed."""
from __future__ import annotations

import re

from .handoff import natural_key
from .session import log

# the groups, top to bottom, by words of the catalog item; the rest below them
GROUPS = (("et200sp", ("IM 15",)), ("coupler", ("PN/PN",)), ("gateway", ("Anybus",)), ("iolink", ("AL1",)),
          ("switch", ("SCALANCE",)), ("drive", ("ServoOne", "Drive")))
CONTROLLER_RECT = (21, 34, 53, 66)
FIRST_ROW_TOP, X0, DX, DY, PER_ROW = 83, 60, 60, 22, 8
ROW_PITCH, GROUP_GAP, LINE_TOP = 200, 36, 36
SIZE = {"switch": (40, 70)}                       # (height, width) - the rest 32 x 32
STEP = {"switch": (80, 26)}                       # (dx, dy) of a bigger box

DEVICE_TAG = re.compile(r"<Device\b[^>]*>")
RECT_TAG = re.compile(r'<PositionRect top="\d+" left="\d+" bottom="\d+" right="\d+"/>')
SYMBOLIC_ATTR = re.compile(r'(syc:symbolicName=")([^"]*)(")')
DEVICE_NO = re.compile(r'\bdeviceNo="([^"]*)"')


def group_of(catalog_item) -> str:
    text = str(catalog_item or "")
    for name, words in GROUPS:
        if any(w.lower() in text.lower() for w in words):
            return name
    return "other"


def layout(stations) -> dict:
    """{station name (as written): (top, left, bottom, right)} for the handoff's stations (natural FLD order
    within a group)."""
    groups = {name: [] for name, _w in GROUPS}
    groups["other"] = []
    # the rows in FLD order (user 2026-10-24: "the canvas rows should sort by FLD"; the project's own order is by
    # PROFINET name) - a station without an FLD sorts by its name
    for s in sorted(stations, key=lambda s: natural_key(s.get("fld") or s["station_name"])):
        groups[group_of(s.get("catalog_item"))].append(s["station_name"])
    rects, y = {}, FIRST_ROW_TOP
    for name in list(groups):
        names = groups[name]
        if not names:
            continue
        h, w = SIZE.get(name, (32, 32))
        dx, dy = STEP.get(name, (DX, DY))
        chunks = [names[i:i + PER_ROW] for i in range(0, len(names), PER_ROW)]
        for k, chunk in enumerate(chunks):
            for i, station in enumerate(chunk):
                top, left = y + i * dy, X0 + i * dx
                rects[station] = (top, left, top + h, left + w)
            if k + 1 < len(chunks):
                y += ROW_PITCH
            else:
                y += (len(chunk) - 1) * dy + h + GROUP_GAP
    return rects


def _escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _rect(top, left, bottom, right):
    return '<PositionRect top="%d" left="%d" bottom="%d" right="%d"/>' % (top, left, bottom, right)


def apply(xml_path, symbolics, rects, controller_rect=CONTROLLER_RECT):
    """Write the symbolic names (`{station: label}`) and the device rectangles (`{station: (top, left, bottom,
    right)}`, the controller's from `controller_rect`) into the project XML. Station keys are matched to the
    `deviceNo` attribute case-insensitively. Returns (symbolic names written, rectangles written)."""
    raw = open(xml_path, "rb").read()
    text = raw.decode("utf-8")
    symbolics = {k.lower(): v for k, v in symbolics.items()}
    rects = {k.lower(): v for k, v in rects.items()}
    edits, n_sym, n_rect = [], 0, 0
    for m in DEVICE_TAG.finditer(text):
        tag = m.group(0)
        no = DEVICE_NO.search(tag)
        if not no:
            continue
        key = no.group(1).lower()
        is_controller = 'devicekind="HIL_MASTER"' in tag
        label = symbolics.get(key)
        if label is not None:
            new_tag, n = SYMBOLIC_ATTR.subn(lambda a: a.group(1) + _escape(label) + a.group(3), tag, count=1)
            if n and new_tag != tag:
                edits.append((m.start(), m.end(), new_tag))
                n_sym += 1
        rect = controller_rect if is_controller else rects.get(key)
        if rect is None:
            continue
        top, left, bottom, right = rect
        own = RECT_TAG.search(text, m.end(), m.end() + 600)
        if own:
            edits.append((own.start(), own.end(), _rect(top, left, bottom, right)))
            n_rect += 1
        bus = text.rfind("<BusLine>", 0, m.start())
        if bus >= 0:
            line = RECT_TAG.search(text, bus, m.start())
            if line:
                if is_controller:
                    edits.append((line.start(), line.end(), _rect(bottom - 1, left + 15, bottom, left + 17)))
                else:
                    edits.append((line.start(), line.end(), _rect(LINE_TOP, left + 14, top, left + 16)))
    for start, end, new in sorted(edits, key=lambda e: e[0], reverse=True):
        text = text[:start] + new + text[end:]
    open(xml_path, "wb").write(text.encode("utf-8"))
    return n_sym, n_rect


def apply_layout(xml_path, handoff):
    """The handoff's symbolic names and the rule layout of its stations, into the saved project."""
    symbolics = {s["station_name"]: s["symbolic_name"] for s in handoff.stations if s.get("symbolic_name")}
    n_sym, n_rect = apply(xml_path, symbolics, layout(handoff.stations))
    log("canvas: %d symbolic names, %d positions written to %s" % (n_sym, n_rect, xml_path))
    return n_sym, n_rect
