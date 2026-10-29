// The dev preview's Web API simulator (C-050 M3). app.js loads it only for ?mock=1 on a local host and the page
// then says SIMULATED DATA in a banner on every view. It answers Api.Login / Api.Logout / PlcProgram.Read /
// PlcProgram.Browse like the 1518F did in M0: a token is needed for a read, an expired token answers every call
// code 2 (tokens here live 25 s, so the page's re-login runs), an unknown name answers code 200. The plant's
// faults come and go (two e-stops, a door, a failed node, a warning, one change every 4 s), and PL5_CustomData is
// a sample DB with every shape the custom view renders.
// Options: &polarity=plant keeps the plant's unconfirmed polarity (the page as the CPU shows it before the M0
// watch); &unknown=1 makes one area member unknown to the CPU; &fail=lost drops the link from 6 s to 16 s;
// &fail=rights refuses every read.
(function (SD) {
  "use strict";
  var started = Date.now(), tokens = {}, nextToken = 0, stats = { requests: 0, logins: 0, reads: 0 };

  function hash(text) {
    var h = 2166136261;
    for (var i = 0; i < text.length; i += 1) { h ^= text.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  function sec() { return Math.floor((Date.now() - started) / 1000); }

  // --- PL5_CustomData ------------------------------------------------------------------------------------- //
  function f(name, datatype, extra) {
    var n = { name: name, datatype: datatype };
    Object.keys(extra || {}).forEach(function (k) { n[k] = extra[k]; });
    return n;
  }
  var CUSTOM = [
    f("Counter", "dint"), f("Running", "bool"), f("Speed", "real"), f("Mode", "int"), f("Status", "word"),
    f("Name", "string", { max_length: 20 }), f("Label", "wstring", { max_length: 40 }), f("Letter", "char"),
    f("Uptime", "time"), f("Cycle", "ltime"), f("LastChange", "dtl"), f("Today", "date"), f("Blob", "variant"),
    f("Recipe", "struct", { children: [f("Id", "int"), f("Weight", "real"), f("Active", "bool"),
      f("Limits", "struct", { children: [f("Min", "real"), f("Max", "real")] })] }),
    f("Motor", "struct", { children: [f("Speed", "real"), f("Current", "real"), f("Fault", "bool")] }),
    f("Temperatures", "real", { array_dimensions: [{ start_index: 0, count: 10 }] }),
    f("Grid", "int", { array_dimensions: [{ start_index: 1, count: 3 }, { start_index: 1, count: 4 }] }),
    f("Lanes", "struct", { array_dimensions: [{ start_index: 1, count: 12 }], element: [f("Count", "dint"), f("Full", "bool"),
      f("Destination", "string", { max_length: 16 }), f("Pos", "struct", { children: [f("X", "real"), f("Y", "real")] })] }),
    f("History", "bool", { array_dimensions: [{ start_index: 0, count: 120 }] })
  ];
  var CUSTOM_DB = { name: "PL5_CustomData", datatype: "struct", children: CUSTOM };

  function tokensOf(path) {
    var out = [], i = 0;
    while (i < path.length) {
      var ch = path.charAt(i);
      if (ch === "\"") {
        var j = i + 1, s = "";
        while (j < path.length && path.charAt(j) !== "\"") { if (path.charAt(j) === "\\") { j += 1; } s += path.charAt(j); j += 1; }
        out.push({ name: s });
        i = j + 1;
      } else if (ch === "[") {
        var k = path.indexOf("]", i);
        out.push({ index: path.slice(i + 1, k).split(",").map(Number) });
        i = k + 1;
      } else if (ch === ".") { i += 1; }
      else { var m = /^[^.[]+/.exec(path.slice(i))[0]; out.push({ name: m }); i += m.length; }
    }
    return out;
  }
  // a custom path -> {node, element: true for an array element} or null
  function walk(path) {
    var parts = tokensOf(path), node = null, element = false;
    if (!parts.length || parts[0].name !== CUSTOM_DB.name) { return null; }
    node = CUSTOM_DB;
    for (var i = 1; i < parts.length; i += 1) {
      var p = parts[i];
      if (p.index) {
        if (!node.array_dimensions || p.index.length !== node.array_dimensions.length) { return null; }
        var inside = p.index.every(function (v, d) {
          var dim = node.array_dimensions[d];
          return v >= dim.start_index && v < dim.start_index + dim.count;
        });
        if (!inside) { return null; }
        node = { name: node.name, datatype: node.datatype, children: node.element, elementOf: node };
        element = true;
      } else {
        var list = node.children || [];
        node = list.filter(function (c) { return c.name === p.name; })[0];
        if (!node) { return null; }
        element = false;
      }
    }
    return { node: node, element: element };
  }
  function browse(path) {
    var hit = walk(path || "");
    if (!hit) { return { error: { code: 200, message: "Address does not exist" } }; }
    var n = hit.node;
    if (n.array_dimensions && !hit.element) {
      return { result: [] };
    }
    return { result: (n.children || []).map(function (c) {
      var child = { name: c.name, datatype: c.datatype, db_number: 900, read_only: false };
      if (c.children || c.array_dimensions) { child.has_children = true; }
      if (c.array_dimensions) { child.array_dimensions = c.array_dimensions; }
      if (c.max_length) { child.max_length = c.max_length; }
      return child;
    }) };
  }
  function customValue(path) {
    var hit = walk(path);
    if (!hit) { return { error: { code: 200, message: "Address does not exist" } }; }
    var n = hit.node, h = hash(path), t = sec();
    if (n.children || (n.array_dimensions && !hit.element)) { return { error: { code: 203, message: "Not an elementary value" } }; }
    switch (n.datatype) {
      case "bool": return { result: ((h + t) % 7) < 3 };
      case "dint": return { result: (h % 1000) + t };
      case "int": return { result: (h % 200) - 100 };
      case "real": return { result: Math.round((50 + 40 * Math.sin(t / 5 + h % 10)) * 1000) / 1000 };
      case "word": return { result: h & 0xffff };
      case "string": return { result: "Lane " + (h % 40) };
      case "wstring": return { result: "Prüfung ✓ " + (t % 10) };
      case "char": return { result: String.fromCharCode(65 + (h % 26)) };
      case "time": return { result: 1000 * t + 250 };
      case "ltime": return { result: 1000000 * t + 125 };
      case "dtl": return { result: { year: 2026, month: 10, day: 29, weekday: 5, hour: 9, minute: Math.floor(t / 60) % 60, second: t % 60, nanosecond: 0 } };
      case "date": return { result: "2026-10-29" };
      default: return { error: { code: 202, message: "Unsupported datatype" } };
    }
  }

  // --- the plant ------------------------------------------------------------------------------------------ //
  SD.mock = { stats: stats, install: function (plant, params) {
    var assume = params.get("polarity") !== "plant", failMode = params.get("fail") || "";
    var diag = plant.diag, healthyGuess = /NOT_RUNNING|RESET|Error|Alarm|failed|Not installed|NodesNotInstalled|PROFINET_NODES_ALARM/i;
    function eachMember(fn) {
      plant.areas.forEach(function (a) { a.members.forEach(fn); });
      plant.sorters.forEach(function (s) { s.members.forEach(fn); });
      plant.devices.concat(plant.nodes).forEach(function (e) { (e.members || []).forEach(fn); });
    }
    if (assume) {
      if (diag.alarm_bit === null || diag.alarm_bit === undefined) { diag.alarm_bit = 1; }
      if (diag.warning_bit === null || diag.warning_bit === undefined) { diag.warning_bit = 1; }
      eachMember(function (m) { if (m.healthy === null || m.healthy === undefined) { m.healthy = !healthyGuess.test(m.label + " " + m.var); } });
    }
    var byId = {}, byKind = {};
    plant.devices.concat(plant.nodes).forEach(function (e) { byId[e.id] = e; (byKind[e.kind] = byKind[e.kind] || []).push(e); });
    function pick(kind, n) { var list = byKind[kind] || []; return list.length ? list[n % list.length] : null; }
    var active = {}, warn = {};
    [pick("estop", 7), pick("estop", 60), pick("door", 1)].forEach(function (e) { if (e) { active[e.id] = true; } });
    var failedNode = (plant.nodes.filter(function (n) { return plant.devices.some(function (d) { return (d.nodes || []).indexOf(n.id) >= 0; }); })[3]) || null;
    if (failedNode) { active[failedNode.id] = true; }
    var tri = plant.cabinets.filter(function (c) { return c.tristate; })[0];
    var warned = tri && tri.bits.filter(function (b) { return b.owner; })[5];
    if (warned) { warn[warned.owner] = true; }
    var flip = [];        // one more device at a time is faulted, a different one every 4 s
    ["estop", "contactor", "breaker"].forEach(function (k) { (byKind[k] || []).forEach(function (e, i) { if (i % 9 === 4) { flip.push(e.id); } }); });

    function on(id) {
      if (active[id] || (flip.length && flip[Math.floor(sec() / 4) % flip.length] === id)) { return true; }
      var e = byId[id];
      return !!(e && (e.nodes || []).some(function (n) { return active[n]; }));
    }
    function raw(isActive, polarity) {
      var p = polarity === null || polarity === undefined ? 1 : polarity;
      return isActive ? p : 1 - p;
    }
    function words(cab) {
      var w = {}, anyAlarm = false, anyWarning = false, alarmAt = {}, warningAt = {};
      Object.keys(cab.words).forEach(function (k) { w[k] = 0; });
      cab.bits.forEach(function (b) { (b.warning ? warningAt : alarmAt)[b.bit] = b; });
      for (var bit = 0; bit < 64; bit += 1) {
        var entry = alarmAt[bit], went = warningAt[bit];
        var alarmOn = !!(entry && entry.owner && on(entry.owner));
        var warnOn = !!((went && went.owner && on(went.owner)) || (cab.tristate && entry && entry.owner && warn[entry.owner] && !alarmOn));
        anyAlarm = anyAlarm || alarmOn;
        anyWarning = anyWarning || warnOn;
        var aw = cab.alarm_words[bit < 32 ? 0 : 1], ww = cab.warning_words[bit < 32 ? 0 : 1];
        if (aw && raw(alarmOn, diag.alarm_bit)) { w[aw] = (w[aw] | (1 << (bit % 32))) >>> 0; }
        if (ww && raw(warnOn, diag.warning_bit)) { w[ww] = (w[ww] | (1 << (bit % 32))) >>> 0; }
      }
      if (cab.words.STATE) {
        w.STATE = ((anyAlarm ? 1 << diag.state_alarm_bit : 0) | (anyWarning ? 1 << diag.state_warning_bit : 0) | 1) >>> 0;
      }
      return w;
    }

    var areaHit = {};
    function areaTripped(areaId) {
      var kids = plant.areas.filter(function (a) { return a.parent === areaId; }).map(function (a) { return a.id; });
      var own = plant.devices.some(function (d) { return (d.areas || []).indexOf(areaId) >= 0 && on(d.id) && d.kind !== "contactor"; });
      return own || kids.some(areaTripped);
    }
    function cause(areaId, kinds) {
      return plant.devices.some(function (d) { return (d.areas || []).indexOf(areaId) >= 0 && on(d.id) && kinds.indexOf(d.kind) >= 0; });
    }
    var values = {};
    function memberValue(m, bad) { return m.healthy === null || m.healthy === undefined ? !!bad : bad ? !m.healthy : m.healthy; }
    plant.cabinets.forEach(function (cab) {
      Object.keys(cab.words).forEach(function (k) { values[cab.words[k]] = function () { return words(cab)[k]; }; });
    });
    plant.areas.forEach(function (a) {
      a.members.forEach(function (m) {
        values[m.var] = function () {
          if (m.role === "cause") {
            var kinds = /PUSHBUTTON|PB/.test(m.var) ? ["estop"] : /FEEDBACK|FDB/.test(m.var) ? ["contactor"]
              : /BREAKER/.test(m.var) ? ["breaker"] : /DOOR/.test(m.var) ? ["door"] : [];
            return memberValue(m, cause(a.id, kinds));
          }
          if (m.role === "reset") { return false; }
          areaHit[a.id] = areaTripped(a.id);
          return memberValue(m, areaHit[a.id]);
        };
      });
    });
    plant.sorters.forEach(function (s) {
      s.members.forEach(function (m) { values[m.var] = function () { return memberValue(m, s.area ? areaTripped(s.area) : false); }; });
    });
    plant.devices.concat(plant.nodes).forEach(function (e) {
      (e.members || []).forEach(function (m) {
        values[m.var] = function () { return /NodesNotInstalled|00_Commissioning/.test(m.var) ? false : memberValue(m, on(e.id)); };
      });
      (e.tags || []).forEach(function (t) {
        values[t.var] = function () { return /^[IE]/.test(t.address) ? !on(e.id) : (hash(t.var) % 2 === 0); };
      });
    });
    plant.interfaces.forEach(function (i) {
      i.elements.forEach(function (el) {
        values[el.var] = function () { return /HEARTBEAT/.test(el.var) ? sec() % 2 === 0 : (el.data_type || "").toUpperCase() === "BOOL" ? hash(el.var) % 3 !== 0 : hash(el.var) % 100; };
      });
    });
    var unknownVar = params.get("unknown") === "1" && plant.areas[0] && plant.areas[0].members[plant.areas[0].members.length - 1];
    if (unknownVar) { delete values[unknownVar.var]; }

    function answer(entry) {
      var method = entry.method, p = entry.params || {};
      if (method === "Api.Login") {
        if (["Everybody", "Anonymous"].indexOf(p.user) < 0 || p.password !== "") { return { error: { code: 100, message: "Login failed" } }; }
        stats.logins += 1;
        nextToken += 1;
        var token = "mock-" + nextToken;
        tokens[token] = Date.now() + 25000;
        return { result: { token: token } };
      }
      if (method === "Api.Logout") { return { result: true }; }
      return null;
    }
    SD.transport = function (payload, token, timeoutMs) {
      stats.requests += 1;
      var age = (Date.now() - started) / 1000;
      return new Promise(function (resolve, reject) {
        setTimeout(function () {
          if (failMode === "lost" && age > 6 && age < 16) {
            var error = new Error("the CPU cannot be reached");
            error.kind = "network";
            reject(error);
            return;
          }
          var valid = token && tokens[token] && tokens[token] > Date.now();
          resolve({ status: 200, data: payload.map(function (entry) {
            var out = answer(entry);
            if (!out) {
              if (!valid || failMode === "rights") { out = { error: { code: 2, message: "Permission denied" } }; }
              else if (entry.method === "PlcProgram.Browse") { out = browse(entry.params && entry.params["var"]); }
              else if (entry.method === "PlcProgram.Read") {
                stats.reads += 1;
                var name = entry.params["var"];
                out = values[name] ? { result: values[name]() } : name.indexOf("\"" + CUSTOM_DB.name + "\"") === 0 ? customValue(name)
                  : { error: { code: 200, message: "Address does not exist" } };
              } else { out = { error: { code: -32601, message: "Method not found" } }; }
            }
            return { jsonrpc: "2.0", id: entry.id, result: out.result, error: out.error };
          }) });
        }, 25 + (hash(String(stats.requests)) % 40));
      });
    };
    return { note: assume ? " Polarity assumed for the preview: a set bit is active, members healthy by their name." : "" };
  } };
})(window.SD);
