// Diagnosis cabinets: one card per cabinet (its STATE summary), and per cabinet (#/cabinets/<id>) the 64 alarm
// channels - and its warning channels - as a bit grid plus the table of the used bits with their texts.
(function (SD) {
  "use strict";
  function hex(value) {
    return typeof value === "number" ? "16#" + ("0000000" + (value >>> 0).toString(16).toUpperCase()).slice(-8) : "-";
  }

  function list(ctx) {
    var plant = ctx.plant, cards = {}, node = SD.el("div");
    var grid = SD.el("div", { cls: "cards" });
    plant.cabinets.forEach(function (c) {
      var chip = SD.chip("stale"), used = SD.el("dd", { text: String(c.bits.length) });
      cards[c.id] = { card: SD.el("a", { cls: "card link s-stale", href: SD.href("cabinets", String(c.id)) }, [
        SD.el("h3", null, [SD.icon("cabinet"), SD.el("span", { text: c.fld })]),
        SD.el("dl", { cls: "kv" }, [SD.el("dt", { text: "State" }), SD.el("dd", null, chip),
          SD.el("dt", { text: "Channels used" }), used, SD.el("dt", { text: "Tristate" }),
          SD.el("dd", { text: c.tristate ? "yes (alarm + warning per channel)" : "no" })])]), chip: chip };
      grid.appendChild(cards[c.id].card);
    });
    SD.add(node, [SD.el("div", { cls: "head" }, SD.el("h2", { text: "Diagnosis cabinets" })), grid]);
    return { node: node, update: function (ev) {
      plant.cabinets.forEach(function (c) {
        var s = ev.cabinet[c.id].summary, chip = cards[c.id].chip;
        chip.textContent = s.state === "alarm" ? "Alarm" + (s.warning ? " + warning" : "") : SD.STATE_TEXT[s.state];
        SD.setState(chip, s.state);
        SD.setState(cards[c.id].card, s.state);
      });
    } };
  }

  function one(ctx, cab) {
    var model = ctx.model, node = SD.el("div"), squares = [], rows = {}, words = {};
    var summary = SD.chip("stale");
    var families = [{ warning: false, names: cab.alarm_words, label: "Alarm channels" }];
    if (!cab.tristate && cab.bits.some(function (b) { return b.warning; })) {
      families.push({ warning: true, names: cab.warning_words, label: "Warning channels" });
    }
    var wordList = SD.el("dl", { cls: "kv" });
    Object.keys(cab.words).forEach(function (w) {
      words[w] = SD.el("dd", { cls: "mono", text: "-" });
      SD.add(wordList, [SD.el("dt", { text: w }), words[w]]);
    });
    SD.add(node, [SD.el("div", { cls: "head" }, [SD.el("h2", { text: "Cabinet " + cab.fld }), summary,
      SD.el("a", { cls: "btn", href: SD.href("cabinets"), text: "All cabinets" })])]);
    families.forEach(function (fam) {
      SD.add(node, SD.el("h3", { cls: "section", text: fam.label + (cab.tristate ? " (each also carries a warning)" : "") }));
      [0, 1].forEach(function (half) {
        var grid = SD.el("div", { cls: "bits", role: "group" });
        for (var i = 0; i < 32; i += 1) {
          var bit = half * 32 + i, entry = cab.bitAt[(fam.warning ? "w" : "a") + bit];
          var sq = SD.el(entry ? "button" : "span", { cls: "bit " + (entry ? "used s-stale" : "free"), text: String(bit),
            type: entry ? "button" : null, title: entry ? "bit " + bit + ": " + entry.text : "bit " + bit + ": not used" });
          if (entry && entry.owner) {
            sq.addEventListener("click", (function (owner) { return function () { SD.open(owner); }; })(entry.owner));
          }
          if (entry) { squares.push({ sq: sq, key: (fam.warning ? "w" : "a") + bit, bit: entry }); }
          grid.appendChild(sq);
        }
        SD.add(node, [SD.el("div", { cls: "wordname mono", text: (fam.names[half] || "-") + " - bits " + (half * 32) + " to " + (half * 32 + 31) }), grid]);
      });
    });
    var tbody = SD.el("tbody");
    cab.bits.slice().sort(function (a, b) { return a.bit - b.bit || (a.warning ? 1 : -1); }).forEach(function (b) {
      var chip = SD.chip("stale"), raw = SD.el("td", { cls: "num mono", text: "-" }), owner = model.byId[b.owner];
      var tr = SD.el("tr", { cls: owner ? "click" : "", on: owner ? { click: function () { SD.open(owner.id); } } : null }, [
        SD.el("td", { cls: "num", text: b.bit + (b.warning ? " w" : "") }), SD.el("td", null, chip), raw,
        SD.el("td", { text: b.text }), SD.el("td", { cls: "wide mono", text: owner ? owner.fld : "" }),
        SD.el("td", { cls: "wide", text: b.source })]);
      rows[(b.warning ? "w" : "a") + b.bit] = { chip: chip, raw: raw, tr: tr };
      tbody.appendChild(tr);
    });
    SD.add(node, [SD.el("h3", { cls: "section", text: "Used channels" }), SD.el("div", { cls: "scroll" }, SD.el("table", { cls: "grid" }, [
      SD.el("thead", null, SD.el("tr", null, ["Bit", "State", "Raw", "Text", "Device", "Source"].map(function (h, i) {
        return SD.el("th", { cls: i >= 4 ? "wide" : i === 0 || i === 2 ? "num" : "", text: h }); }))), tbody])),
      SD.el("h3", { cls: "section", text: "Words read" }), wordList]);

    return { node: node, update: function (ev) {
      var c = ev.cabinet[cab.id], snap = ev.snap;
      summary.textContent = SD.STATE_TEXT[c.summary.state] + (c.summary.warning && c.summary.alarm ? " + warning" : "");
      SD.setState(summary, c.summary.state);
      squares.forEach(function (s) { SD.setState(s.sq, c.channels[s.key].state); });
      Object.keys(rows).forEach(function (key) {
        var ch = c.channels[key], r = rows[key];
        r.chip.textContent = SD.STATE_TEXT[ch.state];
        SD.setState(r.chip, ch.state);
        r.raw.textContent = ch.raw === null ? "-" : String(ch.raw);
      });
      Object.keys(words).forEach(function (w) { words[w].textContent = hex(snap.v[cab.words[w]]); });
    } };
  }

  SD.view("cabinets", { label: "Cabinets", icon: "cabinet", order: 30, nav: true, render: function (ctx, route) {
    var cab = route.arg ? ctx.model.cabinet[route.arg] : null;
    return cab ? one(ctx, cab) : list(ctx);
  } });
})(SD);
