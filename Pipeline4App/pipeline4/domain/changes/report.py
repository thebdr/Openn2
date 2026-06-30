"""Render the classified before/after result to a self-contained graphical HTML dashboard.

A single standalone .html (inline CSS, no dependency, light/dark aware, print-friendly) - the
"show-quality" artifact for a "what went wrong" review. The honest structure: genuine defects and
regressions are headlined; systematic re-schemes are shown as their own netted-out section; upgrades are
positive (amber). Numbers come straight from `classify`.
"""
from __future__ import annotations

import html
import re
from collections import Counter, defaultdict

_C = {"intact": "#0ca30c", "corrected": "#d03b3b", "regression": "#791f1f",
      "upgrade": "#e0991a", "systematic": "#7a7a73",
      "critical": "#a32d2d", "major": "#e24b4a", "minor": "#f09595",   # dark red / red / light red
      "unused": "#c4c2ba", "complementary": "#8f8d84", "neutral": "#888780"}   # light grey / mid grey


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _card(label: str, value, accent: str = "") -> str:
    dot = f'<span class="dot" style="background:{accent}"></span>' if accent else ""
    return (f'<div class="card"><div class="card-l">{dot}{esc(label)}</div>'
            f'<div class="card-v">{esc(value)}</div></div>')


def _badge(text: str, color: str) -> str:
    return f'<span class="badge" style="--bc:{color}">{esc(text)}</span>'


def _bar(segments: list) -> str:
    """segments = [(width_pct, color, label)]; renders a stacked bar + a legend."""
    cells = "".join(f'<div style="width:{w:.1f}%;background:{c}"></div>' for w, c, _ in segments if w > 0)
    legend = "".join(f'<span class="lg"><span class="sw" style="background:{c}"></span>{esc(label)}</span>'
                     for _, c, label in segments if label)
    return f'<div class="bar">{cells}</div><div class="legend">{legend}</div>'


def _hbars(rows: list, color: str) -> str:
    """rows = [(label, count)] -> horizontal bars whose fill is each value's SHARE OF THE GROUP TOTAL, so
    the bar lengths read as real percentages (they add up to 100%). The count + % are shown."""
    total = sum(n for _, n in rows) or 1
    out = []
    for label, n in rows:
        pct = 100 * n / total
        out.append(f'<div class="hb"><span class="hb-l">{esc(label)}</span>'
                   f'<span class="hb-t"><span class="hb-f" style="width:{pct:.0f}%;background:{color}">'
                   f'</span></span><span class="hb-n">{esc(n)} · {pct:.0f}%</span></div>')
    return "".join(out)


def _table(headers: list, rows: list, empty: str = "none") -> str:
    if not rows:
        return f'<p class="empty">{esc(empty)}</p>'
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


_ADDR_FIELDS = {"bit", "address", "digital_output"}
_ADDR_RE = re.compile(r"^\s*([IQO])\s*\.?\s*(\d+(?:\.\d+)*)\s*$", re.IGNORECASE)


def _decompose(addr) -> tuple | None:
    """A PLC address -> (prefix, [coords]) or None. Handles both Siemens-compact `I922.0` (coords
    [922, 0]) and node-qualified `I.10.0.0` (coords [10, 0, 0]). The LAST coord is always the bit."""
    m = _ADDR_RE.match(str(addr or ""))
    return (m.group(1).upper(), m.group(2).split(".")) if m else None


def _parts(dec: tuple) -> tuple:
    """(prefix, node|None, byte|None, bit) from a decomposition. 2 coords -> (byte, bit); 3+ ->
    (node, byte, bit) [node-qualified: node . byte . bit]."""
    pf, c = dec
    if len(c) >= 3:
        return pf, c[0], c[1], c[-1]
    if len(c) == 2:
        return pf, None, c[0], c[1]
    return pf, None, None, (c[0] if c else "")


