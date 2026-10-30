// The Web API JSON-RPC client: same-origin POST /api/jsonrpc, batched, one HTTP request at a time page-wide.
// FW V2.9.4 grants no right without a token (C-050 M0, 2026-10-28), so the page logs in as the CPU's built-in
// anonymous user - plant.login.users in order ("Everybody" before FW V3.1, "Anonymous" after), the empty
// password, nothing secret - and sends X-Auth-Token. An expired token answers like no token (code 2
// "Permission denied" on every call), so a batch refused whole with code 2 logs in again once and is retried.
// Read-only by construction: only the methods in READ_ONLY can be sent.
(function (SD) {
  "use strict";
  var ENDPOINT = "/api/jsonrpc";
  SD.DENIED = 2;
  var READ_ONLY = { "Api.Login": true, "Api.Logout": true, "PlcProgram.Read": true, "PlcProgram.Browse": true };

  function failure(kind, message) {
    var error = new Error(message);
    error.kind = kind;     // network | http | rights | login
    return error;
  }
  SD.failure = failure;

  // the HTTP leg -> Promise {status, data}; data undefined = not JSON. The mock (mock.js) replaces it.
  SD.transport = function (payload, token, timeoutMs, keepalive) {
    var headers = { "Content-Type": "application/json" };
    if (token) { headers["X-Auth-Token"] = token; }
    var control = !keepalive && typeof AbortController === "function" ? new AbortController() : null;
    var timer = control ? setTimeout(function () { control.abort(); }, timeoutMs) : null;
    return fetch(ENDPOINT, { method: "POST", headers: headers, body: JSON.stringify(payload), cache: "no-store",
      credentials: "same-origin", keepalive: !!keepalive, signal: control ? control.signal : undefined })
      .then(function (reply) {
        return reply.text().then(function (text) {
          var data;
          try { data = text ? JSON.parse(text) : null; } catch (e) { data = undefined; }
          clearTimeout(timer);
          return { status: reply.status, data: data };
        });
      }, function (error) {
        clearTimeout(timer);
        throw failure("network", error && error.name === "AbortError" ? "no reply within " + timeoutMs + " ms"
          : "the CPU cannot be reached");
      });
  };

  function Rpc(login, polling) {
    this.users = login.users.slice();
    this.timeout = polling.timeout_ms;
    this.token = null;
    this.user = null;
    this.nextId = 0;
    this.tail = Promise.resolve();
  }

  // [{method, params}] in ONE request -> Promise [{result} | {error}] in call order
  Rpc.prototype.post = function (calls, token) {
    var self = this;
    var payload = calls.map(function (call) {
      if (!READ_ONLY[call.method]) { throw new Error("not a read-only method: " + call.method); }
      self.nextId += 1;
      var entry = { jsonrpc: "2.0", method: call.method, id: self.nextId };
      if (call.params) { entry.params = call.params; }
      return entry;
    });
    var run = function () {
      return SD.transport(payload, token, self.timeout).then(function (reply) {
        if (reply.status === 401 || reply.status === 403) { throw failure("rights", "HTTP " + reply.status); }
        if (reply.status !== 200) { throw failure("http", "the CPU answered HTTP " + reply.status); }
        var data = reply.data;
        if (data === undefined) { throw failure("network", "the CPU's reply is not JSON"); }
        if (data && !Array.isArray(data)) { data = [data]; }
        var byId = {};
        (data || []).forEach(function (entry) { if (entry && typeof entry === "object") { byId[String(entry.id)] = entry; } });
        var whole = byId["null"] || byId["undefined"] || { error: { code: null, message: "no reply" } };
        return payload.map(function (entry) { return byId[String(entry.id)] || whole; });
      });
    };
    var next = this.tail.then(run, run);
    this.tail = next.then(function () {}, function () {});
    return next;
  };

  Rpc.prototype.login = function () {
    var self = this, users = this.users.slice(), last = null;
    this.token = null;
    function attempt() {
      if (!users.length) {
        return Promise.reject(failure("login", "the CPU refused the anonymous login (" + self.users.join(", ") + ")"
          + (last && last.message ? ": " + last.message : "")));
      }
      var user = users.shift();
      return self.post([{ method: "Api.Login", params: { user: user, password: "" } }], null).then(function (entries) {
        var result = entries[0].result;
        if (result && typeof result.token === "string" && result.token) {
          self.token = result.token;
          self.user = user;
          return user;
        }
        last = entries[0].error;
        return attempt();
      });
    }
    return attempt();
  };

  function allDenied(entries) {
    return entries.length > 0 && entries.every(function (e) { return e.error && e.error.code === SD.DENIED; });
  }

  // a new login in place of the token: the old session is logged out first (a token that only lacks a right is
  // still a session on the CPU), so the page never holds more than one
  Rpc.prototype.relogin = function () {
    var self = this, old = this.token, done = function () { return self.login(); };
    this.token = null;
    return old ? this.post([{ method: "Api.Logout" }], old).then(done, done) : done();
  };

  // calls with the token; refused whole with code 2 -> one fresh login and one retry (unless `once` says this
  // read already retried). Still refused whole: the entries come back as they are and the caller decides
  // (a lone variable or the user's rights).
  Rpc.prototype.calls = function (calls, once) {
    var self = this;
    var ready = this.token ? Promise.resolve() : this.login();
    return ready.then(function () { return self.post(calls, self.token); }).then(function (entries) {
      if (!allDenied(entries) || once) { return entries; }
      return self.relogin().then(function () { return self.post(calls, self.token); });
    });
  };

  // vars -> Promise {var: {value} | {error}}, `chunk` names per request, the requests one after another
  Rpc.prototype.read = function (vars, chunk) {
    var self = this, out = {}, at = 0, retried = false;
    function step() {
      if (at >= vars.length) { return Promise.resolve(out); }
      var part = vars.slice(at, at + chunk);
      at += chunk;
      return self.calls(part.map(function (name) { return { method: "PlcProgram.Read", params: { var: name } }; }), retried)
        .then(function (entries) {
          retried = retried || allDenied(entries);
          entries.forEach(function (entry, i) {
            out[part[i]] = entry.error ? { error: entry.error } : { value: entry.result };
          });
          return step();
        });
    }
    return step();
  };

  // the children of `name` (a quoted variable path; "" = the root) -> Promise [child] or a {error} object
  Rpc.prototype.browse = function (name) {
    var params = { mode: "children" };
    if (name) { params["var"] = name; }
    return this.calls([{ method: "PlcProgram.Browse", params: params }]).then(function (entries) {
      return entries[0].error ? { error: entries[0].error } : (entries[0].result || []);
    });
  };

  // on pagehide: free the CPU's session now instead of after its ~2 min idle timeout
  Rpc.prototype.logout = function () {
    if (!this.token) { return; }
    var token = this.token;
    this.token = null;
    try {
      SD.transport([{ jsonrpc: "2.0", method: "Api.Logout", id: 0 }], token, this.timeout, true)
        .then(function () {}, function () {});
    } catch (e) { /* the page is going away */ }
  };

  SD.Rpc = Rpc;
})(SD);
