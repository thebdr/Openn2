// Device notes (C-050): plant.notes ("kind|fld" -> {text, updated}, the project's webui_notes.csv at 650) under
// the edits made in this browser (localStorage, per project). The Notes view downloads them all as
// webui_notes.csv for the project's webui config: the CPU stays read-only, so a note reaches the other browsers
// through 650 and the upload. A note edited back to the project's text is no longer a local edit.
(function (SD) {
  "use strict";
  var MAX = 2000;

  function Notes(plant) {
    this.key = "pl5-notes-v1:" + (plant.meta.project || plant.app.name);
    this.shipped = plant.notes || {};
    this.local = {};
    try { this.local = JSON.parse(localStorage.getItem(this.key) || "{}") || {}; } catch (e) { this.local = {}; }
  }
  Notes.MAX = MAX;

  Notes.prototype.save = function () {
    try { localStorage.setItem(this.key, JSON.stringify(this.local)); return true; } catch (e) { return false; }
  };
  // {text, updated, local}: this browser's edit when there is one, else the project's note, else an empty one
  Notes.prototype.get = function (key) {
    var mine = this.local[key], theirs = this.shipped[key];
    if (mine) { return { text: mine.text, updated: mine.updated, local: true }; }
    return theirs ? { text: theirs.text, updated: theirs.updated, local: false } : { text: "", updated: "", local: false };
  };
  Notes.prototype.set = function (key, text) {
    var theirs = this.shipped[key];
    text = String(text || "").slice(0, MAX);
    if ((theirs ? theirs.text : "") === text) { delete this.local[key]; }
    else { this.local[key] = { text: text, updated: new Date().toISOString().slice(0, 16).replace("T", " ") }; }
    return this.save();
  };
  // every key with a note (the project's and this browser's), the empty ones left out
  Notes.prototype.keys = function () {
    var self = this, seen = {};
    return Object.keys(this.shipped).concat(Object.keys(this.local)).filter(function (k) {
      if (seen[k]) { return false; }
      seen[k] = true;
      return !!self.get(k).text;
    }).sort();
  };
  Notes.prototype.edits = function () { return Object.keys(this.local).length; };
  Notes.prototype.discard = function () { this.local = {}; return this.save(); };
  // the file the loader reads (config.load_webui_notes): kind,fld,note,updated - CRLF, csv quoting
  Notes.prototype.csv = function () {
    var self = this, rows = [["kind", "fld", "note", "updated"]];
    this.keys().forEach(function (key) {
      var at = key.indexOf("|"), n = self.get(key);
      rows.push([key.slice(0, at), key.slice(at + 1), n.text, n.updated]);
    });
    return rows.map(SD.csvRow).join("\r\n") + "\r\n";
  };

  SD.Notes = Notes;
})(SD);