def _hl(s) -> str:
    return f'<span class="hl">{esc(s)}</span>'


def _mu(s) -> str:
    return f'<span class="mut2">{esc(s)}</span>'


def _address_lines(changes: list) -> str:
    """Style B: qualitative transformation lines for a node's I/O address changes. Each change is
    classified by WHICH component differs - direction flip (in<->out), node move, byte relocation, or bit
    reshuffle - grouped, and rendered most-impacted first with only the differing component highlighted."""
    flips: dict = defaultdict(list)      # (pf_old, pf_new, byte) -> [bit]
    nodes: dict = defaultdict(int)       # (pf, old_node, new_node) -> count
    relocs: dict = defaultdict(list)     # (pf, old_byte, new_byte) -> [(old_bit, new_bit)]
    shuffles: dict = defaultdict(list)   # (pf, byte) -> [(old_bit, new_bit)]
    others: list = []
    for old, new in changes:
        do, dn = _decompose(old), _decompose(new)
        if not do or not dn:
            others.append((old, new))
            continue
        pfo, no, byo, bio = _parts(do)
        pfn, nn, byn, bin_ = _parts(dn)
        if pfo != pfn:
            flips[(pfo, pfn, byo)].append(bio)
        elif no != nn:
            nodes[(pfo, no, nn)] += 1
        elif byo != byn:
            relocs[(pfo, byo, byn)].append((bio, bin_))
        elif bio != bin_:
            shuffles[(pfo, byo)].append((bio, bin_))
        else:
            others.append((old, new))

    lines: list = []                     # (priority, count, html)
    for (pfo, pfn, by), bits in flips.items():
        direction = "input→output" if pfo == "I" else "output→input"
        lines.append((4, len(bits), f'{_hl("⚠ Direction flip (" + direction + ")")} — '
                      f'{esc(pfo)}{_mu(by)} → {_hl(pfn)}{_mu(by)} {_mu("(" + " ".join("." + b for b in bits) + ")")}'))
    for (pf, on, nn), count in nodes.items():
        lines.append((3, count, f'{_mu("Node move")} — {esc(pf)}.{_hl(on)} → {esc(pf)}.{_hl(nn)} '
                      f'{_mu("(" + str(count) + " addr · byte.bit unchanged)")}'))
    for (pf, byo, byn), pairs in relocs.items():
        if all(a == b for a, b in pairs):
            detail = _mu(f'({len(pairs)} ch · ' + " ".join("." + a for a, _ in pairs) + ")")
        else:
            detail = _mu("bits ") + " ".join(_hl(f"{a}→{b}") for a, b in pairs)
        lines.append((2, len(pairs), f'{_mu("Byte relocation")} — {esc(pf)}{_hl(byo)} → {esc(pf)}{_hl(byn)} {detail}'))
    for (pf, by), pairs in shuffles.items():
        lines.append((1, len(pairs), f'{_mu("Bit reshuffle in " + pf + by)} — '
                      + " · ".join(_hl(f"{a}→{b}") for a, b in pairs)))
    for old, new in others:
        lines.append((0, 1, f'<code>{esc(old)}</code> → <code>{esc(new)}</code>'))

    lines.sort(key=lambda x: (-x[0], -x[1]))
    cap = 12
    out = "".join(f'<div class="aln">{h}</div>' for _, _, h in lines[:cap])
    if len(lines) > cap:
        out += f'<div class="empty">+ {len(lines) - cap} more transformations in the CSV</div>'
    return out


def _changes_cell(field: str, changes: list) -> str:
    """The per-node 'Changes' cell: qualitative address lines for an address field, else the dedup list."""
    return _address_lines(changes) if field in _ADDR_FIELDS else _changes_inline(changes)


