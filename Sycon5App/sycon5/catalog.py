"""Adding a device from the device catalog = a drag-drop of the catalog tree item (SysTreeView32 ctrl 40000,
PROFINET IO > Master | Slave | Gateway / Stand-Alone Slave > <item>) onto a bus line of the drawing. The
netProject tree is the oracle: a new item appears, `<label>[<type>]<station-name>`.
"""
import re
import time

from pywinauto import mouse

from .drawing import drawing_pane, locate_lines, master_points, slave_points
from .session import Session, SyconError, log, pid_at_point

FIELDBUS = "PROFINET IO"
KINDS = {"master": "Master", "slave": "Slave", "gateway": "Gateway / Stand-Alone Slave"}
NODE_RE = re.compile(r"^(?P<symbolic>.*?)\[(?P<type>[^\]]*)\]<(?P<station>[^>]*)>(?P<suffix>.*)$")


def parse_node(label):
    """'IM_155-6_PN_ST_V4.2[IM 155-6 PN ST V4.2]<et200sp>' -> dict(symbolic, type, station, suffix)."""
    m = NODE_RE.match(label)
    return m.groupdict() if m else None


GSDML_RE = re.compile(r"\[([^\[\]]*\.xml)\]", re.I)
TOKEN_RE = re.compile(r"\[([^\[\]]+)\]")
ITEM_RE = re.compile(r"^(?P<name>.*?)\s*\[(?P<variant>[^\[\]]+)\]\s*$")
_chosen = {}          # (kind, item, gsdml lower) -> the index among the same-named entries found last time


def info_files(text):
    """The GSDML file names the catalog info pane cites in brackets."""
    return GSDML_RE.findall(text or "")


def info_tokens(text):
    """Every bracketed token of the info pane: `0x00010006`, `DAP X2 V4.2`, the GSDML file."""
    return TOKEN_RE.findall(text or "")


def split_item(item):
    """'PN/PN Coupler X2 [DAP X2 V4.2]' -> ('PN/PN Coupler X2', 'DAP X2 V4.2'): the bracketed variant names the
    DAP the info pane must cite when several entries share the name AND the GSDML file (the five PN/PN Coupler
    X2 entries are the DAPs V1.0 / V2.2 / V3.0 / V4.0 / V4.2 of one file, 2026-10-23)."""
    m = ITEM_RE.match(item or "")
    return (m.group("name"), m.group("variant")) if m else (item, "")


def _child_items(element):
    """The tree items directly under an element (never the whole catalog: thousands of UIA calls, 15-30 s)."""
    return [c for c in element.children() if c.element_info.control_type == "TreeItem"]


def _kind_node(session: Session, kind):
    node = session.catalog_tree()
    for name in (FIELDBUS, KINDS[kind]):
        found = [i for i in _child_items(node) if i.window_text() == name]
        if not found:
            raise SyconError("catalog node %r not found under %s > %s" % (name, FIELDBUS, KINDS[kind]))
        node = found[0]
        node.expand()
        time.sleep(0.4)
    return node


def _cites(session: Session, entry, gsdml, variant=""):
    """Select the catalog entry and tell whether its info pane cites the GSDML file and the variant (each when
    given). Returns (cited, files, tokens)."""
    entry.ensure_visible()
    time.sleep(0.3)
    session.safe_click(entry)
    time.sleep(0.6)
    text = session.catalog_info()
    files, tokens = info_files(text), info_tokens(text)
    ok = (not gsdml or any(f.lower() == gsdml.lower() for f in files)) and \
         (not variant or any(Session.same_text(t, variant) for t in tokens))
    return ok, files, tokens


