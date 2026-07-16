"""Phase 600 builder (600b): populate the unified `diagnosis_entries` table from the `signals` +
`diagnosis_cabinets` SSOT tables + the `diagnosis_logic_rules`. Clean-room port of PL3's diagnosis.py
(`build_diag_list_io` / `_resolve_logic` / `ml_value` / `fl_value` / `node_of` / `diag_entries`), reading
the PL4 `type` object (not PL3's `_type`) and the STORED `plc_binding` (not a re-derivation).

Two entry kinds (`source`):
  - "io"    - one per in-diag signal (`type.in_diag`); the DiagList_IO source + an SCL channel when its
              `(diag_cabinet, diag_bit)` is numeric.
  - "logic" - the diagnosis_logic_rules firing once per row whose script_type is ANY of `required_types`
              (OR/per-row), at the next free bit of its cabinet's alarm/warning family.
Each entry carries the SCL channel values (cabinet/bit/is_warning/in_binding/ml_value/fl_value) computed
HERE + a frozen `diag_columns` snapshot ({header -> rendered cell}) the DiagList projector (600c) picks -
so both projectors are pure. The OPC SCL (600d) reads the channel columns.
"""
from __future__ import annotations

from pipeline5 import config
from pipeline5.truth.database import Database
from pipeline5.findings.finding import record
from pipeline5.truth import identity
from pipeline5.truth.diagnosis import diagnosis_cabinets_table, diagnosis_entries_table
from pipeline5.truth.signals import signals_table

def _binding_sentinel() -> str:
    """The DiagList placeholder cell text that resolves to each entry's PLC binding - relocated to
    user_input/generation_params.yaml (diagnosis.plc_binding_placeholder; UI_REFRESH_PLAN F). STRICT:
    a missing key is a located error, never an in-code default. Must match the expression cells in
    diagnosis/diagnosis_columns.csv."""
    section = (config.load_generation_params() or {}).get("diagnosis") or {}
    try:
        return str(section["plc_binding_placeholder"])
    except KeyError:
        raise RuntimeError("generation_params.yaml: diagnosis.plc_binding_placeholder is missing") from None


# --- small helpers (ported) --------------------------------------------------------------------- #
def _in_diag(row) -> bool:
    return bool((row.get("type") or {}).get("in_diag"))


def _is_warning(row) -> bool:
    """A diagnosis row is in the WARNING family when its `type_hw` ends 'W' (an alarm + a warning may
    share a (cabinet, bit) slot - different families)."""
    return str(row.get("type_hw", "")).strip().upper().endswith("W")


def _is_warning_devtype(dev_type) -> bool:
    return str(dev_type).strip().upper().endswith("W")


