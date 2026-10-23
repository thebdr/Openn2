"""Read a saved SYCON.net project back: `<name>\\_S129\\SYCON_net.xml`, one `<Device>` per node whose `<BinData>`
hex blob (after a 4-byte length) is an OLE compound file with the DTM's persisted data:
  PNIODeviceDataModelBasic                      station name, type, IP, mask, gateway, GSDML path (UTF-16 strings)
  STLModuleMap/<slot>/PNIOModuleBasic          the module of a slot (id text, name)
  STLModuleMap/<slot>/STLSubModuleMap/<sub>/PNIOSubModuleBasic   a submodule (id text, name) - an AL1202's
                                                `8 Ports` module holds `IO-Link Master` in sub 1 and its ports after
  STLModuleMap/<slot>/STLSubModuleMap/<sub>/STLRecordParamDataMap/<index>/PNIORecordParamDataBasic
                                                a parameter record: after the marker 11 20 <len u32> its bytes
The controller's blob also lists every slave (name + IP) in FdtChannelColl/PROFINET_IO/SlaveDTMsGetParameters.
This is the verification oracle of every driver operation.
"""
import io
import re
from dataclasses import dataclass, field

import olefile
import xml.etree.ElementTree as ET

UTF16_RUN = re.compile(rb"(?:[\x20-\x7e]\x00){3,}")
IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
RECORD_MARKER = b"\x11\x20"


@dataclass
class Device:
    device_no: str
    symbolic: str
    prog_id: str
    gsdml: str
    name: str = ""
    ip: str = ""
    mask: str = ""
    gateway: str = ""
    type_name: str = ""
    dap: str = ""                                  # the DAP id text of slot 0 (`DAP V2.1 X2`, `DIM ST V4.2`, `DIM 1`)
    order_no: str = ""                             # the DAP's order number (`6ES7 158-3AD00-0XA0`, `AL1202`)
    slots: dict = field(default_factory=dict)      # slot -> module name
    submodules: dict = field(default_factory=dict) # (slot, subslot) -> submodule name (the DAP's 0x8000+ ones too)
    records: dict = field(default_factory=dict)    # (slot, subslot, index) -> bytes
    network: list = field(default_factory=list)    # controller only: [(name of station, ip)]
    timing: dict = field(default_factory=dict)     # controller only: name of station -> (update ms, watchdog ms)

    @property
    def is_controller(self):
        return "Controller" in self.prog_id


@dataclass
class Project:
    path: str
    devices: list

    def device(self, device_no):
        for d in self.devices:
            if d.device_no == device_no:
                return d
        raise KeyError(device_no)

    @property
    def controller(self):
        return [d for d in self.devices if d.is_controller][0]


def _strings(data):
    return [m.decode("utf-16-le", "replace") for m in UTF16_RUN.findall(data)]


def _local(tag):
    return tag.split("}")[-1]


def _attr(el, name):
    for k, v in el.attrib.items():
        if _local(k) == name:
            return v
    return ""


def _record_bytes(data):
    pos = data.find(RECORD_MARKER)
    if pos < 0 or pos + 6 > len(data):
        return b""
    length = int.from_bytes(data[pos + 2:pos + 6], "little")
    return data[pos + 6:pos + 6 + length]


