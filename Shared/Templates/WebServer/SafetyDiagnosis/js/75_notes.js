// Notes: every device note (the project's and this browser's edits), with the download of webui_notes.csv for
// the project's config and the discard of this browser's edits.
(function (SD) {
  "use strict";
  SD.view("notes", { label: "Notes", icon: "note", order: 75, nav: true, render: function (ctx) {
    var notes = ctx.notes, model = ctx.model, node = SD.el("div"), host = SD.el("div"), count = SD.el("span", { cls: "muted" });
    var save = SD.el("button", { cls: "btn", type: "button", text: "Download webui_notes.csv",
      on: { click: function () { SD.download("webui_notes.csv", notes.csv(), "text/csv"); } } });
    var discard = SD.el("button", { cls: "btn", type: "button", text: "Discard this browser's edits", on: { click: function () {
      if (window.confirm("Discard the notes edited in this browser? The project's notes stay.")) { notes.discard(); draw(); }
    } } });
    SD.add(node, [SD.el("div", { cls: "head" }, [SD.el("h2", { text: "Notes" }), count]),
      SD.el("div", { cls: "toolbar" }, [save, discard]),
      SD.el("p", { cls: "note", text: "Notes are written in a device's detail panel and kept in this browser. To show them on "
        + "every browser, download webui_notes.csv, save it in the project's webui config (config_project/systems/"
        + "siemens_s7_safety/webui/), run 650 again and upload the application." }), host]);

    function draw() {
      var keys = notes.keys(), byKey = {};
      model.entities.forEach(function (e) { byKey[e.kind + "|" + e.fld] = e; });
      count.textContent = keys.length + " note(s), " + notes.edits() + " edited in this browser";
      discard.disabled = !notes.edits();
      SD.clear(host);
      if (!keys.length) { host.appendChild(SD.el("div", { cls: "empty", text: "No note yet - open a device and write one." })); return; }
      var tbody = SD.el("tbody");
      keys.forEach(function (key) {
        var n = notes.get(key), e = byKey[key], kind = e && model.kind[e.kind];
        tbody.appendChild(SD.el("tr", { cls: e ? "click" : "", on: e ? { click: function () { SD.open(e.id); } } : null }, [
          SD.el("td", { cls: "mono", text: key.slice(key.indexOf("|") + 1) }), SD.el("td", { cls: "wide", text: kind ? kind.label : "" }),
          SD.el("td", { cls: "notetext", text: n.text }),
          SD.el("td", { cls: "wide nw", text: n.updated + (n.local ? " (this browser)" : "") })]));
      });
      host.appendChild(SD.el("div", { cls: "scroll" }, SD.el("table", { cls: "grid" }, [SD.el("thead", null, SD.el("tr", null,
        ["Device", "Kind", "Note", "Edited"].map(function (h, i) { return SD.el("th", { cls: i === 1 || i === 3 ? "wide" : "", text: h }); }))),
        tbody])));
    }
    draw();
    return { node: node };
  } });
})(SD);