def _block_changes(block: dict) -> str:
    """WHAT changed in a per-device block: per field, the tier, the direction tag(s) (gap-fill /
    value-change / value-loss), and the old -> new values across the device's rows (deduped with x N)."""
    lines = []
    for f in block.get("fields", []):
        dirs = " ".join(_badge(d, _dir_color(d)) for d in f.get("directions", []))
        lines.append(f'<code>{esc(f["field"])}</code> {_badge(f["tier"], _tier_color(f["tier"]))} {dirs} '
                     f'{_changes_inline(f["values"])}')
    body = "<br>".join(lines) or "—"
    if block.get("desc"):
        body = f'{_mu(block["desc"])}<br>{body}'
    return body


def _scope(block: dict) -> str:
    """The block's scope: a single device's fld, else 'N devices · M rows'."""
    if block.get("devices", 1) > 1:
        return f'{block["devices"]} devices · {block["count"]} rows'
    return esc(block.get("fld") or "") or f'{block.get("count", 0)} rows'


def _changes_inline(changes: list, cap: int = 24) -> str:
    """An inline old → new list for a node's structural changes, e.g. `I922.0 → I1120.0 · …`. DISTINCT
    pairs (a repeated low-cardinality change like a re-slot collapses to `…×N`); capped with a '+N more'
    tail (the full per-row list is in the CSV audit trail)."""
    if not changes:
        return ""
    counts = Counter((str(o), str(n)) for o, n in changes)        # first-seen order preserved
    cells = []
    for (o, n), c in list(counts.items())[:cap]:
        mult = f' <span class="empty">×{c}</span>' if c > 1 else ""
        cells.append(f'<code>{esc(o) or "∅"}</code> → <code>{esc(n) or "∅"}</code>{mult}')
    tail = f' <span class="empty">+{len(counts) - cap} more</span>' if len(counts) > cap else ""
    return "  ·  ".join(cells) + tail


def _diff_cells(diffs: list) -> str:
    return "<br>".join(f'<code>{esc(d["field"])}</code>: {esc(d["old"]) or "∅"} → {esc(d["new"]) or "∅"} '
                       f'{_badge(d["direction"], _dir_color(d["direction"]))}' for d in diffs)


def _dir_color(direction: str) -> str:
    return {"value-loss": _C["regression"], "value-change": _C["corrected"],
            "gap-fill": _C["major"]}.get(direction, _C["neutral"])


def _tier_color(tier: str) -> str:
    return _C.get(tier, _C["neutral"])


def _unavailable(title: str, note: str) -> str:
    return (f'<section><h2>{esc(title)}</h2><p class="notice"><strong>No prior revision to compare.</strong> '
            f'{esc(note)} Point the <code>*_previous_path</code> in project_params.yaml at the prior '
            f'document revision to enable the before/after comparison.</p></section>')


