"""End-to-end round 1 on the VM. It WRITES: the in-memory project (OK/Apply in dialogs) and ONE 'Save as' into
spike/scratch (authorized by the user for this round, 2026-10-23). Staged: --from N --to M (default 1..8).

 1 restart SYCON.net on the scratch base project, File > New
 2 controller CIFX RE/PNM from the catalog onto the grey root line (located by colour)
 3 ET200SP 'IM 155-6 PN ST V4.2' onto the controller's green line
 4 controller dialog: Device Table -> station name et200sp -> n0005-ms1-k2501; IP Address Table -> 192.168.2.5; OK
 5 NORD 'SK CU4-ETH' from the catalog onto the green line
 6 ET200SP dialog: Add Module 'DI 8x24VDC HF V2.0  [6ES7 131-6BF00-0CA0]' (win32 combo), Apply, parameter test, OK
 7 Save as spike/scratch/E2E_Round1.spj
 8 read back the saved SYCON_net.xml (+ the DTM blobs)
"""
import os, sys, time, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pywinauto import mouse, keyboard, Desktop
from _probe_lib import (sycon_main, bring_front, safe_click, iter_items, project_tree, dismiss_errors, close_menus,
                        wait_menu, pid_at_point, top_windows, new_dialog, config_dialogs, station_item, user32,
                        close_sycon_no_save, launch_sycon, login_default, sycon_pids)
from find_buslines import lines

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = os.path.join(HERE, "scratch")
SAVE_AS = os.path.join(SCRATCH, "E2E_Round1.spj")
FROM = int(sys.argv[sys.argv.index("--from") + 1]) if "--from" in sys.argv else 1
TO = int(sys.argv[sys.argv.index("--to") + 1]) if "--to" in sys.argv else 8
WM_COMMAND, ID_FILE_NEW, ID_FILE_SAVE_AS = 0x0111, 57600, 57604
STATION_OLD, STATION_NEW, IP_NEW, CTRL_IP = "et200sp", "n0005-ms1-k2501", "192.168.2.5", "192.168.2.1"
MODULE = "DI 8x24VDC HF V2.0  [6ES7 131-6BF00-0CA0]"


def log(*a):
    print(time.strftime("%H:%M:%S"), *a)
    sys.stdout.flush()


def nodes(main):
    try:
        return [i.window_text() for i in iter_items(project_tree(main))]
    except SystemExit:
        return []


def pane(scope, auto):
    return [p for p in scope.descendants(control_type="Pane") if p.element_info.automation_id == auto][0]