def _parse_blob(dev, hexdata):
    raw = bytes.fromhex(hexdata.strip())
    ole = olefile.OleFileIO(io.BytesIO(raw[4:]))
    try:
        for parts in ole.listdir():
            path = "/".join(parts)
            data = ole.openstream(parts).read()
            if path == "PNIODeviceDataModelBasic":
                strs = _strings(data)
                ips = [s for s in strs if IPV4.match(s)]
                dev.name = strs[0] if strs else ""
                dev.type_name = strs[1] if len(strs) > 1 else ""
                dev.ip, dev.mask, dev.gateway = (ips + ["", "", ""])[:3]
                xmls = [s for s in strs if s.lower().endswith(".xml")]
                if xmls and not dev.gsdml:
                    dev.gsdml = xmls[0]
            elif path.endswith("/PNIOModuleBasic") and path.startswith("STLModuleMap/"):
                slot = int(path.split("/")[1])
                strs = _strings(data)
                dev.slots[slot] = strs[1] if len(strs) > 1 else (strs[0] if strs else "")
                if slot == 0 and strs:
                    dev.dap = strs[0]
                    tail = [s for s in strs[1:] if not GUID.match(s)]
                    dev.order_no = tail[-1] if tail and tail[-1] != dev.slots[0] else ""
            elif path.endswith("/PNIOSubModuleBasic") and path.startswith("STLModuleMap/"):
                p = path.split("/")
                try:
                    key = (int(p[1]), int(p[3]))
                except (IndexError, ValueError):
                    continue
                strs = _strings(data)
                dev.submodules[key] = strs[1] if len(strs) > 1 else (strs[0] if strs else "")
            elif path.endswith("/PNIORecordParamDataBasic") and path.startswith("STLModuleMap/"):
                p = path.split("/")
                try:
                    key = (int(p[1]), int(p[3]), int(p[5]))
                except (IndexError, ValueError):
                    continue
                dev.records[key] = _record_bytes(data)
            elif "SlaveDTMsGetParameters" in path:
                text = data.decode("utf-16-le", "replace") if "nameOfStation".encode("utf-16-le") in data else data.decode("latin-1", "replace")
                pairs = re.findall(r'nameOfStation="([^"]*)"[^>]*ipAddress="([^"]*)"', text)
                dev.network.extend(pairs)
                # one DTMProxy stream per slave: its timing = send clock (x 31.25 us) x reduction ratio, the
                # watchdog that times the factor (sendClockFactor="32" reductionRatio="8" watchdogFactor="3" = 8 / 24 ms)
                m = re.search(r'sendClockFactor="(\d+)"\s+reductionRatio="(\d+)"\s+watchdogFactor="(\d+)"', text)
                if pairs and m:
                    update_ms = int(m.group(1)) * 31.25 / 1000 * int(m.group(2))
                    dev.timing[pairs[0][0]] = (update_ms, update_ms * int(m.group(3)))
    finally:
        ole.close()


def read_project(xml_path):
    """Parse a SYCON_net.xml (or a .spj: its <name>\\_S129\\SYCON_net.xml) into a Project."""
    if xml_path.lower().endswith(".spj"):
        xml_path = xml_path[:-4] + "\\_S129\\SYCON_net.xml"
    tree = ET.parse(xml_path)
    devices = []
    for el in tree.getroot().iter():
        if _local(el.tag) != "Device":
            continue
        dev = Device(device_no=_attr(el, "deviceNo"), symbolic=_attr(el, "symbolicName"), prog_id=_attr(el, "progId"),
                     gsdml=_attr(el, "deviceTypeInformation").split("\\")[-1])
        for child in el:
            if _local(child.tag) == "BinData" and child.text:
                _parse_blob(dev, child.text)
                break
        devices.append(dev)
    return Project(path=xml_path, devices=devices)


def describe(project):
    lines = [project.path]
    for d in project.devices:
        lines.append("  %s%s symbolic=%s type=%r ip=%s mask=%s gsdml=%s dap=%r order=%r" % (
            d.device_no, " (controller)" if d.is_controller else "", d.symbolic, d.type_name, d.ip, d.mask, d.gsdml,
            d.dap, d.order_no))
        for slot in sorted(d.slots):
            lines.append("    slot %d: %s" % (slot, d.slots[slot]))
            for (s, sub), name in sorted(d.submodules.items()):
                if s == slot and sub < 0x8000:
                    lines.append("      sub %d: %s" % (sub, name))
        for key in sorted(d.records):
            lines.append("    record slot %d sub %d index %d: %s" % (key + (d.records[key].hex(" "),)))
        for name, ip in d.network:
            t = d.timing.get(name)
            lines.append("    network: %s %s%s" % (name, ip, " (update %g ms, watchdog %g ms)" % t if t else ""))
    return "\n".join(lines)
