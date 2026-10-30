// Boot: load plant.json (schema 1), then start the shell and the poll loop. ?mock=1 swaps the Web API for the
// simulator in mock.js - only on a local host (the dev preview: python -m http.server in the app folder); on a
// CPU the parameter is ignored, so a link can never make the plant page show simulated states.
(function (SD) {
  "use strict";
  var LOCAL = ["localhost", "127.0.0.1", "[::1]", "::1"];
  SD.mockWanted = function () {
    return /(^|[?&])mock=1(&|$)/.test(location.search.slice(1)) && LOCAL.indexOf(location.hostname) >= 0;
  };

  function fail(message) {
    var host = SD.clear(document.getElementById("view"));
    host.appendChild(SD.el("div", { cls: "banner alarm", role: "alert", text: message }));
    var conn = document.getElementById("conn");
    conn.textContent = "Stopped";
    conn.className = "conn lost";
  }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var tag = document.createElement("script");
      tag.src = src;
      tag.onload = resolve;
      tag.onerror = function () { reject(new Error(src + " cannot be loaded")); };
      document.head.appendChild(tag);
    });
  }

  function start(plant) {
    if (!plant || plant.schema !== 1) {
      throw new Error("plant.json schema " + (plant && plant.schema) + " - this page reads schema 1; regenerate (PL5 650)");
    }
    var mock = null;
    if (SD.mockWanted()) { mock = SD.mock.install(plant, new URLSearchParams(location.search)); }
    var rpc = new SD.Rpc(plant.login, plant.polling);
    var poller = new SD.Poller(rpc, plant);
    SD.shell({ plant: plant, model: new SD.Model(plant), rpc: rpc, poller: poller, mock: mock });
    poller.start();
    window.addEventListener("pagehide", function () { rpc.logout(); });
  }

  fetch("plant.json", { cache: "no-store" })
    .then(function (reply) {
      if (!reply.ok) { throw new Error("plant.json cannot be loaded (HTTP " + reply.status + ")"); }
      return reply.json();
    })
    .then(function (plant) { return SD.mockWanted() ? loadScript("mock.js").then(function () { return plant; }) : plant; })
    .then(start)
    .catch(function (error) { fail("The page cannot start: " + (error && error.message ? error.message : error)); });
})(SD);