def _iolist_section(iol: dict) -> str:
    if not iol.get("available"):
        return _unavailable("I/O list", iol.get("reason", ""))
    matched = iol["matched"] or 1
    intact, changed = iol["intact"], iol["changed"]
    bt = iol["by_tier"]
    structural = iol.get("structural", [])
    address = next((s for s in structural if s["field"] == "bit"), None)
    addr_rows = address["rows"] if address else 0
    cards = "".join([
        _card("Matched rows", iol["matched"]),
        _card("Intact", intact, _C["intact"]),
        _card("Changed rows", changed, _C["corrected"]),
        _card("I/O address changes", addr_rows, _C["critical"] if addr_rows else _C["neutral"]),
        _card("Upgrade rows", f'+{iol["upgrade_rows"]}', _C["upgrade"]),
        _card("Removed", len(iol["removed"]), _C["neutral"]),
    ])
    unused, comp = iol.get("unused", 0), iol.get("complementary", 0)
    added = iol.get("added_total", 0)
    new_total = (matched + added) or 1                    # = the new revision's row count (matched + added)
    seg = [(100 * unused / new_total, _C["unused"], f'No description (unused) {unused}'),
           (100 * comp / new_total, _C["complementary"], f'Complementary review {comp}'),
           (100 * intact / new_total, _C["intact"], f'Intact {intact}'),
           (100 * bt["critical"] / new_total, _C["critical"], f'Critical {bt["critical"]}'),
           (100 * bt["major"] / new_total, _C["major"], f'Major {bt["major"]}'),
           (100 * bt["minor"] / new_total, _C["minor"], f'Minor {bt["minor"]}'),
           (100 * added / new_total, _C["upgrade"], f'Added / retrofit {added}')]

    struct_summary = [[_badge(s["tier"], _tier_color(s["tier"])), esc(s["label"]),
                       s["rows"], s["nodes"]] for s in structural]
    addr = next((s for s in structural if s["field"] == "bit"), None)
    addr_callout = ""
    if addr:
        addr_callout = (f'<p class="notice" style="border-left-color:{_C["critical"]}">'
                        f'<strong>{addr["rows"]} I/O address changes across {addr["nodes"]} nodes</strong> '
                        f'{_badge("critical", _C["critical"])}<br>An address change is the most time-consuming fix '
                        f'on a built machine — re-read the manuals, re-test on site, and propagate to every affected '
                        f'device. The exact old → new values are listed by node below.</p>')
    grouped = iol.get("grouped_changes", [])
    gnode_rows = [[_badge(g["tier"], _tier_color(g["tier"])), esc(g["node"]), esc(g["label"]),
                   g["count"], _changes_cell(g["field"], g.get("changes", []))] for g in grouped[:60]]
    gmore = (f'<p class="empty">+ {len(grouped) - 60} more node-groups in the CSV audit trail</p>'
             if len(grouped) > 60 else "")
    ctx = ""
    if iol["systematic_events"]:
        joined = "; ".join(f'{esc(e["summary"])}' for e in iol["systematic_events"])
        ctx = (f'<p class="hint" style="margin:8px 0 0">These follow a coordinated re-map ({joined}) — '
               f'but each row is still a separate address to re-verify and apply on site, not a free pass.</p>')

    sev_panel = (f'<div class="panel"><h3>Changed rows by severity <span class="hint">share of the {changed} changed rows</span></h3>'
                 f'{_hbars([("Critical", bt["critical"]), ("Major", bt["major"]), ("Minor", bt["minor"])], _C["corrected"])}'
                 f'<h3 style="margin-top:14px">Field changes by direction <span class="hint">share of the field-edits — a row can change several fields</span></h3>'
                 f'{_hbars([("Gap-fill (old was blank)", iol["by_direction"]["gap-fill"]), ("Value change", iol["by_direction"]["value-change"]), ("Value loss (got worse)", iol["by_direction"]["value-loss"])], _C["major"])}</div>')
    up_blocks = []
    for u in sorted(iol["upgrades"], key=lambda u: -u["count"]):
        drows = [[esc(r["desc"]), _mu(r["fld"]), (f'<code>{esc(r["address"])}</code>' if r["address"] else "")]
                 for r in u.get("rows", [])]
        hidden = u["count"] - len(u.get("rows", []))
        extra = f'<p class="empty">+ {hidden} rows without a description (layout)</p>' if hidden > 0 else ""
        up_blocks.append(
            f'<div style="margin:14px 0 4px">{_badge("retrofit", _C["upgrade"])} '
            f'<strong>{esc(u["node"])}</strong> {_mu("· +" + str(u["count"]) + " rows")}</div>'
            f'{_table(["Description", "FLD", "I/O address"], drows, "—")}{extra}')
    forgotten_n = len(iol.get("forgotten", []))
    fnote = (f'<p class="hint">Plus {forgotten_n} isolated forgotten signal(s) — a single row added inside an '
             f'existing block (a smaller "something was missed").</p>' if forgotten_n else "")
    up_section = (f'<h3 style="margin-top:26px">Upgrades and Retrofits '
                  f'<span class="hint">additions to the document</span></h3>'
                  f'<p class="notice" style="border-left-color:{_C["upgrade"]}">An addition is not a defect — '
                  f'but it means the original revision was incomplete, so <strong>something was missed</strong>. '
                  f'Review whether it should have been there from the start.</p>'
                  + ("".join(up_blocks) or '<p class="empty">no upgrades or retrofits</p>') + fnote)

    cblocks = sorted(iol.get("correction_blocks", []),
                     key=lambda b: (-{"critical": 3, "major": 2, "minor": 1}.get(b["tier"], 0), -b["count"]))

    def _conf_flag(b):
        return (f' {_badge("⚠ channel mapping unverified", _C["neutral"])}'
                if b.get("confidence") == "channel-uncertain" else "")
    crows = [[_badge(b["tier"], _tier_color(b["tier"])), esc(b["node"]) + _conf_flag(b), _scope(b),
              _block_changes(b)] for b in cblocks[:80]]
    more = f'<p class="empty">+ {len(cblocks) - 80} more device-blocks in the CSV audit trail</p>' if len(cblocks) > 80 else ""

    comp_blocks = sorted(iol.get("complementary_blocks", []),
                         key=lambda b: (-{"critical": 3, "major": 2, "minor": 1}.get(b["tier"], 0), -b["count"]))
    comp_rows = [[esc(b["node"]), _scope(b), _block_changes(b)] for b in comp_blocks[:60]]
    comp_section = (
        f'<h3 style="margin-top:22px">Complementary reviews '
        f'<span class="hint">changes on UNUSED channels (no description) — not defects today</span></h3>'
        f'<p class="notice" style="border-left-color:{_C["complementary"]}">A free slot that was re-addressed '
        f'is not a current defect — nothing is wired to it. But if a signal is added to it later, a wrong '
        f'address would reproduce the original class of mistake, so it is tracked for review.</p>'
        f'<div class="faded">{_table(["Node", "Scope", "What changed (old → new)"], comp_rows, "none")}</div>'
        ) if comp_blocks else ""

    noise_blocks = sorted(iol.get("noise_blocks", []),
                          key=lambda b: (-{"critical": 3, "major": 2, "minor": 1}.get(b["tier"], 0), -b["count"]))
    noise_rows = [[esc(b["node"]), _scope(b), _block_changes(b)] for b in noise_blocks[:60]]
    noise_section = (
        f'<h3 style="margin-top:22px">Noise — FLD cleanup '
        f'<span class="hint">FLD changes of only punctuation or a single character</span></h3>'
        f'<p class="notice" style="border-left-color:{_C["neutral"]}">These FLD values differ only by '
        f'punctuation or a single character — a stray text-guard apostrophe, a whitespace tweak, a one-char '
        f'typo or renumber. A human reading the sheet normalizes past them without thinking; '
        f'<strong>the software may not</strong> — it can read <code>-&#39;Q66305</code> and '
        f'<code>-Q66305</code> as two different identities and break the cross-document join, unless that '
        f'normalization is explicitly managed. Counts unchanged; listed here only.</p>'
        f'{_table(["Node", "Scope", "What changed (old → new)"], noise_rows, "none")}') if noise_blocks else ""

    return f'''<section>
  <h2>I/O list <span class="sub">{esc(iol["before"])} → {esc(iol["after"])} · {iol["before_rows"]}→{iol["after_rows"]} rows</span></h2>
  <div class="cards">{cards}</div>
  <div class="barwrap"><div class="bar-title">The {iol["after_rows"]} rows of the new revision, by highest-severity change</div>{_bar(seg)}</div>
  {sev_panel}
  <h3>Structural changes — grouped by node <span class="hint">address / slot / pin / device re-keying — the MOST TIME-CONSUMING to fix on a built machine, counted not hidden</span></h3>
  {addr_callout}
  {_table(["Tier", "Field", "Rows", "Nodes"], struct_summary, "no structural changes")}
  {ctx}
  {f'<h4 style="margin:16px 0 4px;font-size:13px;font-weight:500">By node — old → new</h4><p class="notice" style="border-left-color:{_C["critical"]}">The per-node breakdown of the structural re-keying above — the actual old → new values, grouped by transformation (byte relocation, bit reshuffle, in↔out flip, device rename). Each is a field to re-verify and apply on the machine.</p>{_table(["Tier", "Node", "Field", "Rows", "Changes (old → new)"], gnode_rows)}{gmore}' if gnode_rows else ""}
  <h3>Corrections — by node <span class="hint">non-structural field edits, grouped per node, with direction</span></h3>
  <p class="notice" style="border-left-color:{_C["corrected"]}">Genuine content fixes on REAL (described) signals — descriptions, type, safety contact sense, terminal refs — grouped per node and tagged by direction: gap-fill (a blank finally filled), value-change (a value corrected), or value-loss (a value that got worse). These are the "what went wrong" edits to review.</p>
  {_table(["Tier", "Node", "Scope", "What changed (old → new)"], crows, "no other corrections")}
  {more}
  <p class="hint" style="margin-top:6px"><span class="badge" style="--bc:{_C["neutral"]}">⚠ channel mapping unverified</span> = a multichannel device whose channels were re-addressed/re-pinned, so the edits are shown but not which specific channel got which.</p>
  {noise_section}
  {comp_section}
  {up_section}
</section>'''


