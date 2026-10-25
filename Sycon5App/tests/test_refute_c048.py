"""C-048 refute round 1 (2026-10-26): the process-data export reader attacked with encodings and odd display names,
`verify_exports` with an empty export, the shipped UpdateCardV5.bat with two cards and no one at the keyboard. What
broke and was fixed: with two card folders and no input the bat looped on its prompt forever (an unattended run) -
an empty choice now ends it with exit code 1 and nothing copied. What held: UTF-16 with and without a BOM and UTF-8
read alike, a display name without `<station>` comes back whole, an empty export fails every check, a remembered
card is used without a prompt even with two cards present."""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
from sycon5 import consumer, exports  # noqa: E402
from sycon5.handoff import Handoff  # noqa: E402

BAT = os.path.join(os.path.dirname(APP), "Shared", "HardwareConfigBuilderData", "nWid", "UpdateCardV5.bat")
BODY = ('<ProcessData><Controller displayName="CIFX_RE_PNM[CIFX RE/PNM]&lt;n0001&gt;"><Channel>'
        '<Device displayName="A[T]&lt;n0002&gt;"/><Device displayName="plain name"/>'
        '<Device displayName="x&lt;y[T]&lt;n0003&gt;"/><Device displayName="open&lt;n0004"/></Channel></Controller></ProcessData>')


def test_the_export_reads_alike_in_every_encoding(tmp_path):
    for enc, decl in (("utf-16", "UTF-16"), ("utf-16-le", "UTF-16"), ("utf-8", "UTF-8")):
        path = str(tmp_path / ("%s.xml" % enc))
        open(path, "wb").write(('<?xml version="1.0" encoding="%s"?>' % decl + BODY).encode(enc))
        ctrl, devices = exports.process_data_devices(path)
        assert exports.station_of(ctrl) == "n0001"
        assert [exports.station_of(d) for d in devices] == ["n0002", "plain name", "n0003", "open<n0004"], enc


def test_an_empty_export_fails_every_check(tmp_path):
    path = str(tmp_path / "HilscherIO.xml")
    open(path, "wb").write(b'<?xml version="1.0"?><ProcessData/>')
    assert exports.process_data_devices(path) == ("", [])
    h = Handoff(folder=str(tmp_path), controller={"station_name": "c"}, stations=[{"station_name": "n0002"}, {"station_name": "n0003"}])
    v = consumer.Verification()
    consumer.verify_exports(v, h, path, str(tmp_path / "config.nxd"))
    assert v.failed == 5 and v.ok == 0, v.report()


def fake_driver(tmp_path, serials):
    driver = os.path.join(str(tmp_path), "cifX Device Driver")
    for s in serials:
        os.makedirs(os.path.join(driver, s, "Channel0"))
    nwid = os.path.join(str(tmp_path), "nWid")
    os.makedirs(nwid)
    shutil.copy2(BAT, os.path.join(nwid, "UpdateCardV5.bat"))
    for name in ("config.nxd", "config_nwid.nxd"):
        open(os.path.join(nwid, name), "wb").write(b"nxd " + name.encode())
    return driver, nwid


def run_bat(nwid, driver):
    env = dict(os.environ, CIFX_DRIVER_PATH=driver)
    r = subprocess.run(["cmd", "/c", os.path.join(nwid, "UpdateCardV5.bat")], cwd=nwid, env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout


def test_two_cards_and_nobody_at_the_keyboard_ends_without_copying(tmp_path):
    driver, nwid = fake_driver(tmp_path, ("1280100_11111", "1280100_22222"))
    rc, out = run_bat(nwid, driver)
    assert rc == 1 and "Multiple folders" in out and "No choice entered" in out, out
    assert out.count("Insert choice") == 1, "one prompt, no loop"
    for s in ("1280100_11111", "1280100_22222"):
        assert os.listdir(os.path.join(driver, s, "Channel0")) == []
    assert not os.path.exists(os.path.join(nwid, "card.txt"))


def test_a_remembered_card_is_used_without_a_prompt_even_with_two_cards(tmp_path):
    driver, nwid = fake_driver(tmp_path, ("1280100_11111", "1280100_22222"))
    open(os.path.join(nwid, "card.txt"), "w").write("1280100_22222\n")
    rc, out = run_bat(nwid, driver)
    assert rc == 0 and "the card remembered in card.txt" in out and "Insert choice" not in out and "COPY SUCCESSFUL" in out, out
    assert sorted(os.listdir(os.path.join(driver, "1280100_22222", "Channel0"))) == ["config.nxd", "nwid.nxd"]
    assert os.listdir(os.path.join(driver, "1280100_11111", "Channel0")) == []


def test_a_stale_remembered_card_falls_back_to_the_prompt(tmp_path):
    driver, nwid = fake_driver(tmp_path, ("1280100_11111", "1280100_22222"))
    open(os.path.join(nwid, "card.txt"), "w").write("1280100_99999\n")
    rc, out = run_bat(nwid, driver)
    assert rc == 1 and "is not present" in out and "Multiple folders" in out and "No choice entered" in out, out
    assert open(os.path.join(nwid, "card.txt")).read().strip() == "1280100_99999", "nothing chosen, nothing remembered"
