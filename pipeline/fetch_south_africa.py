#!/usr/bin/env python3
"""Monthly re-base of places/south-africa.json from the South African Reserve Bank (SARB) Quarterly Bulletin statistical table "National government debt, at face value"
(table S-59, series KB406/4114M): national government total gross loan debt in rand million, at fiscal year-end (31 March), calendar year-end and monthly for the
current year. The latest quarterly bulletin and the one four quarters earlier are read (the earlier one supplies the point a year before the latest month).
Never invents a number: each row must add up (domestic + foreign = total gross loan debt), otherwise it is skipped; fewer than the needed rows leaves the file untouched (exit 0)."""
import re, sys, datetime as dt
from place_util import *

HOST = "https://www.resbank.co.za"
PAGE = HOST + "/en/home/publications/publication-detail-pages/quarterly-bulletins/quarterly-bulletin-publications/{y}/{m}"
LINK = re.compile(r'href="([^"]*public(?:%20|-|\s|\.)*finance[^"]*\.pdf)"', re.I)       # file names differ from one bulletin to the next
QMONTHS = ["december", "september", "june", "march"]
M = 10**6
MON3 = {m[:3]: i + 1 for i, m in enumerate(MONTHS)}
DET = {}      # date -> (domestic, foreign) in rand
NUMTOK = re.compile(r"^-?\d{1,3}(?: \d{3})*$")

def table_text(pdf):
    import io
    try:
        import pypdf
        pages = [pg.extract_text() or "" for pg in pypdf.PdfReader(io.BytesIO(pdf)).pages]
    except ImportError:
        pages = pdf_text(pdf).split("\f")
    for t in pages:
        if "(4114M)" in t and "At face value" in t: return t
    raise RuntimeError("table not found")

def parse(t):
    """-> {YYYY-MM-DD: rand} from the face-value table text."""
    out, block, year = {}, None, None
    for line in t.splitlines():
        s = line.strip()
        if s == "31 March": block = 3; continue
        if s == "31 December": block = 12; continue
        if block is None: continue
        if re.match(r"^(KB\d+|\d\s+Including|Ratios of)", s): break
        s = re.sub(r"((?:19|20)\d\d):\s*", r"\1 ", s)        # some bulletins print "2025:" before the month
        toks = re.split(r"\s{2,}", s)
        if len(toks) < 8: continue
        mm = re.search(r"^(.*?)(?:\s+((?:19|20)\d\d))?(?:\s+([A-Z][a-z]{2}))?\s*$", toks[-1])
        numpart, y, mon = mm.group(1), mm.group(2), mm.group(3)
        nums = toks[:-1] + [numpart]
        vals = []
        for n in nums:
            n = n.strip()
            if NUMTOK.match(n): vals.append(int(n.replace(" ", "")))
            elif n in ("...", ""): vals.append(None)
        if y: year = int(y)
        if len(vals) < 7 or None in vals[:7]: continue
        if abs(vals[2] + vals[5] - vals[6]) > 1: continue          # domestic + foreign must equal the total
        if mon:
            if mon not in MON3 or year is None: continue
            date = month_end(year, MON3[mon])
        elif y: date = month_end(int(y), block)
        else: continue
        out[date] = vals[6] * M; DET[date] = (vals[2] * M, vals[5] * M)
    return out

def bulletin(y, m):
    links = LINK.findall(get(PAGE.format(y=y, m=m), ua=BROWSER_UA, timeout=90))
    if not links: raise RuntimeError(f"no public finance table listed for {m} {y}")
    href = links[0]
    return parse(table_text(get(href if href.startswith("http") else HOST + href, ua=BROWSER_UA, raw=True, timeout=90)))

def latest_candidate(today):
    for y in (today.year, today.year - 1):
        for m in QMONTHS:
            mi = MON3[m[:3].capitalize()]
            if y == today.year and mi > today.month: continue
            yield y, m

def build(p):
    today = dt.date.today(); series = {}; found = None
    for y, m in latest_candidate(today):
        try: series = bulletin(y, m); found = (y, m); break
        except Exception as e: last = e
    if not found: raise RuntimeError(f"no readable quarterly bulletin: {last}")
    try: series.update({k: v for k, v in bulletin(found[0] - 1, found[1]).items() if k not in series})
    except Exception as e: print(f"south-africa: bulletin a year earlier not read ({e})")
    if len(series) < 4: raise RuntimeError("too few rows")
    p = rebase(p, series, tol_days=20, keep_months=14, hist_monthly=True)
    c = p["components"][0]
    if c["as_of"] in DET:
        dom, frn = DET[c["as_of"]]
        c["breakdown"] = [{"label": "Domestic debt", "value": dom, "group": "Domestic"}, {"label": "Foreign debt", "value": frn, "group": "External"}]
    p["next_update"] = "The Reserve Bank publishes the Quarterly Bulletin in March, June, September and December; each adds the months since the last one. This page re-bases to it automatically on the next daily build after it appears."
    return p

if __name__ == "__main__": sys.exit(run("south-africa", build))
