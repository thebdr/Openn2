"""Phase 900 / 910 - the signal-paths report: every signal's logical paths through the generated program, drawn
FBD-style (user 2026-10-10: "draw an .html coverage report of each signal in fdb (or flowchart) style: each logical
path a signal follows").

The paths are FACTS of the generated program, never guesses - a GRAPH of variables (PLC tags, DB members) and the
places that read or write them:
  * every block network PL5 generates (`software_block_members`): a block PL5 renders READY (03 Zone Cumulative -
    an FC sized to its inputs, whatever the template's capacity) is traced from that rendered XML (`ready`, handed
    in by the system); a template-filled one (OP5 fills the template from the CreationInfo csv) from its template
    network - the block template's network numbered by the row's `TemplateType` (the templates are marker-less TIA exports - network k is variant
    k); a network READS the symbols its FBD wires into a part's input (an FB pin, a gate input, a contact's operand)
    and WRITES those a part output or a coil's operand drives (`template_variants`); the symbols are the row's
    placeholder values, `ITERATOR_STRINGS` handed out one per iterator access in document order (OP5's generator
    does the same). An FB whose numbered pins carry the iterator both ways (02 EM Push Button `IN_n` -> `OUT_n` /
    `Lamp_n`, 06 Feedback Error `FDBACK ERROR n` -> `ERROR n`) is traced per channel, so one push button never
    leads into another's member;
  * the machine-interface SCL (`interface_elements`): an outgoing element reads its expression and writes its
    interface tag, an incoming one the other way round - one node per assignment;
  * the diagnosis (`diagnosis_entries`): an entry reads its binding and raises its cabinet's alarm bit (an end);
  * the I/O List row (`coverage`): an input row feeds its PLC tag, an output row is the physical point its tag drives.
Each signal's page shows the subgraph upstream and downstream of its row, layered left to right like an FBD, and
lists every path from the row to an end (a physical output, an alarm bit, a symbol nothing reads). The seed pads
(`No Operation`, `AlwaysTRUE`, ...) are no symbols. One self-contained HTML (no network access): the graph is
embedded as JSON, a small script lays it out as SVG.

Place in the flow: run_reporting (910) calls `project` after the coverage report
(src://pipeline5/phases/coverage/coverage.py) over the same in-memory database; writes
ProjectDocumentation/Reports/io_signal_paths.html (`config.coverage_dir()`) - documentation, not a BuilderData
surface. A pure projection: returns notes, records nothing.
"""
from __future__ import annotations

import html
import json
import os
import re
import xml.etree.ElementTree as ET
from collections import deque

from pipeline5 import config

REPORT_FILE = "io_signal_paths.html"
_PLACEHOLDER = re.compile(r"!!(.+?)\$\$")
_ITERATOR = "!!ITERATOR_STRINGS$$"
_CHANNEL_PIN = re.compile(r"[_ ](\d+)\s*$")          # IN_1, Lamp_1, FDBACK ERROR 1 - never Bypass_ET200
# FBD parts whose `operand` pin is the variable they WRITE (any other operand - a contact - is read)
_WRITING_OPERANDS = {"Coil", "SCoil", "RCoil", "SR", "RS"}


# --- the templates' wiring --------------------------------------------------------------------- #
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _network_accesses(unit, placeholders_only: bool = True) -> list:
    """[(components, direction, channel)] of one template network, in document order: every placeholder-carrying
    variable, 'read' when it feeds a part's input pin (or is a contact's operand), 'write' when a part's output pin
    feeds it (or it is a coil's operand); `channel` = (call, n) when the pin is an FB call's numbered pin
    (`IN_1`, `Lamp_1`, `FDBACK ERROR 1`), else None."""
    access, calls, parts, uses = {}, set(), {}, {}
    order = []
    for el in unit.iter():
        name = _local(el.tag)
        if name == "Access":
            comps = tuple(c.get("Name", "") for c in el.iter() if _local(c.tag) == "Component")
            if comps and (any("!!" in c for c in comps) or not placeholders_only):
                access[el.get("UId")] = comps
                order.append(el.get("UId"))
        elif name == "Part":
            parts[el.get("UId")] = el.get("Name", "")
        elif name == "Call":
            calls.add(el.get("UId"))
    for wire in (el for el in unit.iter() if _local(el.tag) == "Wire"):
        ends = [(_local(c.tag), c.get("UId"), c.get("Name", "")) for c in wire]
        if not ends:
            continue
        source_is_variable = ends[0][0] == "IdentCon"
        pins = [(u, p) for k, u, p in ends if k == "NameCon"]
        for kind, uid, _pin in ends:
            if kind != "IdentCon" or uid not in access:
                continue
            if source_is_variable:
                writes = any(p == "operand" and parts.get(u) in _WRITING_OPERANDS for u, p in pins)
                direction = "write" if writes else "read"
            else:
                direction = "write"                     # a part output drives the variable
            channel = None
            for u, p in pins:
                m = _CHANNEL_PIN.search(p)
                if u in calls and m:
                    channel = (u, int(m.group(1)))
            uses.setdefault(uid, []).append((direction, channel))
    return [(access[uid], direction, channel) for uid in order for direction, channel in uses.get(uid, [])]


