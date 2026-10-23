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


def catalog_item(session: Session, kind, item):
    cat = session.catalog_tree()
    node = None
    for name in (FIELDBUS, KINDS[kind], item):
        scope = session._iter_items(cat) if node is None else session._iter_items(node)
        found = [i for i in scope if i.window_text() == name]
        if not found:
            raise SyconError("catalog item %r not found under %s > %s" % (name, FIELDBUS, KINDS[kind]))
        node = found[0]
        if name != item:
            node.expand()
            time.sleep(0.4)
    node.ensure_visible()
    time.sleep(0.4)
    return [i for i in session._iter_items(cat) if i.window_text() == item][0]


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


def add_device(session: Session, kind, item_name):
    """Add a catalog device (kind: master | slave | gateway). Returns the parsed new node."""
    session.close_menus()
    session.bring_front()
    item = catalog_item(session, kind, item_name)
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
        item = catalog_item(session, kind, item_name)
    raise SyconError("no node appeared after dropping %r on %d points" % (item_name, len(points)))
