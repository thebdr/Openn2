"""The S7-1500 Web API probe - the C-050 milestone-0 check on a real CPU (stdlib only).

Chapter: before PL5 generates the web diagnosis app (sub-phase 650) and OP5 uploads it, this probe answers
on the CPU itself what the documentation leaves open:
  - the Web API method list, and the rights the Anonymous user really has (`info`)
  - whether every name PL5 writes reads back through PlcProgram.Read - spaces, [ ], =, /, F-DB members,
    the struct members of 99_Commissioning, the PLC tags, the interface tags (`read-set --all`)
  - the batch size and the latency of the hybrid poll set (`sweep`)
  - the bit polarity per device kind: `watch` prints every change of the cabinet diagnosis words (decoded
    to the device text) and of the area states while someone presses an e-stop / opens a door
  - how PlcProgram.Browse describes a free-form PL5_CustomData DB (`browse`)
  - with a deploy user: whether a throwaway web application is created, served and deleted
    (`deploy-probe`, `delete-probe`)
Everything it learns goes into .zen/evidence/C-050.md (`--out` keeps the raw replies as JSON).

It never writes a PLC value. The only write-type calls are WebApp.* on the throwaway app, and those log in
with a user whose password is asked on the terminal (getpass) - never taken from an argument, a file or the
environment.

Run with the CPU's own certificate pinned (it is usually self-signed): fetch it once (`openssl s_client
-connect <ip>:443 -showcerts`), compare its SHA-256 fingerprint with the one TIA shows for the CPU's web server
certificate, save the PEM and pass `--cafile <pem>` - verification stays on, only that certificate is accepted
(and its subjectAltName must name the IP). `--insecure` skips the check altogether - a last resort on a bench.
    <python> scripts/webapi_probe.py --host 192.168.20.1 --cafile cpu.pem info
    <python> scripts/webapi_probe.py --host 192.168.20.1 --cafile cpu.pem read-set --database <project>/Database [--all]
    <python> scripts/webapi_probe.py --host 192.168.20.1 --cafile cpu.pem sweep --database <project>/Database
    <python> scripts/webapi_probe.py --host 192.168.20.1 --cafile cpu.pem watch --database <project>/Database
    <python> scripts/webapi_probe.py --host 192.168.20.1 --cafile cpu.pem browse "\"PL5_CustomData\""
    <python> scripts/webapi_probe.py --host 192.168.20.1 --cafile cpu.pem read "\"05_EM_STATE\".\"AREA 1 Q\""
    <python> scripts/webapi_probe.py --host 192.168.20.1 --cafile cpu.pem call Api.Browse
    <python> scripts/webapi_probe.py --host 192.168.20.1 --cafile cpu.pem --user deploy deploy-probe
    <python> scripts/webapi_probe.py --host 192.168.20.1 --cafile cpu.pem --user deploy delete-probe
`--user <name>` on any command logs in first (password prompt) - `info` with and without it shows what the
Anonymous user lacks. `--anonymous` logs in as the built-in anonymous user instead ("Everybody" before FW
V3.1, "Anonymous" after, empty password): on FW V2.9.4 a call without any token has no rights, even when TIA
gives "Everybody" some. Exit code: 0 = the probe ran, 1 = it could not reach / log in to the CPU.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import getpass
import hashlib
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request

SEEDS = {"AlwaysFALSE", "AlwaysTRUE", "No Operation"}   # generation_params.yaml seed members, in every DB
AREA_DBS = ("05_EM_STATE", "02_COM")
DIAG_DB = "DiagnosticTags"
WORDS = ("STATE", "ALARM1", "ALARM2", "WARNING1", "WARNING2")
EXPECTED_METHODS = ("Api.Login", "Api.Logout", "Api.GetPermissions", "Api.BrowseTickets", "Api.CloseTicket",
                    "PlcProgram.Browse", "PlcProgram.Read", "WebApp.Browse", "WebApp.Create",
                    "WebApp.Delete", "WebApp.SetState", "WebApp.SetDefaultPage", "WebApp.BrowseResources",
                    "WebApp.CreateResource", "WebApp.DeleteResource")
_CABINET = re.compile(r"CABINET(\d+)\.(\w+)$")


class ProbeError(Exception):
    """The CPU could not be reached, answered something that is not JSON-RPC, or refused the login."""


class WebApi:
    """A minimal JSON-RPC 2.0 client of the S7-1500 Web API: POST /api/jsonrpc (single or batch),
    POST /api/ticket?id=<ticket> for resource bytes, GET for the served pages. The token from Api.Login
    rides in X-Auth-Token; without one every call runs as the Anonymous user."""

    def __init__(self, host: str, context, timeout: float, scheme: str = "https"):
        self.base = f"{scheme}://{host}"
        self.context = context
        self.timeout = timeout
        self.token = None
        self._next_id = 0

    def _request(self, method: str, path: str, body: bytes | None, content_type: str | None,
                 token: bool = True):
        headers = {"Content-Type": content_type} if content_type else {}
        if token and self.token:
            headers["X-Auth-Token"] = self.token
        request = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, context=self.context, timeout=self.timeout) as reply:
                return reply.status, reply.read(), time.perf_counter() - start
        except urllib.error.HTTPError as err:
            return err.code, err.read(), time.perf_counter() - start
        except (urllib.error.URLError, OSError) as err:
            raise ProbeError(f"{self.base}{path}: {getattr(err, 'reason', err)}") from err

    def batch(self, calls):
        """[(method, params)] in ONE request -> ([reply entry per call, in order], http status, seconds).
        An entry is the JSON-RPC object ({"result": ...} or {"error": {...}}); a call the CPU left
        unanswered gets a synthetic error naming the HTTP status (a whole-batch refusal)."""
        payload = []
        for method, params in calls:
            self._next_id += 1
            entry = {"jsonrpc": "2.0", "method": method, "id": self._next_id}
            if params is not None:
                entry["params"] = params
            payload.append(entry)
        status, raw, seconds = self._request("POST", "/api/jsonrpc", json.dumps(payload).encode("utf-8"),
                                             "application/json")
        try:
            data = json.loads(raw.decode("utf-8") or "null")
        except ValueError as err:
            raise ProbeError(f"HTTP {status}, not JSON: {raw[:200]!r}") from err
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ProbeError(f"HTTP {status}, unexpected reply: {str(data)[:200]}")
        by_id = {entry.get("id"): entry for entry in data if isinstance(entry, dict)}
        whole = by_id.get(None) or {"error": {"code": None, "message": f"no reply (HTTP {status})"}}
        return [by_id.get(call["id"], whole) for call in payload], status, seconds

    def call(self, method: str, params=None):
        """One call -> (result, error, seconds); exactly one of result / error is None."""
        (entry,), _status, seconds = self.batch([(method, params)])
        return entry.get("result"), entry.get("error"), seconds

    def upload(self, ticket: str, data: bytes):
        return self._request("POST", f"/api/ticket?id={ticket}", data, "application/octet-stream")

    def get(self, path: str):
        """An anonymous GET (no token) -> (status, body bytes, seconds)."""
        return self._request("GET", path, None, None, token=False)

    def login(self, user: str) -> None:
        password = getpass.getpass(f"Password for web user {user!r} on {self.base}: ")
        result, error, _ = self.call("Api.Login", {"user": user, "password": password})
        del password
        if error or not isinstance(result, dict) or not result.get("token"):
            raise ProbeError(f"Api.Login refused for {user!r}: {error or result}")
        self.token = result["token"]

    def login_anonymous(self) -> str:
        """Log in as the CPU's built-in anonymous user, whose password is empty (nothing secret). On FW V2.9.4
        a call without a token has no rights at all; only a token of "Everybody" carries the rights TIA gives
        that user. FW V3.1 renamed it "Anonymous"."""
        for user in ("Everybody", "Anonymous"):
            result, error, _ = self.call("Api.Login", {"user": user, "password": ""})
            if not error and isinstance(result, dict) and result.get("token"):
                self.token = result["token"]
                return user
        raise ProbeError(f"Api.Login refused for 'Everybody' and 'Anonymous' (empty password): {error or result}")

    def logout(self) -> None:
        if self.token:
            self.call("Api.Logout")
            self.token = None


# --- the Database: the exact names PL5 writes --------------------------------------------------------------- #

def _rows(database: str, table: str) -> list:
    path = os.path.join(database, f"{table}.csv")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def quote(*parts: str) -> str:
    """The TIA symbol: each part double-quoted, joined by dots (symbols.TiaSymbols, generalized to a
    struct level)."""
    return ".".join(f'"{part}"' for part in parts if part)


def member_var(row: dict) -> str:
    return quote(row["db_name"], row.get("struct") or "", row["member"])


def poll_set(database: str) -> list:
    """The hybrid set the page reads every cycle: the DiagnosticTags words of the cabinets that carry
    entries, then every non-seed member of the area DBs."""
    members = _rows(database, "db_members")
    used = {int(row["cabinet"]) for row in _rows(database, "diagnosis_entries") if row.get("cabinet")}
    words = [row for row in members if row["db_name"] == DIAG_DB
             and (m := _CABINET.search(row["member"])) and int(m.group(1)) in used]
    areas = [row for row in members if row["db_name"] in AREA_DBS and row["member"] not in SEEDS]
    return [member_var(row) for row in words + areas]


def name_set(database: str, everything: bool) -> list:
    """[(group, var)]: the poll set, then the names a device detail reads - one per DB / tag table /
    interface (everything=False) or every one of them (everything=True)."""
    out = [("poll", var) for var in poll_set(database)]
    seen = {var for _group, var in out}
    taken: set = set()

    def add(group: str, var: str) -> None:
        if var and var not in seen and (everything or group not in taken):
            out.append((group, var))
            seen.add(var)
            taken.add(group)

    for row in _rows(database, "db_members"):
        if row["member"] not in SEEDS:
            struct = f".{row['struct']}" if row.get("struct") else ""
            add(f"db:{row['db_name']}{struct}", member_var(row))
    for row in _rows(database, "signals"):
        if row.get("name_in_tagtable") and row.get("tagtable"):
            add(f"tags:{row['tagtable']}", quote(row["name_in_tagtable"]))
    for row in _rows(database, "interface_elements"):
        if row.get("signal_name"):
            add(f"if:{row['interface']}", quote(row["signal_name"]))
    return out


def diag_texts(database: str) -> dict:
    """{(cabinet, bit 0..63): text} from diagnosis_entries (the DiagList's Diag Desc)."""
    texts = {}
    for row in _rows(database, "diagnosis_entries"):
        try:
            columns = json.loads(row.get("diag_columns") or "{}")
        except ValueError:
            columns = {}
        text = columns.get("Diag Desc") or row.get("rule_name") or row.get("in_binding") or ""
        texts[(int(row["cabinet"]), int(row["bit"]))] = text
    return texts


# --- commands ----------------------------------------------------------------------------------------------- #

def read_many(api: WebApi, names: list, chunk: int) -> list:
    """[(var, value, error)] reading `names` in batches of `chunk`; the per-batch timing printed."""
    out = []
    for start in range(0, len(names), chunk):
        part = names[start:start + chunk]
        entries, status, seconds = api.batch([("PlcProgram.Read", {"var": var}) for var in part])
        failed = sum(1 for entry in entries if "error" in entry)
        print(f"  batch {start // chunk + 1}: {len(part)} vars, HTTP {status}, {seconds * 1000:.0f} ms,"
              f" {failed} failed")
        out += [(var, entry.get("result"), entry.get("error")) for var, entry in zip(part, entries)]
    return out


def cmd_info(api: WebApi, args, record: dict) -> None:
    host = args.host.split(":")[0]
    port = int(args.host.split(":")[1]) if ":" in args.host else 443
    if not args.http:
        pem = ssl.get_server_certificate((host, port))
        thumb = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
        print(f"certificate sha256: {thumb}")
        record["certificate_sha256"] = thumb
    for method in ("Api.Ping", "Api.Version", "Api.GetPermissions"):
        result, error, seconds = api.call(method)
        print(f"{method}: {json.dumps(result if error is None else {'error': error})} ({seconds * 1000:.0f} ms)")
        record[method] = result if error is None else {"error": error}
    result, error, _ = api.call("Api.Browse")
    names = sorted(entry.get("name", "") for entry in result or [] if isinstance(entry, dict))
    record["Api.Browse"] = names if error is None else {"error": error}
    if error:
        print(f"Api.Browse: error {error}")
        return
    print(f"Api.Browse: {len(names)} methods")
    for method in EXPECTED_METHODS:
        print(f"  [{'x' if method in names else ' '}] {method}")
    others = [name for name in names if name not in EXPECTED_METHODS]
    print("  other: " + ", ".join(others))


def cmd_read(api: WebApi, args, record: dict) -> None:
    results = read_many(api, list(args.vars), args.chunk)
    for var, value, error in results:
        print(f"{var} = {json.dumps(value)}" if error is None else f"{var} !! {json.dumps(error)}")
    record["read"] = [{"var": v, "value": r, "error": e} for v, r, e in results]


def cmd_read_set(api: WebApi, args, record: dict) -> None:
    named = name_set(args.database, args.all)
    print(f"{len(named)} names from {args.database} ({'every name' if args.all else 'poll set + one per group'})")
    results = read_many(api, [var for _group, var in named], args.chunk)
    groups: dict = {}
    failures = []
    for (group, var), (_var, value, error) in zip(named, results):
        ok, total = groups.get(group, (0, 0))
        groups[group] = (ok + (error is None), total + 1)
        if error is not None:
            failures.append((group, var, error))
        elif group == "poll" or not args.all:
            print(f"  {var} = {json.dumps(value)}")
    print("per group (readable / total):")
    for group, (ok, total) in groups.items():
        print(f"  {group}: {ok}/{total}")
    errors: dict = {}
    for group, var, error in failures:
        errors.setdefault(json.dumps(error, sort_keys=True), []).append(var)
    for error, names in errors.items():
        print(f"FAILED x{len(names)} {error}:")
        for var in names[:20]:
            print(f"    {var}")
        if len(names) > 20:
            print(f"    ... {len(names) - 20} more")
    print(f"total: {len(results) - len(failures)}/{len(results)} readable")
    record["read_set"] = [{"group": g, "var": v, "value": r, "error": e}
                          for (g, v), (_v, r, e) in zip(named, results)]


def cmd_sweep(api: WebApi, args, record: dict) -> None:
    names = [var for _group, var in name_set(args.database, True)]
    sizes = [int(size) for size in args.sizes.split(",")]
    rows = []
    print("size  repeats  ok-calls  failed  http  min/avg/max ms")
    for size in sizes:
        part = (names * (size // max(1, len(names)) + 1))[:size]
        times, failed, statuses = [], 0, set()
        for _ in range(args.repeat):
            entries, status, seconds = api.batch([("PlcProgram.Read", {"var": var}) for var in part])
            times.append(seconds * 1000)
            failed += sum(1 for entry in entries if "error" in entry)
            statuses.add(status)
        calls = size * args.repeat
        print(f"{size:>4}  {args.repeat:>7}  {calls - failed:>8}  {failed:>6}  {sorted(statuses)}"
              f"  {min(times):.0f}/{sum(times) / len(times):.0f}/{max(times):.0f}")
        rows.append({"size": size, "repeat": args.repeat, "failed": failed, "http": sorted(statuses),
                     "ms": times})
    poll = poll_set(args.database)
    times = []
    for _ in range(args.repeat):
        start = time.perf_counter()
        read_many(api, poll, args.chunk)
        times.append((time.perf_counter() - start) * 1000)
    print(f"full poll set ({len(poll)} vars, chunk {args.chunk}): "
          f"{min(times):.0f}/{sum(times) / len(times):.0f}/{max(times):.0f} ms")
    record["sweep"] = {"sizes": rows, "poll_set": {"vars": len(poll), "chunk": args.chunk, "ms": times}}


def _decode(var: str, old, new, texts: dict) -> list:
    """The changed bits of a cabinet word as readable lines; [] for any other variable."""
    m = _CABINET.search(var.replace('"', ""))
    if not m or m.group(2) == "STATE" or not isinstance(new, int):
        return []
    cabinet, word = int(m.group(1)), m.group(2)
    offset = 32 if word.endswith("2") else 0
    old = old if isinstance(old, int) else 0
    lines = []
    for bit in range(32):
        if (old ^ new) >> bit & 1:
            text = texts.get((cabinet, bit + offset), "(no diagnosis entry)")
            lines.append(f"      cabinet {cabinet:03d} {word} bit {bit + offset:02d}:"
                         f" {old >> bit & 1}->{new >> bit & 1}  {text}")
    return lines


def cmd_watch(api: WebApi, args, record: dict) -> None:
    poll = poll_set(args.database)
    texts = diag_texts(args.database)
    print(f"watching {len(poll)} vars every {args.interval} s - Ctrl+C to stop")
    last: dict = {}
    events = []
    stop = time.time() + args.duration if args.duration else None
    try:
        while stop is None or time.time() < stop:
            for start in range(0, len(poll), args.chunk):
                part = poll[start:start + args.chunk]
                entries, _status, _seconds = api.batch([("PlcProgram.Read", {"var": var}) for var in part])
                for var, entry in zip(part, entries):
                    value = entry.get("result") if "error" not in entry else {"error": entry["error"]}
                    if var in last and last[var] == value:
                        continue
                    stamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    previous = last.get(var, "(first)")
                    print(f"{stamp}  {var}: {json.dumps(previous)} -> {json.dumps(value)}")
                    for line in _decode(var, last.get(var), value, texts):
                        print(line)
                    events.append({"t": stamp, "var": var, "old": previous, "new": value})
                    last[var] = value
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("stopped")
    record["watch"] = events


def cmd_browse(api: WebApi, args, record: dict) -> None:
    nodes = []

    def walk(var: str, depth: int) -> None:
        params = {"mode": "children"}
        if var:
            params["var"] = var
        result, error, _ = api.call("PlcProgram.Browse", params)
        if error:
            print(f"{'  ' * depth}{var or '(root)'} !! {json.dumps(error)}")
            nodes.append({"var": var, "error": error})
            return
        for child in result or []:
            name = child.get("name", "?")
            path = f'{var}.{quote(name)}' if var else quote(name)
            print(f"{'  ' * depth}{name}  {json.dumps(child, sort_keys=True)}")
            nodes.append({"parent": var, "child": child})
            if child.get("has_children") and depth + 1 < args.depth:
                walk(path, depth + 1)

    walk(args.var, 0)
    record["browse"] = nodes


def _step(api: WebApi, label: str, method: str, params, record: list):
    result, error, _ = api.call(method, params)
    print(f"{label}: {method} -> {json.dumps(result) if error is None else 'ERROR ' + json.dumps(error)}")
    record.append({"step": label, "method": method, "result": result, "error": error})
    return result, error


def cmd_deploy_probe(api: WebApi, args, record: dict) -> None:
    if not api.token:
        raise ProbeError("deploy-probe needs --user <deploy user> (a user with the manage-user-pages right)")
    app = args.app
    steps: list = []
    _step(api, "permissions", "Api.GetPermissions", None, steps)
    _step(api, "apps before", "WebApp.Browse", None, steps)
    _step(api, "create", "WebApp.Create", {"name": app, "state": "disabled"}, steps)
    now = datetime.datetime.now(datetime.timezone.utc)
    html = (f"<!doctype html><meta charset=utf-8><title>{app}</title>"
            f"<p>{app} uploaded {now.isoformat(timespec='seconds')} by Pipeline5 webapi_probe</p>").encode()
    stamp = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
    ticket, error = _step(api, "resource", "WebApp.CreateResource",
                          {"app_name": app, "name": "index.html", "media_type": "text/html",
                           "last_modified": stamp, "visibility": "public"}, steps)
    if error is None and ticket:
        try:
            status, body, seconds = api.upload(str(ticket), html)
            print(f"upload: HTTP {status} {body[:120]!r} ({seconds * 1000:.0f} ms)")
            steps.append({"step": "upload", "http": status, "body": body[:200].decode("utf-8", "replace")})
            _step(api, "ticket state", "Api.BrowseTickets", {"id": ticket}, steps)
        finally:
            _step(api, "close ticket", "Api.CloseTicket", {"id": ticket}, steps)
    _step(api, "default page", "WebApp.SetDefaultPage", {"name": app, "resource_name": "index.html"}, steps)
    _step(api, "enable", "WebApp.SetState", {"name": app, "state": "enabled"}, steps)
    _step(api, "resources", "WebApp.BrowseResources", {"app_name": app}, steps)
    _step(api, "apps after", "WebApp.Browse", {"name": app}, steps)
    for path in (f"/~{app}/", f"/~{app}/index.html"):
        status, body, seconds = api.get(path)
        print(f"anonymous GET {path}: HTTP {status} ({seconds * 1000:.0f} ms) {body[:120]!r}")
        steps.append({"step": f"GET {path}", "http": status, "body": body[:200].decode("utf-8", "replace")})
    record["deploy_probe"] = steps


def cmd_delete_probe(api: WebApi, args, record: dict) -> None:
    if not api.token:
        raise ProbeError("delete-probe needs --user <deploy user>")
    steps: list = []
    _step(api, "delete", "WebApp.Delete", {"name": args.app}, steps)
    _step(api, "apps after", "WebApp.Browse", None, steps)
    record["delete_probe"] = steps


def cmd_call(api: WebApi, args, record: dict) -> None:
    params = json.loads(args.params) if args.params else None
    result, error, seconds = api.call(args.method, params)
    print(json.dumps(result if error is None else {"error": error}, indent=2))
    print(f"({seconds * 1000:.0f} ms)")
    record["call"] = {"method": args.method, "params": params, "result": result, "error": error}


COMMANDS = {"info": cmd_info, "read": cmd_read, "read-set": cmd_read_set, "sweep": cmd_sweep,
            "watch": cmd_watch, "browse": cmd_browse, "deploy-probe": cmd_deploy_probe,
            "delete-probe": cmd_delete_probe, "call": cmd_call}


def _context(args):
    if args.http:
        return None
    if args.insecure:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    return ssl.create_default_context(cafile=args.cafile)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--host", required=True, help="CPU address (IP or name, optional :port)")
    parser.add_argument("--insecure", action="store_true", help="accept the CPU's self-signed certificate")
    parser.add_argument("--cafile", help="PEM to verify the CPU certificate against")
    parser.add_argument("--http", action="store_true", help=argparse.SUPPRESS)   # a local mock server only
    who = parser.add_mutually_exclusive_group()
    who.add_argument("--user", help="log in first as this web user (password prompted)")
    who.add_argument("--anonymous", action="store_true",
                     help="log in first as the built-in Everybody / Anonymous user (empty password)")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--chunk", type=int, default=50, help="variables per JSON-RPC batch")
    parser.add_argument("--out", help="append the raw results to this JSON file (evidence)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("info")
    p = sub.add_parser("read")
    p.add_argument("vars", nargs="+")
    p = sub.add_parser("read-set")
    p.add_argument("--database", required=True)
    p.add_argument("--all", action="store_true", help="every member / tag / interface name")
    p = sub.add_parser("sweep")
    p.add_argument("--database", required=True)
    p.add_argument("--sizes", default="10,25,50,100,150,200")
    p.add_argument("--repeat", type=int, default=5)
    p = sub.add_parser("watch")
    p.add_argument("--database", required=True)
    p.add_argument("--interval", type=float, default=0.5)
    p.add_argument("--duration", type=float, default=0, help="seconds (0 = until Ctrl+C)")
    p = sub.add_parser("browse")
    p.add_argument("var", nargs="?", default="", help='e.g. "\\"PL5_CustomData\\"" (empty = the root)')
    p.add_argument("--depth", type=int, default=6)
    for name in ("deploy-probe", "delete-probe"):
        p = sub.add_parser(name)
        p.add_argument("--app", default="pl5probe")
    p = sub.add_parser("call")
    p.add_argument("method")
    p.add_argument("params", nargs="?", help="JSON params")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    sys.stdout.reconfigure(errors="replace")    # a device text the console code page lacks must not abort a watch
    api = WebApi(args.host, _context(args), args.timeout, "http" if args.http else "https")
    record = {"host": args.host, "command": args.command, "user": args.user or "Anonymous",
              "at": datetime.datetime.now().isoformat(timespec="seconds")}
    try:
        if args.user:
            api.login(args.user)
        elif args.anonymous:
            record["user"] = api.login_anonymous()
        COMMANDS[args.command](api, args, record)
    except ProbeError as err:
        print(f"PROBE FAILED: {err}", file=sys.stderr)
        record["failed"] = str(err)
        return 1
    finally:
        try:
            api.logout()
        except ProbeError:
            pass
        if args.out:
            existing = []
            if os.path.isfile(args.out):
                with open(args.out, encoding="utf-8") as handle:
                    existing = json.load(handle)
            with open(args.out, "w", encoding="utf-8") as handle:
                json.dump(existing + [record], handle, indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
