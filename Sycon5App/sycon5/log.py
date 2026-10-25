"""The one log line of Sycon5App: `HH:MM:SS <parts>` on stdout, flushed (the scripts' logs and the GUI's viewer read
it line by line). Its own module so the XML / folder side (`canvas`, `workspace`, `gui`) logs without importing the
driver's `session` (law L2 of tests/test_architecture_contracts.py)."""
import time


def log(*parts):
    print(time.strftime("%H:%M:%S"), *parts, flush=True)
