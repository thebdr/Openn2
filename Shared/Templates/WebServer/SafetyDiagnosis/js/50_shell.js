// The shell: navigation, header status, banners, the routed view and the detail panel. A view registers with
// SD.view(id, {label, icon, order, nav, render(ctx, route) -> {node, update(ev), leave()}}); after every poll the
// shell evaluates the model once and hands the result to the view and the panel.
(function (SD) {
  "use strict";
  SD.views = {};
  SD.view = function (id, def) { def.id = id; SD.views[id] = def; };

  var ctx, current = null, currentKey = "", panel = null, panelId = "", navLinks = {}, faultCount = null;

  function $(id) { return document.getElementById(id); }

  function buildNav() {
    var nav = SD.clear($("nav"));
    Object.keys(SD.views).map(function (k) { return SD.views[k]; }).filter(function (v) { return v.nav; })
      .sort(function (a, b) { return a.order - b.order; }).forEach(function (v) {
        var link = SD.el("a", { href: SD.href(v.id) }, [SD.icon(v.icon), SD.el("span", { text: v.short || v.label })]);
        if (v.id === "faults") { faultCount = SD.el("b", { cls: "count zero", text: "0" }); link.appendChild(faultCount); }
        navLinks[v.id] = link;
        nav.appendChild(link);
      });
  }

  function render() {
    var route = SD.route(), view = SD.views[route.view] || SD.views.overview, key = view.id + "/" + route.arg;
    ctx.route = route;
    if (key !== currentKey) {
      if (current && current.leave) { current.leave(); }
      var host = SD.clear($("view"));
      try {
        current = view.render(ctx, route);
      } catch (error) {
        if (window.console) { console.error(error); }
        current = { node: SD.el("div", { cls: "banner alarm", role: "alert", text: "This view cannot be shown: " + error.message }) };
      }
      host.appendChild(current.node);
      currentKey = key;
      document.title = view.label + " - " + ctx.plant.app.title;
      Object.keys(navLinks).forEach(function (id) {
        navLinks[id].className = id === view.id || (view.parent && view.parent === id) ? "on" : "";
      });
      window.scrollTo(0, 0);
    }
    if (route.detail !== panelId) {
      if (panel && panel.leave) { panel.leave(); }
      panel = null;
      panelId = route.detail;
      var aside = SD.clear($("detail"));
      if (panelId) { panel = SD.detail(ctx, panelId); aside.appendChild(panel.node); }
      aside.hidden = !panel;
      $("app").classList.toggle("has-detail", !!panel);
    }
    if (ctx.ev) { refresh(); }
  }

  function connText(status, poller) {
    switch (status.state) {
      case "live": return "Live " + SD.clock(poller.at);
      case "paused": return "Paused";
      case "lost": return "Connection lost";
      case "rights": return "No read right";
      case "login": return "Login refused";
      default: return "Connecting";
    }
  }

  function banners(poller) {
    var host = SD.clear($("banners")), status = poller.status, retry = status.retryAt ? new Date(status.retryAt) : null;
    if (ctx.mock) {
      host.appendChild(SD.el("div", { cls: "banner mock", role: "alert",
        text: "SIMULATED DATA - not read from the PLC (mock mode, local preview only)." + (ctx.mock.note || "") }));
    }
    if (status.state === "lost") {
      host.appendChild(SD.el("div", { cls: "banner alarm", role: "alert", text: "Connection to the CPU lost (" + status.message
        + "). The states are greyed out; " + (poller.at ? "the last values were read at " + SD.clock(poller.at)
        : "no value has been read yet") + ". Retrying at " + SD.clock(retry) + "." }));
    } else if (status.state === "rights") {
      host.appendChild(SD.el("div", { cls: "banner alarm", role: "alert", text: "The CPU's anonymous user has no read right: "
        + status.message + ". In TIA, the CPU's web server user management must give \"" + ctx.plant.login.users.join("\" / \"")
        + "\" the right to read tags. Retrying at " + SD.clock(retry) + "." }));
    } else if (status.state === "login") {
      host.appendChild(SD.el("div", { cls: "banner alarm", role: "alert", text: status.message + ". Retrying at "
        + SD.clock(retry) + "." }));
    }
    var problems = poller.problems();
    if (problems.length) {
      host.appendChild(SD.el("div", { cls: "banner warning" }, [
        problems.length + " variable(s) of this plant model cannot be read. ",
        SD.el("a", { href: SD.href("problems"), text: "Configuration problems" })]));
    }
    if (!ctx.model.polarityKnown && status.state === "live") {
      host.appendChild(SD.el("div", { cls: "banner info", text: "The diagnosis bits' polarity is not confirmed for this "
        + "plant yet (webui_params.yaml diag), so device states show Unknown. The cabinet summaries and the raw bits are live." }));
    }
  }

  function refresh() {
    if (current && current.update) { current.update(ctx.ev); }
    if (panel && panel.update) { panel.update(ctx.ev); }
  }

  function onPoll(poller) {
    ctx.ev = ctx.model.evaluate(poller.snap());
    var conn = $("conn");
    conn.textContent = connText(poller.status, poller);
    conn.className = "conn " + poller.status.state;
    banners(poller);
    if (faultCount) {
      var n = ctx.ev.faults.filter(function (f) { return f.severity === "alarm" || f.severity === "warning"; }).length;
      faultCount.textContent = String(n);
      faultCount.className = "count" + (n ? "" : " zero");
    }
    refresh();
  }

  SD.shell = function (context) {
    ctx = context;
    var plant = ctx.plant;
    $("title").textContent = plant.app.title;
    $("plc").textContent = [plant.plc.station, plant.plc.ip, "plant model " + plant.meta.run].filter(Boolean).join(" · ");
    buildNav();
    window.addEventListener("hashchange", render);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && panelId) { location.hash = SD.detailHref(null); }
    });
    ctx.poller.on(onPoll);
    render();
    onPoll(ctx.poller);
  };
})(SD);
