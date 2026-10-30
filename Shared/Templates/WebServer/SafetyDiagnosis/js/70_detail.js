// The detail panel of a device or PROFINET node (?d=<id> on any route): its state, its diagnosis channels, its
// node (or, for a node, the devices on it), its areas, and its own members and PLC tags - read every
// polling.detail_interval_ms only while the panel is open.
(function (SD) {
  "use strict";
  function valueText(value) {
    return value === true ? "TRUE" : value === false ? "FALSE" : value === undefined ? "-" : String(value);
  }

  SD.detail = function (ctx, id) {
    var model = ctx.model, plant = ctx.plant, e = model.byId[id];
    var close = SD.el("button", { cls: "iconbtn", type: "button", title: "Close", "aria-label": "Close",
      on: { click: function () { location.hash = SD.detailHref(null); } } }, SD.icon("close"));
    if (!e) {
      return { node: SD.el("div", null, [SD.el("div", { cls: "dhead" }, [SD.el("div", { cls: "t" }, SD.el("h2", { text: id })), close]),
        SD.el("div", { cls: "dbody" }, SD.el("p", { cls: "muted", text: "This plant model has no device " + id + "." }))]) };
    }
    var kind = model.kind[e.kind] || { label: e.kind, icon: "device" }, state = SD.chip("stale"), body = SD.el("div", { cls: "dbody" });
    var node = SD.el("div", null, [SD.el("div", { cls: "dhead" }, [SD.icon(kind.icon), SD.el("div", { cls: "t" }, [
      SD.el("div", { cls: "muted", text: kind.label }), SD.el("h2", { cls: "mono", text: e.fld || e.name }),
      SD.el("div", { text: e.description || "" }), state]), close]), body]);
    var facts = SD.el("dl", { cls: "kv" });
    function fact(label, value) { if (value) { SD.add(facts, [SD.el("dt", { text: label }), SD.el("dd", null, value)]); } }
    if (e.kind === "pn_node") { fact("PROFINET name", e.name); fact("IP", e.ip); }
    fact("Areas", (e.areas || []).length ? (e.areas || []).join(", ") : null);
    body.appendChild(facts);

    // diagnosis channels
    var channels = [];
    if ((e.diag || []).length) {
      var list = SD.el("tbody");
      e.diag.forEach(function (d) {
        var cab = model.cabinet[d.cabinet], entry = cab && cab.bitAt[(d.warning ? "w" : "a") + d.bit], chip = SD.chip("stale");
        channels.push({ d: d, chip: chip });
        list.appendChild(SD.el("tr", null, [SD.el("td", null, chip),
          SD.el("td", null, [SD.el("a", { href: SD.href("cabinets", String(d.cabinet)) + "?d=" + encodeURIComponent(e.id),
            text: (cab ? cab.fld : "cabinet " + d.cabinet) }), " bit " + d.bit + (d.warning ? " (warning)" : "")]),
          SD.el("td", { text: entry ? entry.text : "" })]));
      });
      SD.add(body, [SD.el("h3", { cls: "section", text: "Diagnosis" }), SD.el("div", { cls: "scroll" }, SD.el("table", { cls: "grid" }, list))]);
    }

    // the node, or the devices on the node
    var nodeChips = [];
    if (e.kind === "pn_node") {
      var on = model.onNode[e.id] || [];
      if (on.length) {
        var box = SD.el("div", { cls: "strip" });
        on.forEach(function (d) {
          var chip = SD.chip("stale", d.fld);
          nodeChips.push({ id: d.id, chip: chip });
          box.appendChild(SD.el("a", { href: SD.detailHref(d.id) }, chip));
        });
        SD.add(body, [SD.el("h3", { cls: "section", text: "Devices on this node (" + on.length + ")" }), box]);
      }
    } else if ((e.nodes || []).length) {
      var row = SD.el("div", { cls: "strip" });
      e.nodes.forEach(function (n) {
        var item = model.byId[n], chip = SD.chip("stale", item ? item.name + " " + item.ip : n);
        nodeChips.push({ id: n, chip: chip });
        row.appendChild(SD.el("a", { href: SD.detailHref(n) }, chip));
      });
      SD.add(body, [SD.el("h3", { cls: "section", text: "PROFINET node" }), row]);
    }

    // own members + PLC tags, read while open
    var reads = [];
    function table(title, rows, cols) {
      if (!rows.length) { return; }
      var tbody = SD.el("tbody");
      rows.forEach(function (r) {
        var value = SD.el("td", { cls: "mono nw", text: "-" });
        reads.push({ var: r.var, td: value, member: r.member });
        tbody.appendChild(SD.el("tr", { title: r.var }, [SD.el("td", { text: r.label })].concat([value]).concat(r.extra.map(function (x, i) {
          return SD.el("td", { cls: (i ? "wide " : "") + "mono nw", text: x }); }))));
      });
      SD.add(body, [SD.el("h3", { cls: "section", text: title }), SD.el("div", { cls: "scroll" }, SD.el("table", { cls: "grid" }, [
        SD.el("thead", null, SD.el("tr", null, cols.map(function (h, i) { return SD.el("th", { cls: i > 2 ? "wide" : "", text: h }); }))), tbody]))]);
    }
    table("Members", (e.members || []).map(function (m) {
      return { var: m.var, label: m.label, member: m, extra: [m.role] };
    }), ["Member", "Value", "Role"]);
    table("PLC tags", (e.tags || []).map(function (t) {
      return { var: t.var, label: t.var.replace(/^"|"$/g, ""), extra: [t.type, t.address] };
    }), ["Tag", "Value", "Type", "Address"]);
    if (reads.length) {
      body.appendChild(SD.el("p", { cls: "note", text: "Members and tags are read every " + plant.polling.detail_interval_ms
        + " ms while this panel is open." }));
      ctx.poller.watch("detail", reads.map(function (r) { return r.var; }), plant.polling.detail_interval_ms);
    }

    return { node: node, leave: function () { ctx.poller.unwatch("detail"); }, update: function (ev) {
      var s = ev.entity[e.id];
      state.textContent = SD.STATE_TEXT[s];
      SD.setState(state, s);
      channels.forEach(function (c) {
        var cab = ev.cabinet[c.d.cabinet], ch = cab && cab.channels[(c.d.warning ? "w" : "a") + c.d.bit];
        var st = ch ? ch.state : "unknown";
        c.chip.textContent = SD.STATE_TEXT[st] + (ch && ch.raw !== null && st === "unknown" ? " (raw " + ch.raw + ")" : "");
        SD.setState(c.chip, st);
      });
      nodeChips.forEach(function (c) { SD.setState(c.chip, ev.entity[c.id] || "unknown"); });
      reads.forEach(function (r) {
        var err = ctx.poller.errors[r.var], value = ev.snap.v[r.var];
        if (err) { r.td.textContent = "not readable: " + err.message; return; }
        var text = valueText(value);
        if (r.member && r.member.healthy !== null && r.member.healthy !== undefined && typeof value === "boolean") {
          text += value === r.member.healthy ? " (healthy)" : " (" + r.member.severity + ")";
        }
        r.td.textContent = text;
      });
    } };
  };
})(SD);
