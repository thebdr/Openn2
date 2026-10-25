"""The workspace of the users' GUI (user 2026-10-25: "sycon5app needs a basic gui for the users. buttons to retrieve the
workspace data and a log viewer"): a PRODUCTION folder as PL5 writes it (`<out>/HilscherIOCard<n>/SyconNetProjectInterface/`
per cifX card) and Sycon5App fills it (`HilscherPnCard_<n>.spj`, the exports, `_PL_Logs/`, `IODriver/BusField.csv`).
`scan(root)` reads what is there - no SYCON.net, nothing written; the `*_command` builders give the command lines of
the steps (the same scripts `scripts/build_production.sh` runs, the same log files) for the GUI's runner. No tkinter here."""
import os
import re
import sys
import time
from dataclasses import dataclass, field

from .handoff import MODULES_FILE, STATIONS_FILE, read_headed_csv

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PL5 = os.path.join(os.path.dirname(APP), "Pipeline5App")
HANDOFF_FOLDER, LOGS_FOLDER, IODRIVER_FOLDER = "SyconNetProjectInterface", "_PL_Logs", "IODriver"
CARD_FOLDER, PROJECT_NAME = "HilscherIOCard%d", "HilscherPnCard_%d"
CARD_RE = re.compile(r"^HilscherIOCard(\d+)$")
EXPORTS = ("HilscherIO.xml", os.path.join("nWid", "config.nxd"), os.path.join("nWid", "config_nwid.nxd"),
           os.path.join("nWid", "UpdateCardV5.bat"))
REPORT_RE = re.compile(r"^verification: (\d+) PASS, (\d+) FAIL")
BASE_PROJECT = os.path.join(APP, "spike", "scratch", "AutomateSyconProj_BaseProj.spj")


@dataclass
class Card:
    number: int
    folder: str
    handoff: str = ""                   # the SyconNetProjectInterface folder, "" when missing
    headers: dict = field(default_factory=dict)      # the #!openn header of SyconStations.csv
    stations: int = 0                   # the station rows (the controller excluded)
    controller: str = ""
    modules: int = 0                    # the module rows
    project: str = ""                   # the .spj, "" when not built
    project_time: float = 0.0
    report: str = ""                    # the verification report, "" when none
    report_time: float = 0.0
    passed: int = -1                    # -1: no report
    failed: int = -1
    notes: int = 0
    exports: dict = field(default_factory=dict)      # relative path -> mtime (0.0 when missing)
    logs: list = field(default_factory=list)         # the files of the card's _PL_Logs
    problems: list = field(default_factory=list)

    @property
    def name(self):
        return PROJECT_NAME % self.number

    @property
    def logs_dir(self):
        return os.path.join(self.folder, LOGS_FOLDER)

    @property
    def project_path(self):
        return os.path.join(self.folder, self.name + ".spj")

    @property
    def xml(self):
        return os.path.join(self.folder, self.name, "_S129", "SYCON_net.xml")

    @property
    def report_path(self):
        return os.path.join(self.logs_dir, self.name + ".verification.txt")

    @property
    def exports_present(self):
        return sum(1 for t in self.exports.values() if t)

    @property
    def verdict(self):
        """`823 PASS, 0 FAIL (29 notes)` of the report, "" without one."""
        if self.passed < 0:
            return ""
        return "%d PASS, %d FAIL%s" % (self.passed, self.failed, " (%d notes)" % self.notes if self.notes else "")

    def status(self):
        """One phrase for the table: what the card still needs, `complete` when nothing."""
        if not self.handoff:
            return "no handoff"
        if self.problems:
            return "handoff: " + self.problems[0]
        if not self.project:
            return "not built"
        if self.passed < 0:
            return "built, not verified"
        todo = []
        if self.failed > 0:
            todo.append("%d FAIL" % self.failed)
        if self.report_time < self.project_time - 1:
            todo.append("verified before the last save")
        if self.exports_present < len(EXPORTS):
            todo.append("exports %d/%d" % (self.exports_present, len(EXPORTS)))
        return ", ".join(todo) or "complete"


