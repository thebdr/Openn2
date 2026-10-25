"""The architecture contracts of Sycon5App - the structure's laws, machine-enforced (C-046; the shape of
Pipeline5App/tests/unit/test_architecture_contracts.py). The test walks every module's imports (module-level AND
function-level, via ast) and the sources, and fails on any edge or token that breaks a law and is not in the
RATCHET below. The rules are pure functions (`imports_of`, `l1_violations`, `constructions_in`, `calls_in`) so the
refute round can attack them on synthetic sources (tests/test_refute_c046.py).

THE LAWS
  L1 LAYERS      one dependency direction:
                 log < handoff, readback < canvas, workspace < session, drawing < catalog, dialog, exports
                 < controller, device < driver < consumer < gui. An import may only point DOWN - sideways is
                 up. Dynamic imports (`importlib.import_module`, `__import__`) only in the package's `__init__`
                 (the lazy driver), so the ast sees every edge.
  L2 THE ORACLE APART   `readback` (the saved SYCON_net.xml decoded - the oracle of every operation), `handoff`
                 (the PL5 tables) and `log` import nothing of the package; the XML / folder side (readback,
                 handoff, log, canvas, workspace, gui) never imports the driver's packages - pywinauto, pywin32,
                 comtypes - directly or through the package: the oracle and the users' GUI run without SYCON.net.
  L3 GUI SEALED  tkinter is importable only from `gui`; `gui` imports only `workspace` of the package (the steps
                 are subprocesses, never the driver in-process); nothing of the package imports `gui`.
  L4 ONE FACADE  inside the package `Session` is constructed, `attach_if_running` called and the dialogs
                 (`ControllerDialog`, `DeviceDialog`) constructed only by `driver` - the user's running SYCON.net
                 is never reached around `SyconDriver.open` (2026-10-25 22:56: a probe attached to the user's
                 instance); `SyconDriver` is constructed only by `consumer`. A construction through a module
                 attribute (`driver.SyconDriver()`) counts (refute round 1); one through `getattr` does not - the
                 law is static.
  L5 TESTS NEVER DRIVE   no test constructs a driver or a session or opens / launches SYCON.net: the suite runs
                 on the fixtures alone, on any machine.

THE RATCHET (Kraken-style): known violations are quarantined here with their burn-down step.
Shrink it; never grow it silently - adding an entry is an architecture decision, not a fix.
"""
import ast
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
PKG = os.path.join(APP, "sycon5")
PACKAGE = "sycon5"

LAYERS = [("log",), ("handoff", "readback"), ("canvas", "workspace"), ("session", "drawing"),
          ("catalog", "dialog", "exports"), ("controller", "device"), ("driver",), ("consumer",), ("gui",)]
RANK = {m: i for i, group in enumerate(LAYERS) for m in group}
HEADLESS = {"log", "handoff", "readback", "canvas", "workspace", "gui"}
DRIVER_PACKAGES = ("pywinauto", "win32gui", "win32con", "win32ui", "win32api", "win32process", "win32clipboard",
                   "pywintypes", "comtypes")
DYNAMIC_IMPORT = re.compile(r"\bimportlib\.import_module\(|\b__import__\(")
# a construction: the name followed by `(`, not its class or function definition; a module attribute before it
# (`driver.SyconDriver()`) is still a construction - refute round 1 found the first rule skipped those
CONSTRUCTION = r"(?<!class )(?<!def )(?<!\w)%s\("
CALL = r"(?<!def )\b%s\("
# (importer module, imported target) -> reason + the burn-down step. EMPTY: adding an entry is an architecture
# decision, not a fix.
RATCHET: dict = {}


def modules():
    out = {}
    for name in os.listdir(PKG):
        if name.endswith(".py"):
            out[name[:-3]] = os.path.join(PKG, name)
    return out


def source(path):
    return open(path, encoding="utf-8").read()


def imports_of(text):
    """Every imported target of a source text, relative imports resolved to the package module they name."""
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.module:
                    yield PACKAGE + "." + node.module.split(".")[0]
                else:
                    for a in node.names:
                        yield PACKAGE + "." + a.name
            elif node.module:
                yield node.module


def imports(path):
    return imports_of(source(path))


