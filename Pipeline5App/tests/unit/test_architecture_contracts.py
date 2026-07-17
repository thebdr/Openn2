"""The architecture contracts - the structure's laws, machine-enforced (P-008 R2-R5).

Chapter: how the codebase polices its own shape. The blend decision (2026-07-17) made four laws;
this test walks every module's imports (module-level AND function-level, via ast) and fails on any
edge that breaks a law and is not in the RATCHET list below.

THE LAWS
  L1 LAYERS      one dependency direction:
                 language < truth < documents < findings < config < phases < systems
                 < project < workbench < app. An import may only point DOWN (or stay inside
                 its own part).
  L2 FILTERS     phases/<a> never imports phases/<b> - chapters meet only in the truth tables.
  L3 SEALED      only workbench / project / app (and systems itself) may import pipeline5.systems.
  L4 HEADLESS    tkinter is importable only from workbench and app.
  L5 NO TYPE-ID  no module below workbench (except systems/ itself) may carry a SYSTEM-id string
                 literal - kernel/phase code receives a System OBJECT and gates on capabilities;
                 branching on who the system IS belongs to nobody.

THE RATCHET (Kraken-style): known violations are quarantined here with their burn-down step.
Shrink it; never grow it silently - adding an entry is an architecture decision, not a fix.
"""
import ast
import os

from _harness import run, eq, ok

APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKG = os.path.join(APP_ROOT, "pipeline5")

LAYERS = ["language", "truth", "documents", "findings", "config",
          "phases", "systems", "project", "workbench", "app"]

# (importer module, imported target-prefix as the AST records it) -> reason + the burn-down step.
# EMPTY since step 5 (the last edge - fillout's stage->fill->re-stage wiring - moved to the system
# run-plan, safety/main.py). Adding an entry is an architecture decision, not a fix.
RATCHET: dict = {}


def _part(mod: str):
    head = mod.split(".")[0]
    return head if head in LAYERS else None


def _chapter(mod: str):
    bits = mod.split(".")
    return bits[1] if bits[0] == "phases" and len(bits) > 1 else None


def _modules():
    out = {}
    for root, dirs, files in os.walk(PKG):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if not f.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(root, f), PKG)
            mod = rel[:-3].replace(os.sep, ".")
            if mod.endswith(".__init__"):
                mod = mod[: -len(".__init__")] or "__init__"
            out[mod] = os.path.join(root, f)
    return out


def _imports(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


def _edges():
    """(importer_module, imported_target) for every pipeline5-internal + tkinter import."""
    for mod, path in _modules().items():
        for target in _imports(path):
            if target == "tkinter" or target.startswith("tkinter."):
                yield mod, "tkinter"
            elif target == "pipeline5" or target.startswith("pipeline5."):
                yield mod, target[len("pipeline5."):] or "__root__"


def _ratcheted(importer, target):
    for (imp, pref), _reason in RATCHET.items():
        if importer == imp and (target == pref or target.startswith(pref + ".")):
            return True
    return False


def test_l1_layers_one_direction():
    bad = []
    for importer, target in _edges():
        if target in ("tkinter", "__root__"):
            continue
        a, b = _part(importer), _part(target)
        if a is None or b is None or a == b:
            continue
        if LAYERS.index(a) < LAYERS.index(b) and not _ratcheted(importer, target):
            bad.append(f"{importer} -> {target}  ({a} may not reach up to {b})")
    eq(bad, [], "L1: no upward imports")


def test_l2_phases_are_filters():
    bad = []
    for importer, target in _edges():
        ca, cb = _chapter(importer), _chapter(target)
        if ca and cb and ca != cb and not _ratcheted(importer, target):
            bad.append(f"{importer} -> {target}  (chapter {ca} reaching into {cb})")
    eq(sorted(set(bad)), [], "L2: chapters meet only in the truth tables")


def test_l3_systems_sealed():
    allowed = ("systems", "workbench", "project", "app")
    bad = [f"{importer} -> {target}" for importer, target in _edges()
           if target.split(".")[0] == "systems" and _part(importer) not in allowed]
    eq(bad, [], "L3: only workbench/project/app may import systems")


def test_l4_headless_pipeline():
    bad = [f"{importer} imports tkinter" for importer, target in _edges()
           if target == "tkinter" and _part(importer) not in ("workbench", "app")]
    eq(sorted(set(bad)), [], "L4: tkinter only in the workbench/app")


def test_ratchet_entries_still_real():
    """A ratchet entry whose edge no longer exists is DEBT PAID - remove it (keeps the list honest)."""
    live = set()
    for importer, target in _edges():
        for key in RATCHET:
            imp, pref = key
            if importer == imp and (target == pref or target.startswith(pref + ".")):
                live.add(key)
    stale = [f"{imp} -> {pref}" for (imp, pref) in RATCHET if (imp, pref) not in live]
    eq(stale, [], "ratchet entries must match real edges - delete paid-off ones")


_SYSTEM_ID_LITERALS = ("siemens_s7_safety", "intervalzero_rtx_", "siemens_plc_safety", "rtx_cpci_")
_L5_ALLOWED_PARTS = ("systems", "workbench", "app")   # the registry, the (transitional) GUI wiring, the root
_L5_ALLOWED_MODULES = {"language.i18n"}               # the DISPLAY-NAME catalog (sys_* keys) - data, not branching


def test_l5_no_type_id_literals_below_workbench():
    """The grep-gate the C-021 refuter demanded: a kernel/phase module mentioning a system id AT ALL
    is one `==` away from type-branching - the System object and its capability flags are the only
    sanctioned way to differ per system. Scans STRING LITERALS via ast (comments can say anything)."""
    bad = []
    for mod, path in _modules().items():
        if _part(mod) in _L5_ALLOWED_PARTS or mod in _L5_ALLOWED_MODULES:
            continue
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                hit = next((l for l in _SYSTEM_ID_LITERALS if l in node.value), None)
                if hit:
                    bad.append(f"{mod}:{node.lineno}: string literal contains {hit!r}")
    eq(sorted(set(bad)), [], "L5: no system-id literals below the workbench")


def test_parts_all_known():
    unknown = sorted({m.split(".")[0] for m in _modules()
                      if m.split(".")[0] not in LAYERS and m not in ("__init__", "__main__")})
    eq(unknown, [], "every top-level package must be a declared layer")


if __name__ == "__main__":
    import sys
    sys.exit(run("architecture_contracts", [
        ("l1_layers_one_direction", test_l1_layers_one_direction),
        ("l2_phases_are_filters", test_l2_phases_are_filters),
        ("l3_systems_sealed", test_l3_systems_sealed),
        ("l4_headless_pipeline", test_l4_headless_pipeline),
        ("l5_no_type_id_literals_below_workbench", test_l5_no_type_id_literals_below_workbench),
        ("ratchet_entries_still_real", test_ratchet_entries_still_real),
        ("parts_all_known", test_parts_all_known),
    ]))