def _cematrix_section(ce: dict) -> str:
    if not ce.get("available"):
        return _unavailable("Cause &amp; Effect matrix", ce.get("reason", ""))
    addr_rows = ce.get("structural_rows", 0)
    cards = "".join([
        _card("Cause rows", f'{ce["before_rows"]}→{ce["after_rows"]}'),
        _card("Intact", ce["intact"], _C["intact"]),
        _card("Address changes", addr_rows, _C["critical"] if addr_rows else _C["neutral"]),
        _card("Other corrections", ce["correction_count"], _C["corrected"]),
        _card("Effects lost", len(ce["effects_lost"]), _C["regression"]),
        _card("Added (upgrade)", f'+{ce["added_upgrade"]["count"]}' if ce.get("added_upgrade") else len(ce.get("added_corrections", [])), _C["upgrade"]),
    ])
    ctx = "; ".join(f'{esc(e["label"])} — {esc(e["summary"])}' for e in ce["systematic_events"])
    sys_panel = ""
    if addr_rows:
        sys_panel = (f'<div class="panel"><h3>I/O address changes <span class="hint">counted, not hidden</span></h3>'
                     f'<p>{addr_rows} cause rows changed I/O address {_badge("critical", _C["critical"])}'
                     f'{f"<br><span class=hint>Pattern: {ctx}</span>" if ctx else ""}</p></div>')
    rollout = ""
    if ce.get("new_area_columns"):
        rollout = (f'<div class="panel" style="border-left:3px solid {_C["upgrade"]}">'
                   f'<h3>New effect column <span class="badge" style="--bc:{_C["upgrade"]}">upgrade</span></h3><p>'
                   f'{esc(", ".join(ce["new_area_columns"]))} rolled out across {ce["rollout_rows"]} cause rows '
                   f'<span class="hint">a feature roll-out, not corrections</span></p></div>')
    lost = _table(["Cause", "Area", "Description"],
                  [[esc(x["concat_id"]), esc(x["area"]), esc(x["desc"])] for x in ce["effects_lost"]],
                  "no effects removed (good)")
    up = ""
    if ce.get("added_upgrade"):
        up = (f'<p class="notice" style="border-left-color:{_C["upgrade"]}"><strong style="color:{_C["upgrade"]}">'
              f'Upgrade:</strong> +{ce["added_upgrade"]["count"]} new contiguous cause rows '
              f'({esc(ce["added_upgrade"]["desc"])}) — a coherent new block.</p>')
    crows = [[_badge(c["tier"], _tier_color(c["tier"])), esc(c.get("concat_id")), esc(c["desc"]), _diff_cells(c["diffs"])]
             for c in ce["corrections"][:60]]
    return f'''<section>
  <h2>Cause &amp; Effect matrix <span class="sub">{esc(ce["before"])} → {esc(ce["after"])}</span></h2>
  <div class="cards">{cards}</div>
  <div class="two">{sys_panel}{rollout}</div>
  {up}
  <h3>Effects removed <span class="hint">a deleted effect is safety-critical — review</span></h3>
  {lost}
  <h3>Cause-row corrections</h3>
  {_table(["Tier", "Cause", "Description", "Change"], crows, "no isolated corrections")}
</section>'''


