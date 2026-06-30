"""Row matching across two document revisions - node-scoped and ADDRESS-BLIND.

The hard problem (confirmed on real revision pairs): addresses, slots, pins AND device tags all get
re-schemed between revisions, so NO single field is a stable identity. The cascade therefore anchors on
the stable profinet NODE structure and the (functional-unit/location/device)+description text, and uses
the wiring (connector+pin) and position only as in-block tie-breakers - never the address. Validated on
the FVX R0.0->R1.2 pair: 883/883 old rows matched, 0 false buckets.

Each I/O List pair carries a TIER and a CONFIDENCE:
  T1 exact fld+desc (unique)      -> high
  T2cp dup-group by connector+pin -> high
  T2pos dup-group by position     -> channel-uncertain (the per-channel attribution is not provable)
  T3 within-node connector+pin    -> high (recovers device-tag renames where fld drifted)
  T4 within-node fuzzy desc/fld   -> fuzzy
  T5pos positional spacer fill    -> positional (layout scaffolding)
"""
from __future__ import annotations

import difflib
from collections import defaultdict

_TIER_CONFIDENCE = {"T1": "high", "T2cp": "high", "T2pos": "channel-uncertain",
                    "T3": "high", "T4": "fuzzy", "T5pos": "positional"}


def norm(value) -> str:
    """The comparison normal form: strip a leading Excel text-guard apostrophe, collapse whitespace,
    uppercase. (`'Q66307` == `Q66307`; `SAFETY  RELAY` == `SAFETY RELAY`.)"""
    text = str(value or "").strip()
    if text.startswith("'"):
        text = text[1:]
    return " ".join(text.split()).upper()


def fld(row: dict) -> str:
    return norm(row.get("functional_unit")) + "|" + norm(row.get("location")) + "|" + norm(row.get("device"))


def desc(row: dict) -> str:
    return norm(row.get("desc_l1")) + "|" + norm(row.get("desc_l1b"))


def _cp(row: dict) -> str:
    return norm(row.get("connector")) + "/" + norm(row.get("pin_no"))


def is_blank(row: dict) -> bool:
    """A layout-scaffolding spacer row: no fld AND no description (excluded from defect ratios)."""
    return fld(row) == "||" and desc(row) == "|"


def _rownum(row: dict) -> int:
    try:
        return int(row.get("_row") or 0)
    except (TypeError, ValueError):
        return 0


def assign_nodes(rows: list) -> None:
    """Carry each head row's profinet_name down to the rows beneath it (the IO node block). Rows before
    the first head share the synthetic node ''. Mutates each row's `_node`."""
    current = ""
    for row in rows:
        pn = norm(row.get("profinet_name"))
        if pn:
            current = pn
        row["_node"] = current