def template_variants(path: str) -> list:
    """The template's networks in document order - network k is the variant `TemplateType` k (marker-less TIA
    exports, as OP5's generator reads them) - each as `_network_accesses`. [] for a file that is no FBD export."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return []
    return [_network_accesses(unit) for unit in root.iter() if _local(unit.tag) == "SW.Blocks.CompileUnit"]


def _title(unit) -> str:
    for el in unit.iter():
        if _local(el.tag) == "MultilingualText" and el.get("CompositionName") == "Title":
            return next((t.text for t in el.iter() if _local(t.tag) == "Text" and t.text), "")
    return ""


def ready_networks(xml_text: str) -> list:
    """[(title, [(symbol parts, direction, channel)])] - the networks of a block PL5 rendered READY, every global
    variable as wired (its symbol already resolved). [] for text that is no block XML."""
    try:
        root = ET.fromstring(xml_text.lstrip("\ufeff"))
    except ET.ParseError:
        return []
    return [(_title(unit), _network_accesses(unit, placeholders_only=False))
            for unit in root.iter() if _local(unit.tag) == "SW.Blocks.CompileUnit"]


def resolve(components, values, item=None) -> tuple:
    """A template symbol with the network row's values put in (`item` = this access's iterator value); () when a
    placeholder has no value (an unused access)."""
    parts = []
    for comp in components:
        text = comp
        for key in _PLACEHOLDER.findall(comp):
            value = item if f"!!{key}$$" == _ITERATOR else values.get(key)
            if value in (None, "") or isinstance(value, (list, tuple)):
                return ()
            text = text.replace(f"!!{key}$$", str(value).strip())
        parts.append(text)
    return tuple(parts)


def symbol(parts) -> str:
    """The TIA spelling of a symbol: `"db"."member"` / `"tag"`."""
    return ".".join(f'"{p}"' for p in parts)


def parse_symbol(text: str) -> tuple:
    """A stored binding (`"db"."member"`, `"tag"`, a bare tag) -> its parts."""
    text = str(text or "").strip()
    quoted = re.findall(r'"([^"]*)"', text)
    return tuple(quoted) if quoted else ((text,) if text else ())


# --- the graph --------------------------------------------------------------------------------- #
class Graph:
    """Nodes (id -> kind, label, sub) and directed edges (writer -> variable -> reader). A variable's id is its
    case-folded symbol (TIA names are case-insensitive: the 02 template's `01_PushButton` is the DB
    `01_Pushbutton`)."""

    def __init__(self):
        self.nodes: dict = {}
        self.edges: set = set()

    def var(self, parts) -> str:
        node = "v:" + symbol(parts).lower()
        if node not in self.nodes:
            self.nodes[node] = ("tag" if len(parts) == 1 else "member", symbol(parts), "")
        return node

    def add(self, node, kind, label, sub=""):
        self.nodes.setdefault(node, (kind, label, sub))
        return node

    def edge(self, a, b):
        if a != b:
            self.edges.add((a, b))

    def adjacency(self, reverse: bool = False) -> dict:
        out: dict = {}
        for a, b in self.edges:
            if reverse:
                a, b = b, a
            out.setdefault(a, []).append(b)
        return out


def _rows(database, name):
    return list(database[name]) if name in database else []


def _values(member_row) -> dict:
    values = member_row.get("values") or {}
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except ValueError:
            values = {}
    return values


def network_symbols(variant, values, pads) -> list:
    """[(symbol parts, direction, channel)] of one generated network: its variant's accesses with the row's values,
    the iterator list handed out one value per iterator access in document order; pads and blanks dropped."""
    items = values.get("ITERATOR_STRINGS") or []
    items = list(items) if isinstance(items, (list, tuple)) else [items]
    out = []
    for comps, direction, channel in variant:
        item = None
        if any(_ITERATOR in c for c in comps):
            item = items.pop(0) if items else ""
        parts = resolve(comps, values, item)
        if parts and parts[-1].lower() not in pads:
            out.append((parts, direction, channel if item is not None else None))
    return out


def _wire_network(g, node, resolved):
    """The edges of one network node: its reads into it, its writes out of it."""
    for parts, direction, _channel in resolved:
        if direction == "read":
            g.edge(g.var(parts), node)
        else:
            g.edge(node, g.var(parts))


def build_graph(database, ready: dict | None = None) -> tuple:
    """(Graph, notes) from the SSOT tables - the block networks, the interface assignments, the diagnosis entries
    and the coverage rows (see the module doc); `ready` = {block name: the XML PL5 renders for it} for the blocks
    that ship ready. `notes` names what could not be wired (a block whose template is missing or no FBD export, a
    network whose TemplateType names no template network)."""
    pads = {str(p).lower() for p in config.load_seed_members()}
    g, notes = Graph(), []
    ready = ready or {}
    for block, xml_text in ready.items():
        for k, (title, resolved) in enumerate(ready_networks(xml_text)):
            node = g.add(f"n:{block}#{k}", "net", block, title)
            _wire_network(g, node, [(p, d, c) for p, d, c in resolved if p[-1].lower() not in pads])
    templates = {str(b.get("name")): str(b.get("template_ref") or "") for b in _rows(database, "software_blocks")
                 if str(b.get("name")) not in ready}
    variants = {ref: (template_variants(ref) if ref and os.path.isfile(ref) else []) for ref in set(templates.values())}
    unwired = sorted(name for name, ref in templates.items() if not variants.get(ref))
    if unwired:
        notes.append("not traced (no FBD template to read the wiring from): " + ", ".join(unwired))
    unmatched = set()

    for row in _rows(database, "software_block_members"):
        block, seq = str(row.get("block")), str(row.get("seq"))
        if block in ready:
            continue
        networks = variants.get(templates.get(block, ""), [])
        if not networks:
            continue
        values = _values(row)
        kind = str(values.get("TemplateType") or "").strip()
        if not kind.isdigit() or not 1 <= int(kind) <= len(networks):
            unmatched.add(block)
            continue
        comment = str(values.get("NetworkComment") or "").strip()
        resolved = network_symbols(networks[int(kind) - 1], values, pads)
        channels = {ch for _p, _d, ch in resolved if ch is not None}
        split = {d for _p, d, ch in resolved if ch is not None} >= {"read", "write"}
        nets = ({ch: g.add(f"n:{block}#{seq}:{ch[0]}.{ch[1]}", "net", block, comment) for ch in sorted(channels)}
                if split else {None: g.add(f"n:{block}#{seq}", "net", block, comment)})
        for parts, direction, channel in resolved:
            v = g.var(parts)
            for net in ([nets[channel]] if split and channel is not None else nets.values()):
                if direction == "read":
                    g.edge(v, net)
                else:
                    g.edge(net, v)
    if unmatched:
        notes.append("networks whose TemplateType names no template network: " + ", ".join(sorted(unmatched)))

    for e in _rows(database, "interface_elements"):
        expr, tag = parse_symbol(e.get("expression")), str(e.get("signal_name") or "").strip()
        if not expr or not tag:
            continue
        node = g.add(f"i:{e.get('uid')}", "iface", "10_Machine Interfaces",
                     f"{e.get('interface')} · {e.get('direction')} {e.get('io_address_side1') or ''}".strip())
        a, b = g.var(expr), g.var((tag,))
        if str(e.get("direction") or "").upper() == "I":
            a, b = b, a
        g.edge(a, node)
        g.edge(node, b)

    for d in _rows(database, "diagnosis_entries"):
        binding = parse_symbol(d.get("in_binding"))
        if not binding:
            continue
        level = "warning" if str(d.get("is_warning")).lower() == "true" else "alarm"
        rule = str(d.get("rule_name") or "").strip()
        node = g.add(f"d:{d.get('uid')}", "diag", "Diagnostic_for_OPC",
                     f"cabinet {d.get('cabinet')} bit {d.get('bit')} {level}" + (f" · {rule}" if rule else ""))
        g.edge(g.var(binding), node)

    for r in _rows(database, "coverage"):
        node = g.add(f"r:{r.get('uid')}", "row", f"{r.get('script_type') or '-'}  {r.get('FLD') or ''}".strip(),
                     f"{r.get('address') or ''} · {r.get('source_cell') or ''}")
        tag, address = str(r.get("tag") or "").strip(), str(r.get("address") or "").strip().upper()
        if tag and address.startswith("Q"):
            g.edge(g.var((tag,)), node)
        elif tag:
            g.edge(node, g.var((tag,)))
    return g, notes


def reach(adjacency, start, limit=None) -> dict:
    """{node: hops} reachable from `start` along `adjacency` (BFS; `start` itself at 0)."""
    seen, queue = {start: 0}, deque([start])
    while queue:
        node = queue.popleft()
        if limit is not None and seen[node] >= limit:
            continue
        for nxt in adjacency.get(node, ()):
            if nxt not in seen:
                seen[nxt] = seen[node] + 1
                queue.append(nxt)
    return seen


def ends(g: Graph, out: dict, start: str, inn: dict | None = None) -> dict:
    """What a row's downstream reaches: 'outputs' (physical output rows), 'alarms' (diagnosis bits), 'interfaces'
    (interface assignments), 'unread' (symbols written but read by nothing), 'steps' (every node reached) - and
    'feeders': the input rows its upstream reaches (an output row's paths run INTO it)."""
    found = {"outputs": 0, "alarms": 0, "interfaces": 0, "unread": 0, "steps": 0, "feeders": 0}
    if inn is not None:
        found["feeders"] = sum(1 for node in reach(inn, start) if node != start and g.nodes[node][0] == "row")
    for node in reach(out, start):
        if node == start:
            continue
        kind = g.nodes[node][0]
        found["steps"] += 1
        if kind == "row":
            found["outputs"] += 1
        elif kind == "diag":
            found["alarms"] += 1
        elif kind == "iface":
            found["interfaces"] += 1
        elif kind in ("tag", "member") and not out.get(node):
            found["unread"] += 1
    return found


# --- the page ---------------------------------------------------------------------------------- #
def page_data(database, title: str = "", ready: dict | None = None) -> dict:
    """The JSON the page draws from: nodes [id, kind, label, sub], edges [from, to] by node index, and per
    signal [row node index, kind, type, FLD, address, tag, source cell, `ends`]."""
    g, notes = build_graph(database, ready)
    ids = list(g.nodes)
    index = {node: n for n, node in enumerate(ids)}
    out, inn = g.adjacency(), g.adjacency(reverse=True)
    signals = []
    for r in _rows(database, "coverage"):
        node = f"r:{r.get('uid')}"
        signals.append([index[node], r.get("kind") or "", r.get("script_type") or "", r.get("FLD") or "",
                        r.get("address") or "", r.get("tag") or "", r.get("source_cell") or "", ends(g, out, node, inn)])
    return {"title": title, "notes": notes,
            "nodes": [[node, *g.nodes[node]] for node in ids],
            "edges": sorted([index[a], index[b]] for a, b in g.edges),
            "signals": signals}


def render(data: dict) -> str:
    """The self-contained page: the data embedded as JSON (a closing `</` escaped), the CSS and script inline."""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return (_PAGE.replace("__TITLE__", html.escape(data.get("title") or "Signal paths"))
            .replace("__DATA__", payload))


def project(database, out_dir: str | None = None, title: str = "", ready: dict | None = None) -> dict:
    """Write `io_signal_paths.html` into `out_dir` (default: the coverage reports folder); `ready` as for
    `build_graph`. Returns {'html', 'signals', 'traced', 'notes'} - `traced` = rows with a path out or in."""
    data = page_data(database, title or f"Signal paths - {config.load_params().get('project_code') or 'project'}",
                     ready)
    out_dir = out_dir or config.coverage_dir()
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, REPORT_FILE)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render(data))
    traced = sum(1 for s in data["signals"] if s[7]["steps"] or s[7]["feeders"])
    return {"html": path, "signals": len(data["signals"]), "traced": traced, "notes": data["notes"]}


