"""Print the parameter records of one slave from a saved SYCON_net.xml (the DTM blob's STLRecordParamDataMap).

Usage:  python -I scripts/read_records.py <SYCON_net.xml> <deviceNo>
"""
import sys, re, io, olefile
xml = open(sys.argv[1], encoding="utf-8", errors="replace").read()
want = sys.argv[2]
for m in re.finditer(r'<Device\b[^>]*deviceNo="([^"]*)"[^>]*>.*?<BinData[^>]*>([0-9a-fA-F]+)</BinData>', xml, re.S):
    if m.group(1) != want:
        continue
    ole = olefile.OleFileIO(io.BytesIO(bytes.fromhex(m.group(2))[4:]))
    for s in ole.listdir():
        p = "/".join(s)
        if "STLRecordParamDataMap" in p and p.endswith("PNIORecordParamDataBasic"):
            data = ole.openstream(s).read()
            print(p, "|", len(data), "bytes |", data.hex(" "))
    ole.close()
