#!/usr/bin/env python3
"""Quarterly re-base of places/kenya.json from the National Treasury of Kenya's Quarterly Economic and Budgetary Review (QEBR), the newest report listed on
treasury.go.ke. Its "Public and Publicly Guaranteed Debt" table (KSh million) gives external and domestic debt and the GRAND TOTAL GROSS for nine consecutive
quarter-ends, ending with the quarter just closed (the newest column is provisional, marked *). Never invents a number: the sub-totals must add up to the grand total,
otherwise the file is left untouched (exit 0)."""
import re, sys, urllib.parse
from place_util import *

PAGE = "https://www.treasury.go.ke/quarterly-economic-and-budgetary-review-report"
BASE = "https://www.treasury.go.ke"
M = 10**6

def nums(line): return [int(x.replace(",", "")) for x in re.findall(r"\(?\d[\d,]{4,}\)?", line)]

def build(p):
    h = get(PAGE, ua=BROWSER_UA)
    hrefs = re.findall(r'href="(/sites/default/files/[^"]*QEBR[^"]*\.pdf)"', h, re.I)
    if not hrefs: raise RuntimeError("no QEBR links")
    url = BASE + hrefs[0]                      # the page lists the newest report first
    t = pdf_text(get(url, ua=BROWSER_UA, raw=True))
    m = re.search(r"debt stock as at (?:the )?end (?:of )?(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})", re.sub(r"\s+", " ", t))
    if not m: raise RuntimeError("period not stated")
    last = month_end(int(m.group(3)), MONTHS.index(m.group(2).capitalize()) + 1)
    def row(label):
        r = re.search(r"^\s*" + label + r"\b(.*)$", t, re.M)
        if not r: raise RuntimeError(f"row {label!r} missing")
        return nums(r.group(1))
    tot, ext, dom = row("GRAND TOTAL GROSS"), row("SUB ?[–-] ?TOTAL EXTERNAL"), row("SUB-TOTAL DOMESTIC")
    if not (len(tot) == len(ext) == len(dom) >= 5): raise RuntimeError("column count mismatch")
    if any(abs(e + d_ - x) > 5 for e, d_, x in zip(ext, dom, tot)): raise RuntimeError("external + domestic != grand total")
    series, y, mo = {}, int(last[:4]), int(last[5:7])
    for v in reversed(tot):
        series[month_end(y, mo)] = v * M
        mo -= 3
        if mo < 1: mo += 12; y -= 1
    p = rebase(p, series, tol_days=20, keep_months=14)
    c = p["components"][0]; c["source_url"] = url
    c["breakdown"] = [{"label": "Domestic debt", "value": dom[-1] * M, "group": "Domestic"}, {"label": "External debt", "value": ext[-1] * M, "group": "External"}]
    p["next_update"] = "The National Treasury publishes a Quarterly Economic and Budgetary Review about six weeks after each quarter ends; this page re-bases to it automatically on the next daily build after it appears."
    return p

if __name__ == "__main__": sys.exit(run("kenya", build))