@dataclass
class Workspace:
    root: str
    cards: list = field(default_factory=list)
    busfield: str = ""
    busfield_time: float = 0.0
    logs: list = field(default_factory=list)         # the files of the root _PL_Logs
    problems: list = field(default_factory=list)

    @property
    def logs_dir(self):
        return os.path.join(self.root, LOGS_FOLDER)

    def card(self, number):
        for c in self.cards:
            if c.number == number:
                return c
        return None

    def log_files(self):
        """(label, path) of every log and report of the workspace, the root's first, newest first within a folder."""
        out = [("%s/%s" % (LOGS_FOLDER, os.path.basename(p)), p) for p in self.logs]
        for c in self.cards:
            out += [("%s/%s/%s" % (os.path.basename(c.folder), LOGS_FOLDER, os.path.basename(p)), p) for p in c.logs]
        return out


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _log_files(folder):
    if not os.path.isdir(folder):
        return []
    files = [os.path.join(folder, n) for n in os.listdir(folder) if n.lower().endswith((".log", ".txt"))]
    return sorted(files, key=_mtime, reverse=True)


def read_report(path):
    """(passed, failed, notes) of a verification report; (-1, -1, 0) when it cannot be read."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            first = f.readline()
            m = REPORT_RE.match(first)
            if not m:
                return -1, -1, 0
            notes = sum(1 for ln in f if ln.startswith("NOTE "))
            return int(m.group(1)), int(m.group(2)), notes
    except OSError:
        return -1, -1, 0


def scan_card(folder, number):
    c = Card(number=number, folder=folder)
    handoff = os.path.join(folder, HANDOFF_FOLDER)
    spath = os.path.join(handoff, STATIONS_FILE)
    if os.path.exists(spath):
        c.handoff = handoff
        try:
            head, rows = read_headed_csv(spath)
            c.headers = head
            if head.get("kind") != "hw/sycon-stations":
                c.problems.append("%s is not hw/sycon-stations" % STATIONS_FILE)
            rows = [r for r in rows if r and r[0]]
            controllers = [r for r in rows if r[0] == "controller"]
            c.stations = len(rows) - len(controllers)
            c.controller = controllers[0][1] if controllers and len(controllers[0]) > 1 else ""
            if len(controllers) != 1:
                c.problems.append("%d controller rows" % len(controllers))
            mpath = os.path.join(handoff, MODULES_FILE)
            if os.path.exists(mpath):
                _mh, mrows = read_headed_csv(mpath)
                c.modules = len([r for r in mrows if r and r[0]])
        except (OSError, UnicodeDecodeError) as ex:
            c.problems.append("%s unreadable: %s" % (STATIONS_FILE, ex))
    if os.path.exists(c.project_path):
        c.project = c.project_path
        c.project_time = max(_mtime(c.project_path), _mtime(c.xml))
    if os.path.exists(c.report_path):
        c.report = c.report_path
        c.report_time = _mtime(c.report_path)
        c.passed, c.failed, c.notes = read_report(c.report_path)
    c.exports = {rel: _mtime(os.path.join(folder, rel)) for rel in EXPORTS}
    c.logs = _log_files(c.logs_dir)
    return c


def scan(root):
    """The workspace as it is on disk: the cards in number order, the BusField, the logs."""
    w = Workspace(root=root)
    if not os.path.isdir(root):
        w.problems.append("not a folder: %s" % root)
        return w
    found = []
    for name in os.listdir(root):
        m = CARD_RE.match(name)
        if m and os.path.isdir(os.path.join(root, name)):
            found.append((int(m.group(1)), os.path.join(root, name)))
    for number, folder in sorted(found):
        w.cards.append(scan_card(folder, number))
    if not w.cards:
        w.problems.append("no HilscherIOCard<n> folder in %s" % root)
    busfield = os.path.join(root, IODRIVER_FOLDER, "BusField.csv")
    if os.path.exists(busfield):
        w.busfield, w.busfield_time = busfield, _mtime(busfield)
    w.logs = _log_files(w.logs_dir)
    return w


# ---- the steps ------------------------------------------------------------------------------------------------- #
@dataclass
class Command:
    label: str                          # what the GUI shows while it runs
    argv: list
    cwd: str
    log: str                            # the file the output is written to (the bash script's naming)
    drives_sycon: bool = False          # the desktop must be left alone while it runs
    summary_logs: list = field(default_factory=list)   # the root build.log lines (time-stamped) at start / end


VENV_PYTHON = os.path.join(os.path.dirname(APP), ".venv", "Scripts", "python.exe")


def python():
    """The interpreter of the steps: the repo venv (pywinauto, PL5's packages), whatever Python runs the GUI."""
    return VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable


def build_command(card, resume=False):
    """build_from_handoff.py of a card - SYCON.net driven; its log `build.log` / `build_resume.log` in the card's _PL_Logs."""
    flag = ["--resume"] if resume else []
    argv = [python(), "-I", os.path.join(APP, "scripts", "build_from_handoff.py"), "--handoff", card.handoff,
            "--out", card.project_path, "--report", card.report_path, "--base", BASE_PROJECT] + flag
    return Command("build card %d%s" % (card.number, " (resume)" if resume else ""), argv, APP,
                   os.path.join(card.logs_dir, "build_resume.log" if resume else "build.log"), drives_sycon=True)


def verify_command(card):
    """verify_saved.py: the saved project against its handoff, no SYCON.net; its log `verify.log` in the card's _PL_Logs."""
    argv = [python(), "-I", os.path.join(APP, "scripts", "verify_saved.py"), "--handoff", card.handoff,
            "--out", card.project_path, "--report", card.report_path]
    return Command("verify card %d" % card.number, argv, APP, os.path.join(card.logs_dir, "verify.log"))


def busfield_command(root):
    """busfield.py --production: IODriver/BusField.csv of every built card; its log in the root _PL_Logs."""
    argv = [python(), "-I", os.path.join(APP, "scripts", "busfield.py"), "--production", root]
    return Command("BusField", argv, APP, os.path.join(root, LOGS_FOLDER, "busfield.log"))


def export_command(iolist, root):
    """PL5's sycon_handoff: the handoff of every card of an I/O List into the workspace; its log export.log in the root _PL_Logs."""
    argv = [python(), "-W", "ignore", "-m", "pipeline5.systems.ipc_based.intervalzero_rtx.sycon_handoff",
            "--iolist", iolist, "--out", root]
    return Command("export the handoff of %s" % os.path.basename(iolist), argv, PL5, os.path.join(root, LOGS_FOLDER, "export.log"))


def note_summary(root, text):
    """A time-stamped line appended to the root _PL_Logs/build.log, as scripts/build_production.sh writes them."""
    logs = os.path.join(root, LOGS_FOLDER)
    os.makedirs(logs, exist_ok=True)
    with open(os.path.join(logs, "build.log"), "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (time.strftime("%H:%M:%S"), text))


# ---- the log viewer's colouring -------------------------------------------------------------------------------- #
LEVELS = ("RSLT", "FAIL", "ERRR", "WARN", "PASS", "NOTE", "INFO")
_TIMED = re.compile(r"^\d\d:\d\d:\d\d ")


def level_of(line):
    """The level a log line is shown as: the report's PASS / FAIL / NOTE lines, the verdicts (RSLT), errors and
    tracebacks (ERRR), warnings (WARN), everything else INFO."""
    s = line.lstrip()
    if s.startswith("PASS "):
        return "PASS"
    if s.startswith("FAIL "):
        return "FAIL"
    if s.startswith("NOTE "):
        return "NOTE"
    if s.startswith(("verification:", "SYCON handoff", "BusField:", "report:")) or " - verification:" in s:
        return "RSLT"
    low = s.lower()
    if s.startswith("Traceback") or "error" in low or "exception" in low or s.startswith("  File "):
        return "ERRR"
    if "warn" in low:
        return "WARN"
    return "INFO"
