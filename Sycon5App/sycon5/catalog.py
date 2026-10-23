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
_chosen = {}          # (kind, item, gsdml lower) -> the index among the same-named entries found last time


def info_files(text):
    """The GSDML file names the catalog info pane cites in brackets."""
    return GSDML_RE.findall(text or "")


def _kind_node(session: Session, kind):
    cat = session.catalog_tree()
    node = None
    for name in (FIELDBUS, KINDS[kind]):
        scope = session._iter_items(cat) if node is None else session._iter_items(node)
        found = [i for i in scope if i.window_text() == name]
        if not found:
            raise SyconError("catalog node %r not found under %s > %s" % (name, FIELDBUS, KINDS[kind]))
        node = found[0]
        node.expand()
        time.sleep(0.4)
    return node


def _cites(session: Session, entry, gsdml):
    """Select the catalog entry and tell whether the info pane cites the GSDML file. Returns (cited, files)."""
    entry.ensure_visible()
    time.sleep(0.3)
    session.safe_click(entry)
    time.sleep(0.6)
    files = info_files(session.catalog_info())
    return any(f.lower() == gsdml.lower() for f in files), files


def catalog_item(session: Session, kind, item, gsdml=None):
    """The catalog tree item to drag: PROFINET IO > <kind> > <item>. The catalog lists one same-named entry per
    GSDML version of a device (five `PN/PN Coupler X2` on 2026-10-23); with `gsdml` given, the entry whose info
    pane cites that file is the one (verified by selecting it - the last index found is tried first), without it
    the first entry is taken and its GSDML logged."""
    node = _kind_node(session, kind)
    entries = [i for i in session._iter_items(node) if i.window_text() == item]
    if not entries:
        raise SyconError("catalog item %r not found under %s > %s" % (item, FIELDBUS, KINDS[kind]))
    if not gsdml:
        entries[0].ensure_visible()
        time.sleep(0.4)
        if len(entries) > 1:
            session.safe_click(entries[0])
            time.sleep(0.6)
            log("catalog: %d entries named %r, the first taken (no GSDML given): %r" % (
                len(entries), item, info_files(session.catalog_info())))
        return entries[0]
    key = (kind, item, gsdml.lower())
    order = list(range(len(entries)))
    if key in _chosen and _chosen[key] < len(entries):
        order.insert(0, order.pop(_chosen[key]))
    seen = {}
    for n in order:
        cited, files = _cites(session, entries[n], gsdml)
        seen[n + 1] = files
        if cited:
            if _chosen.get(key) != n:
                log("catalog: %r from %s is entry %d of %d" % (item, gsdml, n + 1, len(entries)))
            _chosen[key] = n
            return entries[n]
    raise SyconError("no catalog entry %r comes from %s - the %d entries cite %r (reload the device catalog, or fix "
                     "the device-types database)" % (item, gsdml, len(entries), seen))


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