_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root { --bg:#f6f7f9; --panel:#ffffff; --ink:#1d2430; --muted:#5c6675; --line:#d5dae1; --edge:#8a94a3;
  --row:#2d3436; --row-ink:#ffffff; --tag:#e3f6ec; --tag-line:#2f9e64; --member:#e4eefb; --member-line:#3b78c4;
  --net:#ffffff; --net-head:#5f6b7a; --iface:#efe7fb; --iface-line:#7d55c7; --diag:#fdeee2; --diag-line:#d9822b;
  --more:#eceff3; --hit:#ffe08a; --bad:#c0392b; }
@media (prefers-color-scheme: dark) { :root { --bg:#16191e; --panel:#1f242b; --ink:#e7eaee; --muted:#9aa4b2;
  --line:#343b45; --edge:#6f7a89; --row:#dfe6e9; --row-ink:#1d2430; --tag:#183526; --tag-line:#45c486;
  --member:#1a2a40; --member-line:#6aa3ea; --net:#252b33; --net-head:#8796a8; --iface:#2a2140; --iface-line:#a786e8;
  --diag:#3a2618; --diag-line:#f0a35e; --more:#2b3139; --hit:#6b5a17; --bad:#ff7b6b; } }
* { box-sizing:border-box; }
body { margin:0; font:13px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif; background:var(--bg); color:var(--ink);
  height:100vh; min-height:520px; display:flex; flex-direction:column; }
header { padding:6px 16px; border-bottom:1px solid var(--line); background:var(--panel); display:flex; gap:12px;
  align-items:baseline; flex-wrap:wrap; }
header h1 { font-size:15px; margin:0; } header p { margin:0; color:var(--muted); flex:1; min-width:200px; }
main { flex:1; display:flex; min-height:0; }
#side { width:340px; min-width:260px; display:flex; flex-direction:column; border-right:1px solid var(--line);
  background:var(--panel); }
#filters { padding:10px; display:flex; flex-direction:column; gap:6px; border-bottom:1px solid var(--line); }
#filters input[type=search] { width:100%; padding:6px 8px; border:1px solid var(--line); border-radius:6px;
  background:var(--bg); color:var(--ink); }
#filters label { color:var(--muted); margin-right:10px; white-space:nowrap; }
#count { color:var(--muted); }
#list { flex:1; overflow:auto; }
.item { padding:6px 10px; border-bottom:1px solid var(--line); cursor:pointer; }
.item:hover { background:var(--bg); } .item.sel { background:var(--hit); }
.item b { font-weight:600; } .item small { color:var(--muted); display:block; overflow:hidden; text-overflow:ellipsis;
  white-space:nowrap; } .item .dead { color:var(--bad); font-weight:600; }
#view { flex:1; display:flex; flex-direction:column; min-width:0; }
#bar { padding:6px 12px; border-bottom:1px solid var(--line); display:flex; gap:8px; align-items:center;
  background:var(--panel); white-space:nowrap; overflow:hidden; }
