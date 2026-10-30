// The plant at runtime: plant.json (PL5 650, schema 1) indexed once, and every state the page shows derived
// from one snapshot of values ({v: {var: value}, fresh, at}). Pure - no DOM, no request.
//
// - A cabinet channel (cabinet, bit): its DiagnosticTags word is ALARM1 / WARNING1 for bits 0-31 and ALARM2 /
//   WARNING2 for 32-63, the bit inside it bit % 32. plant.diag.alarm_bit / warning_bit say which value means
//   active (null = not confirmed yet: the channel is "unknown", its raw bit still shown). A tristate cabinet's
//   alarm channel also carries a warning, in the same bit of the paired warning word.
// - A cabinet's own summary is its STATE word: bit state_alarm_bit / state_warning_bit set = any alarm / warning.
// - A device = the worst of its channels; while one of its PROFINET nodes is failed it is "node" (unknown - node
//   failed), never OK. A member (area, sorter, device detail) compares its value with its `healthy` polarity.
(function (SD) {
  "use strict";

  function parts(entity) {
    if (entity.functional_unit !== undefined) {
      return { functional_unit: entity.functional_unit || "", location: entity.location || "", device: entity.device || "" };
    }
    var m = /^(=[^-+]*)?(\+[^-]*)?(-[^-]*)?(.*)$/.exec(entity.fld || "") || [];
    return { functional_unit: m[1] || "", location: (m[2] || "") + (m[3] || ""), device: m[4] || "" };
  }

  function Model(plant) {
    var self = this;
    this.plant = plant;
    this.diag = plant.diag;
    this.kinds = plant.kinds.slice().sort(function (a, b) { return a.order - b.order; });
    this.kind = {};
    this.kinds.forEach(function (k) { self.kind[k.kind] = k; });
    this.entities = plant.devices.concat(plant.nodes);
    this.byId = {};
    this.byKind = {};
    this.onNode = {};
    this.entities.forEach(function (e) {
      e.parts = parts(e);
      self.byId[e.id] = e;
      (self.byKind[e.kind] = self.byKind[e.kind] || []).push(e);
      (e.nodes || []).forEach(function (n) { (self.onNode[n] = self.onNode[n] || []).push(e); });
    });
    Object.keys(this.byKind).forEach(function (k) { self.byKind[k].sort(SD.byText("fld")); });
    this.cabinet = {};
    plant.cabinets.forEach(function (c) {
      self.cabinet[c.id] = c;
      c.bitAt = {};
      c.bits.forEach(function (b) { c.bitAt[(b.warning ? "w" : "a") + b.bit] = b; });
    });
    this.area = {};
    this.children = {};
    plant.areas.forEach(function (a) {
      self.area[a.id] = a;
      (self.children[a.parent || ""] = self.children[a.parent || ""] || []).push(a);
    });
    this.sorter = {};
    plant.sorters.forEach(function (s) { self.sorter[s.id] = s; });
    this.iface = {};
    plant.interfaces.forEach(function (i) { self.iface[i.id] = i; });
    this.polarityKnown = plant.diag.alarm_bit !== null && plant.diag.alarm_bit !== undefined;
  }

  Model.prototype.word = function (cab, warning, bit) {
    var names = warning ? cab.warning_words : cab.alarm_words;
    var name = names[bit < 32 ? 0 : 1];
    return name ? cab.words[name] || null : null;
  };

  // the raw bit (0 / 1) or null when its word was not read
  Model.prototype.raw = function (snap, cab, warning, bit) {
    var name = this.word(cab, warning, bit);
    var value = name ? snap.v[name] : undefined;
    return typeof value === "number" ? (value >>> (bit % 32)) & 1 : null;
  };

  Model.prototype.channel = function (snap, cab, bit, warning) {
    if (!snap.fresh) { return { state: "stale", raw: null }; }
    var raw = this.raw(snap, cab, warning, bit);
    var polarity = warning ? this.diag.warning_bit : this.diag.alarm_bit;
    var state = raw === null || polarity === null || polarity === undefined ? "unknown"
      : raw === polarity ? (warning ? "warning" : "alarm") : "ok";
    if (!warning && cab.tristate && state === "ok") {
      var paired = this.raw(snap, cab, true, bit), wp = this.diag.warning_bit;
      state = paired === null || wp === null || wp === undefined ? "unknown" : paired === wp ? "warning" : "ok";
    }
    return { state: state, raw: raw };
  };

  Model.prototype.cabinetSummary = function (snap, cab) {
    if (!snap.fresh) { return { state: "stale", alarm: null, warning: null }; }
    var value = cab.words.STATE ? snap.v[cab.words.STATE] : undefined;
    if (typeof value !== "number") { return { state: "unknown", alarm: null, warning: null }; }
    var alarm = ((value >>> this.diag.state_alarm_bit) & 1) === 1;
    var warning = ((value >>> this.diag.state_warning_bit) & 1) === 1;
    return { state: alarm ? "alarm" : warning ? "warning" : "ok", alarm: alarm, warning: warning };
  };

  // a member {var, healthy, severity}: ok / its severity / unknown (+ the raw value)
  Model.prototype.member = function (snap, m) {
    var value = snap.v[m.var];
    if (!snap.fresh) { return { state: "stale", value: value }; }
    if (value === undefined) { return { state: "unknown", value: value }; }
    if (m.healthy === null || m.healthy === undefined || typeof value !== "boolean") { return { state: "unknown", value: value }; }
    return { state: value === m.healthy ? "ok" : m.severity === "info" ? "info" : m.severity, value: value };
  };

  function worstOf(states, none) {
    return states.length ? states.reduce(SD.worse, "ok") : none;
  }

  // everything the views show for one snapshot
  Model.prototype.evaluate = function (snap) {
    var self = this, ev = { snap: snap, entity: {}, cabinet: {}, area: {}, sorter: {}, faults: [], counts: {} };
    this.plant.cabinets.forEach(function (cab) {
      var channels = {};
      cab.bits.forEach(function (b) { channels[(b.warning ? "w" : "a") + b.bit] = self.channel(snap, cab, b.bit, b.warning); });
      ev.cabinet[cab.id] = { summary: self.cabinetSummary(snap, cab), channels: channels };
    });
    function own(e) {
      return worstOf((e.diag || []).map(function (d) {
        var c = ev.cabinet[d.cabinet];
        var ch = c && c.channels[(d.warning ? "w" : "a") + d.bit];
        return ch ? ch.state : snap.fresh ? "unknown" : "stale";
      }), snap.fresh ? "unknown" : "stale");
    }
    this.plant.nodes.forEach(function (n) { ev.entity[n.id] = own(n); });
    this.plant.devices.forEach(function (d) {
      var failed = (d.nodes || []).some(function (n) { return ev.entity[n] === "alarm"; });
      ev.entity[d.id] = failed && snap.fresh ? "node" : own(d);
    });
    this.kinds.forEach(function (k) {
      var counts = { ok: 0, warning: 0, alarm: 0, unknown: 0, node: 0, stale: 0 };
      (self.byKind[k.kind] || []).forEach(function (e) { counts[ev.entity[e.id]] += 1; });
      ev.counts[k.kind] = counts;
    });
    this.plant.areas.forEach(function (a) {
      var members = a.members.map(function (m) { return self.member(snap, m); });
      var states = members.filter(function (r, i) { return a.members[i].role === "state"; })
        .map(function (r) { return r.state; });
      ev.area[a.id] = { state: worstOf(states, snap.fresh ? "unknown" : "stale"), members: members };
    });
    this.plant.sorters.forEach(function (s) {
      ev.sorter[s.id] = s.members.map(function (m) { return self.member(snap, m); });
    });
    if (snap.fresh) { this.collectFaults(ev); }
    return ev;
  };

  Model.prototype.collectFaults = function (ev) {
    var self = this, faults = ev.faults;
    this.plant.cabinets.forEach(function (cab) {
      var c = ev.cabinet[cab.id], decoded = 0;
      cab.bits.forEach(function (b) {
        var state = c.channels[(b.warning ? "w" : "a") + b.bit].state;
        if (state === "alarm" || state === "warning") {
          decoded += 1;
          faults.push({ severity: state, group: 0, text: b.text, where: cab.fld + " bit " + b.bit, cabinet: cab.id, bit: b.bit,
            owner: b.owner });
        }
      });
      if (!decoded && (c.summary.alarm || c.summary.warning)) {
        faults.push({ severity: c.summary.alarm ? "alarm" : "warning", group: 1, cabinet: cab.id, owner: null,
          text: "Cabinet " + cab.fld + " reports " + (c.summary.alarm ? "an alarm" : "a warning"),
          where: self.polarityKnown ? "no channel bit decoded" : "bit polarity not confirmed - see the cabinet's bits" });
      }
    });
    this.plant.areas.forEach(function (a) {
      ev.area[a.id].members.forEach(function (r, i) {
        var m = a.members[i];
        if ((r.state === "alarm" || r.state === "warning") && (m.role === "state" || m.role === "cause")) {
          faults.push({ severity: r.state, group: 2, text: a.name + ": " + m.label, where: m.role === "cause" ? "area cause" : "area state",
            area: a.id });
        }
      });
    });
    this.plant.sorters.forEach(function (s) {
      ev.sorter[s.id].forEach(function (r, i) {
        if (r.state === "info" || r.state === "alarm" || r.state === "warning") {
          faults.push({ severity: r.state, group: 3, text: "Sorter " + s.index + ": " + s.members[i].label, where: s.area || "", area: s.area });
        }
      });
    });
    // the devices' channels (the causes) before the cabinets, the areas they trip and the sorters
    var rank = { alarm: 0, warning: 1, info: 2 };
    faults.sort(function (a, b) {
      return rank[a.severity] - rank[b.severity] || a.group - b.group || String(a.text).localeCompare(String(b.text), "en", { numeric: true });
    });
  };

  SD.Model = Model;
})(SD);