def _area_section(area: dict) -> str:
    if not area.get("available"):
        return ""
    counts = sorted(set(area["counts_old"]) | set(area["counts_new"]))
    crow = [[esc(s), area["counts_old"].get(s, 0), area["counts_new"].get(s, 0),
             _badge("reorganized", _C["upgrade"]) if any(r["sheet"] == s for r in area["reorganized"]) else ""]
            for s in counts]
    reorg = ""
    if area["reorganized"] or area["moved"]:
        reorg = (f'<p class="notice" style="border-left-color:{_C["critical"]}"><strong>Structural '
                 f'reorganization:</strong> {area["moved"]} matched rows moved to a different AREA sheet — the '
                 f'output-to-area assignment changed. <strong>This is safety-critical:</strong> moving a device '
                 f'between areas can mean the safety logic no longer protects against the real hazard — the cause '
                 f'that trips that output now belongs to a different zone. Confirm every move below is intentional '
                 f'and that the new area is the correct protection zone.</p>')

    def _mv_addr(m):                                       # show old → new only when the output address moved too
        a, b = str(m.get("addr_old") or "").strip(), str(m.get("addr_new") or "").strip()
        return f'{esc(a)} → {esc(b)}' if a != b else esc(a)
    moves = area.get("moves", [])
    move_rows = [[esc(m["device_tag"]), esc(m["desc"]),
                  f'{esc(m["sheet_old"])} → {esc(m["sheet_new"])}', _mv_addr(m)] for m in moves[:200]]
    move_table = (f'<h3>What moved where '
                  f'<span class="hint">device · area reassignment · output address — each is a safety-zone change '
                  f'to confirm</span></h3>'
                  f'{_table(["Device", "Description", "Area: from → to", "Output address"], move_rows)}'
                  f'{f"<p class=empty>+ {len(moves) - 200} more moves in the CSV audit trail</p>" if len(moves) > 200 else ""}'
                  ) if moves else ""

    crows = [[_badge(c["tier"], _tier_color(c["tier"])), esc(c.get("sheet_old")) + (" → " + esc(c.get("sheet_new")) if c.get("moved") else ""),
              esc(c["desc"]), _diff_cells(c["diffs"])] for c in area["corrections"][:50]]
    return f'''<section>
  <h2>AREA sheets <span class="sub">output-to-area assignment</span></h2>
  {reorg}
  {move_table}
  <h3>Per-area row counts <span class="hint">before → after</span></h3>
  {_table(["Sheet", "Before", "After", ""], crow)}
  <h3>AREA corrections <span class="hint">device-tag / address / line changes on matched rows</span></h3>
  {_table(["Tier", "Sheet", "Description", "Change"], crows, "no AREA-row corrections")}
</section>'''


