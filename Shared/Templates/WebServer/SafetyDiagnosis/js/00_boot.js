// The M2 placeholder (C-050): loads plant.json and lists what it holds. M3 replaces it with the page itself.
// Every text is set with textContent; nothing is written to the PLC.
(function () {
  "use strict";
  function text(tag, value) {
    var node = document.createElement(tag);
    node.textContent = value;
    return node;
  }
  function show(plant) {
    var main = document.getElementById("main");
    main.textContent = "";
    document.getElementById("title").textContent = plant.app.title;
    document.getElementById("plc").textContent = plant.plc.station + " " + plant.plc.ip + " - run " + plant.meta.run;
    var table = document.createElement("table");
    plant.kinds.forEach(function (kind) {
      var row = document.createElement("tr");
      row.appendChild(text("th", kind.plural));
      row.appendChild(text("td", String(plant.counts.kinds[kind.kind] || 0)));
      table.appendChild(row);
    });
    [["Areas", plant.areas.length], ["Diagnosis cabinets", plant.cabinets.length],
     ["Machine interfaces", plant.interfaces.length], ["Variables per refresh", plant.poll.length]]
      .forEach(function (pair) {
        var row = document.createElement("tr");
        row.appendChild(text("th", pair[0]));
        row.appendChild(text("td", String(pair[1])));
        table.appendChild(row);
      });
    main.appendChild(table);
  }
  fetch("plant.json", { cache: "no-store" })
    .then(function (reply) {
      if (!reply.ok) { throw new Error("plant.json: HTTP " + reply.status); }
      return reply.json();
    })
    .then(show)
    .catch(function (error) { document.getElementById("status").textContent = String(error); });
})();
