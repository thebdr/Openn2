// Overview: one tab per plant.layout.overview_tabs entry (#/overview/<n>), each with the area and cabinet strips,
// one summary card per kind of the tab, then the plant - the drawing with the tab's icons (55_drawing.js) when the
// project has one, and the auto schematic: the tab's devices and PROFINET nodes as tiles, grouped by
// plant.layout.group_by (functional unit, then location). A tab's "nodes" list, when it has one, keeps its node
// kinds to those nodes (the ones its devices are wired to). The layout filter (regular expressions, one per line,
// kept in this browser) hides the drawing's icons and the schematic's tiles that match none of them.
(function (SD) {
  "use strict";
  // the overview's tabs (plant.layout.overview_tabs, else one tab of every kind)
  SD.overviewTabs = function (ctx) {
    var tabs = ctx.plant.layout.overview_tabs;
    return tabs && tabs.length ? tabs : [{ label: "All devices", kinds: ctx.model.kinds.map(function (k) { return k.kind; }), nodes: null }];
  };
  function inTabOf(ctx, t, e) {
    return t.kinds.indexOf(e.kind) >= 0 && (!t.nodes || ctx.model.kind[e.kind].state !== "node" || t.nodes.indexOf(e.id) >= 0);
  }
  // "Show on layout": the first tab showing the device, its detail panel open, the view centred on it
  SD.layoutHref = function (ctx, e) {
    var tabs = SD.overviewTabs(ctx), at = 0;
    tabs.some(function (t, i) { if (inTabOf(ctx, t, e)) { at = i; return true; } return false; });
    return SD.href("overview", String(at), e.id) + "&at=" + encodeURIComponent(e.id);
  };

  SD.view("overview", { label: "Overview", icon: "overview", order: 10, nav: true, render: function (ctx, route) {
    var model = ctx.model, plant = ctx.plant, tiles = {}, areaChips = {}, cabChips = {}, kindChips = {}, onlyBad = false;
    var tabs = SD.overviewTabs(ctx);
    var tab = Math.min(tabs.length - 1, Math.max(0, parseInt(route.arg, 10) || 0));
    var kinds = model.kinds.filter(function (k) { return tabs[tab].kinds.indexOf(k.kind) >= 0; });
    var inTab = {}, shownIds = [];
    function members(k) {
      return (model.byKind[k.kind] || []).filter(function (e) { return inTabOf(ctx, tabs[tab], e); });
    }
    kinds.forEach(function (k) { members(k).forEach(function (e) { inTab[e.id] = true; shownIds.push(e.id); }); });
    var tabBar = tabs.length > 1 ? SD.el("div", { cls: "tabs" }, tabs.map(function (t, i) {
      return SD.el("a", { href: SD.href("overview", String(i)), cls: i === tab ? "on" : "", text: t.label });
    })) : null;
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
    kinds.forEach(function (k) {
      var shown = members(k).length, all = (model.byKind[k.kind] || []).length;
      kindChips[k.kind] = SD.el("div", { cls: "chips" });
      summary.appendChild(SD.el("a", { href: SD.href("list", k.kind), title: shown < all ? "the " + k.plural
        + " this tab's devices are wired to" : "" }, [
        SD.el("div", { cls: "n" }, [SD.icon(k.icon), SD.el("span", { text: k.plural + " " }),
          SD.el("span", { cls: "muted", text: shown < all ? shown + " of " + all : String(all) })]), kindChips[k.kind]]));
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
    kinds.forEach(function (k) {
      members(k).forEach(function (e) {
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

    // the layout filter: one text for every tab, kept in this browser
    var filterKey = "pl5-layout-filter-v1:" + (plant.meta.project || plant.app.name), filterText = "";
    try { filterText = localStorage.getItem(filterKey) || ""; } catch (e) { filterText = ""; }
    var filterBox = SD.el("textarea", { cls: "filterbox", rows: "2", spellcheck: "false", "aria-label": "Layout filter",
      placeholder: "Filter: regular expressions, one per line, matched against the FLD, PROFINET name, IP and description "
        + "(e.g. ^=IH04 or S505)" });
    filterBox.value = filterText;
    var filterNote = SD.el("p", { cls: "note" }), findNote = SD.el("p", { cls: "note", hidden: true });
    var patterns = SD.patterns(filterText), pass = {}, finding = null, findTimer = 0;
    filterBox.addEventListener("input", SD.debounce(function () {
      patterns = SD.patterns(filterBox.value);
      try { localStorage.setItem(filterKey, filterBox.value); } catch (e) { /* this browser keeps no filter */ }
      if (ctx.ev) { update(ctx.ev); }
    }, 250));
    var drawing = plant.layout.image ? SD.drawing(ctx, function (e) { return !!inTab[e.id]; }) : null, plantHead = null;
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
      SD.el("div", { cls: "head" }, [SD.el("h2", { text: "Overview" }), toggle]), tabBar,
      SD.el("h3", { cls: "section", text: "Areas" }), areaStrip,
      SD.el("h3", { cls: "section", text: "Diagnosis cabinets" }), cabStrip,
      SD.el("h3", { cls: "section", text: "Devices" }), summary,
      SD.el("h3", { cls: "section", text: drawing ? "Plant" : "Plant (" + levels.join(", then ").replace(/_/g, " ") + ")" }),
      filterBox, filterNote, findNote, plantHead, drawing ? drawing.node : null, schematic]);

    // "Show on layout" (SD.layoutHref): the drawing centred on the icon, else the schematic scrolled to the tile
    function focus(id) {
      var e = model.byId[id];
      if (!e || !inTab[id]) { return; }
      findNote.hidden = true;
      if (drawing && drawing.has(id)) {
        showDrawing(true);
        drawing.show(id);
        drawing.box.scrollIntoView({ block: "center" });
        return;
      }
      if (drawing) {
        showDrawing(false);
        findNote.textContent = e.fld + " has no position on the plant drawing - shown in the schematic.";
        findNote.hidden = false;
      }
      finding = id;
      clearTimeout(findTimer);
      findTimer = setTimeout(function () { finding = null; if (ctx.ev) { update(ctx.ev); } }, 2600);
      if (ctx.ev) { update(ctx.ev); }
      tiles[id].scrollIntoView({ block: "center" });
    }

    function update(ev) {
      pass = {};
      var passing = 0;
      shownIds.forEach(function (id) {
        var e = model.byId[id];
        pass[id] = SD.matchesAny(patterns.res, [e.fld, e.name, e.ip, e.description]);
        passing += pass[id] ? 1 : 0;
      });
      filterNote.textContent = (patterns.res.length ? passing + " of " + shownIds.length + " match the filter. " : "")
        + (patterns.bad.length ? "Not applied: " + patterns.bad.join("; ") : "");
      filterNote.hidden = !filterNote.textContent;
      if (drawing) { drawing.update(ev, onlyBad, patterns.res.length ? pass : null); }
      plant.areas.forEach(function (a) { SD.setState(areaChips[a.id], ev.area[a.id].state); });
      plant.cabinets.forEach(function (c) { SD.setState(cabChips[c.id], ev.cabinet[c.id].summary.state); });
      kinds.forEach(function (k) {
        var counts = model.count(ev, members(k)), host = SD.clear(kindChips[k.kind]);
        ["alarm", "warning", "node", "unknown", "stale", "ok"].forEach(function (s) {
          if (counts[s]) { host.appendChild(SD.chip(s, counts[s] + " " + SD.STATE_TEXT[s])); }
        });
        if (counts.ni) { host.appendChild(SD.el("span", { cls: "chip ni", text: counts.ni + " not installed" })); }
      });
      var selected = ctx.route.detail;
      Object.keys(tiles).forEach(function (id) {
        var state = ev.entity[id], tile = tiles[id];
        var e = model.byId[id];
        tile.className = "tile s-" + state + (ev.ni[id] ? " ni" : "") + (id === selected ? " sel" : "")
          + (id === finding ? " find" : "") + (ctx.notes.get(e.kind + "|" + e.fld).text ? " noted" : "");
        tile.hidden = id !== selected && ((onlyBad && state === "ok") || !pass[id]);   // the open one stays
        tile.setAttribute("aria-label", tile.title + ": " + SD.STATE_TEXT[state] + (ev.ni[id] ? ", node not installed" : ""));
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
    return { node: node, update: update, focus: focus,
      leave: function () { clearTimeout(findTimer); if (drawing) { drawing.leave(); } } };
  } });
})(SD);
