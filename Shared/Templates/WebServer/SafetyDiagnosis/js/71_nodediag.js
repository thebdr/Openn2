// A PROFINET node's diagnostics from the CPU itself (user 2026-10-29): read when its detail panel opens and on
// Refresh, never polled. The methods depend on the CPU's firmware (Web server Function Manual 11/2025,
// A5E53797648-AB, S7-1500): from V4.1 Modules.Browse finds the node by its TIA device name and Modules.ReadStatus
// gives the status and diagnostic texts of the node and of each of its modules; from V3.1 Alarms.Browse gives the
// CPU's active alarms - the node's are those with its or a module's hardware ID or its name in the text.
// Api.Browse says which the CPU has: the 1518F at V2.9.4 has none, so the panel says what is needed instead.
// All need the read_diagnostics right (the anonymous user has it on the 1518F).
(function (SD) {
  "use strict";
  // Modules.ReadStatus status.own -> the page's state; any other (deactivated, unknown) is unknown
  var STATE = { good: "ok", maintenance_required: "warning", maintenance_demanded: "warning", error: "alarm", not_reachable: "alarm",
    io_not_available: "alarm" };
  var cache = {};

  // one call -> Promise result; refused -> rejected with the reason
  function call(rpc, method, params) {
    return rpc.calls([{ method: method, params: params }]).then(function (entries) {
      var error = entries[0].error;
      if (error) { throw new Error(error.code === SD.DENIED ? "no read_diagnostics right" : error.message + " (code " + error.code + ")"); }
      return entries[0].result;
    });
  }
  function status(entry) {
    var r = entry.result;
    if (!r || !r.status) { return { error: entry.error ? entry.error.message : "no status" }; }
    return { own: r.status.own, sub: r.status.subordinate, texts: (r.messages || []).map(function (m) { return m && m.text; }).filter(Boolean) };
  }
  // the texts' language: an active English project language, else the first one, else en-US
  function language(rpc, has) {
    cache.lang = cache.lang || (has["Project.ReadLanguages"] ? call(rpc, "Project.ReadLanguages", { mode: "active" }) : Promise.resolve({}))
      .then(function (r) {
        var list = ((r && r.languages) || []).map(function (l) { return l.language; });
        return list.filter(function (l) { return /^en/i.test(l); })[0] || list[0] || "en-US";
      }, function () { return "en-US"; });
    return cache.lang;
  }
  // the hardware configuration's devices and CPU modules (the root and its children) by lower-case TIA name
  function devices(rpc, fresh) {
    if (fresh || !cache.devices) {
      cache.devices = call(rpc, "Modules.Browse", { mode: "children" }).then(function (r) {
        var out = {};
        (r.nodes || []).forEach(function (n) {
          [n].concat(n.children || []).forEach(function (c) { if (c.type === "device" || c.subtype === "cpu") { out[c.name.toLowerCase()] = c; } });
        });
        return out;
      });
      cache.devices.catch(function () { cache.devices = null; });
    }
    return cache.devices;
  }

  // -> Promise {hw, al (the CPU has the methods), device, status, modules, alarms, problems}
  SD.readNodeDiag = function (rpc, e, fresh) {
    var out = { modules: [], problems: [] }, ids = {}, name = e.name.toLowerCase();
    function failed(what) { return function (error) { out.problems.push(what + ": " + error.message); }; }
    return rpc.methods().then(function (has) {
      out.hw = has["Modules.Browse"] && has["Modules.ReadStatus"];
      out.al = has["Alarms.Browse"];
      return (out.hw || out.al) && language(rpc, has).then(function (lang) {
        return (out.hw ? devices(rpc, fresh).then(function (list) {
          var dev = out.device = list[name];
          return dev && call(rpc, "Modules.Browse", { hwid: dev.hwid, mode: "children" }).then(function (r) {
            var kids = (((r.nodes || [])[0] || {}).children || []).slice(0, 40), all = [dev].concat(kids);
            all.forEach(function (n) { ids[n.hwid] = true; });
            return rpc.calls(all.map(function (n) { return { method: "Modules.ReadStatus", params: { hwid: n.hwid, language: lang } }; }))
              .then(function (entries) {
                out.status = status(entries[0]);
                out.modules = kids.map(function (k, i) { return { name: k.name, type: k["class"], status: status(entries[i + 1]) }; });
              });
          });
        }).catch(failed("Hardware status")) : Promise.resolve()).then(function () {
          return out.al && call(rpc, "Alarms.Browse", { language: lang, count: 200 }).then(function (r) {
            out.alarms = (r.entries || []).filter(function (a) { return ids[a.hwid] || (a.alarm_text || "").toLowerCase().indexOf(name) >= 0; });
          }, failed("Alarms"));
        });
      });
    }).then(function () { return out; });
  };

  // the detail panel's section for node `e` -> {node, leave}
  SD.nodeDiag = function (ctx, e) {
    var gone = false, body = SD.el("div");
    var refresh = SD.el("button", { cls: "btn", type: "button", title: "Read again from the CPU" }, [SD.icon("refresh"), "Refresh"]);
    var node = SD.el("div", null, [SD.el("div", { cls: "head sub" }, [SD.el("h3", { cls: "section", text: "CPU diagnostics" }), refresh]), body]);
    function note(text, cls) { return SD.el("p", { cls: cls || "note", text: text }); }
    function chip(s) {
      if (s.error) { return SD.chip("unknown", "Not readable: " + s.error); }
      var own = String(s.own || "unknown").replace(/^io_/, "I/O_").replace(/_/g, " ");
      return SD.chip(STATE[s.own] || "unknown", own.charAt(0).toUpperCase() + own.slice(1) + (s.sub === "error" ? " - a module has a problem" : ""));
    }
    function grid(head, rows) {
      return SD.el("div", { cls: "scroll" }, SD.el("table", { cls: "grid" }, [SD.el("thead", null, SD.el("tr", null, head.map(function (h) {
        return SD.el("th", { text: h }); }))), SD.el("tbody", null, rows.map(function (r) {
        return SD.el("tr", null, r.map(function (c) { return SD.el("td", null, c); })); }))]));
    }
    function show(r) {
      SD.clear(body);
      refresh.hidden = !r.hw && !r.al;
      if (refresh.hidden) {
        return body.appendChild(note("This CPU's Web API has no diagnostics methods: a node's status needs S7-1500 firmware V4.1 or later "
          + "(Modules.ReadStatus), its alarms V3.1 or later (Alarms.Browse)."));
      }
      if (r.hw && !r.device && !r.problems.length) { body.appendChild(note("The CPU's hardware configuration has no device named " + e.name + ".")); }
      if (r.status) {
        SD.add(body, [SD.el("dl", { cls: "kv" }, [SD.el("dt", { text: "Status" }), SD.el("dd", null, chip(r.status)), SD.el("dt", { text: "Hardware" }),
          SD.el("dd", { text: (r.device["class"] ? r.device["class"] + ", " : "") + "HW ID " + r.device.hwid })]),
          r.status.texts.map(function (t) { return SD.el("p", { cls: "msg", text: t }); })]);
      }
      if (r.modules.length) {     // their texts are in the node's own (a node's messages cover its child nodes)
        body.appendChild(grid(["Status", "Module", "Type"], r.modules.map(function (m) { return [chip(m.status), m.name, m.type]; })));
      }
      if (r.alarms) {
        body.appendChild(note(r.alarms.length ? "Active alarms (" + r.alarms.length + ")" : "No active alarm of this node on the CPU."));
        r.alarms.forEach(function (a) {
          var ack = a.acknowledgement && a.acknowledgement.state === "not_acknowledged" ? ", not acknowledged" : "";
          body.appendChild(SD.el("div", { cls: "msg" }, [SD.chip(a.status === "outgoing" ? "ok" : "alarm",
            (a.status === "outgoing" ? "Outgoing" : "Incoming") + ack), " ", SD.el("span", { cls: "muted", text: a.timestamp
            ? new Date(a.timestamp).toLocaleString() : "" }), SD.el("div", { text: (a.alarm_text || "") + (a.info_text ? " - " + a.info_text : "") })]));
        });
      }
      r.problems.forEach(function (p) { body.appendChild(note("Not read - " + p, "note err")); });
      body.appendChild(note("Read at " + new Date().toLocaleTimeString() + ", not refreshed automatically"
        + (r.hw ? "." : "; alarms matched by the node's name (finding its modules needs firmware V4.1).")));
    }
    function load(fresh) {
      refresh.disabled = true;
      SD.clear(body).appendChild(note("Reading from the CPU..."));
      SD.readNodeDiag(ctx.rpc, e, fresh).then(function (r) { if (!gone) { show(r); } }, function (error) {
        if (!gone) { SD.clear(body).appendChild(note("The CPU's diagnostics cannot be read: " + error.message, "note err")); }
      }).then(function () { refresh.disabled = false; });
    }
    refresh.addEventListener("click", function () { load(true); });
    load(false);
    return { node: node, leave: function () { gone = true; } };
  };
})(SD);
