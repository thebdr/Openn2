// The plant drawing (C-050 M5): plant.layout.image with one icon per placed device or node
// (plant.layout.positions, "kind|fld" -> [x, y] in the drawing's view_box), coloured by its state. Drag to pan,
// wheel, buttons or two fingers to zoom: the view is the SVG's viewBox, so nothing is styled inline, and the icons
// keep their screen size. Edit mode moves icons, places the unplaced ones (pick one in the tray, then tap the
// drawing) and downloads webui_positions.csv for the project's config - the page itself writes nothing anywhere.
(function (SD) {
  "use strict";
  var NS = "http://www.w3.org/2000/svg", PIN = 11, TAP = 5;   // the icons' largest radius (screen px)
  var draft = null;                  // unsaved edits survive a change of view (not a reload)

  function svg(tag, attrs) {
    var node = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    return node;
  }
  function cell(v) {
    v = String(v);
    return /[",\r\n]/.test(v) ? "\"" + v.replace(/"/g, "\"\"") + "\"" : v;
  }
  // the positions file the loader reads (config.load_webui_positions): kind,fld,x,y - CRLF, csv quoting
  SD.positionsCsv = function (positions) {
    var rows = [["kind", "fld", "x", "y"]];
    Object.keys(positions).sort().forEach(function (key) {
      var at = key.indexOf("|"), p = positions[key];
      rows.push([key.slice(0, at), key.slice(at + 1), (+p[0]).toFixed(1), (+p[1]).toFixed(1)]);
    });
    return rows.map(function (r) { return r.map(cell).join(","); }).join("\r\n") + "\r\n";
  };

  SD.drawing = function (ctx) {
    var model = ctx.model, image = ctx.plant.layout.image, v0 = image.view_box;
    var saved = ctx.plant.layout.positions || {};
    var positions = draft ? draft.positions : JSON.parse(JSON.stringify(saved));
    var vb = { x: v0[0], y: v0[1], w: v0[2], h: v0[3] }, fitW = v0[2], pins = {}, pointers = {}, gesture = null;
    var editing = false, armed = null, selected = null, frame = 0, lastEv = null, onlyBad = false;
    var keyOf = function (e) { return e.kind + "|" + e.fld; };

    var view = svg("svg", { class: "plantsvg", role: "group", "aria-label": "Plant drawing" });
    view.appendChild(svg("image", { href: image.file, x: v0[0], y: v0[1], width: v0[2], height: v0[3], preserveAspectRatio: "none" }));
    var layer = svg("g", { class: "pins" });
    view.appendChild(layer);
    var box = SD.el("div", { cls: "plantbox" }, view);

    function makePin(e) {
      var kind = model.kind[e.kind] || { label: e.kind, icon: "device" };
      var g = svg("g", { class: "pin s-stale", tabindex: "0", role: "button" });
      g.appendChild(svg("circle", { r: "1" }));
      g.appendChild(svg("use", { href: "icons.svg#" + kind.icon, x: "-0.62", y: "-0.62", width: "1.24", height: "1.24" }));
      var title = svg("title");
      title.textContent = kind.label + " " + e.fld + (e.description ? " - " + e.description : "");
      g.appendChild(title);
      g.addEventListener("click", function (ev) {
        ev.stopPropagation();
        if (editing) { select(e.id); } else { SD.open(e.id); }
      });
      g.addEventListener("keydown", function (ev) { if (ev.key === "Enter") { SD.open(e.id); } });
      g.addEventListener("pointerdown", function (ev) {
        if (editing) { ev.stopPropagation(); startDrag(ev, e); }
      });
      pins[e.id] = { g: g, e: e, title: kind.label + " " + e.fld };
      layer.appendChild(g);
    }
    model.entities.forEach(function (e) { if (positions[keyOf(e)]) { makePin(e); } });

    // --- the view ---------------------------------------------------------------------------------------- //
    function size() { return { w: box.clientWidth || 800, h: box.clientHeight || 500 }; }
    function fit() {
      var s = size(), a = s.w / s.h;
      if (v0[2] / v0[3] > a) { vb = { x: v0[0], w: v0[2], h: v0[2] / a, y: v0[1] - (v0[2] / a - v0[3]) / 2 }; }
      else { vb = { y: v0[1], h: v0[3], w: v0[3] * a, x: v0[0] - (v0[3] * a - v0[2]) / 2 }; }
      fitW = vb.w;
      draw();
    }
    function draw() {
      if (frame) { return; }
      frame = window.requestAnimationFrame(function () {
        frame = 0;
        view.setAttribute("viewBox", [vb.x, vb.y, vb.w, vb.h].join(" "));
        var w = size().w, fitted = Math.max(2.5, Math.min(4.5, w / 240));   // the radius at the fitted view
        var k = Math.min(PIN, fitted * fitW / vb.w) * vb.w / w;                 // icons grow as the view zooms in
        Object.keys(pins).forEach(function (id) {
          var p = positions[keyOf(pins[id].e)];
          if (p) { pins[id].g.setAttribute("transform", "translate(" + p[0] + " " + p[1] + ") scale(" + k + ")"); }
        });
      });
    }
    function toDrawing(cx, cy) {
      var m = view.getScreenCTM();
      if (!m) { return { x: 0, y: 0 }; }
      var p = new DOMPoint(cx, cy).matrixTransform(m.inverse());
      return { x: p.x, y: p.y };
    }
    function zoom(factor, cx, cy) {
      var w = Math.min(v0[2] * 2, Math.max(v0[2] / 60, vb.w / factor)), f = vb.w / w;
      var at = cx === undefined ? { x: vb.x + vb.w / 2, y: vb.y + vb.h / 2 } : toDrawing(cx, cy);
      vb = { x: at.x - (at.x - vb.x) / f, y: at.y - (at.y - vb.y) / f, w: w, h: vb.h / f };
      draw();
    }
    function pan(dx, dy) {
      var s = size();
      vb.x -= dx * vb.w / s.w;
      vb.y -= dy * vb.h / s.h;
      draw();
    }
    view.addEventListener("wheel", function (ev) {
      ev.preventDefault();
      zoom(Math.pow(1.0015, -ev.deltaY), ev.clientX, ev.clientY);
    }, { passive: false });
    view.addEventListener("pointerdown", function (ev) {
      pointers[ev.pointerId] = { x: ev.clientX, y: ev.clientY };
      var ids = Object.keys(pointers);
      if (ids.length === 2) {
        var a = pointers[ids[0]], b = pointers[ids[1]];
        gesture = { pinch: Math.hypot(a.x - b.x, a.y - b.y), mid: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }, moved: TAP + 1 };
      } else if (!gesture || !gesture.pin) {
        gesture = { x: ev.clientX, y: ev.clientY, moved: 0 };
      }
    });
    view.addEventListener("pointermove", function (ev) {
      var p = pointers[ev.pointerId];
      if (!p || !gesture) { return; }
      var dx = ev.clientX - p.x, dy = ev.clientY - p.y;
      p.x = ev.clientX;
      p.y = ev.clientY;
      var ids = Object.keys(pointers);
      if (gesture.pin) {
        var at = toDrawing(ev.clientX, ev.clientY);
        positions[gesture.pin] = [Math.round(at.x * 10) / 10, Math.round(at.y * 10) / 10];
        gesture.moved += Math.abs(dx) + Math.abs(dy);
        changed();
      } else if (ids.length === 2 && gesture.pinch) {
        var a = pointers[ids[0]], b = pointers[ids[1]], d = Math.hypot(a.x - b.x, a.y - b.y);
        var mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
        pan(mid.x - gesture.mid.x, mid.y - gesture.mid.y);
        zoom(d / gesture.pinch, mid.x, mid.y);
        gesture.pinch = d;
        gesture.mid = mid;
      } else {
        gesture.moved += Math.abs(dx) + Math.abs(dy);
        if (gesture.moved > TAP) {
          if (!view.hasPointerCapture(ev.pointerId)) { capture(ev.pointerId); view.classList.add("panning"); }
          pan(dx, dy);
        }
      }
    });
    function capture(id) {
      try { view.setPointerCapture(id); } catch (e) { /* the pointer is gone already */ }
    }
    function release(ev) {
      delete pointers[ev.pointerId];
      view.classList.remove("panning");
      if (!Object.keys(pointers).length) {
        var g = gesture;
        gesture = null;
        if (g && !g.pin && g.moved <= TAP && editing && armed && ev.type === "pointerup") { place(armed, ev.clientX, ev.clientY); }
      }
    }
    view.addEventListener("pointerup", release);
    view.addEventListener("pointercancel", release);

    // --- edit mode --------------------------------------------------------------------------------------- //
    var count = SD.el("span", { cls: "muted" });
    var save = SD.el("button", { cls: "btn", type: "button", text: "Download webui_positions.csv" });
    var discard = SD.el("button", { cls: "btn", type: "button", text: "Discard changes" });
    var unplace = SD.el("button", { cls: "btn", type: "button", text: "Unplace selected", disabled: true });
    var tray = SD.el("div", { cls: "tray" });
    var editBar = SD.el("div", { cls: "editbar", hidden: true }, [
      SD.el("div", { cls: "toolbar" }, [count, save, discard, unplace]),
      SD.el("p", { cls: "note", text: "Drag an icon to move it. Pick a device below, then tap the drawing to place it. "
        + "Save the downloaded file as webui/webui_positions.csv in the project's config (config_project/systems/"
        + "siemens_s7_safety/webui/), run 650 again and upload the application." }),
      SD.el("div", { cls: "section", text: "Not placed" }), tray]);
    var editBtn = SD.el("button", { cls: "btn", type: "button", text: "Edit positions", "aria-pressed": "false" });
    var placedText = SD.el("span", { cls: "muted", text: Object.keys(pins).length + " of " + model.entities.length + " placed" });

    function startDrag(ev, e) {
      pointers[ev.pointerId] = { x: ev.clientX, y: ev.clientY };
      gesture = { pin: keyOf(e), moved: 0 };
      select(e.id);
      capture(ev.pointerId);
    }
    function select(id) {
      selected = id;
      unplace.disabled = !id;
      refresh();
    }
    function dirty() { return SD.positionsCsv(positions) !== SD.positionsCsv(saved); }
    function changed() {
      draft = dirty() ? { positions: positions } : null;
      count.textContent = draft ? "Unsaved changes" : "No change";
      placedText.textContent = Object.keys(pins).length + " of " + model.entities.length + " placed";
      draw();
    }
    function place(e, cx, cy) {
      var at = toDrawing(cx, cy);
      positions[keyOf(e)] = [Math.round(at.x * 10) / 10, Math.round(at.y * 10) / 10];
      if (!pins[e.id]) { makePin(e); }
      armed = null;
      fillTray();
      select(e.id);
      changed();
    }
    function fillTray() {
      SD.clear(tray);
      var left = model.entities.filter(function (e) { return !positions[keyOf(e)]; });
      if (!left.length) { tray.appendChild(SD.el("span", { cls: "muted", text: "Every device is placed." })); }
      left.forEach(function (e) {
        var kind = model.kind[e.kind] || { icon: "device" };
        tray.appendChild(SD.el("button", { cls: "btn" + (armed === e ? " on" : ""), type: "button", on: { click: function () {
          armed = armed === e ? null : e;
          fillTray();
        } } }, [SD.icon(kind.icon), SD.el("span", { cls: "mono", text: e.fld })]));
      });
    }
    editBtn.addEventListener("click", function () {
      editing = !editing;
      editBtn.className = "btn" + (editing ? " on" : "");
      editBtn.setAttribute("aria-pressed", String(editing));
      box.classList.toggle("editing", editing);
      editBar.hidden = !editing;
      armed = null;
      if (editing) { fillTray(); changed(); } else { select(null); }
    });
    save.addEventListener("click", function () {
      var url = URL.createObjectURL(new Blob([SD.positionsCsv(positions)], { type: "text/csv" }));
      var link = SD.el("a", { href: url, download: "webui_positions.csv" });
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
    });
    discard.addEventListener("click", function () {
      positions = JSON.parse(JSON.stringify(saved));
      Object.keys(pins).forEach(function (id) {
        if (!positions[keyOf(pins[id].e)]) { layer.removeChild(pins[id].g); delete pins[id]; }
      });
      model.entities.forEach(function (e) { if (positions[keyOf(e)] && !pins[e.id]) { makePin(e); } });
      select(null);
      fillTray();
      changed();
    });
    unplace.addEventListener("click", function () {
      var pin = selected && pins[selected];
      if (!pin) { return; }
      delete positions[keyOf(pin.e)];
      layer.removeChild(pin.g);
      delete pins[selected];
      select(null);
      fillTray();
      changed();
    });
    function guard(ev) { if (draft) { ev.preventDefault(); ev.returnValue = ""; } }
    window.addEventListener("beforeunload", guard);
    // the box resized (a panel opened, the window turned): same centre and width, the height to the new aspect
    function resized() {
      var s = size(), cy = vb.y + vb.h / 2;
      vb.h = vb.w * s.h / s.w;
      vb.y = cy - vb.h / 2;
      draw();
    }
    var watcher = typeof ResizeObserver === "function" ? new ResizeObserver(resized) : null;
    if (watcher) { watcher.observe(box); } else { window.addEventListener("resize", resized); }

    var zoomBar = SD.el("div", { cls: "toolbar" }, [
      SD.el("button", { cls: "btn", type: "button", text: "−", title: "Zoom out", "aria-label": "Zoom out", on: { click: function () { zoom(1 / 1.4); } } }),
      SD.el("button", { cls: "btn", type: "button", text: "+", title: "Zoom in", "aria-label": "Zoom in", on: { click: function () { zoom(1.4); } } }),
      SD.el("button", { cls: "btn", type: "button", text: "Fit", on: { click: fit } }), editBtn, placedText]);
    var node = SD.el("div", { cls: "plant" }, [zoomBar, box, editBar]);

    function refresh() {
      var ev = lastEv;
      Object.keys(pins).forEach(function (id) {
        var state = ev ? ev.entity[id] : "stale", pin = pins[id];
        var hide = onlyBad && state === "ok" && !editing;
        pin.g.setAttribute("class", "pin s-" + state + (id === selected || id === ctx.route.detail ? " sel" : "") + (hide ? " off" : ""));
        pin.g.setAttribute("aria-label", pin.title + ": " + SD.STATE_TEXT[state]);
      });
    }
    window.requestAnimationFrame(fit);
    return { node: node, fit: fit, update: function (ev, bad) { lastEv = ev; onlyBad = !!bad; refresh(); }, leave: function () {
      window.removeEventListener("beforeunload", guard);
      if (watcher) { watcher.disconnect(); } else { window.removeEventListener("resize", resized); }
    } };
  };
})(SD);
