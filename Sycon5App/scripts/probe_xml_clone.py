"""Can a station be cloned in the XML alone (user 2026-10-25: "adding one station per type, saving and closing sycon;
doing the cloning + other parameters assignment (i see profinet name) in the .xml")? The device element and its DTM
blob are copied with the name, the IP and the GUIDs patched in place (same lengths); the CONTROLLER's blob - which
holds a DTMProxy stream and a DeviceList entry per station - is left alone. Then SYCON.net opens the project: does
the clone show in the netProject tree, in the controller's Device Table, and does a save give it a DTMProxy stream?
On a copy of spike/scratch/_probe_canvas/Probe.spj (a controller and two AL1202). Nothing of the user's touched.
Usage (from Sycon5App, the repo venv):  python -I scripts\\probe_xml_clone.py"""
import io
import os
import re
import shutil
import sys
import time
import uuid

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

import olefile                                    # noqa: E402
from sycon5 import SyconDriver                    # noqa: E402
from sycon5.controller import ControllerDialog    # noqa: E402
from sycon5.readback import read_project          # noqa: E402
from sycon5.session import log                    # noqa: E402

SRC = os.path.join(APP, "spike", "scratch", "_probe_canvas")
DST = os.path.join(APP, "spike", "scratch", "_probe_xmlclone")
SOURCE_NO, CLONE_NO = "al1202-001", "al1202-002"          # equal lengths: the blob strings are patched in place
DEV_BLOCK = re.compile(r'(<BusLine>\s*<PositionRect[^>]*/>\s*<Device [^>]*deviceNo="%s"[^>]*>.*?</Device>\s*</BusLine>)', re.S)


def proxies(blob_hex):
    ole = olefile.OleFileIO(io.BytesIO(bytes.fromhex(blob_hex)[4:]))
    return sorted("/".join(e) for e in ole.listdir() if "DTMProxy" in "/".join(e))


def patch_utf16(blob, old, new):
    o, n = old.encode("utf-16-le"), new.encode("utf-16-le")
    assert len(o) == len(n)
    count = blob.count(o)
    return blob.replace(o, n), count


shutil.rmtree(DST, ignore_errors=True)
shutil.copytree(SRC, DST)
spj = os.path.join(DST, "Probe.spj")
xml = os.path.join(DST, "Probe", "_S129", "SYCON_net.xml")
text = open(xml, encoding="utf-8").read()
m = DEV_BLOCK.search(text % SOURCE_NO if "%s" in DEV_BLOCK.pattern else text) if False else re.search(DEV_BLOCK.pattern % re.escape(SOURCE_NO), text, re.S)
assert m, "source block not found"
block = m.group(1)
# the blob of the source: its name, IP and GUIDs
hexblob = re.search(r'<BinData[^>]*>([0-9a-fA-F]+)</BinData>', block).group(1)
blob = bytes.fromhex(hexblob)
p = read_project(xml)
src = p.device(SOURCE_NO)
src_ip = src.ip
clone_ip = src_ip.rsplit(".", 1)[0] + "." + str(int(src_ip.rsplit(".", 1)[1]) + 1)
assert len(clone_ip) == len(src_ip)
blob2, n_name = patch_utf16(blob, SOURCE_NO, CLONE_NO)
blob2, n_ip = patch_utf16(blob2, src_ip, clone_ip)
systemtag = re.search(r'systemtag="([^"]+)"', block).group(1)
new_tag = str(uuid.uuid4())
inner = sorted(set(re.findall(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", blob2)))
inner16 = sorted(set(re.findall("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", blob2.decode("utf-16-le", "replace"))))
log("source blob: %d bytes, name x%d, ip x%d, ascii GUIDs %s, utf16 GUIDs %s" % (len(blob), n_name, n_ip, inner, inner16))
for g in inner:
    blob2 = blob2.replace(g, str(uuid.uuid4()).encode())
for g in inner16:
    blob2, _n = patch_utf16(blob2, g, str(uuid.uuid4()))
clone = block.replace('deviceNo="%s"' % SOURCE_NO, 'deviceNo="%s"' % CLONE_NO).replace(systemtag, new_tag).replace(hexblob, blob2.hex())
# the clone right after the source's block, its box 60 px lower
clone = re.sub(r'<PositionRect top="(\d+)" left="(\d+)" bottom="(\d+)" right="(\d+)"/>',
               lambda r: '<PositionRect top="%d" left="%s" bottom="%d" right="%s"/>' % (int(r.group(1)) + 60, r.group(2), int(r.group(3)) + 60, r.group(4)), clone)
text = text[:m.end()] + "\n" + clone + text[m.end():]
open(xml, "w", encoding="utf-8", newline="").write(text)
ctrl_hex = re.search(r'devicekind="HIL_MASTER"[^>]*>\s*<PositionRect[^>]*/>\s*<BinData[^>]*>([0-9a-fA-F]+)</BinData>', text, re.S).group(1)
log("controller blob before: %d DTMProxy streams" % len(proxies(ctrl_hex)))
p = read_project(xml)
log("read-back before SYCON.net: devices %s; controller lists %s" % ([d.device_no for d in p.devices], p.controller.network))

d = SyconDriver()
try:
    d.open(spj)
    s = d.session
    log("tree:", [n for n in s.nodes() if "<" in n])
    dlg = ControllerDialog(s, d.controller_station())
    try:
        rows = dlg.device_rows(max_rows=6)
        log("Device Table rows:", [(n, name) for n, _y, name in rows])
    finally:
        dlg.close(keep=False)
    # does an OK of the controller dialog make the controller take the new child in?
    dlg = ControllerDialog(s, d.controller_station())
    try:
        dlg.select_page("Device Table")
        dlg.ok()
    except Exception as ex:  # noqa: BLE001
        log("OK on the controller dialog:", ex)
        if dlg.is_open():
            dlg.close(keep=False)
    dlg = ControllerDialog(s, d.controller_station())
    try:
        rows = dlg.device_rows(max_rows=6)
        log("Device Table rows after an OK:", [(n, name) for n, _y, name in rows])
    finally:
        dlg.close(keep=False)
    d.save(xml)
    time.sleep(2.0)
finally:
    log("close:", d.close())
text = open(xml, encoding="utf-8").read()
ctrl_hex = re.search(r'devicekind="HIL_MASTER"[^>]*>\s*<PositionRect[^>]*/>\s*<BinData[^>]*>([0-9a-fA-F]+)</BinData>', text, re.S).group(1)
log("controller blob after the save: %d DTMProxy streams" % len(proxies(ctrl_hex)))
p = read_project(xml)
log("read-back after SYCON.net: devices %s; controller lists %s" % ([d.device_no for d in p.devices], p.controller.network))