def catalog_item(session: Session, kind, item, gsdml=None):
    """The catalog tree item to drag: PROFINET IO > <kind> > <item>. The catalog lists one same-named entry per
    GSDML version of a device AND per DAP of one file (five `PN/PN Coupler X2` on 2026-10-23, all from one
    GSDML); `item` may carry the DAP as `name [DAP X2 V4.2]` (what the info pane cites in brackets). With a
    GSDML or a variant given, the entry whose info pane cites them is the one (verified by selecting it - the
    index found last is tried first); without either the first entry is taken and its info logged."""
    name, variant = split_item(item)
    node = _kind_node(session, kind)
    entries = [i for i in _child_items(node) if i.window_text() == name]
    if not entries:
        raise SyconError("catalog item %r not found under %s > %s" % (name, FIELDBUS, KINDS[kind]))
    if not gsdml and not variant:
        entries[0].ensure_visible()
        time.sleep(0.4)
        if len(entries) > 1:
            session.safe_click(entries[0])
            time.sleep(0.6)
            log("catalog: %d entries named %r, the first taken (no GSDML / variant given): %r" % (
                len(entries), name, info_tokens(session.catalog_info())))
        return entries[0]
    key = (kind, item, (gsdml or "").lower())
    order = list(range(len(entries)))
    if key in _chosen and _chosen[key] < len(entries):
        order.insert(0, order.pop(_chosen[key]))
    seen = {}
    for n in order:
        cited, files, tokens = _cites(session, entries[n], gsdml or "", variant)
        seen[n + 1] = tokens
        if cited:
            if _chosen.get(key) != n:
                log("catalog: %r from %s is entry %d of %d" % (item, gsdml or "(any file)", n + 1, len(entries)))
            _chosen[key] = n
            return entries[n]
    raise SyconError("no catalog entry %r cites %s - the %d entries cite %r (reload the device catalog, or fix the "
                     "device-types database)" % (item, " + ".join(x for x in (gsdml, variant) if x), len(entries), seen))


def drop(session: Session, item, dx, dy, settle=6.0):
    """Drag the catalog item onto the drawing at pane offsets (dx, dy). Returns the new node label or None."""
    before = session.nodes()
    r = drawing_pane(session.main()).rectangle()
    x, y = r.left + dx, r.top + dy
    h, owner = pid_at_point(x, y)
    if owner != session.pid:
        raise SyconError("drop point (%d,%d) is covered by pid %d" % (x, y, owner))
    src = item.rectangle().mid_point()
    session.safe_click(item)
    time.sleep(0.4)
    mouse.press(coords=(src.x, src.y))
    time.sleep(0.4)
    mouse.move(coords=(src.x + 5, src.y + 5))
    time.sleep(0.2)
    mouse.move(coords=(src.x + 15, src.y + 15))
    time.sleep(0.4)
    for i in range(1, 21):
        mouse.move(coords=(src.x + (x - src.x) * i // 20, src.y + (y - src.y) * i // 20))
        time.sleep(0.06)
    time.sleep(0.6)
    mouse.release(coords=(x, y))
    time.sleep(settle)
    errors = session.dismiss_errors()
    session.ensure_alive("the drop of %r" % item.window_text())
    new = [n for n in session.nodes() if n not in before]
    log("drop", repr(item.window_text()), "at", (dx, dy), "errors", errors, "new", new)
    if errors:
        raise SyconError("errors after the drop of %r: %r" % (item.window_text(), errors))
    return new[0] if new else None


def add_device(session: Session, kind, item_name, gsdml=None):
    """Add a catalog device (kind: master | slave | gateway; `gsdml` = the file its catalog entry must come
    from). Returns the parsed new node."""
    session.close_menus()
    session.bring_front()
    item = catalog_item(session, kind, item_name, gsdml)
    r, grey_dy, green = locate_lines(session.main())
    log("lines: grey root dy=%s green=%s" % (grey_dy, green))
    if kind == "master":
        if grey_dy is None:
            raise SyconError("the grey root line was not found in the drawing")
        points = master_points(grey_dy)
    else:
        if green is None:
            raise SyconError("no green controller line in the drawing (add the controller first)")
        points = slave_points(green)
    for dx, dy in points:
        label = drop(session, item, dx, dy)
        if label:
            return parse_node(label) or {"symbolic": label, "type": "", "station": "", "suffix": ""}
        item = catalog_item(session, kind, item_name, gsdml)
    raise SyconError("no node appeared after dropping %r on %d points" % (item_name, len(points)))