def package_edges():
    """(importer, imported package module) for every sycon5-internal import."""
    for mod, path in modules().items():
        for target in imports(path):
            if target == PACKAGE or target.startswith(PACKAGE + "."):
                bits = target.split(".")
                if len(bits) > 1:
                    yield mod, bits[1]


def external_imports(mod):
    return {t.split(".")[0] for t in imports(modules()[mod]) if not t.startswith(PACKAGE)}


def l1_violations(edges, rank=RANK, ratchet=RATCHET):
    """The edges that point up or sideways (an unknown target is a violation too)."""
    return [(m, t) for m, t in edges if m != "__init__" and (m, t) not in ratchet and (t not in rank or rank[t] >= rank[m])]


def constructions_in(text, name):
    return re.search(CONSTRUCTION % re.escape(name), text) is not None


def calls_in(text, name):
    return re.search(CALL % re.escape(name), text) is not None


def _constructions(name):
    return sorted(m for m, p in modules().items() if constructions_in(source(p), name))


DRIVE_NAMES, DRIVE_METHODS = ("SyconDriver", "Session"), ("open", "launch", "new_project")


def drives_in(text):
    """The calls of a source that would drive SYCON.net: a driver or session constructed, `.open(` / `.launch(` /
    `.new_project(` called - as ast Call nodes, so a string or a comment that mentions them is not a call (refute
    round 1: the textual rule flagged the law's own docstring)."""
    out = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in DRIVE_NAMES:
                out.append(f.id + "(")
            elif isinstance(f, ast.Attribute) and f.attr in DRIVE_METHODS:
                out.append("." + f.attr + "(")
    return out


def test_parts_all_known():
    unknown = sorted(m for m in modules() if m != "__init__" and m not in RANK)
    assert not unknown, "modules without a layer (place them in LAYERS): %s" % unknown


def test_l1_layers_one_direction():
    bad = l1_violations(package_edges())
    assert not bad, "imports pointing up or sideways: %s" % bad
    dynamic = sorted(m for m, p in modules().items() if m != "__init__" and DYNAMIC_IMPORT.search(source(p)))
    assert not dynamic, "dynamic imports outside __init__ (the ast cannot see their edges): %s" % dynamic


def test_l2_the_oracle_apart():
    inner = {mod: {t for m, t in package_edges() if m == mod} for mod in modules()}
    for mod in ("log", "handoff", "readback"):
        assert not inner[mod], "%s imports the package: %s" % (mod, sorted(inner[mod]))
    for mod in sorted(HEADLESS):
        direct = external_imports(mod) & set(DRIVER_PACKAGES)
        assert not direct, "%s imports the driver's packages: %s" % (mod, sorted(direct))
        leak = inner[mod] - HEADLESS
        assert not leak, "%s reaches the driver through the package: %s" % (mod, sorted(leak))


def test_l3_gui_sealed():
    for mod in modules():
        if mod != "gui":
            assert "tkinter" not in external_imports(mod), "%s imports tkinter" % mod
    gui_inner = {t for m, t in package_edges() if m == "gui"}
    assert gui_inner == {"workspace"}, "gui imports %s" % sorted(gui_inner)
    importers = sorted(m for m, t in package_edges() if t == "gui")
    assert not importers, "modules importing gui: %s" % importers


def test_l4_one_facade():
    assert _constructions("Session") == ["driver"]
    assert _constructions("ControllerDialog") == ["driver"]
    assert _constructions("DeviceDialog") == ["driver"]
    assert _constructions("SyconDriver") == ["consumer"]
    callers = sorted(m for m, p in modules().items() if calls_in(source(p), "attach_if_running"))
    assert callers == ["driver"], "attach_if_running called by %s" % callers


def test_l5_tests_never_drive():
    bad = []
    for name in sorted(os.listdir(HERE)):
        if name.endswith(".py"):
            for call in drives_in(source(os.path.join(HERE, name))):
                bad.append((name, call))
    assert not bad, "tests driving SYCON.net: %s" % bad


def test_ratchet_entries_still_real():
    edges = set(package_edges())
    gone = [e for e in RATCHET if e not in edges]
    assert not gone, "ratchet entries whose edge is gone (shrink the ratchet): %s" % gone
