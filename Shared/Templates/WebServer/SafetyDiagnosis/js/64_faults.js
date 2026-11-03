// Active faults: every active cabinet channel, the cabinets whose STATE reports a fault no decoded bit explains,
// the areas' tripped states and causes, the sorters' info members. Rebuilt after every poll.
(function (SD) {
  "use strict";
  SD.view("faults", { label: "Active faults", short: "Faults", icon: "faults", order: 50, nav: true, render: function (ctx) {
    var model = ctx.model, node = SD.el("div"), list = SD.el("div", { cls: "card" }), count = SD.el("span", { cls: "muted" });
    var note = SD.el("p", { cls: "note" });
    SD.add(node, [SD.el("div", { cls: "head" }, [SD.el("h2", { text: "Active faults" }), count]), list, note]);
    var last = "";
    return { node: node, update: function (ev) {
      var faults = ev.faults, key = JSON.stringify(faults) + ev.snap.fresh;
      if (key === last) { return; }
      last = key;
      SD.clear(list);
      count.textContent = ev.snap.fresh ? faults.length + " active" : "no data";
      if (!ev.snap.fresh) {
        list.appendChild(SD.el("div", { cls: "empty", text: "No data from the CPU - the fault list is not known." }));
      } else if (!faults.length) {
        list.appendChild(SD.el("div", { cls: "empty", text: "No active fault." }));
      }
      faults.forEach(function (f) {
        var owner = f.owner && model.byId[f.owner];
        var where = [f.where];
        if (f.cabinet) { where.push(" · "); where.push(SD.el("a", { href: SD.href("cabinets", String(f.cabinet)), text: "cabinet" })); }
        if (owner) { where.push(" · "); where.push(SD.el("a", { href: SD.detailHref(owner.id), text: owner.fld })); }
        if (f.area) { where.push(" · "); where.push(SD.el("a", { href: SD.href("areas"), text: f.area })); }
        list.appendChild(SD.el("div", { cls: "fault" }, [SD.chip(f.severity),
          SD.el("div", { cls: "what" }, [SD.el("div", { text: f.text }), SD.el("div", { cls: "where" }, where)])]));
      });
      note.textContent = model.polarityKnown ? "" : "The diagnosis bits' polarity is not confirmed yet: a cabinet whose STATE "
        + "reports a fault is listed, its channels are not decoded.";
    } };
  } });
})(SD);
