// Configuration problems: the plant.json variables the CPU refused (dropped from the poll), with the plant
// model's run id - the program on the CPU and the PL5 run that generated this page disagree.
(function (SD) {
  "use strict";
  SD.view("problems", { label: "Configuration problems", icon: "faults", order: 90, nav: false, render: function (ctx) {
    var node = SD.el("div"), host = SD.el("div"), last = "";
    SD.add(node, [SD.el("div", { cls: "head" }, SD.el("h2", { text: "Configuration problems" })),
      SD.el("p", { cls: "muted", text: "These variables of the plant model (PL5 run " + ctx.plant.meta.run + ", generated "
        + ctx.plant.meta.generated + ") cannot be read on this CPU and are no longer polled. Regenerate the web application "
        + "(PL5 650) from the project the CPU runs and upload it again." }), host]);
    return { node: node, update: function () {
      var problems = ctx.poller.problems(), key = JSON.stringify(problems);
      if (key === last) { return; }
      last = key;
      SD.clear(host);
      if (!problems.length) { host.appendChild(SD.el("div", { cls: "empty", text: "Every variable of the plant model is readable." })); return; }
      var tbody = SD.el("tbody");
      problems.forEach(function (p) {
        tbody.appendChild(SD.el("tr", null, [SD.el("td", { cls: "mono", text: p.var }), SD.el("td", { cls: "num", text: String(p.code) }),
          SD.el("td", { text: p.message })]));
      });
      host.appendChild(SD.el("div", { cls: "scroll" }, SD.el("table", { cls: "grid" }, [SD.el("thead", null, SD.el("tr", null,
        ["Variable", "Code", "CPU message"].map(function (h) { return SD.el("th", { text: h }); }))), tbody])));
    } };
  } });
})(SD);
