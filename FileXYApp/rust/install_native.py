"""Build the Rust engine and install it for the app: compiles filexy-core with maturin (the
"python" feature -> the `filexy_core` extension module) and drops the .pyd next to the `filexy`
package, where both the standalone viewer and PL4's embedding find it on sys.path.

    py rust/install_native.py            (from FileXYApp/)

After it succeeds, `filexy.core.ENGINE` reports "rust" and xlsx loading goes through calamine.
Disable at any time with the environment variable FILEXY_RUST=0 (no rebuild needed)."""
from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

CRATE = Path(__file__).resolve().parent / "filexy-core"
DEST = Path(__file__).resolve().parents[1]  # FileXYApp/ - already on sys.path for all embedders
CARGO_BIN = Path.home() / ".cargo" / "bin"


def run(*cmd: str) -> None:
    print("->", " ".join(cmd))
    env = dict(os.environ)
    env["PATH"] = f"{CARGO_BIN}{os.pathsep}{env.get('PATH', '')}"
    env.setdefault("PYO3_PYTHON", sys.executable)
    subprocess.run(cmd, check=True, cwd=CRATE, env=env)


def install(target: Path, data: bytes) -> None:
    """Write the module SAFELY: a loaded .pyd is write-locked on Windows (the running app maps
    it), but renaming it aside is allowed - so park the old one and give the new file its name
    (written to a temp first, so a crash mid-write can't leave a truncated module behind)."""
    for old in target.parent.glob(target.name + ".old*"):   # from previous locked installs
        try:
            old.unlink()
        except OSError:
            pass  # still loaded by some process - next run collects it
    fresh = target.with_name(target.name + ".new")
    fresh.write_bytes(data)
    if target.exists():
        try:
            target.unlink()
        except PermissionError:  # loaded by the running app - rename-aside
            aside, n = target.with_name(target.name + ".old"), 0
            while aside.exists():
                n += 1
                aside = target.with_name(f"{target.name}.old{n}")
            os.replace(target, aside)
            print(f"note: the old engine is loaded by a running app - parked it as {aside.name};"
                  " RESTART the app to pick up the new engine")
    os.replace(fresh, target)
    print(f"installed {target}")


def main() -> None:
    try:
        run(sys.executable, "-m", "maturin", "--version")
    except (subprocess.CalledProcessError, FileNotFoundError):
        run(sys.executable, "-m", "pip", "install", "maturin")
    run(sys.executable, "-m", "maturin", "build", "--release")

    wheels = sorted((CRATE / "target" / "wheels").glob("filexy_core-*.whl"),
                    key=lambda p: p.stat().st_mtime)
    if not wheels:
        sys.exit("no wheel produced - see the maturin output above")
    with zipfile.ZipFile(wheels[-1]) as wheel:
        pyds = [n for n in wheel.namelist() if n.endswith((".pyd", ".so"))]
        if not pyds:
            sys.exit(f"no extension module inside {wheels[-1].name}")
        for name in pyds:
            try:
                install(DEST / Path(name).name, wheel.read(name))
            except PermissionError as exc:
                sys.exit(f"could not install {Path(name).name} ({exc}) - close FileXY/PL4 "
                         "and re-run rust/install_native.py")
    print("done - filexy.core.ENGINE is now 'rust' (opt out with FILEXY_RUST=0)")


if __name__ == "__main__":
    main()