def match_iolist(old_rows: list, new_rows: list) -> dict:
    """The cascade. Returns {pairs, removed, added} where a pair is
    {'old','new','tier','confidence'}, removed = unmatched non-blank old rows, added = unmatched new rows.
    Operates on the reader's row dicts (canonical field names + `_row`/`_node`)."""
    assign_nodes(old_rows)
    assign_nodes(new_rows)

    def keymap(rows):
        out = defaultdict(list)
        for i, r in enumerate(rows):
            out[fld(r) + "#" + desc(r)].append(i)
        return out

    ok, nk = keymap(old_rows), keymap(new_rows)
    matched_old, used_new = set(), set()
    pairs: list = []
    blank_key = "||#|"

    def add(i, j, tier):
        pairs.append({"old": old_rows[i], "new": new_rows[j], "tier": tier,
                      "confidence": _TIER_CONFIDENCE[tier]})
        matched_old.add(i)
        used_new.add(j)

    # T1 - exact fld+desc, unique on both sides.
    for key, ois in ok.items():
        if key == blank_key:
            continue
        nis = nk.get(key, [])
        if len(ois) == 1 and len(nis) == 1:
            add(ois[0], nis[0], "T1")

    # T2 - fld+desc duplicate groups (multichannel devices): connector+pin, then positional.
    for key, ois in ok.items():
        if key == blank_key:
            continue
        nis = [j for j in nk.get(key, []) if j not in used_new]
        ois = [i for i in ois if i not in matched_old]
        if not ois or not nis:
            continue
        by_cp = defaultdict(list)
        for j in nis:
            by_cp[_cp(new_rows[j])].append(j)
        leftover_old = []
        for i in ois:
            cand = by_cp.get(_cp(old_rows[i]))
            if cand:
                add(i, cand.pop(0), "T2cp")
            else:
                leftover_old.append(i)
        leftover_new = [j for j in nis if j not in used_new]
        leftover_old.sort(key=lambda i: _rownum(old_rows[i]))
        leftover_new.sort(key=lambda j: _rownum(new_rows[j]))
        for i, j in zip(leftover_old, leftover_new):
            add(i, j, "T2pos")

    # T3 - within-node exact connector+pin (recovers a device-tag rename where fld drifted).
    for i in [i for i in range(len(old_rows)) if i not in matched_old and not is_blank(old_rows[i])]:
        node, cp = old_rows[i]["_node"], _cp(old_rows[i])
        best = None
        for j in range(len(new_rows)):
            if j in used_new or new_rows[j]["_node"] != node:
                continue
            if cp != "/" and _cp(new_rows[j]) == cp:
                ratio = difflib.SequenceMatcher(None, desc(old_rows[i]), desc(new_rows[j])).ratio()
                if best is None or ratio > best[1]:
                    best = (j, ratio)
        if best and best[1] >= 0.5:
            add(i, best[0], "T3")

    # T4 - within-node fuzzy desc (0.6) + fld (0.4) - the rename safety net.
    for i in [i for i in range(len(old_rows)) if i not in matched_old and not is_blank(old_rows[i])]:
        node, best = old_rows[i]["_node"], None
        for j in range(len(new_rows)):
            if j in used_new or new_rows[j]["_node"] != node or is_blank(new_rows[j]):
                continue
            ratio = (0.6 * difflib.SequenceMatcher(None, desc(old_rows[i]), desc(new_rows[j])).ratio()
                     + 0.4 * difflib.SequenceMatcher(None, fld(old_rows[i]), fld(new_rows[j])).ratio())
            if best is None or ratio > best[1]:
                best = (j, ratio)
        if best and best[1] >= 0.6:
            add(i, best[0], "T4")

    # T5 - within-node positional fill (blank<->blank preferred); HARD GUARD: never pair a blank-device
    # old row to a device-NAMED new row (the one mislabel kind the audit found).
    free_new = defaultdict(list)
    for j in range(len(new_rows)):
        if j not in used_new:
            free_new[new_rows[j]["_node"]].append(j)
    for i in sorted([i for i in range(len(old_rows)) if i not in matched_old],
                    key=lambda i: _rownum(old_rows[i])):
        cands = [j for j in free_new[old_rows[i]["_node"]] if j not in used_new]
        if not cands:
            continue
        if is_blank(old_rows[i]):
            cands = [j for j in cands if is_blank(new_rows[j])]
            if not cands:                                # GUARD: a blank old row never pairs to a named new
                continue                                 # row (else a real added signal is hidden) - leave it
        else:
            cands = [j for j in cands if not is_blank(new_rows[j])] or cands
        cands.sort(key=lambda j: _rownum(new_rows[j]))
        add(i, cands[0], "T5pos")

    # removed = unmatched NON-BLANK old rows (an unmatched blank spacer is layout, not a deletion).
    removed = [old_rows[i] for i in range(len(old_rows))
               if i not in matched_old and not is_blank(old_rows[i])]
    added = [new_rows[j] for j in range(len(new_rows)) if j not in used_new]
    return {"pairs": pairs, "removed": removed, "added": added}


