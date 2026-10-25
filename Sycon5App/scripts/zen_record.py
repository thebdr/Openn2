"""Record a clause's verification run as the repo's zen method keeps it: `.zen/evidence/runs/<clause>.json` - the
command, its exit code, the sha256 and the tail of its output, when and at which commit it ran, the test files it
named with their sha256 (the shape of the recorded runs of C-021 ... C-040). The verdict stays the command's exit code.
Usage (from anywhere, the repo venv):
    python -I Sycon5App\\scripts\\zen_record.py --clause C-046 -- bash Sycon5App/scripts/verify_c046.sh
    python -I Sycon5App\\scripts\\zen_record.py --clause C-047 --test Pipeline5App/tests/unit/test_sycon_handoff.py -- ...
The test files are taken from the command's arguments (paths under a tests folder) and from --test; paths are kept
repo-relative with forward slashes."""
import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNS = os.path.join(REPO, ".zen", "evidence", "runs")
TAIL_LINES = 15


def sha256_of(data):
    return hashlib.sha256(data).hexdigest()


def rel(path):
    return os.path.relpath(os.path.abspath(path), REPO).replace("\\", "/")


def head_commit():
    try:
        return subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def tests_in(script_path):
    """The test files a verify script names (its `tests/...py` tokens, resolved from the script's folder's parent)."""
    found = []
    try:
        text = open(script_path, encoding="utf-8").read()
    except OSError:
        return found
    base = os.path.dirname(os.path.dirname(os.path.abspath(script_path)))
    for m in re.finditer(r"(\.\./)?([\w./-]*tests/[\w./-]+\.py)", text):
        path = os.path.normpath(os.path.join(base, m.group(0)))
        if os.path.exists(path) and path not in found:
            found.append(path)
    return found


def main(argv=None):
    p = argparse.ArgumentParser(description="record a clause's verification run under .zen/evidence/runs")
    p.add_argument("--clause", required=True)
    p.add_argument("--test", action="append", default=[], help="a test file the run covers (repo-relative or absolute)")
    p.add_argument("--refute", choices=("held", "refuted"), default="",
                   help="record a refute round instead (.zen/evidence/refutes/<clause>.json): the verdict of the round, "
                        "its tests with their symbolSha (the sha256 of the test names they define)")
    p.add_argument("--round", type=int, default=0, help="with --refute: the round's number")
    p.add_argument("command", nargs=argparse.REMAINDER, help="the verification command (after --)")
    a = p.parse_args(argv)
    cmd = a.command[1:] if a.command and a.command[0] == "--" else a.command
    if not cmd:
        p.error("no command given (after --)")
    ran_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (datetime.datetime.now().microsecond // 1000)
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = (r.stdout or "") + (r.stderr or "")
    tests = []
    candidates = [c for c in cmd if c.endswith(".py") and "tests" in c.replace("\\", "/")] + list(a.test)
    for c in cmd:
        if c.endswith(".sh"):
            candidates += tests_in(os.path.join(REPO, c) if not os.path.isabs(c) else c)
    for c in candidates:
        path = c if os.path.isabs(c) else os.path.join(REPO, c)
        if not os.path.exists(path):
            print("warning: test file not found:", c, file=sys.stderr)
            continue
        entry = {"name": rel(path), "file": rel(path), "fileSha": sha256_of(open(path, "rb").read())}
        if entry not in tests:
            tests.append(entry)
    if a.refute:
        if a.refute == "held" and r.returncode != 0:
            print(output, end="")
            print("the round cannot be recorded as held: the command exited %d" % r.returncode, file=sys.stderr)
            return r.returncode or 1
        for t in tests:
            names = re.findall(r"^def (test_\w+)", open(os.path.join(REPO, t["file"]), encoding="utf-8").read(), re.M)
            t["symbolSha"] = sha256_of("\n".join(names).encode("utf-8"))
            del t["fileSha"]
        record = {"clause": a.clause, "verdict": a.refute, "ranAt": ran_at, "headCommit": head_commit(), "tests": tests}
        if a.round:
            record["round"] = a.round
        folder = os.path.join(REPO, ".zen", "evidence", "refutes")
        os.makedirs(folder, exist_ok=True)
        out = os.path.join(folder, a.clause + ".json")
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(record, f, indent=2)
            f.write("\n")
        print(output, end="")
        print("recorded:", rel(out), "| verdict", a.refute, "| exit", r.returncode)
        return r.returncode
    record = {
        "clause": a.clause,
        "command": " ".join(cmd),
        "commandArgv": list(cmd),
        "exitCode": r.returncode,
        "outputSha": sha256_of(output.encode("utf-8")),
        "outputTail": "\n".join(output.rstrip().splitlines()[-TAIL_LINES:]),
        "ranAt": ran_at,
        "headCommit": head_commit(),
        "tests": tests,
    }
    os.makedirs(RUNS, exist_ok=True)
    out = os.path.join(RUNS, a.clause + ".json")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(record, f, indent=2)
        f.write("\n")
    print(output, end="")
    print("recorded:", rel(out), "| exit", r.returncode)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
