// Machine interfaces: the list, and per interface (#/interfaces/<id>) its elements with their live values -
// PLC tags (I/O), read only while the view is open (M0: tags read about ten times slower than DB members).
(function (SD) {
  "use strict";
  function valueText(value) {
    return value === true ? "TRUE" : value === false ? "FALSE" : value === undefined ? "-" : String(value);
  }

  SD.view("interfaces", { label: "Machine interfaces", short: "Interfaces", icon: "interface", order: 60, nav: true,
    render: function (ctx, route) {
      var plant = ctx.plant, iface = route.arg ? ctx.model.iface[route.arg] : null, node = SD.el("div");
      if (!iface) {
        var tbody = SD.el("tbody");
        plant.interfaces.forEach(function (i) {
          tbody.appendChild(SD.el("tr", { cls: "click", on: { click: function () { location.hash = SD.href("interfaces", i.id); } } }, [
            SD.el("td", { cls: "mono", text: i.id }), SD.el("td", { text: i.machine_type }), SD.el("td", { cls: "wide", text: i.description }),
            SD.el("td", { cls: "num", text: String(i.elements.length) })]));
        });
        SD.add(node, [SD.el("div", { cls: "head" }, SD.el("h2", { text: "Machine interfaces" })),
          plant.interfaces.length ? SD.el("div", { cls: "scroll" }, SD.el("table", { cls: "grid" }, [SD.el("thead", null, SD.el("tr", null,
            ["Interface", "Type", "Description", "Elements"].map(function (h, i) {
              return SD.el("th", { cls: i === 2 ? "wide" : i === 3 ? "num" : "", text: h }); }))), tbody]))
            : SD.el("div", { cls: "empty", text: "This plant has no machine interface." })]);
        return { node: node };
      }
      var cells = {}, body = SD.el("tbody");
      iface.elements.forEach(function (e) {
        cells[e.var] = SD.el("td", { cls: "mono nw", text: "-" });
        body.appendChild(SD.el("tr", null, [SD.el("td", { cls: "mono", text: e.label }), cells[e.var],
          SD.el("td", { cls: "wide", text: e.description }), SD.el("td", { cls: "wide", text: e.category }),
          SD.el("td", { text: e.direction }), SD.el("td", { cls: "mono nw wide", text: e.address })]));
      });
      SD.add(node, [SD.el("div", { cls: "head" }, [SD.el("h2", { text: iface.id }),
        SD.el("a", { cls: "btn", href: SD.href("interfaces"), text: "All interfaces" })]),
        SD.el("p", { cls: "muted", text: iface.description }),
        SD.el("div", { cls: "scroll" }, SD.el("table", { cls: "grid" }, [SD.el("thead", null, SD.el("tr", null,
          ["Element", "Value", "Description", "Category", "Dir", "Address"].map(function (h, i) {
            return SD.el("th", { cls: i === 2 || i === 3 || i === 5 ? "wide" : "", text: h }); }))), body])),
        SD.el("p", { cls: "note", text: "Values are read every " + plant.polling.detail_interval_ms + " ms while this page is open." })]);
      ctx.poller.watch("interface", iface.elements.map(function (e) { return e.var; }), plant.polling.detail_interval_ms);
      return { node: node, leave: function () { ctx.poller.unwatch("interface"); }, update: function (ev) {
        iface.elements.forEach(function (e) {
          var err = ctx.poller.errors[e.var];
          cells[e.var].textContent = err ? "not readable: " + err.message : ev.snap.fresh ? valueText(ev.snap.v[e.var]) : "-";
        });
      } };
    } });
})(SD);
