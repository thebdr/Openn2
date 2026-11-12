"""What a GSDML file says about a device access point's modules - for the verification, headless (no SYCON.net, no
driver packages: law L2 of tests/test_architecture_contracts.py).

2026-10-29 (user: "the servo one junior were missing their module on the sorter"): the ServoOne Junior's DAP takes
one module in slot 1 and fixes none, so a catalog drop plugs nothing; its database row said `default`, the handoff
had no module rows, and the verification - which compares the modules the table names - had nothing to compare. The
GSDML is the oracle of "this device takes modules": its DAP's `UseableModules/ModuleItemRef` entries place modules
in slots (`AllowedInSlots`, `FixedInSlots`, `UsedInSlots`). A SCALANCE XC200 DAP lists none (a switch is whole with its
DAP); the ServoOne, the PN/PN coupler allow modules and fix none; the AL1202 and the KEBA drive fix theirs in slot 1."""
import os
import xml.etree.ElementTree as ET

GSDML_DIR = r"C:\ProgramData\SYCONnet\PROFINET\GSDML"      # SYCON.net 1.500's catalog folder (scripts/gsdml_dedupe.py)
_CACHE = {}


def _local(tag):
    return tag.split("}")[-1]


def slot_list(text):
    """`1..3 7 9..10` -> {1, 2, 3, 7, 9, 10}: a GSDML slot list (`ValueList` syntax); an empty or malformed one -> set()."""
    out = set()
    for token in str(text or "").split():
        lo, sep, hi = token.partition("..")
        try:
            a, b = int(lo), int(hi) if sep else int(lo)
        except ValueError:
            continue
        if b - a > 4096:                               # a nonsense range is not a slot list
            continue
        out.update(range(a, b + 1))
    return out


def dap_module_slots(path):
    """{DAP id: the slots >= 1 its modules may go in} of a GSDML file (cached per path); {} when the file cannot be read."""
    key = os.path.normcase(os.path.abspath(path))
    if key in _CACHE:
        return _CACHE[key]
    out = {}
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        _CACHE[key] = out
        return out
    for dap in root.iter():
        if _local(dap.tag) != "DeviceAccessPointItem" or not dap.get("ID"):
            continue
        slots = set()
        for ref in dap.iter():
            if _local(ref.tag) == "ModuleItemRef":
                for attr in ("AllowedInSlots", "FixedInSlots", "UsedInSlots"):
                    slots |= slot_list(ref.get(attr))
        out[dap.get("ID")] = {s for s in slots if s >= 1}
    _CACHE[key] = out
    return out


def module_slots(gsdml_file, dap_id, folder=None):
    """The slots >= 1 the DAP `dap_id` of `gsdml_file` (a file name, looked up in `folder` - default the SYCON.net
    catalog folder - or a path) takes modules in; None when the file or the DAP is not found."""
    if not gsdml_file or not dap_id:
        return None
    path = gsdml_file if os.path.isabs(gsdml_file) else os.path.join(folder or GSDML_DIR, gsdml_file)
    if not os.path.exists(path):
        return None
    daps = dap_module_slots(path)
    for key, slots in daps.items():
        if key.strip().lower() == str(dap_id).strip().lower():
            return slots
    return None
