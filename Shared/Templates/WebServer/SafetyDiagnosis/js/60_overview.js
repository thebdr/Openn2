// Overview: the area and cabinet strips, one summary card per device kind, then the plant - the drawing with its
// icons (55_drawing.js) when the project has one, and the auto schematic: every device and PROFINET node as a
// tile, grouped by plant.layout.group_by (functional unit, then location).
(function (SD) {
  "use strict";
  SD.view("overview", { label: "Overview", icon: "overview", order: 10, nav: true, render: function (ctx) {
    var model = ctx.model, plant = ctx.plant, tiles = {}, areaChips = {}, cabChips = {}, kindChips = {}, onlyBad = false;
    var node = SD.el("div"), toggle = SD.el("button", { cls: "btn", type: "button", text: "Only not OK", "aria-pressed": "false" });

    var areaStrip = SD.el("div", { cls: "strip" });
    plant.areas.forEach(function (a) {
      areaChips[a.id] = SD.chip("stale", a.name);
      areaStrip.appendChild(SD.el("a", { href: SD.href("areas"), title: a.description }, areaChips[a.id]));
    });
    var cabStrip = SD.el("div", { cls: "strip" });
    plant.cabinets.forEach(function (c) {
      cabChips[c.id] = SD.chip("stale", c.fld);
      cabStrip.appendChild(SD.el("a", { href: SD.href("cabinets", String(c.id)) }, cabChips[c.id]));
    });
    var summary = SD.el("div", { cls: "summary" });
    model.kinds.forEach(function (k) {
      kindChips[k.kind] = SD.el("div", { cls: "chips" });
      summary.appendChild(SD.el("a", { href: SD.href("list", k.kind) }, [
        SD.el("div", { cls: "n" }, [SD.icon(k.icon), SD.el("span", { text: k.plural + " " }),
          SD.el("span", { cls: "muted", text: String((model.byKind[k.kind] || []).length) })]), kindChips[k.kind]]));
    });

    // the schematic: group_by levels -> tiles. A device without a location of its own (FVT's =ES-nnnn e-stops)
    // is placed at its PROFINET node's location within the same functional unit - the station it is wired to.
    var levels = plant.layout.group_by && plant.layout.group_by.length ? plant.layout.group_by : ["functional_unit", "location"];
    var groups = {}, order = [];
    function level(e, name) {
      var own = e.parts[name];
      if (own || name !== "location") { return own || ""; }
      var host = (e.nodes || []).map(function (n) { return model.byId[n]; }).filter(function (n) {
        return n && n.parts.functional_unit === e.parts.functional_unit && n.parts.location;
      })[0];
      return host ? host.parts.location : "";
    }
    model.kinds.forEach(function (k) {
      (model.byKind[k.kind] || []).forEach(function (e) {
        var top = level(e, levels[0]) || "(none)", sub = levels[1] ? level(e, levels[1]) || "(none)" : "";
        if (!groups[top]) { groups[top] = {}; order.push(top); }
        (groups[top][sub] = groups[top][sub] || []).push(e);
      });
    });
    order.sort(function (a, b) { return a.localeCompare(b, "en", { numeric: true }); });
    var schematic = SD.el("div");
    var sections = order.map(function (top) {
      var box = SD.el("div", { cls: "card group" }, SD.el("h3", { text: top }));
      Object.keys(groups[top]).sort(function (a, b) { return a.localeCompare(b, "en", { numeric: true }); }).forEach(function (sub) {
        var row = SD.el("div", { cls: "tiles" });
        groups[top][sub].forEach(function (e) {
          var k = model.kind[e.kind];
          var tile = SD.el("button", { cls: "tile s-stale", type: "button", title: k.label + " " + e.fld + " - " + (e.description || ""),
            on: { click: function () { SD.open(e.id); } } }, [SD.icon(k.icon), SD.el("span", { text: e.parts.device || e.fld })]);
          tiles[e.id] = tile;
          row.appendChild(tile);
        });
        box.appendChild(SD.el("div", { cls: "loc" }, [SD.el("b", { text: sub }), row]));
      });
      schematic.appendChild(box);
      return box;
    });

    toggle.addEventListener("click", function () {
      onlyBad = !onlyBad;
      toggle.className = "btn" + (onlyBad ? " on" : "");
      toggle.setAttribute("aria-pressed", String(onlyBad));
      if (ctx.ev) { update(ctx.ev); }
    });
    var drawing = plant.layout.image ? SD.drawing(ctx) : null, plantHead = null;
    if (drawing) {
      var tabDrawing = SD.el("a", { href: "#", cls: "on", text: "Drawing" });
      var tabSchematic = SD.el("a", { href: "#", text: "Schematic (" + levels.join(", then ").replace(/_/g, " ") + ")" });
      var showDrawing = function (yes) {
        tabDrawing.className = yes ? "on" : "";
        tabSchematic.className = yes ? "" : "on";
        drawing.node.hidden = !yes;
        schematic.hidden = yes;
        if (yes) { drawing.fit(); }
      };
      tabDrawing.addEventListener("click", function (e) { e.preventDefault(); showDrawing(true); });
      tabSchematic.addEventListener("click", function (e) { e.preventDefault(); showDrawing(false); });
      plantHead = SD.el("div", { cls: "tabs" }, [tabDrawing, tabSchematic]);
      schematic.hidden = true;
    }
    SD.add(node, [
      SD.el("div", { cls: "head" }, [SD.el("h2", { text: "Overview" }), toggle]),
      SD.el("h3", { cls: "section", text: "Areas" }), areaStrip,
      SD.el("h3", { cls: "section", text: "Diagnosis cabinets" }), cabStrip,
      SD.el("h3", { cls: "section", text: "Devices" }), summary,
      SD.el("h3", { cls: "section", text: drawing ? "Plant" : "Plant (" + levels.join(", then ").replace(/_/g, " ") + ")" }),
      plantHead, drawing ? drawing.node : null, schematic]);

    function update(ev) {
      if (drawing) { drawing.update(ev, onlyBad); }
      plant.areas.forEach(function (a) { SD.setState(areaChips[a.id], ev.area[a.id].state); });
      plant.cabinets.forEach(function (c) { SD.setState(cabChips[c.id], ev.cabinet[c.id].summary.state); });
      model.kinds.forEach(function (k) {
        var counts = ev.counts[k.kind], host = SD.clear(kindChips[k.kind]);
        ["alarm", "warning", "node", "unknown", "stale", "ok"].forEach(function (s) {
          if (counts[s]) { host.appendChild(SD.chip(s, counts[s] + " " + SD.STATE_TEXT[s])); }
        });
      });
      var selected = ctx.route.detail;
      Object.keys(tiles).forEach(function (id) {
        var state = ev.entity[id], tile = tiles[id];
        tile.className = "tile s-" + state + (id === selected ? " sel" : "");
        tile.hidden = onlyBad && (state === "ok");
        tile.setAttribute("aria-label", tile.title + ": " + SD.STATE_TEXT[state]);
      });
      sections.forEach(function (box) {
        var rows = box.querySelectorAll(".loc"), any = false;
        Array.prototype.forEach.call(rows, function (row) {
          var visible = Array.prototype.some.call(row.querySelectorAll(".tile"), function (t) { return !t.hidden; });
          row.hidden = !visible;
          any = any || visible;
        });
        box.hidden = !any;
      });
    }
    return { node: node, update: update, leave: function () { if (drawing) { drawing.leave(); } } };
  } });
})(SD);
