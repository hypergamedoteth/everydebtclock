#!/usr/bin/env python3
"""Monthly re-base of places/turkey.json from the Turkish Ministry of Treasury and Finance (Hazine ve Maliye Bakanlığı) monthly release
"Central Government Debt Stock as of <date>" (en.hmb.gov.tr, WordPress REST API, billion Turkish lira, month-end).
Each release says: "Central government debt stock was TL X billion as of <Month> <day>, <year>. TL A billion ... local currency and TL B
billion ... foreign currencies." The trend is the official change over the latest twelve months. Never invents a number; on any error the
file is left untouched (exit 0).
"""
import re, sys, json
from place_util import *

API = "https://en.hmb.gov.tr/portal/v2/posts?search=Central%20Government%20Debt%20Stock&per_page=20&orderby=date&order=desc&_fields=slug,date,link,content"
RX = re.compile(r"debt stock was TL\s*([\d,.]+)\s*billion as of\s*([A-Za-z]+)\s*(\d{1,2})\s*(?:st|nd|rd|th)?\s*,?\s*(\d{4})\.?\s*"
                r"TL\s*([\d,.]+)\s*billion of the debt stock is denominated in local currency and TL\s*([\d,.]+)\s*billion is denominated in foreign", re.S | re.I)
B = 10**9

def parse():
    out = {}
    for post in json.loads(get(API)):
        t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", post["content"]["rendered"] if isinstance(post["content"], dict) else post["content"]))
        m = RX.search(t)
        if not m: continue
        mon = MONTHS.index(m.group(2).capitalize()) + 1; y = int(m.group(4)); day = int(m.group(3))
        date = f"{y:04d}-{mon:02d}-{day:02d}"
        tot, loc, fx = (float(m.group(i).replace(",", "")) for i in (1, 5, 6))
        if abs(loc + fx - tot) > 0.3: continue            # the two parts must add up to the total (rounded to 0.1 billion)
        out[date] = (tot, loc, fx, post.get("link") or "")
    return out

def build(p):
    s = parse()
    if len(s) < 13: raise RuntimeError(f"need 13 monthly releases, got {len(s)}")
    p = rebase(p, {a: v[0] * B for a, v in s.items()}, tol_days=10, hist_monthly=False)
    last = max(s); tot, loc, fx, link = s[last]; c = p["components"][0]
    if link.startswith("https://"): c["source_url"] = link
    c["breakdown"] = [{"label": "Domestic debt (Turkish lira)", "value": int(round(loc * B)), "group": "Currency"},
                      {"label": "Foreign-currency debt (converted to lira)", "value": int(round(fx * B)), "group": "Currency"}]
    for f in c.get("facts", []):
        if f.get("key") == "fxshare": f.update(value=round(100 * fx / tot, 2), as_of=last, kind="pct")
    y, m = int(last[:4]), int(last[5:7]); ny, nm = (y + (m == 12), m % 12 + 1)
    p["next_update"] = (f"The {MONTHS[nm - 1]} {ny} month-end figure is expected from the Ministry of Treasury and Finance around the 20th of the following month; "
                        "this page re-bases to it automatically on the next daily build after it appears.")
    return p

if __name__ == "__main__": sys.exit(run("turkey", build))