def _int_or_none(value):
    s = str(value if value is not None else "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return int(s) if s.lstrip("-").isdigit() else None


def _addr_byte(bit):
    b = str(bit or "").strip().upper()
    if b[:1] in ("I", "Q") and "." in b:
        try:
            return b[0], int(b[1:b.index(".")])
        except ValueError:
            return None
    return None


def _nodes(rows):
    return [r for r in rows or [] if r.get("profinet_name")]


def node_of(rows, row):
    """The Profinet node whose POSITIONAL I/Q byte range (staging `I_/Q_startByte/endByte`) contains this
    signal's address; None otherwise."""
    ab = _addr_byte(row.get("bit"))
    if not ab:
        return None
    kind, byte = ab
    sk, ek = f"{kind}_startByte", f"{kind}_endByte"
    for n in _nodes(rows):
        s, e = n.get(sk, ""), n.get(ek, "")
        if str(s) != "" and int(s) <= byte <= int(e):
            return n
    return None


def ml_value(row) -> str:
    """ML_xx (mirror logic): the type's `diag_logic` mirror->TRUE / invert->FALSE; blank -> derived from
    `normal_condition` (set -> FALSE, empty -> TRUE)."""
    logic = ((row.get("type") or {}).get("diag_logic") or "").strip().lower()
    if logic == "mirror":
        return "TRUE"
    if logic == "invert":
        return "FALSE"
    nc = str(row.get("normal_condition") or "").strip().lower()
    return "FALSE" if nc and nc not in ("0", "0.0", "false", "no") else "TRUE"


def fl_value(rows, row) -> str:
    """FL_xx mute term: the row's node alarm `"PROFINET_NODES_ALARM"."<pname> <pip>"`, or 'false' when no
    node resolves. A node-level alarm (PA/PW - it carries its own profinet_name) never self-filters."""
    if row.get("profinet_name"):
        return "false"
    node = node_of(rows, row)
    if node and node.get("profinet_name"):
        member = f'{node["profinet_name"]} {node.get("profinet_ip", "")}'.strip()
        return f'"PROFINET_NODES_ALARM"."{member}"'
    return "false"


# --- the rule engine (the shared 610/620 core) -------------------------------------------------- #
def resolve_logic(rows, cabinets, rules) -> list:
    """The rule-generated diagnosis items. `required_types` is an OR list: a row matches when its
    script_type is ANY of them, firing once per match at the next free bit of its cabinet's alarm/warning
    family, bound to `"<db_name>"."<member>"`. Cabinet = numeric `diag_cabinet` -> a paired-channel
    sibling's cabinet (same device FLD) -> FU+LOC -> `diagnosis_cabinets`. Returns
    [{cabinet, bit, is_warning, binding, src, rule}]."""
    fld_to_cab = {b["fld"]: _int_or_none(b["cabinet_id"]) for b in cabinets if b.get("fld")}
    fld_to_cab_sibling: dict = {}
    for r in rows or []:
        dc = _int_or_none(r.get("diag_cabinet"))
        if dc is not None:
            fld_to_cab_sibling.setdefault(identity.fld(r), dc)

    used: dict = {}                                            # bits taken per (cabinet, is_warning)
    for r in rows or []:
        if not _in_diag(r):
            continue
        cab, bit = _int_or_none(r.get("diag_cabinet")), _int_or_none(r.get("diag_bit"))
        if cab is not None and bit is not None:
            used.setdefault((cab, _is_warning(r)), set()).add(bit)

    def _cabinet_of(r):
        dc = _int_or_none(r.get("diag_cabinet"))
        if dc is not None:
            return dc
        cab = fld_to_cab_sibling.get(identity.fld(r))           # paired-channel sibling
        if cab is None:
            cab = fld_to_cab.get(f"{r.get('functional_unit', '')}{r.get('location', '')}")
        return cab

    items = []
    for rule in rules or []:
        is_warn = _is_warning_devtype(rule["dev_type"])
        for r in rows or []:
            if r.get("script_type") not in rule["required_types"]:   # OR: any required type
                continue
            cab = _cabinet_of(r)
            if cab is None:
                continue
            taken = used.setdefault((cab, is_warn), set())
            bit = 0
            while bit in taken:
                bit += 1
            taken.add(bit)
            db, member = rule["db_name"], identity.interp(rule["member"], r)
            binding = f'"{db}"."{member}"' if db else f'"{member}"'
            items.append({"cabinet": cab, "bit": bit, "is_warning": is_warn,
                          "binding": binding, "src": r, "rule": rule})
    return items


# --- column rendering --------------------------------------------------------------------------- #
def _render(columns, row, binding, sentinel) -> dict:
    """{header -> cell} for one DiagList row: the configured binding `sentinel` -> `binding`, else the
    column's `{canonical}` template interpolated against `row` (`:03d`/`:02d` specs honored by interp)."""
    return {c["header"]: (binding if str(c["expression"]).strip() == sentinel
                          else identity.interp(c["expression"], row))
            for c in columns}


def build(database: Database | None = None) -> tuple:
    """600b: build the unified `diagnosis_entries` table from `signals` + `diagnosis_cabinets` + the
    diagnosis_logic_rules. Records the findings to `validation_issues` + saves. Returns (database, findings) -
    the build emits none in the common path (the unified table is a pure function of the SSOT)."""
    if database is None:
        colmap = config.load_column_map("IoList")
        database = Database([signals_table([m["canonical"] for m in colmap]),
                             diagnosis_cabinets_table()]).load(config.database_dir())
    rows = list(database["signals"])
    cabinets = list(database["diagnosis_cabinets"]) if "diagnosis_cabinets" in database else []
    rules = config.load_diagnosis_logic_rules()
    columns = config.load_diagnosis_columns()
    sentinel = _binding_sentinel()
    findings = []

    etab = diagnosis_entries_table()
    for r in rows:                                            # (1) the in-diag signals
        if not _in_diag(r):
            continue
        binding = str(r.get("plc_binding", "") or "")
        cab, bit = _int_or_none(r.get("diag_cabinet")), _int_or_none(r.get("diag_bit"))
        etab.add(source="io", source_signal=r.get("uid", ""), rule_name="",
                 cabinet=("" if cab is None else cab), bit=("" if bit is None else bit),
                 is_warning=_is_warning(r), in_binding=binding,
                 ml_value=ml_value(r), fl_value=fl_value(rows, r),
                 diag_columns=_render(columns, r, binding, sentinel))

    for it in resolve_logic(rows, cabinets, rules):          # (2) the rule-generated logic items
        r = dict(it["src"])                                  # a synthetic row for the column render
        # as STRINGS (not ints): interp's `value or ""` would turn the falsy int 0 into '' (bit 0 -> '');
        # the column spec then pads them ({diag_cabinet:03d}/{diag_bit:02d}).
        r["diag_cabinet"], r["diag_bit"] = str(it["cabinet"]), str(it["bit"])
        r["type_hw"] = it["rule"]["dev_type"]
        r["script_type"] = it["rule"]["name"] or it["src"].get("script_type")
        if it["rule"].get("diag_desc"):
            r["diag_desc"] = identity.interp(it["rule"]["diag_desc"], r)
        etab.add(source="logic", source_signal=it["src"].get("uid", ""), rule_name=it["rule"]["name"],
                 cabinet=it["cabinet"], bit=it["bit"], is_warning=it["is_warning"], in_binding=it["binding"],
                 ml_value=ml_value(it["src"]), fl_value=fl_value(rows, it["src"]),
                 diag_columns=_render(columns, r, it["binding"], sentinel))

    if etab.name in database:
        database[etab.name].rows = etab.rows
    else:
        database.add_table(etab)
    record(database, findings)                      # persist the facts to the validation_issues table
    database.save(config.database_dir())
    return database, findings
