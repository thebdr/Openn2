// The safety diagnosis page (C-050) - a read-only Web API web application served by the S7-1500 F CPU. PL5 650
// joins js/*.js into app.js in name order; each file adds to the one SD namespace. Every text from plant.json
// or the PLC is set with textContent / createTextNode, never as HTML.
var SD = window.SD = window.SD || {};
(function (SD) {
  "use strict";
  var SVG = "http://www.w3.org/2000/svg";

  // el("tr", {cls: "click", text: "...", on: {click: f}, title: "..."}, [child nodes / strings])
  SD.el = function (tag, props, kids) {
    var node = document.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (key) {
        var value = props[key];
        if (value === undefined || value === null || value === false) { return; }
        if (key === "cls") { node.className = value; }
        else if (key === "text") { node.textContent = String(value); }
        else if (key === "on") { Object.keys(value).forEach(function (ev) { node.addEventListener(ev, value[ev]); }); }
        else { node.setAttribute(key, value === true ? "" : String(value)); }
      });
    }
    SD.add(node, kids);
    return node;
  };
  SD.add = function (node, kids) {
    (Array.isArray(kids) ? kids : kids === undefined || kids === null ? [] : [kids]).forEach(function (kid) {
      if (kid === undefined || kid === null || kid === false) { return; }
      if (Array.isArray(kid)) { SD.add(node, kid); return; }
      node.appendChild(typeof kid === "object" ? kid : document.createTextNode(String(kid)));
    });
    return node;
  };
  SD.clear = function (node) {
    while (node.firstChild) { node.removeChild(node.firstChild); }
    return node;
  };
  SD.icon = function (name, cls) {
    var svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("class", "ico" + (cls ? " " + cls : ""));
    svg.setAttribute("aria-hidden", "true");
    var use = document.createElementNS(SVG, "use");
    use.setAttribute("href", "icons.svg#" + (name || "device"));
    svg.appendChild(use);
    return svg;
  };

  // the states the page shows, worst last; "node" = unknown because the device's PROFINET node failed
  SD.STATES = ["ok", "stale", "unknown", "node", "warning", "alarm"];
  SD.STATE_TEXT = { ok: "OK", warning: "Warning", alarm: "Alarm", unknown: "Unknown", node: "Unknown - node failed",
    stale: "No data", info: "Info" };
  SD.worse = function (a, b) { return SD.STATES.indexOf(b) > SD.STATES.indexOf(a) ? b : a; };
  SD.chip = function (state, text, title) {
    return SD.el("span", { cls: "chip s-" + state, text: text || SD.STATE_TEXT[state] || state, title: title });
  };
  SD.setState = function (node, state) {
    node.className = node.className.replace(/\bs-[a-z]+\b/g, "").trim() + " s-" + state;
    return node;
  };

  SD.quote = function (name) { return "\"" + String(name).replace(/"/g, "\\\"") + "\""; };
  SD.byText = function (key) {
    return function (a, b) { return String(a[key] || "").localeCompare(String(b[key] || ""), "en", { numeric: true }); };
  };
  SD.matches = function (needle, fields) {
    if (!needle) { return true; }
    var hay = fields.join(" ").toLowerCase();
    return needle.toLowerCase().split(/\s+/).every(function (word) { return hay.indexOf(word) >= 0; });
  };
  SD.clock = function (date) {
    return date ? date.toLocaleTimeString("en-GB", { hour12: false }) : "";
  };
  SD.debounce = function (fn, ms) {
    var timer = null;
    return function () {
      var args = arguments, self = this;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(self, args); }, ms);
    };
  };
})(SD);
