"""Minimal .xlsx reader (stdlib only): the Swiss and Australian workbooks break openpyxl (missing drawing parts), and the daily build installs nothing."""
import zipfile,re,sys
import xml.etree.ElementTree as ET
NS={"m":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
def read(path):
    return read_bytes(path)

def read_bytes(path):
    import io
    z=zipfile.ZipFile(io.BytesIO(path) if isinstance(path, (bytes, bytearray)) else path)
    ss=[]
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si",NS):
            ss.append("".join(t.text or "" for t in si.iter("{%s}t"%NS["m"])))
    wb=ET.fromstring(z.read("xl/workbook.xml"))
    rels=ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rid={r.get("Id"):r.get("Target") for r in rels}
    out={}
    for s in wb.find("m:sheets",NS):
        t=rid[s.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")]
        t=t.lstrip("/"); t=t if t.startswith("xl/") else "xl/"+t
        rows=[]
        for r in ET.fromstring(z.read(t)).iter("{%s}row"%NS["m"]):
            row={}
            for c in r.findall("m:c",NS):
                col=re.match(r"[A-Z]+",c.get("r")).group(0)
                v=c.find("m:v",NS); 
                if v is None:
                    is_=c.find("m:is",NS)
                    val="".join(t.text or "" for t in is_.iter("{%s}t"%NS["m"])) if is_ is not None else None
                elif c.get("t")=="s": val=ss[int(v.text)]
                else: val=v.text
                row[col]=val
            rows.append((int(r.get("r")),row))
        out[s.get("name")]=rows
    return out
