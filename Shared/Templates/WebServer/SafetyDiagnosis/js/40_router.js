// The hash routes: #/<view>[/<arg>][?d=<entity id>] - e.g. #/list/estop?d=estop-0035. The detail panel rides
// on any view, so a link to a device keeps the view it was opened from.
(function (SD) {
  "use strict";
  SD.route = function () {
    var hash = location.hash.replace(/^#\/?/, ""), query = "", at = hash.indexOf("?");
    if (at >= 0) { query = hash.slice(at + 1); hash = hash.slice(0, at); }
    var segments = hash.split("/").map(function (s) { try { return decodeURIComponent(s); } catch (e) { return s; } });
    var params = {};
    query.split("&").forEach(function (pair) {
      if (!pair) { return; }
      var eq = pair.indexOf("="), key = eq < 0 ? pair : pair.slice(0, eq), value = eq < 0 ? "" : pair.slice(eq + 1);
      try { params[decodeURIComponent(key)] = decodeURIComponent(value); } catch (e) { params[key] = value; }
    });
    return { view: segments[0] || "overview", arg: segments.slice(1).join("/"), detail: params.d || "" };
  };
  SD.href = function (view, arg, detail) {
    return "#/" + encodeURIComponent(view) + (arg ? "/" + encodeURIComponent(arg) : "")
      + (detail ? "?d=" + encodeURIComponent(detail) : "");
  };
  // the current view with the detail panel of `id` (null closes it)
  SD.detailHref = function (id) {
    var r = SD.route();
    return SD.href(r.view, r.arg, id);
  };
  SD.open = function (id) { location.hash = SD.detailHref(id); };
})(SD);
