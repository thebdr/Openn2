"""Render the classified before/after result to a self-contained graphical HTML dashboard.

A single standalone .html (inline CSS, no dependency, light/dark aware, print-friendly) - the
"show-quality" artifact for a "what went wrong" review. The honest structure: genuine defects and
regressions are headlined; systematic re-schemes are shown as their own netted-out section; upgrades are
positive (amber). Numbers come straight from `classify`.
"""
from __future__ import annotations

import html

_C = {"intact": "#0ca30c", "corrected": "#d03b3b", "regression": "#791f1f",
      "upgrade": "#e0991a", "systematic": "#7a7a73", "minor": "#f09595",
      "major": "#e24b4a", "critical": "#d03b3b", "neutral": "#888780"}


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
    """rows = [(label, count)] -> horizontal bars scaled to the max."""
    top = max((n for _, n in rows), default=0) or 1
    out = []
    for label, n in rows:
        out.append(f'<div class="hb"><span class="hb-l">{esc(label)}</span>'
                   f'<span class="hb-t"><span class="hb-f" style="width:{100*n/top:.0f}%;background:{color}">'
                   f'</span></span><span class="hb-n">{esc(n)}</span></div>')
    return "".join(out)


def _table(headers: list, rows: list, empty: str = "none") -> str:
    if not rows:
        return f'<p class="empty">{esc(empty)}</p>'
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


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
    seg = [(100 * intact / matched, _C["intact"], f'Intact {intact}'),
           (100 * bt["critical"] / matched, _tier_color("critical"), f'Critical {bt["critical"]}'),
           (100 * bt["major"] / matched, _tier_color("major"), f'Major {bt["major"]}'),
           (100 * bt["minor"] / matched, _tier_color("minor"), f'Minor {bt["minor"]}')]

    struct_summary = [[_badge(s["tier"], _tier_color(s["tier"])), esc(s["label"]),
                       s["rows"], s["nodes"]] for s in structural]
    grouped = iol.get("grouped_changes", [])
    gnode_rows = [[_badge(g["tier"], _tier_color(g["tier"])), esc(g["node"]), esc(g["label"]), g["count"]]
                  for g in grouped[:40]]
    gmore = (f'<p class="empty">+ {len(grouped) - 40} more node-groups in the CSV audit trail</p>'
             if len(grouped) > 40 else "")
    ctx = ""
    if iol["systematic_events"]:
        joined = "; ".join(f'{esc(e["label"])} — {esc(e["summary"])}' for e in iol["systematic_events"])
        ctx = (f'<p class="hint" style="margin:8px 0 0">Pattern: {joined}. Coordinated (likely a re-base), '
               f'but every row is still a field to re-verify and apply on the machine.</p>')

    sev_panel = (f'<div class="panel"><h3>Changed rows by severity</h3>'
                 f'{_hbars([("Critical", bt["critical"]), ("Major", bt["major"]), ("Minor", bt["minor"])], _C["corrected"])}'
                 f'<h3 style="margin-top:14px">Itemized (non-structural) changes by direction</h3>'
                 f'{_hbars([("Gap-fill (old was blank)", iol["by_direction"]["gap-fill"]), ("Value change", iol["by_direction"]["value-change"]), ("Value loss (got worse)", iol["by_direction"]["value-loss"])], _C["major"])}</div>')
    up_rows = [[esc(u["node"]), f'+{u["count"]} rows', esc(u["desc"])] for u in iol["upgrades"]]
    up_panel = (f'<div class="panel"><h3>Upgrades <span class="hint">new feature blocks, not defects</span></h3>'
                f'{_table(["Node", "Added", "Description"], up_rows, "none")}</div>')

    crows = []
    for c in sorted(iol["corrections"], key=lambda c: -{"critical": 3, "major": 2, "minor": 1}.get(c["tier"], 0))[:80]:
        crows.append([_badge(c["tier"], _tier_color(c["tier"])) + (" " + _badge("value-loss", _C["regression"]) if c["regression"] else ""),
                      esc(c["node"]), esc(c["desc"]) or "—", _diff_cells(c["diffs"]),
                      _badge(c["confidence"], _C["neutral"]) if c["confidence"] != "high" else ""])
    more = f'<p class="empty">+ {len(iol["corrections"]) - 80} more in the CSV audit trail</p>' if len(iol["corrections"]) > 80 else ""
    blocks = [[esc(b["node"]), f'{b["channels"]} channels', _badge(b["tier"], _tier_color(b["tier"])), esc(b["desc"])]
              for b in iol["channel_blocks"]]

    return f'''<section>
  <h2>I/O list <span class="sub">{esc(iol["before"])} → {esc(iol["after"])} · {iol["before_rows"]}→{iol["after_rows"]} rows</span></h2>
  <div class="cards">{cards}</div>
  <div class="barwrap"><div class="bar-title">The {iol["matched"]} matched rows, by highest-severity change</div>{_bar(seg)}</div>
  <h3>Structural changes — grouped by node <span class="hint">address / slot / pin / device re-keying — the costliest to fix on a built machine, counted not hidden</span></h3>
  {_table(["Tier", "Field", "Rows", "Nodes"], struct_summary, "no structural changes")}
  {ctx}
  {f'<h4 style="margin:16px 0 4px;font-size:13px;font-weight:500">By node</h4>{_table(["Tier", "Node", "Field", "Rows"], gnode_rows)}{gmore}' if gnode_rows else ""}
  <div class="two">{sev_panel}{up_panel}</div>
  {f'<h3>Channel-uncertain blocks <span class="hint">multichannel attribution not provable — aggregated</span></h3>{_table(["Node", "Channels", "Tier", "Description"], blocks)}' if blocks else ""}
  <h3>Other corrections <span class="hint">non-structural field changes, itemized per row</span></h3>
  {_table(["Tier", "Node", "Description", "Change", "Note"], crows, "no other corrections")}
  {more}
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
        rollout = (f'<div class="panel"><h3>New effect column (upgrade)</h3><p>'
                   f'{esc(", ".join(ce["new_area_columns"]))} rolled out across {ce["rollout_rows"]} cause rows '
                   f'<span class="hint">a feature roll-out, not corrections</span></p></div>')
    lost = _table(["Cause", "Area", "Description"],
                  [[esc(x["concat_id"]), esc(x["area"]), esc(x["desc"])] for x in ce["effects_lost"]],
                  "no effects removed (good)")
    up = ""
    if ce.get("added_upgrade"):
        up = (f'<p class="notice good"><strong>Upgrade:</strong> +{ce["added_upgrade"]["count"]} new contiguous '
              f'cause rows ({esc(ce["added_upgrade"]["desc"])}) — a coherent new block.</p>')
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
        reorg = (f'<p class="notice"><strong>Structural reorganization:</strong> {area["moved"]} matched rows '
                 f'moved to a different AREA sheet. The area taxonomy was restructured — review whether intentional.</p>')
    crows = [[_badge(c["tier"], _tier_color(c["tier"])), esc(c.get("sheet_old")) + (" → " + esc(c.get("sheet_new")) if c.get("moved") else ""),
              esc(c["desc"]), _diff_cells(c["diffs"])] for c in area["corrections"][:50]]
    return f'''<section>
  <h2>AREA sheets <span class="sub">output-to-area assignment</span></h2>
  {reorg}
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
.hb-f{display:block;height:100%}.hb-n{flex:0 0 auto;width:34px;text-align:right;font-variant-numeric:tabular-nums}
table{border-collapse:collapse;width:100%;font-size:13px;margin:6px 0}
th{text-align:left;color:var(--mut);font-weight:500;border-bottom:1px solid var(--bd);padding:6px 9px}
td{border-bottom:1px solid var(--bd);padding:6px 9px;vertical-align:top}
code{background:var(--card);padding:1px 5px;border-radius:4px;font-size:12px}
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
<footer>Structural re-keying (I/O address / slot / pin / device tag) is the costliest correction to apply on a built machine, so it is COUNTED and grouped by node — not hidden. A coordinated re-map is flagged as context, but every changed row is still a field to re-verify on site. Other field changes are itemized per row and tagged by direction (gap-fill / value-change / value-loss). Tiers come from change_weights.csv. Full per-row detail is in the CSV audit trail beside this file.</footer>
</body></html>'''
