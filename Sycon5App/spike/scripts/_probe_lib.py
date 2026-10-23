"""Shared helpers for the SYCON.net UI Automation probes (read-only: nothing here saves a project).

Every click goes through safe_click(), which refuses to click when a popup menu is open (SYCON.net's context
menu takes a few seconds to appear, and a click meant for the tree would land on the menu) or when the pixel
under the target belongs to another process (the Claude desktop window can overlap SYCON.net).
"""
import sys, time, ctypes
from ctypes import wintypes
from pywinauto import Desktop, keyboard

user32 = ctypes.windll.user32


def desktop():
    return Desktop(backend="uia")


def sycon_main():
    for w in desktop().windows():
        if w.window_text().startswith("SYCON.net - ["):
            return w
    raise SystemExit("no 'SYCON.net - [project]' main window: open the project and log in first")


def bring_front(win):
    try:
        win.set_focus()
    except Exception as e:  # noqa: BLE001
        print("set_focus failed:", e)
    time.sleep(0.5)


def pid_at_point(x, y):
    h = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return h, pid.value


def popup_menus():
    return [w for w in desktop().windows() if w.element_info.control_type == "Menu" or w.class_name() == "#32768"]


def wait_menu(timeout=10.0):
    """Wait for a popup menu to appear; returns it (or None)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        m = popup_menus()
        if m:
            time.sleep(0.3)
            return m[0]
        time.sleep(0.25)
    return None


def close_menus(timeout=5.0):
    """Esc until no popup menu is open; returns True when clean."""
    t0 = time.time()
    while popup_menus():
        keyboard.send_keys("{ESC}")
        time.sleep(0.5)
        if time.time() - t0 > timeout:
            return not popup_menus()
    return True


def safe_click(el, pid, button="left", double=False, allow_menu=False):
    """Click the element's mid point only if no popup menu is open (unless the target IS a menu item) and that
    pixel belongs to process `pid`."""
    if not allow_menu and popup_menus():
        raise RuntimeError("a popup menu is open; not clicking (close_menus() first)")
    p = el.rectangle().mid_point()
    h, owner = pid_at_point(p.x, p.y)
    if owner != pid:
        raise RuntimeError(f"({p.x},{p.y}) is covered by another process (pid {owner}, hwnd {h}); not clicking")
    if double:
        el.double_click_input()
    else:
        el.click_input(button=button)


def dump(el, depth=0, max_depth=8, out=sys.stdout, width=100):
    if depth > max_depth:
        return
    try:
        info = el.element_info
        name = (info.name or "")[:width]
        print("  " * depth + f"{info.control_type} | {name!r} | cls={info.class_name} | auto={info.automation_id} | {info.rectangle}", file=out)
        for c in el.children():
            dump(c, depth + 1, max_depth, out, width)
    except Exception as e:  # noqa: BLE001
        print("  " * depth + f"<err {e}>", file=out)


def iter_items(el):
    for c in el.children():
        if c.element_info.control_type == "TreeItem":
            yield c
        yield from iter_items(c)


def project_tree(main):
    for t in main.descendants(control_type="Tree"):
        if any(i.window_text().startswith("Project:") for i in iter_items(t)):
            return t
    raise SystemExit("netProject tree not found")


def station_item(main, station):
    for i in iter_items(project_tree(main)):
        if f"<{station}>" in i.window_text():
            return i
    raise SystemExit(f"station <{station}> not in the netProject tree")


def top_windows(pid):
    """Visible top-level windows of the process as UIA wrappers - enumerated through win32, because UIA lists a
    dialog OWNED by the main window (every DTM configuration dialog, every Error box) under its owner, not on the
    desktop."""
    out = []
    for w in Desktop(backend="win32").windows(process=pid, visible_only=True):
        if w.class_name() in ("tooltips_class32", "MSCTFIME UI", "IME", "ComboLBox"):
            continue
        try:
            out.append(desktop().window(handle=w.handle).wrapper_object())
        except Exception:  # noqa: BLE001
            pass
    return out


def config_dialogs(pid, title_sub="Configuration"):
    return [w for w in top_windows(pid) if w.class_name() == "#32770" and title_sub in w.window_text()]


def new_dialog(pid, before, timeout=60.0, settle=3.0):
    """Wait for a new non-menu top-level window of the process (handles not in `before`); returns the list."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        new = [w for w in top_windows(pid) if w.handle not in before and w.window_text().strip()
               and w.class_name() != "#32768"]
        if new:
            time.sleep(settle)
            return [w for w in top_windows(pid) if w.handle not in before and w.class_name() != "#32768"]
        time.sleep(1.0)
    return []