_STYLE = """
:root{--bg:#fbfbfa;--fg:#1a1a19;--mut:#6b6b66;--card:#f1efe8;--bd:#e1e0d9;--panel:#fff}
@media(prefers-color-scheme:dark){:root{--bg:#1a1a19;--fg:#ececec;--mut:#9a9a92;--card:#242422;--bd:#33332f;--panel:#202020}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;padding:28px 32px}
h1{font-size:22px;font-weight:600;margin:0 0 2px}h2{font-size:18px;font-weight:600;margin:34px 0 14px;border-bottom:1px solid var(--bd);padding-bottom:6px}
h3{font-size:14px;font-weight:600;margin:18px 0 8px}.sub,.hint{font-weight:400;color:var(--mut);font-size:13px}
.meta{color:var(--mut);font-size:13px;margin-bottom:6px}
.cards{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}
.card{flex:1;min-width:130px;background:var(--card);border-radius:10px;padding:11px 14px}
.card-l{font-size:12px;color:var(--mut);display:flex;align-items:center;gap:6px}.card-v{font-size:24px;font-weight:600;margin-top:2px}
.dot{width:9px;height:9px;border-radius:2px;display:inline-block}
.barwrap{margin:18px 0}.bar-title{font-size:12px;color:var(--mut);margin-bottom:6px}
.bar{display:flex;height:22px;border-radius:6px;overflow:hidden;border:1px solid var(--bd)}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:8px;font-size:12px;color:var(--mut)}
.lg{display:flex;align-items:center;gap:5px}.sw{width:10px;height:10px;border-radius:2px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:14px 0}
.panel{background:var(--card);border-radius:10px;padding:12px 15px}.panel h3{margin-top:0}
.hb{display:flex;align-items:center;gap:9px;font-size:12px;color:var(--mut);margin:7px 0}
.hb-l{flex:0 0 auto;max-width:62%}.hb-t{flex:1;height:12px;background:var(--bd);border-radius:4px;overflow:hidden}
.hb-f{display:block;height:100%}.hb-n{flex:0 0 auto;width:72px;text-align:right;font-variant-numeric:tabular-nums}
table{border-collapse:collapse;width:100%;font-size:13px;margin:6px 0}
th{text-align:left;color:var(--mut);font-weight:500;border-bottom:1px solid var(--bd);padding:6px 9px}
td{border-bottom:1px solid var(--bd);padding:6px 9px;vertical-align:top}
code{background:var(--card);padding:1px 5px;border-radius:4px;font-size:12px}
.hl{color:#d03b3b;font-weight:500}.mut2{color:var(--mut)}
.aln{font-size:12.5px;line-height:1.5;margin:2px 0}
.faded{opacity:.5}
.badge{font-size:11px;padding:1px 7px;border-radius:10px;color:#fff;background:var(--bc);white-space:nowrap}
.empty{color:var(--mut);font-size:13px;font-style:italic}
.notice{background:var(--card);border-left:3px solid var(--upg,#e0991a);padding:10px 14px;border-radius:0 8px 8px 0;font-size:13px}
.notice.good{border-left-color:#0ca30c}
ul{margin:4px 0;padding-left:18px;font-size:13px;color:var(--mut)}
footer{margin-top:34px;color:var(--mut);font-size:12px;border-top:1px solid var(--bd);padding-top:10px}
"""


def render_html(result: dict) -> str:
    meta = result["meta"]
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>I/O documents quality report — {esc(meta["project_code"])}</title>
<style>{_STYLE}</style></head><body>
<h1>Before vs after — document quality report</h1>
<div class="meta">Project {esc(meta["project_code"]) or "—"} · generated {esc(meta["generated"])} · a "what went wrong" review (not part of the pipeline)</div>
{_iolist_section(result["iolist"])}
{_cematrix_section(result["cematrix"])}
{_area_section(result["area"])}
<footer>Structural re-keying (I/O address / slot / pin / device tag) is the most time-consuming correction to apply on a built machine, so it is COUNTED and grouped by node — not hidden. A coordinated re-map is flagged as context, but every changed row is still a field to re-verify on site. Other field changes are itemized per row and tagged by direction (gap-fill / value-change / value-loss). Tiers come from change_weights.csv. Full per-row detail is in the CSV audit trail beside this file.</footer>
</body></html>'''