def locate(main):
    """(pane rect, grey root-line dy, green line) - green = ('h', dy, x0, x1) or ('v', dx, y0, y1)."""
    r = pane(main, "3000").rectangle()
    cols, rows, n, grey = lines(r)
    h = r.height()
    cand = [(hits, dy) for dy, hits in grey.items() if 10 < dy < h - 30 and hits * 2 > r.width() // 4]
    grey_dy = max(cand)[1] if cand else None
    green = None
    for key, cnt in n.most_common(10):
        R, G, B = key
        if G > R + 40 and G > B and cnt > 50:
            rw, c = rows[key], cols[key]
            dy, hits = rw.most_common(1)[0]
            if hits * 2 > 100:
                xs = sorted(c)
                green = ("h", dy, xs[0], xs[-1])
                break
            dx, hits = c.most_common(1)[0]
            if hits * 2 > 100:
                ys = sorted(rw)
                green = ("v", dx, ys[0], ys[-1])
                break
    log("lines: pane", r, "grey root line dy=", grey_dy, "green=", green)
    return r, grey_dy, green


def green_points(green):
    """Candidate drop points along the green line, proven-first (x0+170 was the point that worked)."""
    if green[0] == "h":
        x0, x1, dy = green[2], green[3], green[1]
        return [(x0 + 170, dy), ((x0 + x1) // 2, dy), (x0 + 100, dy), (x1 - 120, dy), (x0 + 170, dy - 1), (x0 + 170, dy + 1)]
    dx, y0, y1 = green[1], green[2], green[3]
    return [(dx, (y0 + y1) // 2), (dx, y0 + 150), (dx, y1 - 150)]


def add_slave(main, pid, path):
    r, grey_dy, green = locate(main)
    assert green, "no green line"
    for dx, dy in green_points(green):
        added = add_from_catalog(main, pid, path, dx, dy)
        if added:
            return added
    return None


def add_from_catalog(main, pid, path, dx, dy):
    before = nodes(main)
    cat = [t for t in main.descendants(control_type="Tree") if t.element_info.automation_id == "40000"][0]
    node = None
    for name in path:
        scope = iter_items(cat) if node is None else iter_items(node)
        node = [i for i in scope if i.window_text() == name][0]
        if name != path[-1]:
            node.expand()
            time.sleep(0.4)
    node.ensure_visible()
    time.sleep(0.4)
    item = [i for i in iter_items(cat) if i.window_text() == path[-1]][0]
    r = pane(main, "3000").rectangle()
    x, y = r.left + dx, r.top + dy
    h, owner = pid_at_point(x, y)
    if owner != pid:
        raise RuntimeError("drop point (%d,%d) covered by pid %d" % (x, y, owner))
    src = item.rectangle().mid_point()
    safe_click(item, pid)
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
    time.sleep(6.0)
    errs = dismiss_errors(pid, 20)
    if pid not in sycon_pids():
        raise RuntimeError("SYCON.net exited after the drop")
    new = [n_ for n_ in nodes(main) if n_ not in before]
    log("drop", repr(path[-1]), "at", (dx, dy), "errors=", errs, "new=", new)
    return new[0] if new else None


def open_config(main, pid, station):
    already = config_dialogs(pid, station)
    if already:
        log("dialog already open:", already[0].window_text())
        return already[0]
    close_menus()
    bring_front(main)
    item = station_item(main, station)
    before = {w.handle for w in top_windows(pid)}
    safe_click(item, pid, button="right")
    m = wait_menu(15)
    conf = [c for c in m.children() if c.window_text().startswith("Configuration")]
    safe_click(conf[0], pid, allow_menu=True)
    new_dialog(pid, before, timeout=90, settle=3)
    dlg = config_dialogs(pid, station)[0]
    log("dialog:", dlg.window_text())
    return dlg


PAGE_PATHS = {"Controller Network Settings": ["Configuration", "Controller Network Settings"],
              "Device Table": ["Configuration", "Device Table"], "IP Address Table": ["Configuration", "IP Address Table"],
              "Modules": ["Configuration", "Modules"], "General": ["Configuration", "General"]}


def select_page(dlg, name):
    """Select a page of the navigation tree with the UIA SelectionItem pattern (the win32 tree-item path hung:
    a 64-bit client reading a 32-bit SysTreeView32). Error boxes are dismissed first."""
    pid = dlg.process_id()
    dismiss_errors(pid, 20)
    nav = dlg.descendants(control_type="Tree")[0]
    [i for i in iter_items(nav) if i.window_text() == name][0].select()
    time.sleep(1.5)


def w32(dlg):
    return Desktop(backend="win32").window(handle=dlg.handle)


def vis(d32, cls, cid=None):
    return [c for c in d32.descendants(class_name=cls) if c.is_visible() and (cid is None or c.control_id() == cid)]


BUTTON_IDS = {"OK": 1, "Cancel": 2, "Apply": 2204, "Add Module": 307, "Add Submodule": 308, "Remove": 309}


def press(dlg, pid, name):
    """Press a dialog button by its control id with a win32 BM_CLICK (no mouse, no UIA pattern). OK / Cancel
    then wait until the dialog is gone, answering a 'save the data?' Question with Yes (OK) or No (Cancel)."""
    d32 = w32(dlg)
    btn = [b for b in d32.descendants(class_name="Button") if b.control_id() == BUTTON_IDS[name] and b.is_visible()][0]
    btn.click()
    time.sleep(2.0)
    if name not in ("OK", "Cancel"):
        return
    t0 = time.time()
    while time.time() - t0 < 60:
        tops = top_windows(pid)
        if not any(w.handle == dlg.handle for w in tops):
            log("  dialog closed after", name)
            return
        q = [w for w in tops if w.window_text() == "Question"]
        if q:
            cid = 6 if name == "OK" else 7
            b = [b for b in Desktop(backend="win32").window(handle=q[0].handle).descendants(class_name="Button") if b.control_id() == cid][0]
            log("  Question after", name, "->", b.window_text())
            b.click()
            time.sleep(2.0)
        time.sleep(1.0)
    raise RuntimeError("dialog still open 60 s after " + name)


def assert_no_modal(main, pid):
    """Never post a command to the main window while a modal dialog is up (PostMessage bypasses modality)."""
    open_ = [w.window_text()[:40] for w in top_windows(pid) if w.class_name() == "#32770"]
    assert main.is_enabled() and not open_, "modal dialog open: %r" % open_


def answer_box(pid, title, button_id, timeout=6.0):
    """Answer a message box of SYCON.net (e.g. 'Warning' after a subnet change) with a win32 button click."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        for w in Desktop(backend="win32").windows(process=pid, visible_only=True):
            if w.class_name() == "#32770" and w.window_text() == title:
                text = [c.window_text()[:100] for c in w.children() if c.class_name() == "Static" and c.window_text()]
                b = [b for b in w.descendants(class_name="Button") if b.control_id() == button_id][0]
                log("  ", title, "box:", text, "->", b.window_text())
                b.click()
                time.sleep(1.5)
                return True
        time.sleep(0.5)
    return False


def dump_windows(pid):
    return [(w.window_text()[:50], w.class_name()) for w in top_windows(pid)]


# ---------------------------------------------------------------------------------------------------------------
def stage1():
    """restart on the scratch base project, File > New"""
    log("close:", close_sycon_no_save())
    pid = launch_sycon(os.path.join(SCRATCH, "AutomateSyconProj_BaseProj.spj"))
    main = login_default()
    log("main:", main.window_text(), "nodes:", len(nodes(main)))
    user32.PostMessageW(main.handle, WM_COMMAND, ID_FILE_NEW, 0)
    time.sleep(3.0)
    for w in top_windows(pid):
        if w.window_text() in ("SYCON.net", "Question"):
            btns = {b.window_text().replace("&", ""): b for b in w.descendants(control_type="Button")}
            log("prompt:", [t.window_text() for t in w.descendants(control_type="Text")][:2], list(btns))
            safe_click(btns["No"], pid, allow_menu=True)
            time.sleep(1.5)
    main = sycon_main()
    log("after New:", main.window_text(), nodes(main))
    assert "Untitled" in main.window_text()


def stage2():
    """controller from the catalog onto the grey root line"""
    main = sycon_main()
    pid = main.process_id()
    bring_front(main)
    r, grey_dy, green = locate(main)
    assert grey_dy, "no grey root line"
    added = add_from_catalog(main, pid, ["PROFINET IO", "Master", "CIFX RE/PNM"], 400, grey_dy)
    assert added and "CIFX" in added, "controller not added"


def stage3():
    """ET200SP onto the green line"""
    main = sycon_main()
    pid = main.process_id()
    bring_front(main)
    added = add_slave(main, pid, ["PROFINET IO", "Slave", "IM 155-6 PN ST V4.2"])
    assert added and ("<%s>" % STATION_OLD) in added, "ET200SP not added"


def stage4():
    """controller dialog: station name + IP of the ET200SP, OK"""
    main = sycon_main()
    pid = main.process_id()
    dlg = open_config(main, pid, "controller")
    d32 = w32(dlg)
    select_page(dlg, "Controller Network Settings")
    ipc = [c for c in vis(d32, "SysIPAddress32") if c.control_id() == 213][0]
    fields = sorted(ipc.children(), key=lambda c: c.rectangle().left)
    log("  controller IP before:", ".".join(f.window_text() for f in fields))
    for f_, part in zip(fields, CTRL_IP.split(".")):
        f_.set_edit_text(part)
    time.sleep(0.4)
    log("  controller IP after:", ".".join(f.window_text() for f in sorted(ipc.children(), key=lambda c: c.rectangle().left)))
    answer_box(pid, "Warning", 6)          # 'Changing subnet will automatically modify IP addresses ...' -> Yes
    select_page(dlg, "Device Table")
    r = pane(dlg, "210").rectangle()
    row_y = None
    for row in range(6):
        y = 30 + 18 * row
        mouse.click(coords=(r.left + 200, r.top + y))
        time.sleep(0.9)
        eds = vis(d32, "Edit", 1902)
        if not eds:
            log("  row", row + 1, ": no editor (past the last row)")
            break
        log("  row", row + 1, ": Name of station =", repr(eds[0].window_text()))
        if eds[0].window_text() in (STATION_OLD, STATION_NEW):
            row_y = y
            break
    assert row_y, "ET200SP row not found in the Device Table"
    ed = vis(d32, "Edit", 1902)[0]
    if ed.window_text() != STATION_NEW:
        ed.select()
        time.sleep(0.2)
        keyboard.send_keys(STATION_NEW)
        time.sleep(0.4)
    mouse.click(coords=(r.left + 400, r.top + row_y))       # commit: a read-only cell
    time.sleep(0.9)
    mouse.click(coords=(r.left + 200, r.top + row_y))       # verify
    time.sleep(0.9)
    val = vis(d32, "Edit", 1902)[0].window_text()
    mouse.click(coords=(r.left + 400, r.top + row_y))
    time.sleep(0.6)
    log("  Name of station after edit:", repr(val))
    assert val == STATION_NEW
    select_page(dlg, "IP Address Table")
    r = pane(dlg, "212").rectangle()
    mouse.click(coords=(r.left + 260, r.top + row_y))
    time.sleep(0.9)
    ipc = vis(d32, "SysIPAddress32")
    assert ipc, "no IP editor"
    fields = sorted(ipc[0].children(), key=lambda c: c.rectangle().left)
    log("  IP before:", ".".join(f.window_text() for f in fields))
    for f_, part in zip(fields, IP_NEW.split(".")):
        f_.set_edit_text(part)
    time.sleep(0.4)
    mouse.click(coords=(r.left + 500, r.top + row_y))       # commit
    time.sleep(0.9)
    mouse.click(coords=(r.left + 260, r.top + row_y))       # verify
    time.sleep(0.9)
    fields = sorted(vis(d32, "SysIPAddress32")[0].children(), key=lambda c: c.rectangle().left)
    ip_after = ".".join(f.window_text() for f in fields)
    mouse.click(coords=(r.left + 500, r.top + row_y))
    time.sleep(0.6)
    log("  IP after edit:", ip_after)
    assert ip_after == IP_NEW
    press(dlg, pid, "OK")
    time.sleep(2.0)
    errs = dismiss_errors(pid, 20)
    log("  after OK: dialogs", [d.window_text()[:40] for d in config_dialogs(pid)], "errors", errs)
    if config_dialogs(pid) and any("subnet" in e for e in errs):
        fallback = "192.168.0.5"
        log("  subnet refused -> slave IP", fallback, "(controller default subnet)")
        select_page(dlg, "IP Address Table")
        r = pane(dlg, "212").rectangle()
        mouse.click(coords=(r.left + 260, r.top + row_y))
        time.sleep(0.9)
        fields = sorted(vis(d32, "SysIPAddress32")[0].children(), key=lambda c: c.rectangle().left)
        for f_, part in zip(fields, fallback.split(".")):
            f_.set_edit_text(part)
        time.sleep(0.4)
        mouse.click(coords=(r.left + 500, r.top + row_y))
        time.sleep(0.9)
        press(dlg, pid, "OK")
        time.sleep(2.0)
        log("  after 2nd OK: dialogs", [d.window_text()[:40] for d in config_dialogs(pid)], "errors", dismiss_errors(pid, 20))
    log("  tree:", nodes(main))
    assert not config_dialogs(pid), "controller dialog still open"
    assert any(("<%s>" % STATION_NEW) in n_ for n_ in nodes(main)), "tree does not show the new station name"


def stage5():
    """NORD SK CU4-ETH onto the green line"""
    main = sycon_main()
    pid = main.process_id()
    bring_front(main)
    added = add_slave(main, pid, ["PROFINET IO", "Slave", "SK CU4-ETH"])
    assert added and "CU4" in added, "NORD not added"


def stage6():
    """ET200SP dialog: Add Module + module choice (win32), Apply, parameter test, OK"""
    main = sycon_main()
    pid = main.process_id()
    dlg = open_config(main, pid, STATION_NEW)
    d32 = w32(dlg)
    select_page(dlg, "Modules")
    r = pane(dlg, "321").rectangle()
    press(dlg, pid, "Add Module")
    time.sleep(0.5)
    mouse.click(coords=(r.left + 150, r.top + 47))
    time.sleep(1.5)
    cb = vis(d32, "ComboBox", 1904)
    assert cb, "no module combo"
    log("  module combo before:", repr(cb[0].selected_text()))
    cb[0].select(MODULE)
    time.sleep(1.5)
    log("  module combo editor alive:", bool(vis(d32, "ComboBox", 1904)))
    mouse.click(coords=(r.left + 150, r.top + 47))
    time.sleep(1.2)
    cb = vis(d32, "ComboBox", 1904)
    log("  module cell reopened:", repr(cb[0].selected_text()) if cb else "(no editor)")
    if cb:
        import win32con
        cb[0].send_message(win32con.CB_SHOWDROPDOWN, 0, 0)
    mouse.click(coords=(r.left + 450, r.top + 47))
    time.sleep(0.8)
    press(dlg, pid, "Apply")
    log("  after Apply: errors", dismiss_errors(pid, 20), "windows", dump_windows(pid))
    for cid in (311, 312):
        c = vis(d32, "ComboBox", cid)
        if c:
            log("  combo", cid, "enabled=", c[0].is_enabled(), "selected=", repr(c[0].selected_text()), "items=", c[0].item_texts())
    mouse.click(coords=(r.left + 450, r.top + 47))
    time.sleep(0.8)
    c311 = vis(d32, "ComboBox", 311)
    if c311 and c311[0].is_enabled():
        c311[0].select("Parameter")
        time.sleep(1.5)
        log("  Dataset -> Parameter:", repr(c311[0].selected_text()))
        lr = pane(dlg, "322").rectangle()
        for y in (30, 48, 66):
            for x in (20, 100, 200, 300, 400, 500):
                before = {(c.class_name(), c.control_id(), str(c.rectangle())) for c in d32.descendants() if c.is_visible()}
                mouse.click(coords=(lr.left + x, lr.top + y))
                time.sleep(0.9)
                new = [c for c in d32.descendants() if c.is_visible() and (c.class_name(), c.control_id(), str(c.rectangle())) not in before]
                if new:
                    log("  lower grid", (x, y), "editors", [(c.class_name(), c.control_id(), c.window_text()[:30]) for c in new][:6])
    else:
        log("  Dataset combo still disabled after Apply")
    # OK does not close a slave dialog (proved twice); Cancel -> Question 'save the data?' -> Yes does, keeping the data
    close_slave_dialog(dlg, pid)
    time.sleep(5.0)
    assert pid in sycon_pids(), "SYCON.net exited after closing the dialog"
    log("  after close: dialogs", [d.window_text()[:40] for d in config_dialogs(pid)], "errors", dismiss_errors(pid, 20))


def close_slave_dialog(dlg, pid):
    d32 = w32(dlg)
    btn = [b for b in d32.descendants(class_name="Button") if b.control_id() == 2 and b.is_visible()][0]
    btn.click()
    t0 = time.time()
    while time.time() - t0 < 60:
        time.sleep(1.0)
        tops = top_windows(pid)
        if not any(w.handle == dlg.handle for w in tops):
            log("  slave dialog closed")
            return
        for w in tops:
            if w.window_text() == "Question":
                text = [c.window_text()[:80] for c in Desktop(backend="win32").window(handle=w.handle).children() if c.class_name() == "Static" and c.window_text()]
                b = [b for b in Desktop(backend="win32").window(handle=w.handle).descendants(class_name="Button") if b.control_id() == 6][0]
                log("  Question:", text, "->", b.window_text())
                b.click()
                time.sleep(2.0)
    raise RuntimeError("slave dialog still open 60 s after Cancel")


def stage7():
    """Save as spike/scratch/E2E_Round1.spj"""
    import shutil
    main = sycon_main()
    pid = main.process_id()
    bring_front(main)
    for p in (SAVE_AS, SAVE_AS[:-4]):
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.exists(p):
            os.remove(p)
    assert_no_modal(main, pid)
    before = {w.handle for w in top_windows(pid)}
    user32.PostMessageW(main.handle, WM_COMMAND, ID_FILE_SAVE_AS, 0)
    new = new_dialog(pid, before, timeout=30, settle=1.5)
    fd = [w for w in new if w.class_name() == "#32770"]
    assert fd, "no file dialog; windows: %r" % dump_windows(pid)
    fd = fd[0]
    log("  file dialog:", repr(fd.window_text()), fd.rectangle())
    edits = fd.descendants(control_type="Edit")
    log("  edits:", [(e.window_text(), e.element_info.automation_id) for e in edits][:6])
    ed = [e for e in edits if e.element_info.automation_id in ("1148", "1001") or e.window_text().startswith(("File name", "Nome file"))]
    assert ed, "file name box not found"
    ed = ed[0]
    ed.set_focus()
    time.sleep(0.3)
    ed.set_edit_text(SAVE_AS)
    time.sleep(0.5)
    log("  typed:", repr(ed.get_value()))
    keyboard.send_keys("{ENTER}")
    for _ in range(30):
        time.sleep(1.0)
        if os.path.exists(SAVE_AS):
            break
    time.sleep(3.0)
    log("  saved file exists:", os.path.exists(SAVE_AS), "| main:", sycon_main().window_text(),
        "| windows:", dump_windows(pid), "| errors:", dismiss_errors(pid, 20))
    assert os.path.exists(SAVE_AS)


def stage8():
    """read back the saved SYCON_net.xml and the DTM blobs"""
    import olefile, io
    xml_path = os.path.join(SAVE_AS[:-4], "_S129", "SYCON_net.xml")
    xml = open(xml_path, encoding="utf-8", errors="replace").read()
    log("read back:", xml_path, len(xml), "chars")
    attr = lambda tag, n: (re.search(n + '="([^"]*)"', tag) or [None, None])[1]
    for m in re.finditer(r"<Device\b[^>]*>", xml):
        tag = m.group(0)
        log("  Device deviceNo=", repr(attr(tag, "deviceNo")), "symbolic=", repr(attr(tag, "syc:symbolicName")),
            "progId=", attr(tag, "syc:progId"), "gsdml=", (attr(tag, "fdt:deviceTypeInformation") or "").split("\\")[-1])
    for m in re.finditer(r'<Device\b[^>]*deviceNo="([^"]*)"[^>]*>.*?<BinData[^>]*>([0-9a-fA-F]+)</BinData>', xml, re.S):
        name, hexdata = m.group(1), m.group(2)
        raw = bytes.fromhex(hexdata)
        ole = olefile.OleFileIO(io.BytesIO(raw[4:]))
        streams = ["/".join(s) for s in ole.listdir()]
        mods = [s for s in streams if "STLModuleMap" in s]
        log("  blob of", repr(name), ":", len(raw), "bytes,", len(streams), "streams, module streams:", len(mods))
        for s in streams:
            if s.endswith("PNIODeviceDataModelBasic"):
                data = ole.openstream(s).read()
                strs = [x.decode("utf-16-le", "replace") for x in re.findall(rb"(?:[\x20-\x7e]\x00){4,}", data)]
                log("   ", s, ": strings", strs[:12])
        for s in streams:
            if s.endswith("PNIOModuleBasic"):
                data = ole.openstream(s).read()
                strs = [x.decode("utf-16-le", "replace") for x in re.findall(rb"(?:[\x20-\x7e]\x00){3,}", data)]
                log("    slot", s.split("STLModuleMap/")[1].split("/")[0], "->", strs[:2])
        for s in streams:
            data = ole.openstream(s).read()
            if b"nameOfStation" in data or "nameOfStation".encode("utf-16-le") in data:
                txt = data.decode("utf-16-le", "replace") if "nameOfStation".encode("utf-16-le") in data else data.decode("latin-1", "replace")
                log("   ", s, ": network entries:", re.findall(r'nameOfStation="([^"]*)"[^>]*ipAddress="([^"]*)"', txt)[:10])
        ole.close()


STAGES = {1: stage1, 2: stage2, 3: stage3, 4: stage4, 5: stage5, 6: stage6, 7: stage7, 8: stage8}
for n_ in range(FROM, TO + 1):
    log("===== stage", n_, ":", STAGES[n_].__doc__)
    STAGES[n_]()
log("done through stage", TO)
