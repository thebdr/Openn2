// Areas: the area tree (an area's parts nested under it), each with its state members, its causes, its reset
// and its sorter. A member whose `healthy` polarity is not configured shows its raw value, neutral.
(function (SD) {
  "use strict";
  function valueText(value) {
    return value === true ? "TRUE" : value === false ? "FALSE" : value === undefined ? "-" : String(value);
  }

  SD.view("areas", { label: "Areas", icon: "area", order: 40, nav: true, render: function (ctx) {
    var model = ctx.model, node = SD.el("div"), cards = {}, chips = {}, sorterChips = {};

    function memberRow(owner, m, i) {
      var chip = SD.chip("stale", m.label);
      chips[owner + "#" + i] = { chip: chip, member: m };
      return SD.el("span", { cls: "member", title: m.var }, chip);
    }
    function card(a) {
      var head = SD.chip("stale");
      var states = SD.el("div", { cls: "members" }), causes = SD.el("div", { cls: "members" }), other = SD.el("div", { cls: "members" });
      a.members.forEach(function (m, i) {
        (m.role === "state" ? states : m.role === "cause" ? causes : other).appendChild(memberRow(a.id, m, i));
      });
      var box = SD.el("div", { cls: "card area s-stale" }, [
        SD.el("h3", null, [SD.icon("area"), SD.el("span", { text: a.name }), head]),
        a.description ? SD.el("div", { cls: "muted", text: a.description }) : null,
        SD.el("div", { cls: "section", text: "State" }), states,
        causes.firstChild ? SD.el("div", { cls: "section", text: "Causes" }) : null, causes.firstChild ? causes : null,
        other.firstChild ? SD.el("div", { cls: "section", text: "Reset and other" }) : null, other.firstChild ? other : null]);
      var sorter = a.sorter && model.sorter[a.sorter];
      if (sorter) {
        var row = SD.el("div", { cls: "members" });
        sorter.members.forEach(function (m, i) {
          var chip = SD.chip("stale", m.label);
          sorterChips[sorter.id + "#" + i] = { chip: chip, member: m, sorter: sorter.id, i: i };
          row.appendChild(SD.el("span", { cls: "member", title: m.var }, chip));
        });
        SD.add(box, [SD.el("div", { cls: "section", text: "Sorter " + sorter.index }), row]);
      }
      var kids = model.children[a.id] || [];
      if (kids.length) { box.appendChild(SD.el("div", { cls: "kids" }, kids.map(card))); }
      cards[a.id] = { box: box, head: head };
      return box;
    }
    SD.add(node, [SD.el("div", { cls: "head" }, SD.el("h2", { text: "Areas" })), (model.children[""] || []).map(card)]);

    function show(chip, member, result) {
      var raw = valueText(result.value);
      chip.textContent = member.label + ": " + (result.state === "unknown" || result.state === "stale" ? raw
        : result.state === "ok" ? "OK" : SD.STATE_TEXT[result.state] || result.state);
      chip.title = member.var + " = " + raw + (member.healthy === null || member.healthy === undefined
        ? " (healthy polarity not configured)" : " (healthy = " + valueText(member.healthy) + ")");
      SD.setState(chip, result.state);
    }
    return { node: node, update: function (ev) {
      Object.keys(cards).forEach(function (id) {
        var state = ev.area[id].state;
        cards[id].head.textContent = SD.STATE_TEXT[state];
        SD.setState(cards[id].head, state);
        SD.setState(cards[id].box, state);
      });
      Object.keys(chips).forEach(function (key) {
        var id = key.split("#")[0], i = Number(key.split("#")[1]);
        show(chips[key].chip, chips[key].member, ev.area[id].members[i]);
      });
      Object.keys(sorterChips).forEach(function (key) {
        var s = sorterChips[key];
        show(s.chip, s.member, ev.sorter[s.sorter][s.i]);
      });
    } };
  } });
})(SD);
