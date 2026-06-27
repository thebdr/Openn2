"""The hand-written software-block builders (phase 800 / 820) - the per-template edit point.

One function per template, registered with `@builds("<output name>")`. Each builder receives the
`Database` (the staged `signals` rows) and returns a `Table`; the engine serializes the Table into the
`$/#/%/@` CreationInfo CSV. NO rules, NO sidecars - the builder's Python does whatever the template needs.
Clean-room port of PL3's `domain/blocks/builders.py` (800a = the simple builders 00/06/07; the rest land
with 800b).

The Database helpers: `db.rows` · `db.by_type("KQ")` · `db.by_db("03_FDBACK")` · `db.by_area("AREA 1")` ·
`db.by_tagtable(...)` · `db.where(pred)` · `db.areas()`. The Table: `t.add(template_type="01", <key>=<value>,
...)` per @ row (a placeholder key -> `!!<key>$$`, a list value -> the horizontal ITERATOR, placed last).
"""
from __future__ import annotations

from pipeline4.domain.blocks.database import Database
from pipeline4.domain.blocks.registry import builds
from pipeline4.domain.blocks.table import Table

PAD = "No Operation"   # iterator filler for a template's unused fixed slots (a DB no-op member, ph520)


# --------------------------------------------------------------------------- #
# small shared helpers (node-by-address grouping, chunking) - free-form Python #
# --------------------------------------------------------------------------- #
def _addr_byte(bit):
    b = str(bit or "").strip().upper()
    if b[:1] in ("I", "Q") and "." in b:
        try:
            return b[0], int(b[1:b.index(".")])
        except ValueError:
            return None
    return None


def _nodes(db: Database) -> list:
    """The Profinet node rows (those carrying a profinet_name)."""
    return [r for r in db.rows if r.get("profinet_name")]


def _node_of(db: Database, row):
    """The node whose I/Q byte range contains this signal's address (else None)."""
    ab = _addr_byte(row.get("bit"))
    if not ab:
        return None
    kind, byte = ab
    for n in _nodes(db):
        s, e = n.get(f"{kind}_startByte", ""), n.get(f"{kind}_endByte", "")
        if s != "" and int(s) <= byte <= int(e):
            return n
    return None


def _group_by_node(db: Database, *script_types) -> list:
    """[(node_row, [rows of those script_types on the node])], in first-seen node order."""
    order, groups = [], {}
    for r in db.by_type(*script_types):
        n = _node_of(db, r)
        if n is None:
            continue
        if id(n) not in groups:
            groups[id(n)] = (n, [])
            order.append(id(n))
        groups[id(n)][1].append(r)
    return [groups[k] for k in order]


def _chunked(seq, n) -> list:
    seq = list(seq)
    return [seq[i:i + n] for i in range(0, len(seq), n)]


@builds("00_Only for Commissioning")
def build_00_commissioning(db: Database) -> Table:
    """One commissioning-bypass network per Profinet IO-device node - the nodes that carry a diagnosis
    member (a non-empty name_in_db, i.e. those in PROFINET_NODES_ALARM/WARNING); the PLC/CM heads + their
    partner cards are skipped. Both the `00_Commissioning` DB member and the network title are the node's
    "<profinet_name> <profinet_ip>"."""
    t = Table("00_Only for Commissioning")
    for n in db.where(lambda r: r.get("profinet_name") and r.get("name_in_db")):
        node = f"{n['profinet_name']} {n['profinet_ip']}".strip()
        t.add(
            template_type="01",
            **{"00_Commissioning.{db_element}": node},
            NetworkComment=node,
        )
    return t


@builds("06_Feedback Error")
def build_06_feedback_error(db: Database) -> Table:
    """One 03_FDBACK error FB instance per node: the node's KQ contactor-feedback members (grouped by
    address range), chunked to the FB's 8 IN/OUT slots. The iterator (each KQ's name_in_db) names a member
    in BOTH 03_FDBACK_RAW (the FDBACK ERROR n inputs) and 03_FDBACK (the ERROR n outputs); it is padded to
    8 with PAD. Commissioning_bypass is the node's '<profinet_name> <profinet_ip>'."""
    SLOTS = 8   # the FB's FDBACK ERROR 1..8 / ERROR 1..8
    t = Table("06_Feedback Error")
    for node, members in _group_by_node(db, "KQ"):
        ident = f"{node['profinet_name']} {node['profinet_ip']}".strip()
        for i, chunk in enumerate(_chunked(members, SLOTS), start=1):
            inst = f"FDBK_ERR_{node['profinet_name']}_{i}"
            names = [m["name_in_db"] for m in chunk]
            names += [PAD] * (SLOTS - len(names))
            t.add(
                template_type="01",
                **{"instanceOf-03_FDBACK error": inst},
                **{"00_Commissioning.{db_element}": ident},
                NetworkComment=f"{inst} {node['profinet_ip']}",
                ITERATOR_STRINGS=names,
            )
    return t


@builds("07_Speed Control")
def build_07_speed_control(db: Database) -> Table:
    """One 01_Speed_Control_SLS FB instance per safety-encoder pair (N1/2 + N2/2 grouped by numeric index =
    the sorter number nn). The 04_SPEED outputs are the sensors' healthy members + the 'Safety Encoder
    Failure [ <FLD> ]' member; SPEED_ZERO -> SPEED_STATE_REC.SORTER_{nn}_STOPPED."""
    enc1_by_idx, enc2_by_idx, order = {}, {}, []
    for r in db.rows:
        st = str(r.get("script_type", "")).upper()
        idx = str(r.get("index", "")).strip()
        if not idx.isdigit():
            continue
        if st == "N1/2" and idx not in enc1_by_idx:
            enc1_by_idx[idx] = r
            order.append(idx)
        elif st == "N2/2":
            enc2_by_idx.setdefault(idx, r)

    t = Table("07_Speed Control")
    for idx in order:
        enc1 = enc1_by_idx[idx]
        enc2 = enc2_by_idx.get(idx)
        nn = f"{int(idx):02d}"
        t.add(
            template_type="01",
            **{"instanceOf-01_Speed_Control_SLS": f"SLS_SORTER_{nn}"},
            **{"tagName:EncoderSensor1": enc1.get("name_in_tagtable", "")},
            **{"tagName:EncoderSensor2": enc2.get("name_in_tagtable", "") if enc2 else ""},
            **{"tagName:SorterRunningIOC": f"PNC_I_SORTER-{nn} SORTER RUNNING"},
            **{"04_SPEED.{db_element:ENC1/2}": enc1.get("name_in_db", "")},
            **{"04_SPEED.{db_element:ENC2/2}": enc2.get("name_in_db", "") if enc2 else ""},
            **{"04_SPEED.{db_element:ENC}": f"Safety Encoder Failure [ {enc1.get('iol_FLD', '')} ]"},
            **{"SPEED_STATE_REC.SORTER_{index}_STOPPED": f"SORTER_{nn}_STOPPED"},
            NetworkComment=f"SORTER {nn} SPEED CONTROL",
        )
    return t