# ---- session control (launch / login / close without saving) ----------------------------------------------
EXE = r"C:\Program Files (x86)\Hilscher GmbH\SYCONnet\Syconu.exe"


def dismiss_errors(pid, max_n=30):
    """Press OK on every modal 'Error' box of the process (they stack one per failed DTM load). Returns texts."""
    texts = []
    for _ in range(max_n):
        errs = [w for w in top_windows(pid) if w.window_text() == "Error"]
        if not errs:
            break
        w = errs[0]
        texts.append(" / ".join(t.window_text() for t in w.children() if t.element_info.control_type == "Text"))
        ok = [b for b in w.children() if b.window_text() == "OK"]
        if ok:
            safe_click(ok[0], pid, allow_menu=True)
        else:
            w.close()
        time.sleep(0.8)
    return texts


def sycon_pids():
    import subprocess
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Syconu.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return [int(l.split('","')[1]) for l in out.splitlines() if l.startswith('"Syconu.exe"')]


def close_sycon_no_save(timeout=30.0):
    """Close SYCON.net WITHOUT saving: Alt+F4 on the main window, answer 'No' to a save prompt, kill if stuck."""
    import subprocess
    pids = sycon_pids()
    if not pids:
        return "not running"
    pid = pids[0]
    mains = [w for w in top_windows(pid) if w.window_text().startswith("SYCON.net")]
    if mains:
        dismiss_errors(pid)
        close_menus()
        bring_front(mains[0])
        keyboard.send_keys("%{F4}")
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(1.0)
        if pid not in sycon_pids():
            return "closed"
        for w in top_windows(pid):
            if w.window_text() in ("SYCON.net", "Save", "Confirm", "Question"):
                btns = {b.window_text().replace("&", ""): b for b in w.descendants(control_type="Button")}
                for name in ("No", "Don't Save", "Nein"):
                    if name in btns:
                        safe_click(btns[name], pid, allow_menu=True)
                        break
                else:
                    if "Yes" in btns or "Save" in btns:
                        raise RuntimeError(f"unexpected save prompt {list(btns)}; refusing to answer")
    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    time.sleep(2)
    return "killed"


def launch_sycon(project, timeout=120.0):
    """Start SYCON.net on a project (must be a scratch copy) and wait for the login dialog; returns the pid."""
    import os, subprocess
    if sycon_pids():
        raise RuntimeError("SYCON.net already running; close_sycon_no_save() first")
    subprocess.Popen([EXE, project], cwd=os.path.dirname(EXE))
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(2.0)
        for w in desktop().windows():
            if w.window_text() == "SYCON.net User Login" or any(
                    c.window_text() == "SYCON.net User Login" for c in w.children()):
                return w.process_id()
    raise RuntimeError("login dialog did not appear")


def login_default(timeout=60.0):
    """Press OK on the login dialog (empty credentials) and wait for the main window; returns it."""
    login = None
    for w in desktop().windows():
        if w.window_text() == "SYCON.net User Login":
            login = w
        else:
            for c in w.children():
                if c.window_text() == "SYCON.net User Login":
                    login = c
    if login is None:
        raise RuntimeError("no login dialog")
    ok = [c for c in login.descendants(control_type="Button") if c.window_text() == "OK"][0]
    ok.click_input()
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(2.0)
        for w in desktop().windows():
            if w.window_text().startswith("SYCON.net - [") and w.descendants(control_type="Tree"):
                time.sleep(3.0)
                return w
    raise RuntimeError("main window did not appear")
