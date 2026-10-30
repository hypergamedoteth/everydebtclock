#!/usr/bin/env python3
"""Monthly re-base of places/south-korea.json from the Ministry of Planning and Budget's (기획예산처) monthly "월간 재정동향" (Monthly Fiscal Trends) PDF,
section "5. 국가채무(중앙정부)": central government debt (중앙정부 채무), KRW trillion with one decimal, annual year-end rows and the current year's month-end rows.
Cross-checks: debt = government bonds + borrowings + Treasury obligations (국채 + 차입금 + 국고채무부담행위). Needs the `pypdf` package (pip install pypdf);
without it the file is left untouched. The trend is the official change over the closest available point to twelve months earlier (history accumulates from each report).
Never invents a number; any error leaves the file untouched (exit 0)."""
import re, sys, io
from place_util import *

BASE = "https://www.mpb.go.kr"
LIST = BASE + "/web/main/bbs/b_0005/list"
T = 10**12
NUM = r"([\d,]+\.\d)"

def latest_pdf():
    h = get(LIST, ua=BROWSER_UA)
    body = h[h.find("<tbody>"):]
    for row in re.findall(r"<tr>(.*?)</tr>", body, re.S):
        if "월간 재정동향" in row:
            links = re.findall(r'href="(/web/main/file/download/uu/[a-f0-9]+)"', row)
            title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", row))
            return title, links
    raise RuntimeError("no 월간 재정동향 row")

def page_texts(pdf):
    import pypdf
    r = pypdf.PdfReader(io.BytesIO(pdf))
    for pg in r.pages: yield pg.extract_text() or ""

def parse(pdf):
    out = {}; ratio = None; d1 = None
    for t in page_texts(pdf):
        if "5. 국가채무(중앙정부)" in t and "중앙정부 채무" in t:
            for line in t.splitlines():
                m = re.match(r"^(20\d\d)(?:\.(\d{1,2}))?\s+" + NUM + r"\s+(?:" + NUM + r"|-)\s+" + NUM + r"\s+" + NUM + r"\s+" + NUM + r"\s+" + NUM + r"\s+" + NUM + r"\s+" + NUM + r"\s*$", line.strip())
                if not m: continue
                y = int(m.group(1)); mo = int(m.group(2)) if m.group(2) else 12
                f = lambda x: float(x.replace(",", ""))
                debt, gdp, bonds, kor, hou, fx, loans, obl = f(m.group(3)), (f(m.group(4)) if m.group(4) else None), f(m.group(5)), f(m.group(6)), f(m.group(7)), f(m.group(8)), f(m.group(9)), f(m.group(10))
                if abs(bonds + loans + obl - debt) > 0.35: raise RuntimeError(f"row {line!r}: components do not add up")
                out[month_end(y, mo)] = dict(debt=debt, gdp=gdp, bonds=bonds, kor=kor, hou=hou, fx=fx, loans=loans, obl=obl)
        if "국가채무(D1)" in t and "일반정부 부채(D2)" in t:
            for line in t.splitlines():
                m = re.match(r"^(20\d\d)\s+" + NUM + r"\s+" + NUM + r"\s*(?:\S.*)?$", line.strip())
                if m: d1 = (m.group(1), float(m.group(2).replace(",", "")), float(m.group(3)))
    if not out: raise RuntimeError("debt table not found")
    return out, d1

def build(p):
    title, links = latest_pdf()
    got = None
    for l in links:
        pdf = get(BASE + l, ua=BROWSER_UA, raw=True)
        if pdf[:4] != b"%PDF": continue
        try: got = parse(pdf)
        except ImportError: raise RuntimeError("pypdf is not installed")
        break
    if not got: raise RuntimeError("no readable PDF in the latest report row")
    tab, d1 = got
    last = max(tab)
    p = rebase(p, {a: v["debt"] * T for a, v in tab.items()}, tol_days=200)
    c = p["components"][0]; v = tab[last]
    c["breakdown"] = [{"label": "Treasury bonds (국고채권)", "value": int(v["kor"] * T), "group": "Government bonds"},
                      {"label": "National housing bonds (국민주택채권)", "value": int(v["hou"] * T), "group": "Government bonds"},
                      {"label": "Foreign exchange stabilisation bonds (외평채권)", "value": int(v["fx"] * T), "group": "Government bonds"},
                      {"label": "Borrowings (차입금)", "value": int(v["loans"] * T), "group": "Borrowings and obligations"},
                      {"label": "Treasury obligations (국고채무부담행위)", "value": int(v["obl"] * T), "group": "Borrowings and obligations"}]
    bsum = sum(b["value"] for b in c["breakdown"])
    other = int(round(v["bonds"] * T)) - sum(b["value"] for b in c["breakdown"][:3])
    if abs(other) > 0.35 * T: raise RuntimeError("bond breakdown does not add up")
    ye = max((a for a in tab if a.endswith("-12-31") and tab[a]["gdp"] is not None), default=None)
    for f in c.get("facts", []):
        if f["key"] == "pctgdp" and ye: f.update(value=tab[ye]["gdp"], as_of=ye, kind="pct")
        if f["key"] == "d1" and d1: f.update(value=int(d1[1] * T), as_of=f"{d1[0]}-12-31", kind="usd",
                                             note=f.get("note", "").split(" The same year")[0] + f" The same year it was {d1[2]}% of GDP.")
    y, m = int(last[:4]), int(last[5:7]); ny, nm = (y + (m == 12), m % 12 + 1)
    p["next_update"] = (f"The {MONTHS[nm - 1]} {ny} month-end figure is expected in the Ministry's Monthly Fiscal Trends about six weeks after the month ends; "
                        "this page re-bases to it automatically on the next daily build after it appears.")
    return p

if __name__ == "__main__": sys.exit(run("south-korea", build))
