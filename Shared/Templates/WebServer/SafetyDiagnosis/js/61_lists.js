// Lists: one table per device kind (#/list/<kind>), filtered by a search box and a state choice.
(function (SD) {
  "use strict";
  SD.view("list", { label: "Devices", icon: "list", order: 20, nav: true, render: function (ctx, route) {
    var model = ctx.model, kind = model.kind[route.arg] || model.kinds[0], rows = {}, cells = {};
    var entities = model.byKind[kind.kind] || [], isNode = kind.kind === "pn_node";
    var node = SD.el("div"), tabs = SD.el("div", { cls: "tabs", role: "tablist" });
    model.kinds.forEach(function (k) {
      tabs.appendChild(SD.el("a", { href: SD.href("list", k.kind), cls: k.kind === kind.kind ? "on" : "" },
        [SD.icon(k.icon), SD.el("span", { text: k.plural + " (" + (model.byKind[k.kind] || []).length + ")" })]));
    });
    var search = SD.el("input", { type: "search", placeholder: "Filter by FLD, name or description", "aria-label": "Filter" });
    var pick = SD.el("select", { "aria-label": "State" }, [["all", "All states"], ["bad", "Not OK"], ["alarm", "Alarm"],
      ["warning", "Warning"], ["unknown", "Unknown"], ["ok", "OK"]].map(function (o) { return SD.el("option", { value: o[0], text: o[1] }); }));
    var count = SD.el("span", { cls: "muted" });
    var head = isNode ? ["State", "PROFINET name", "IP", "FLD", "Description", "Diagnosis", "Devices"]
      : ["State", "FLD", "Description", "Areas", "Diagnosis", "PROFINET node"];
    var wide = isNode ? [false, false, false, true, true, true, true] : [false, false, false, true, true, true];
    var tbody = SD.el("tbody");
    var table = SD.el("table", { cls: "grid" }, [SD.el("thead", null, SD.el("tr", null, head.map(function (h, i) {
      return SD.el("th", { cls: wide[i] ? "wide" : "", text: h });
    }))), tbody]);

    function diagText(e) {
      return (e.diag || []).map(function (d) {
        var cab = model.cabinet[d.cabinet];
        return (cab ? cab.fld : "cabinet " + d.cabinet) + "." + d.bit + (d.warning ? "w" : "");
      }).join(", ");
    }
    entities.forEach(function (e) {
      var chip = SD.chip("stale");
      var values = isNode
        ? [chip, e.name, e.ip, e.fld, e.description, diagText(e), String((model.onNode[e.id] || []).length)]
        : [chip, e.fld, e.description, (e.areas || []).join(", "), diagText(e), (e.nodes || []).map(function (n) {
          return model.byId[n] ? model.byId[n].name : n; }).join(", ")];
      var tr = SD.el("tr", { cls: "click", tabindex: "0", on: {
        click: function () { SD.open(e.id); },
        keydown: function (ev) { if (ev.key === "Enter") { SD.open(e.id); } } } }, values.map(function (v, i) {
        return SD.el("td", { cls: (wide[i] ? "wide " : "") + (i === 1 ? "mono" : "") }, v);
      }));
      e.search = [e.fld, e.name || "", e.ip || "", e.description || "", (e.areas || []).join(" ")];
      rows[e.id] = tr;
      cells[e.id] = chip;
      tbody.appendChild(tr);
    });
    SD.add(node, [SD.el("div", { cls: "head" }, [SD.el("h2", { text: kind.plural }), count]), tabs,
      SD.el("div", { cls: "toolbar" }, [search, pick]), SD.el("div", { cls: "scroll" }, table)]);

    function update(ev) {
      var needle = search.value.trim(), want = pick.value, shown = 0;
      entities.forEach(function (e) {
        var state = ev.entity[e.id], chip = cells[e.id];
        chip.textContent = SD.STATE_TEXT[state];
        SD.setState(chip, state);
        var visible = SD.matches(needle, e.search) && (want === "all" || (want === "bad" ? state !== "ok" : state === want
          || (want === "unknown" && (state === "node" || state === "stale"))));
        rows[e.id].hidden = !visible;
        rows[e.id].className = "click" + (e.id === ctx.route.detail ? " sel" : "");
        shown += visible ? 1 : 0;
      });
      count.textContent = shown + " of " + entities.length;
    }
    var again = SD.debounce(function () { if (ctx.ev) { update(ctx.ev); } }, 120);
    search.addEventListener("input", again);
    pick.addEventListener("change", again);
    return { node: node, update: update };
  } });
})(SD);