#bar #summary { overflow:hidden; text-overflow:ellipsis; min-width:0; flex:1; }
#bar button { padding:4px 10px; border:1px solid var(--line); background:var(--bg); color:var(--ink);
  border-radius:6px; cursor:pointer; }
#title { font-weight:600; } #summary { color:var(--muted); }
#canvas { flex:1; overflow:auto; position:relative; min-height:220px; }
#canvas svg { display:block; }
#bottom { height:clamp(110px, 30vh, 320px); display:flex; border-top:1px solid var(--line); background:var(--panel); }
#bottom.closed { height:auto; } #bottom.closed #paths, #bottom.closed #detail { display:none; }
#toggle { border:0; background:none; color:var(--muted); cursor:pointer; padding:2px 12px; text-align:left; }
#paths, #detail { overflow:auto; padding:8px 12px; }
#paths { flex:2; border-right:1px solid var(--line); } #detail { flex:1; }
h3 { font-size:13px; margin:4px 0 6px; }
.path { margin:0 0 6px; line-height:1.9; }
.chip { display:inline-block; padding:0 6px; border-radius:4px; border:1px solid var(--line); margin:0 2px;
  cursor:pointer; white-space:nowrap; } .arrow { color:var(--muted); }
.k-row { background:var(--row); color:var(--row-ink); } .k-tag { background:var(--tag); border-color:var(--tag-line); }
.k-member { background:var(--member); border-color:var(--member-line); } .k-net { background:var(--net); }
.k-iface { background:var(--iface); border-color:var(--iface-line); } .k-diag { background:var(--diag); border-color:var(--diag-line); }
.muted { color:var(--muted); } .legend span { margin-right:10px; }
svg text { fill:var(--ink); font-size:11px; } svg .head { fill:#fff; font-weight:600; }
svg .rowtext { fill:var(--row-ink); } svg .sub { fill:var(--muted); font-size:10px; }
svg .edge { fill:none; stroke:var(--edge); stroke-width:1.2; } svg .node { cursor:pointer; }
svg .focus { stroke:var(--hit); stroke-width:4; }
</style>
</head>
<body>
<header><h1>__TITLE__</h1><p id="notes"></p>
  <span class="legend muted"><span class="chip k-row">I/O row</span><span class="chip k-tag">PLC tag</span>
    <span class="chip k-member">DB member</span><span class="chip k-net">network</span>
    <span class="chip k-iface">interface</span><span class="chip k-diag">alarm bit</span></span></header>
<main>
  <section id="side">
    <div id="filters">
      <input id="q" type="search" placeholder="Search type, FLD, address, tag, cell…" aria-label="Search signals">
      <div><label><input type="checkbox" id="kSignal" checked> signals</label>
        <label><input type="checkbox" id="kGenerated" checked> generated</label>
        <label><input type="checkbox" id="kChannel"> channels</label></div>
      <div><label><input type="checkbox" id="onlyDead"> only signals with no path</label></div>
      <div id="count"></div>
    </div>
    <div id="list" role="listbox" aria-label="Signals"></div>
  </section>
  <section id="view">
    <div id="bar"><span id="title">Pick a signal</span><span id="summary"></span>
      <button id="fit" aria-label="Fit the diagram">Fit</button>
      <button id="zoomOut" aria-label="Zoom out">−</button><button id="zoomIn" aria-label="Zoom in">+</button>
    </div>
    <div id="canvas"></div>
    <button id="toggle" aria-expanded="true">▾ Paths and details</button>
    <div id="bottom"><div id="paths"></div><div id="detail"><h3>Details</h3><p class="muted">Click a block or symbol.</p></div></div>
  </section>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
(function () {
  const D = JSON.parse(document.getElementById('data').textContent);
  const N = D.nodes.map(n => ({id: n[0], kind: n[1], label: n[2], sub: n[3]}));
  const OUT = N.map(() => []), INN = N.map(() => []);
  D.edges.forEach(([a, b]) => { OUT[a].push(b); INN[b].push(a); });
  const S = D.signals.map(s => ({node: s[0], kind: s[1], type: s[2], fld: s[3], addr: s[4], tag: s[5], cell: s[6], ends: s[7]}));
  document.getElementById('notes').textContent = `${S.length} rows · ${N.length} nodes · ${D.edges.length} links` +
    (D.notes.length ? ' · ' + D.notes.join(' · ') : '');
  const el = id => document.getElementById(id);
  const esc = t => String(t).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  let current = null, zoom = 1, fit = false, expanded = new Set(), focusNode = null;

  // ---- the list ----
  function listRows() {
    const q = el('q').value.trim().toLowerCase();
    const kinds = {signal: el('kSignal').checked, generated: el('kGenerated').checked, channel: el('kChannel').checked};
    const dead = el('onlyDead').checked;
    const rows = S.filter(s => (kinds[s.kind] ?? true) && (!dead || (!s.ends.steps && !s.ends.feeders)) &&
      (!q || `${s.type} ${s.fld} ${s.addr} ${s.tag} ${s.cell}`.toLowerCase().includes(q)));
    el('count').textContent = `${rows.length} of ${S.length}`;
    const list = el('list');
    list.innerHTML = rows.slice(0, 1500).map(s => {
      const e = s.ends, info = e.steps ? `${e.outputs} out · ${e.alarms} alarm · ${e.interfaces} iface` :
        e.feeders ? `driven by ${e.feeders} input row(s)` : '<span class="dead">no path</span>';
      return `<div class="item${current === s ? ' sel' : ''}" data-n="${s.node}" role="option">` +
        `<b>${esc(s.type || '-')}</b> ${esc(s.fld)} <span class="muted">${esc(s.addr)}</span>` +
        `<small>${esc(s.tag || s.cell)} · ${info}</small></div>`;
    }).join('') + (rows.length > 1500 ? `<div class="item muted">… ${rows.length - 1500} more - narrow the search</div>` : '');
  }
  ['q', 'kSignal', 'kGenerated', 'kChannel', 'onlyDead'].forEach(id => el(id).addEventListener('input', listRows));
  el('list').addEventListener('click', ev => {
    const item = ev.target.closest('.item[data-n]'); if (!item) return;
    open(+item.dataset.n);
  });
  el('zoomIn').onclick = () => { zoom = Math.min(2, zoom * 1.2); draw(); };
  el('zoomOut').onclick = () => { zoom = Math.max(0.2, zoom / 1.2); draw(); };
  el('fit').onclick = () => { fit = true; draw(); };
  el('toggle').onclick = () => {
    const closed = el('bottom').classList.toggle('closed');
    el('toggle').textContent = (closed ? '▸' : '▾') + ' Paths and details';
    el('toggle').setAttribute('aria-expanded', String(!closed));
  };

  // ---- reach + layering ----
  function bfs(start, adj, maxDepth, budget) {
    const dist = new Map([[start, 0]]), queue = [start];
    while (queue.length && dist.size < budget) {
      const n = queue.shift(), d = dist.get(n);
      if (d >= maxDepth) continue;
      for (const m of adj[n]) if (!dist.has(m)) { dist.set(m, d + 1); queue.push(m); }
    }
    return dist;
  }
  const LIMIT = 14, KEEP = 12;
  function layout(start) {
    const down = bfs(start, OUT, 30, 1500), up = bfs(start, INN, 30, 1500);
    const layer = new Map();
    down.forEach((d, n) => layer.set(n, d));
    up.forEach((d, n) => { if (!layer.has(n)) layer.set(n, -d); });
    const byLayer = new Map();
    layer.forEach((l, n) => { if (!byLayer.has(l)) byLayer.set(l, []); byLayer.get(l).push(n); });
    const keys = [...byLayer.keys()].sort((a, b) => a - b);
    const pos = new Map([[start, 0]]);
    const order = (l, ref) => {           // barycenter of the neighbours in the layer towards the row
      const nodes = byLayer.get(l), score = n => {
        const nb = (l > 0 ? INN[n] : OUT[n]).filter(m => layer.get(m) === ref && pos.has(m));
        return nb.length ? nb.reduce((s, m) => s + pos.get(m), 0) / nb.length : 1e9;
      };
      nodes.sort((a, b) => score(a) - score(b) || N[a].label.localeCompare(N[b].label));
      nodes.forEach((n, i) => pos.set(n, i));
    };
    keys.filter(l => l > 0).forEach(l => order(l, l - 1));
    keys.filter(l => l < 0).sort((a, b) => b - a).forEach(l => order(l, l + 1));
    const shown = new Map(), more = new Map();
    keys.forEach(l => {
      const nodes = byLayer.get(l);
      if (nodes.length > LIMIT && !expanded.has(l)) {
        nodes.slice(0, KEEP).forEach(n => shown.set(n, l));
        more.set(l, nodes.slice(KEEP));
      } else nodes.forEach(n => shown.set(n, l));
    });
    return {keys, byLayer, shown, more, layer};
  }

  // ---- drawing ----
  const COL = 270, W = 220, GAP = 14;
  const H = {row: 48, tag: 34, member: 42, net: 56, iface: 44, diag: 44, more: 34};
  const cut = (t, n) => (t = String(t || '')).length > n ? t.slice(0, n - 1) + '…' : t;
  const lines = (t, n) => {                 // two lines broken at a space, the rest cut
    t = String(t || ''); if (t.length <= n) return [t, ''];
    let at = t.lastIndexOf(' ', n); if (at < n / 2) at = n;
    return [t.slice(0, at), cut(t.slice(at).trim(), n)];
  };
  function draw() {
    const canvas = el('canvas');
    if (!current) { canvas.innerHTML = ''; return; }
    const start = current.node, L = layout(start), min = L.keys[0];
    el('title').textContent = `${current.type || '-'}  ${current.fld}  ${current.addr}`;
    const e = current.ends;
    el('summary').textContent = (e.steps ? `→ ${e.outputs} physical output(s), ${e.alarms} alarm bit(s), ` +
      `${e.interfaces} interface assignment(s), ${e.unread} unread symbol(s)` : '→ reaches nothing downstream') +
      (e.feeders ? ` · ← driven by ${e.feeders} input row(s)` : '');
    const boxes = new Map();
    let height = 0;
    const columns = L.keys.map(l => {
      const items = [...L.shown].filter(([, ll]) => ll === l).map(([n]) => n)
        .sort((a, b) => L.byLayer.get(l).indexOf(a) - L.byLayer.get(l).indexOf(b));
      if (L.more.has(l)) items.push('more:' + l);
      const total = items.reduce((s, n) => s + (typeof n === 'string' ? H.more : H[N[n].kind]) + GAP, 0);
      height = Math.max(height, total);
      return {l, items, total};
    });
    columns.forEach(({l, items, total}) => {
      let y = 20 + (height - total) / 2;
      items.forEach(n => {
        const h = typeof n === 'string' ? H.more : H[N[n].kind];
        boxes.set(n, {x: 20 + (l - min) * COL, y, h});
        y += h + GAP;
      });
    });
    const width = 40 + (L.keys.length - 1) * COL + W;
    if (fit) {
      zoom = Math.max(0.2, Math.min(1.5, canvas.clientWidth / width, canvas.clientHeight / (height + 40)));
      fit = false;
    }
    const at = n => boxes.get(n) || (L.more.has(L.layer.get(n)) ? boxes.get('more:' + L.layer.get(n)) : null);
    let edges = '';
    const drawn = new Set();
    D.edges.forEach(([a, b]) => {
      if (!L.layer.has(a) || !L.layer.has(b) || L.layer.get(b) !== L.layer.get(a) + 1) return;
      const p = at(a), q = at(b);
      if (!p || !q) return;
      const key = `${p.x},${p.y}>${q.x},${q.y}`; if (drawn.has(key)) return; drawn.add(key);
      const x1 = p.x + W, y1 = p.y + p.h / 2, x2 = q.x, y2 = q.y + q.h / 2, m = (x1 + x2) / 2;
      edges += `<path class="edge" marker-end="url(#arr)" d="M${x1},${y1} C${m},${y1} ${m},${y2} ${x2 - 2},${y2}"/>`;
    });
    let nodes = '';
    boxes.forEach((b, n) => {
      if (typeof n === 'string') {
        const l = +n.slice(5);
        nodes += `<g class="node" data-more="${l}"><rect x="${b.x}" y="${b.y}" width="${W}" height="${b.h}" rx="6" ` +
          `fill="var(--more)" stroke="var(--line)"/><text x="${b.x + 10}" y="${b.y + 21}">+ ${L.more.get(l).length} more ` +
          `- click to show</text></g>`;
        return;
      }
      const v = N[n], cls = n === focusNode ? ' focus' : '', title = `<title>${esc(v.label)}\n${esc(v.sub)}</title>`;
      if (v.kind === 'net') {
        nodes += `<g class="node" data-n="${n}">${title}<rect class="${cls}" x="${b.x}" y="${b.y}" width="${W}" height="${b.h}" ` +
          `rx="4" fill="var(--net)" stroke="var(--net-head)" stroke-width="1.5"/>` +
          `<rect x="${b.x}" y="${b.y}" width="${W}" height="18" rx="4" fill="var(--net-head)"/>` +
          `<text class="head" x="${b.x + 8}" y="${b.y + 13}">${esc(cut(v.label, 32))}</text>` +
          `<text x="${b.x + 8}" y="${b.y + 32}">${esc(lines(v.sub, 34)[0])}</text>` +
          `<text x="${b.x + 8}" y="${b.y + 47}">${esc(lines(v.sub, 34)[1])}</text></g>`;
      } else if (v.kind === 'row') {
        nodes += `<g class="node" data-n="${n}">${title}<rect class="${cls}" x="${b.x}" y="${b.y}" width="${W}" height="${b.h}" ` +
          `rx="8" fill="var(--row)"/><text class="rowtext" x="${b.x + 10}" y="${b.y + 19}" font-weight="600">${esc(cut(v.label, 30))}</text>` +
          `<text class="rowtext" x="${b.x + 10}" y="${b.y + 36}" opacity="0.8">${esc(cut(v.sub, 34))}</text></g>`;
      } else {
        const fill = {tag: 'var(--tag)', member: 'var(--member)', iface: 'var(--iface)', diag: 'var(--diag)'}[v.kind];
        const line = {tag: 'var(--tag-line)', member: 'var(--member-line)', iface: 'var(--iface-line)', diag: 'var(--diag-line)'}[v.kind];
        let t1 = v.label, t2 = v.sub;
        if (v.kind === 'member') { const m = v.label.match(/^"([^"]*)"\.(.*)$/); if (m) { t1 = m[1]; t2 = m[2].replace(/"/g, ''); } }
        if (v.kind === 'tag') { t1 = v.label.replace(/"/g, ''); t2 = ''; }
        nodes += `<g class="node" data-n="${n}">${title}<rect class="${cls}" x="${b.x}" y="${b.y}" width="${W}" height="${b.h}" ` +
          `rx="${v.kind === 'tag' ? 17 : 6}" fill="${fill}" stroke="${line}" stroke-width="1.5"/>` +
          `<text x="${b.x + 10}" y="${b.y + (t2 ? 16 : 21)}" font-weight="${v.kind === 'member' ? 400 : 600}">${esc(cut(t1, 34))}</text>` +
          (t2 ? `<text x="${b.x + 10}" y="${b.y + 32}" font-weight="600">${esc(cut(t2, 34))}</text>` : '') + `</g>`;
      }
    });
    canvas.innerHTML = `<svg width="${width * zoom}" height="${(height + 40) * zoom}" viewBox="0 0 ${width} ${height + 40}" ` +
      `role="img" aria-label="Signal flow"><defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" ` +
      `markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="var(--edge)"/></marker></defs>` +
      edges + nodes + `</svg>`;
    const row = boxes.get(start);
    if (row) {                              // the signal's own row in view: a third from the left, mid-height
      canvas.scrollLeft = Math.max(0, row.x * zoom - canvas.clientWidth / 3);
      canvas.scrollTop = Math.max(0, (row.y + row.h / 2) * zoom - canvas.clientHeight / 2);
    }
  }
  el('canvas').addEventListener('click', ev => {
    const g = ev.target.closest('g.node'); if (!g) return;
    if (g.dataset.more !== undefined) { expanded.add(+g.dataset.more); draw(); return; }
    focusNode = +g.dataset.n; draw(); detail(focusNode);
  });

  // ---- every path ----
  function enumerate(start, adj, cap) {
    const out = [], stack = [[start, [start]]];
    while (stack.length && out.length < cap) {
      const [n, path] = stack.pop(), next = adj[n].filter(m => !path.includes(m));
      if (!next.length || path.length > 40) { if (path.length > 1) out.push(path); continue; }
      for (let i = next.length - 1; i >= 0; i--) stack.push([next[i], path.concat(next[i])]);
    }
    return out;
  }
  const chip = n => `<span class="chip k-${N[n].kind}" data-n="${n}" title="${esc(N[n].label + ' ' + N[n].sub)}">` +
    `${esc(cut(N[n].kind === 'net' ? N[n].label + ': ' + N[n].sub : N[n].label.replace(/"/g, ''), 60))}</span>`;
  function paths() {
    const start = current.node, CAP = 300;
    const down = enumerate(start, OUT, CAP), up = enumerate(start, INN, CAP).map(p => p.slice().reverse());
    const block = (title, list) => !list.length ? '' : `<h3>${title} (${list.length}${list.length >= CAP ? '+' : ''})</h3>` +
      list.map(p => `<div class="path">${p.map(chip).join('<span class="arrow"> → </span>')}</div>`).join('');
    el('paths').innerHTML = (block('Paths from this signal', down) + block('Paths into this signal', up)) ||
      '<h3>Paths</h3><p class="muted">This row reaches nothing and nothing reaches it.</p>';
  }
  function detail(n) {
    const v = N[n];
    const listOf = (ids, verb) => ids.length ? `<p class="muted">${verb}</p>` + ids.slice(0, 60).map(chip).join(' ') +
      (ids.length > 60 ? ` <span class="muted">+${ids.length - 60}</span>` : '') : '';
    const into = v.kind === 'net' ? 'reads' : v.kind === 'row' ? 'driven by' : 'written by';
    const from = v.kind === 'net' ? 'writes' : v.kind === 'row' ? 'feeds' : 'read by';
    el('detail').innerHTML = `<h3>${esc(v.label)}</h3><p class="muted">${esc(v.kind)} · ${esc(v.sub)}</p>` +
      listOf(INN[n], into) + listOf(OUT[n], from);
  }
  ['paths', 'detail'].forEach(id => el(id).addEventListener('click', ev => {
    const c = ev.target.closest('.chip[data-n]'); if (!c) return;
    focusNode = +c.dataset.n; draw(); detail(focusNode);
  }));
  function open(node) {
    current = S.find(s => s.node === node); expanded.clear(); focusNode = null; zoom = 1;
    listRows(); draw(); paths(); detail(node);
  }
  listRows();
  const wanted = decodeURIComponent((location.hash.match(/[#&]s=([^&]*)/) || [])[1] || '');   // #s=<search>: a deep link
  if (wanted) {
    el('q').value = wanted; listRows();
    const first = el('list').querySelector('.item[data-n]');
    if (first) open(+first.dataset.n);
  }
})();
</script>
</body>
</html>
"""
