// Custom data: the users' own standard DB (plant.custom_data.db, "PL5_CustomData"), which PL5 never generates.
// Its structure is discovered live with PlcProgram.Browse when the view opens and on Refresh - so a member added
// in TIA shows after a download, with no PL5 run and no upload. A struct renders as a name / value / type grid
// (nested structs as expandable sections), an array of values as a one-column table, an array of structs as a
// table with the indexes as rows and the members as columns, a multi-dimensional array one slice at a time
// (the leading indexes picked, the last one as rows). Long arrays page by page_rows. Only the cells on screen
// are read, at most max_cells, every interval_ms, only while the view is open. A cell the Web API cannot read
// shows "not readable via Web API". The Browse fields used: name, datatype, has_children, array_dimensions
// [{start_index, count}], max_length (C-050 M0 step 9 checks them on the CPU).
(function (SD) {
  "use strict";
  var ELEMENTARY = /^(bool|byte|word|dword|lword|sint|int|dint|lint|usint|uint|udint|ulint|real|lreal|char|wchar|string|wstring|s5time|time|ltime|date|time_of_day|tod|ltime_of_day|ltod|date_and_time|dt|ldt|dtl)$/i;
  var BITS = { byte: 2, word: 4, dword: 8, lword: 16 };

  function isArray(n) { return n.array_dimensions && n.array_dimensions.length > 0; }
  function isStruct(n) { return !isArray(n) && (n.has_children || /^struct$/i.test(n.datatype || "")) && !ELEMENTARY.test(n.datatype || ""); }

  SD.formatValue = function (value, type) {
    var t = String(type || "").toLowerCase();
    if (value === undefined) { return "-"; }
    if (value === null) { return "null"; }
    if (typeof value === "boolean") { return value ? "TRUE" : "FALSE"; }
    if (typeof value === "number") {
      if (BITS[t]) { return "16#" + ("0000000000000000" + (value >>> 0).toString(16).toUpperCase()).slice(-BITS[t]); }
      if (t === "real" || t === "lreal") { return String(Math.abs(value) >= 1e7 || (value !== 0 && Math.abs(value) < 1e-4) ? value.toExponential(6) : +value.toPrecision(7)); }
      if (t === "time" || t === "s5time") { return "T#" + value + "ms"; }
      if (t === "ltime") { return "LT#" + value + "ns"; }
      return String(value);
    }
    if (typeof value === "string") { return value; }
    if (typeof value === "object") {
      return Object.keys(value).map(function (k) { return k + "=" + SD.formatValue(value[k]); }).join(" ");
    }
    return String(value);
  };

  SD.view("custom", { label: "Custom data", short: "Custom", icon: "custom", order: 70, nav: true, render: function (ctx) {
    var cfg = ctx.plant.custom_data, rpc = ctx.rpc, poller = ctx.poller, root = SD.quote(cfg.db);
    var node = SD.el("div", { cls: "cd" }), body = SD.el("div"), info = SD.el("p", { cls: "note" });
    var refresh = SD.el("button", { cls: "btn", type: "button" }, [SD.icon("refresh"), "Refresh structure"]);
    var cells = [], tree = null, alive = true, pages = {}, slices = {}, opened = {};
    SD.add(node, [SD.el("div", { cls: "head" }, [SD.el("h2", { text: "Custom data - " + cfg.db }), refresh]), body, info]);
    if (!cfg.enabled) {
      body.appendChild(SD.el("div", { cls: "empty", text: "Custom data is off for this plant (webui_params.yaml custom_data.enabled)." }));
      refresh.hidden = true;
      return { node: node };
    }

    // discovery: Browse every struct down to max_depth; an array of structs browses its first element only
    function discover(path, depth) {
      return rpc.browse(path).then(function (children) {
        if (children.error) { return { error: children.error }; }
        var out = children.map(function (c) {
          return { name: c.name, path: path + "." + SD.quote(c.name), datatype: c.datatype || "", dims: c.array_dimensions || [],
            max_length: c.max_length, has_children: !!c.has_children, array_dimensions: c.array_dimensions };
        });
        return out.reduce(function (chain, n) {
          return chain.then(function () {
            if (depth + 1 >= cfg.max_depth) { n.truncated = isStruct(n) || (isArray(n) && !ELEMENTARY.test(n.datatype)); return null; }
            if (isStruct(n)) { return discover(n.path, depth + 1).then(function (r) { n.children = r.error ? null : r; n.error = r.error; }); }
            if (isArray(n) && !ELEMENTARY.test(n.datatype)) {
              return discover(n.path + "[" + n.dims.map(function (d) { return d.start_index; }).join(",") + "]", depth + 1)
                .then(function (r) { n.members = r.error ? null : r; n.error = r.error; });
            }
            return null;
          });
        }, Promise.resolve()).then(function () { return out; });
      });
    }

    function cell(path, type) {
      var td = SD.el("td", { cls: "mono", text: "-" });
      cells.push({ td: td, var: path, type: type });
      return td;
    }
    function typeText(n) {
      var t = n.datatype || (n.has_children ? "struct" : "?");
      if (n.max_length) { t += "[" + n.max_length + "]"; }
      if (isArray(n)) { t = "Array[" + n.dims.map(function (d) { return d.start_index + ".." + (d.start_index + d.count - 1); }).join(", ") + "] of " + t; }
      return t;
    }
    function pager(key, total, size, redraw) {
      var page = pages[key] || 0, last = Math.max(0, Math.ceil(total / size) - 1);
      if (total <= size) { return null; }
      var prev = SD.el("button", { cls: "btn", type: "button", text: "Previous", disabled: page === 0 });
      var next = SD.el("button", { cls: "btn", type: "button", text: "Next", disabled: page >= last });
      prev.addEventListener("click", function () { pages[key] = page - 1; redraw(); });
      next.addEventListener("click", function () { pages[key] = page + 1; redraw(); });
      return SD.el("div", { cls: "pager" }, [prev, SD.el("span", { text: "rows " + (page * size + 1) + "-" + Math.min(total, (page + 1) * size) + " of " + total }), next]);
    }

    function struct(list) {
      var tbody = SD.el("tbody"), nested = [];
      list.forEach(function (n) {
        if (isStruct(n) || isArray(n)) { nested.push(n); return; }
        tbody.appendChild(SD.el("tr", null, [SD.el("td", { text: n.name }), cell(n.path, n.datatype), SD.el("td", { cls: "type", text: typeText(n) })]));
      });
      var parts = [];
      if (tbody.firstChild) {
        parts.push(SD.el("div", { cls: "scroll" }, SD.el("table", { cls: "grid" }, [SD.el("thead", null, SD.el("tr", null,
          ["Name", "Value", "Type"].map(function (h) { return SD.el("th", { text: h }); }))), tbody])));
      }
      nested.forEach(function (n) {
        var open = opened[n.path] !== false, box = SD.el("details", { open: open });
        box.addEventListener("toggle", function () {
          if (box.open === (opened[n.path] !== false)) { return; }     // the toggle event of the open attribute itself
          opened[n.path] = box.open;
          draw();                                                       // a closed section's cells are not read
        });
        var inner = SD.el("div");
        if (open) { inner.appendChild(content(n)); }
        SD.add(box, [SD.el("summary", null, [n.name + " ", SD.el("span", { cls: "type", text: typeText(n) })]), inner]);
        parts.push(box);
      });
      return parts;
    }

    function content(n) {
      if (n.error) { return SD.el("p", { cls: "bad", text: "not browsable via Web API: " + n.error.message }); }
      if (n.truncated) { return SD.el("p", { cls: "bad", text: "deeper than custom_data.max_depth (" + cfg.max_depth + ")" }); }
      if (isStruct(n)) { return SD.el("div", null, struct(n.children || [])); }
      return array(n);
    }

    // an array: the leading dimensions picked (one slice), the last dimension as rows, paged
    function array(n) {
      var dims = n.dims, lead = dims.slice(0, -1), lastDim = dims[dims.length - 1], key = n.path;
      var pick = slices[key] = slices[key] || lead.map(function (d) { return d.start_index; });
      var wrap = SD.el("div");
      if (lead.length) {
        var bar = SD.el("div", { cls: "slice" }, "Slice ");
        lead.forEach(function (d, i) {
          var input = SD.el("input", { type: "number", min: d.start_index, max: d.start_index + d.count - 1, value: pick[i],
            "aria-label": "index " + (i + 1) });
          input.addEventListener("change", function () {
            var v = Math.round(Number(input.value));
            pick[i] = Math.min(d.start_index + d.count - 1, Math.max(d.start_index, isNaN(v) ? d.start_index : v));
            pages[key] = 0;
            draw();
          });
          bar.appendChild(input);
        });
        wrap.appendChild(bar);
      }
      var page = pages[key] || 0, from = page * cfg.page_rows, to = Math.min(lastDim.count, from + cfg.page_rows);
      var members = n.members ? n.members.filter(function (m) { return !isStruct(m) && !isArray(m); }) : null;
      var skipped = n.members ? n.members.length - members.length : 0;
      var head = ["Index"].concat(members ? members.map(function (m) { return m.name; }) : ["Value"]);
      var tbody = SD.el("tbody");
      for (var i = from; i < to; i += 1) {
        var index = pick.concat([lastDim.start_index + i]).join(","), base = n.path + "[" + index + "]";
        var row = SD.el("tr", null, SD.el("td", { cls: "num idx", text: "[" + index + "]" }));
        if (members) { members.forEach(function (m) { row.appendChild(cell(base + "." + SD.quote(m.name), m.datatype)); }); }
        else { row.appendChild(cell(base, n.datatype)); }
        tbody.appendChild(row);
      }
      SD.add(wrap, [SD.el("div", { cls: "scroll" }, SD.el("table", { cls: "grid" }, [SD.el("thead", null, SD.el("tr", null,
        head.map(function (h) { return SD.el("th", { text: h }); }))), tbody])),
        pager(key, lastDim.count, cfg.page_rows, draw),
        skipped ? SD.el("p", { cls: "note", text: skipped + " nested member(s) of each element are not shown in the table." }) : null]);
      return wrap;
    }

    function draw() {
      if (!alive || !tree) { return; }
      cells = [];
      SD.clear(body);
      if (tree.error) {
        var missing = /not exist|invalid address|not found/i.test(tree.error.message || "") || tree.error.code === 200;
        body.appendChild(SD.el("div", { cls: "empty", text: missing ? cfg.db + " not found on this CPU."
          : "The CPU refused to browse " + cfg.db + ": " + tree.error.message + " (code " + tree.error.code + ")" }));
        poller.unwatch("custom");
        info.textContent = "";
        return;
      }
      if (!tree.length) { body.appendChild(SD.el("div", { cls: "empty", text: cfg.db + " has no member." })); }
      SD.add(body, struct(tree));
      var vars = cells.map(function (c) { return c.var; });
      var read = vars.slice(0, cfg.max_cells);
      info.textContent = read.length + (vars.length > read.length ? " of " + vars.length + " cells on screen are" : " cell(s) are")
        + " read every " + cfg.interval_ms + " ms" + (vars.length > read.length ? " (custom_data.max_cells)." : ".");
      cells.forEach(function (c, i) { c.read = i < cfg.max_cells; });
      poller.watch("custom", read, cfg.interval_ms, true);
      if (ctx.ev) { update(ctx.ev); }
    }

    function load() {
      refresh.disabled = true;
      body.textContent = "";
      body.appendChild(SD.el("p", { cls: "muted", text: "Browsing " + cfg.db + "..." }));
      poller.unwatch("custom");
      poller.forget(cells.map(function (c) { return c.var; }));
      discover(root, 0).then(function (result) {
        tree = result;
        refresh.disabled = false;
        draw();
      }, function (error) {
        refresh.disabled = false;
        SD.clear(body).appendChild(SD.el("div", { cls: "empty", text: "Browsing " + cfg.db + " failed: " + error.message }));
      });
    }

    function update(ev) {
      cells.forEach(function (c) {
        var err = poller.errors[c.var];
        if (!c.read) { c.td.textContent = "(not refreshed)"; c.td.className = "mono bad"; return; }
        if (err) {
          c.td.textContent = "not readable via Web API";
          c.td.title = err.message + " (code " + err.code + ")";
          c.td.className = "mono bad";
          return;
        }
        c.td.className = "mono";
        c.td.removeAttribute("title");
        c.td.textContent = SD.formatValue(ev.snap.v[c.var], c.type);
      });
    }

    refresh.addEventListener("click", load);
    load();
    return { node: node, update: update, leave: function () { alive = false; poller.unwatch("custom"); } };
  } });
})(SD);