def _ce_key(row: dict) -> str:
    return norm(row.get("concat_id")) or (norm(row.get("functional_unit"))
                                          + norm(row.get("location")) + norm(row.get("device")))


def match_ce(old_rows: list, new_rows: list) -> dict:
    """C&E cause-row matching by CONCATENATE ID (fallback FU+LOC+DEV) - a clean 1:1 key. Duplicate keys
    resolve positionally. Returns {pairs, removed, added} (pair = {'old','new'})."""
    nk = defaultdict(list)
    for j, r in enumerate(new_rows):
        nk[_ce_key(r)].append(j)
    used_new, pairs, matched_old = set(), [], set()
    for i, r in enumerate(old_rows):
        cand = [j for j in nk.get(_ce_key(r), []) if j not in used_new]
        if cand:
            j = cand[0]
            pairs.append({"old": r, "new": new_rows[j]})
            used_new.add(j)
            matched_old.add(i)
    removed = [old_rows[i] for i in range(len(old_rows)) if i not in matched_old]
    added = [new_rows[j] for j in range(len(new_rows)) if j not in used_new]
    return {"pairs": pairs, "removed": removed, "added": added}


def _area_key(row: dict) -> str:
    """A reorg-tolerant AREA-row identity: the line numbering + description (device tags/addresses are
    re-schemed, so they cannot key)."""
    return norm(row.get("line_numbering")) + "|" + norm(row.get("description"))


def match_area(old_pool: list, new_pool: list) -> dict:
    """Best-effort cross-sheet AREA matching over the POOLED rows of all AREA sheets (areas get
    reorganized, so a row can move sheet). A device may legitimately appear in SEVERAL AREA sheets, so a
    SAME-area match is preferred before a cross-area (moved) one - otherwise a device staying in/spanning
    its area is mis-reported as a move. Each pair notes whether the row actually MOVED to a different sheet.
    Returns {pairs, removed, added}."""
    nk_sheet: dict = defaultdict(list)       # (sheet, line+desc) -> [j]   same-area exact
    nk: dict = defaultdict(list)             # line+desc          -> [j]   cross-area (a move)
    nk_desc_sheet: dict = defaultdict(list)  # (sheet, desc)      -> [j]   same-area, line changed
    nk_desc: dict = defaultdict(list)        # desc               -> [j]   cross-area, line changed
    for j, r in enumerate(new_pool):
        key, d, s = _area_key(r), norm(r.get("description")), r.get("_sheet")
        nk_sheet[(s, key)].append(j)
        nk[key].append(j)
        if d:                                # a BLANK description can't key a desc-only match
            nk_desc_sheet[(s, d)].append(j)
            nk_desc[d].append(j)
    used_new, pairs, matched_old = set(), [], set()

    def take(i, j):
        pairs.append({"old": old_pool[i], "new": new_pool[j],
                      "moved": old_pool[i].get("_sheet") != new_pool[j].get("_sheet")})
        used_new.add(j)
        matched_old.add(i)

    def sweep(candidates):
        for i, r in enumerate(old_pool):
            if i in matched_old:
                continue
            cand = [j for j in candidates(r) if j not in used_new]
            if cand:
                take(i, cand[0])

    sweep(lambda r: nk_sheet.get((r.get("_sheet"), _area_key(r)), []))                            # 0 same-area exact
    sweep(lambda r: nk_desc_sheet.get((r.get("_sheet"), norm(r.get("description"))), []))         # 1 same-area, line changed
    sweep(lambda r: nk.get(_area_key(r), []))                                                     # 2 cross-area (a move)
    sweep(lambda r: nk_desc.get(norm(r.get("description")), []))                                  # 3 cross-area, line changed
    removed = [old_pool[i] for i in range(len(old_pool)) if i not in matched_old]
    added = [new_pool[j] for j in range(len(new_pool)) if j not in used_new]
    return {"pairs": pairs, "removed": removed, "added": added}
