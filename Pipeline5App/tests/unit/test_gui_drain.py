"""The App's UI-thread side of a running phase (workbench/app_main.py) on a stub host - no window: the log drain
keeps its budget (a big records batch drawn RECORD_CHUNK at a time, in order, ONE scroll per call, the next call
right away while work is left) and `_set_busy` hands the GIL over for the run (user 2026-10-10: "the animation
during the running phases lags, can it be smooth?")."""
import queue
import sys
import collections
from types import SimpleNamespace

from _harness import run, eq, ok
from pipeline5.workbench import app_main


class _Clock:
    """A fake perf_counter: drawing a chunk costs 5 ms, so two fit in the 8 ms budget."""
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class _Log:
    def __init__(self, clock=None):
        self.calls = []
        self.clock = clock

    def append(self, level, message, scroll=True):
        self.calls.append(("line", message, scroll))

    def append_records(self, records, scroll=True):
        self.calls.append(("records", [r for r in records], scroll))
        if self.clock:
            self.clock.now += 0.005

    def scroll_end(self):
        self.calls.append(("scroll",))


def _host(clock=None):
    scheduled = []
    host = SimpleNamespace(_q=queue.Queue(), _backlog=collections.deque(), log=_Log(clock),
                           root=SimpleNamespace(after=lambda ms, fn: scheduled.append(ms)),
                           status=SimpleNamespace(configure=lambda **k: None), _drain=lambda: None)
    return host, scheduled


def test_the_drain_draws_a_big_batch_in_chunks_in_order():
    """1000 records then a line: the first call draws RECORD_CHUNK records and keeps the rest, unscrolled
    inserts + ONE scroll, and asks for the next call right away; the rest follows chunk by chunk, the line
    LAST (the order the worker sent); an empty queue waits DRAIN_IDLE_MS."""
    clock = _Clock()
    host, scheduled = _host(clock)
    host._q.put(("records", list(range(1000))))
    host._q.put(("log", "INFO", "after the batch"))
    original = app_main.time.perf_counter
    app_main.time.perf_counter = clock
    try:
        app_main.App._drain(host)
        eq([len(call[1]) for call in host.log.calls if call[0] == "records"], [app_main.RECORD_CHUNK] * 2,
           "two chunks fit the 8 ms budget (5 ms each) - the call stops there")
        eq(host.log.calls[0], ("records", list(range(app_main.RECORD_CHUNK)), False), "a chunk, unscrolled")
        eq(host.log.calls[-1], ("scroll",), "one scroll per call")
        eq(scheduled[-1], 1, "work left: the next call right away")
        for _ in range(40):
            app_main.App._drain(host)
    finally:
        app_main.time.perf_counter = original
    drawn = [n for call in host.log.calls if call[0] == "records" for n in call[1]]
    eq(drawn, list(range(1000)), "every record, in order")
    lines = [i for i, call in enumerate(host.log.calls) if call[0] == "line"]
    last_records = max(i for i, call in enumerate(host.log.calls) if call[0] == "records")
    ok(lines and lines[0] > last_records, "the line after the batch is drawn after it")
    ok(all(call[2] is False for call in host.log.calls if call[0] in ("line", "records")), "inserts never scroll")
    eq(scheduled[-1], app_main.DRAIN_IDLE_MS, "nothing left: the idle cadence")


def test_a_running_phase_hands_the_gil_over():
    """`_set_busy(True)` sets BUSY_SWITCH_S for the run, `_set_busy(False)` restores the interval before it."""
    before = sys.getswitchinterval()
    calls = []
    host = SimpleNamespace(phasebar=SimpleNamespace(set_enabled=lambda on: calls.append(("bar", on))),
                           progress=SimpleNamespace(configure=lambda **k: None, start=lambda ms: calls.append(("start", ms)),
                                                    stop=lambda: calls.append(("stop",))))
    try:
        app_main.App._set_busy(host, True)
        eq(sys.getswitchinterval(), app_main.BUSY_SWITCH_S, "the run's interval")
        app_main.App._set_busy(host, False)
        eq(sys.getswitchinterval(), before, "restored when idle")
        eq(calls, [("bar", False), ("start", 12), ("bar", True), ("stop",)])
    finally:
        sys.setswitchinterval(before)


if __name__ == "__main__":
    sys.exit(run("gui_drain", [
        ("the_drain_draws_a_big_batch_in_chunks_in_order", test_the_drain_draws_a_big_batch_in_chunks_in_order),
        ("a_running_phase_hands_the_gil_over", test_a_running_phase_hands_the_gil_over),
    ]))
