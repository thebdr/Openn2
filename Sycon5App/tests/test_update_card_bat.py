"""The shipped nWid\\UpdateCardV4.bat (the FVZ reference's, with the remembered card): run twice against a fake
driver folder - the first run finds the one card, copies the two nxd files into its Channel0 and remembers the
card in card.txt; the second run reports the remembered card and copies again; a remembered card that is gone
falls back to the normal workflow. `pause` reads nothing (stdin is NUL) and goes on."""
import os
import subprocess
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
BAT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "Shared", "HardwareConfigBuilderData", "nWid", "UpdateCardV4.bat")


def _run(nwid, driver):
    env = dict(os.environ, CIFX_DRIVER_PATH=driver)
    r = subprocess.run(["cmd", "/c", os.path.join(nwid, "UpdateCardV4.bat")], cwd=nwid, env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout


def _prepare(nwid):
    for name in ("config.nxd", "config_nwid.nxd"):
        with open(os.path.join(nwid, name), "wb") as f:
            f.write(b"nxd " + name.encode())


def test_remembered_card():
    text = open(BAT, "rb").read()
    assert b"\r\n" in text and b"card.txt" in text, "a Windows batch file with CRLF line endings, remembering the card"
    with tempfile.TemporaryDirectory() as d:
        driver = os.path.join(d, "cifX Device Driver")
        card = os.path.join(driver, "1280100_12345")
        os.makedirs(os.path.join(card, "Channel0"))
        nwid = os.path.join(d, "nWid")
        os.makedirs(nwid)
        shutil.copy2(BAT, os.path.join(nwid, "UpdateCardV4.bat"))
        _prepare(nwid)
        rc, out = _run(nwid, driver)
        assert "One Hilscher Card folder" in out and "COPY SUCCESSFUL" in out, out
        assert open(os.path.join(nwid, "card.txt")).read().strip() == "1280100_12345"
        assert os.path.exists(os.path.join(card, "Channel0", "config.nxd")) and os.path.exists(os.path.join(card, "Channel0", "nwid.nxd"))
        assert not os.path.exists(os.path.join(nwid, "config.nxd")), "the local copies are deleted after a successful copy"
        # the second run: the remembered card is reported and used
        _prepare(nwid)
        rc, out = _run(nwid, driver)
        assert "found - the card remembered in card.txt" in out and "COPY SUCCESSFUL" in out, out
        assert "One Hilscher Card folder" not in out
        # the remembered card gone: the normal workflow (none found here) runs
        shutil.rmtree(card)
        _prepare(nwid)
        rc, out = _run(nwid, driver)
        assert "is not present" in out and 'No folders starting with "1280100_"' in out, out
        assert rc == 1


if __name__ == "__main__":
    test_remembered_card()
    print("ok")
