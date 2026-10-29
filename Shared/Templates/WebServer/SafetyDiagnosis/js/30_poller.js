// The poll loop: a setTimeout chain with one cycle in flight. A cycle reads plant.poll (the cabinet words and the
// area / sorter members, about 80 names) plus every watched set that is due - the open detail panel, interface
// or custom data view, each read only while it is open - in chunks of polling.chunk. It pauses while the tab is
// hidden. A lost connection keeps the last values but marks them stale and retries after polling.backoff_ms.
// A variable the CPU refuses is dropped from later cycles: a plant.json name is listed as a configuration
// problem, a "quiet" set's (custom data) is left to its view.
(function (SD) {
  "use strict";

  function Poller(rpc, plant) {
    this.rpc = rpc;
    this.cfg = plant.polling;
    this.base = plant.poll.slice();
    this.watches = {};
    this.values = {};
    this.errors = {};
    this.quiet = {};
    this.fresh = false;
    this.at = null;
    this.status = { state: "connecting", message: "" };
    this.failures = 0;
    this.timer = null;
    this.busy = false;
    this.listeners = [];
  }

  Poller.prototype.on = function (fn) { this.listeners.push(fn); };
  Poller.prototype.emit = function () {
    var self = this;
    this.listeners.forEach(function (fn) {
      try { fn(self); } catch (error) { if (window.console) { console.error(error); } }   // a view's bug is not a lost link
    });
  };
  Poller.prototype.snap = function () { return { v: this.values, fresh: this.fresh, at: this.at }; };

  // read `vars` every `interval` ms while watched; quiet = their errors are the caller's, not plant problems
  Poller.prototype.watch = function (key, vars, interval, quiet) {
    var self = this;
    this.watches[key] = { vars: vars.slice(), interval: interval, last: 0 };
    if (quiet) { vars.forEach(function (v) { self.quiet[v] = true; }); }
    this.kick();
  };
  Poller.prototype.unwatch = function (key) { delete this.watches[key]; };
  Poller.prototype.forget = function (vars) {
    var self = this;
    vars.forEach(function (v) { delete self.errors[v]; delete self.values[v]; });
  };
  Poller.prototype.problems = function () {
    var self = this;
    return Object.keys(this.errors).filter(function (v) { return !self.quiet[v]; })
      .map(function (v) { return { var: v, code: self.errors[v].code, message: self.errors[v].message }; });
  };

  Poller.prototype.start = function () {
    var self = this;
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) { self.kick(); }
      else { self.status = { state: "paused", message: "" }; self.emit(); }
    });
    this.cycle();
  };
  // run a cycle now (a panel just opened) unless one is in flight or the loop is backing off
  Poller.prototype.kick = function () {
    if (this.busy || document.hidden || this.failures) { return; }
    clearTimeout(this.timer);
    this.cycle();
  };
  Poller.prototype.schedule = function (ms) {
    var self = this;
    clearTimeout(this.timer);
    this.timer = setTimeout(function () { self.cycle(); }, Math.max(ms, 50));
  };

  Poller.prototype.cycle = function () {
    var self = this;
    if (this.busy) { return; }
    if (document.hidden) { this.status = { state: "paused", message: "" }; this.emit(); return; }
    this.busy = true;
    var started = Date.now(), due = [], seen = {}, vars = [];
    Object.keys(this.watches).forEach(function (key) {
      var w = self.watches[key];
      if (started - w.last >= w.interval - 50) { due.push(key); }
    });
    this.base.concat.apply(this.base, due.map(function (k) { return self.watches[k].vars; })).forEach(function (v) {
      if (!seen[v] && !self.errors[v]) { seen[v] = true; vars.push(v); }
    });
    this.rpc.read(vars, this.cfg.chunk).then(function (result) {
      var readable = 0, denied = [];
      vars.forEach(function (v) {
        var r = result[v];
        if (!r) { return; }
        if (!r.error) { self.values[v] = r.value; readable += 1; }
        else if (r.error.code === SD.DENIED) { denied.push(v); }
        else { self.errors[v] = r.error; delete self.values[v]; }
      });
      if (!readable && denied.length && denied.length === vars.length) {
        throw SD.failure("rights", "the anonymous user (" + (self.rpc.user || "?") + ") has no right to read tags");
      }
      denied.forEach(function (v) { self.errors[v] = { code: SD.DENIED, message: "Permission denied" }; });
      due.forEach(function (k) { if (self.watches[k]) { self.watches[k].last = started; } });
      self.fresh = true;
      self.at = new Date();
      self.failures = 0;
      self.status = { state: "live", message: "" };
      self.busy = false;
      self.emit();
      self.schedule(self.cfg.interval_ms - (Date.now() - started));
    }).catch(function (error) {
      var backoff = self.cfg.backoff_ms;
      var wait = backoff[Math.min(self.failures, backoff.length - 1)];
      self.failures += 1;
      self.fresh = false;
      self.status = { state: error.kind === "rights" || error.kind === "login" ? error.kind : "lost",
        message: error.message || String(error), retryAt: Date.now() + wait };
      self.busy = false;
      self.emit();
      self.schedule(wait);
    });
  };

  SD.Poller = Poller;
})(SD);
