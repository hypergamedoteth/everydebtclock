#!/usr/bin/env python3
"""Quarterly re-base of places/ghana.json from the Ministry of Finance of Ghana "Public Debt Statistical Bulletin" (quarterly PDF): Table 1 "Public Debt Dynamics"
gives total public debt (external + domestic, central government) in GH¢ billion for four quarter-ends, including the same quarter a year earlier.
The latest bulletin is found from the Ministry's bulletin page. Never invents a number: external + domestic must equal the total, otherwise the file is left untouched (exit 0)."""
import re, sys
from place_util import *

PAGE = "https://www.mofep.gov.gh/public-debt/quarterly-public-debt-statistics-bulletin"
BASE = "https://www.mofep.gov.gh"
B = 10**9
QEND = {"1": (3, 31), "2": (6, 30), "3": (9, 30), "4": (12, 31)}

def build(p):
    h = get(PAGE, ua=BROWSER_UA)
    links = re.findall(r'href="([^"]*Debt-Statistics-Bulletin-(\d{4})-Q([1-4])[^"]*\.pdf)"', h, re.I)
    if not links: raise RuntimeError("no bulletin links found")
    href, yr, q = max(links, key=lambda x: (int(x[1]), int(x[2])))
    url = href if href.startswith("http") else BASE + href
    t = pdf_text(get(url, ua=BROWSER_UA, raw=True))
    i = t.rfind("Table 1: Public Debt Dynamics")
    if i < 0: raise RuntimeError("Table 1 not found")
    blk = t[i:i + 2500]
    cols = re.findall(r"Q([1-4])-(\d{4})", blk.split("Total Public Debt")[0])
    def row(label):
        m = re.search(r"^\s*" + label + r"\s+(.*)$", blk, re.M)
        if not m: raise RuntimeError(f"row {label!r} missing")
        return [float(x) for x in re.findall(r"(?<![\d.])(\d{2,4}\.\d{2})(?![\d%])", m.group(1))]
    tot, ext, dom = row("Total Public Debt"), row("External Debt"), row("Domestic Debt")
    if not cols or len(tot) != len(cols): raise RuntimeError("column/row mismatch")
    series = {}
    for (qq, yy), v in zip(cols, tot):
        mo, dd = QEND[qq]; series[f"{yy}-{mo:02d}-{dd:02d}"] = v * B
    if abs(ext[-1] + dom[-1] - tot[-1]) > 0.03: raise RuntimeError("external + domestic != total")
    p = rebase(p, series, tol_days=45, keep_months=14)
    c = p["components"][0]; c["source_url"] = url
    c["breakdown"] = [{"label": "Domestic debt", "value": int(dom[-1] * B), "group": "Domestic"}, {"label": "External debt", "value": int(ext[-1] * B), "group": "External"}]
    p["next_update"] = "The Ministry of Finance publishes each quarter's Public Debt Statistical Bulletin about two to three months after the quarter ends; this page re-bases to it automatically on the next daily build after it appears."
    return p

if __name__ == "__main__": sys.exit(run("ghana", build))
