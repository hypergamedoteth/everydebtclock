#!/usr/bin/env python3
"""Re-base of places/indonesia.json from the Ministry of Finance's Directorate General of Budget Financing and Risk Management (DJPPR) website:
the home page's "Posisi Utang Pemerintah, Per <date>" panel (central government debt position: government securities (SBN) + loans, IDR trillion),
read from the site's own page API (https://api-djppr.kemenkeu.go.id/web/api/v1/page?url=beranda). The page shows only the latest position, so earlier
official positions are kept in the file's history and each new one is appended; the trend is the change over the closest stored point to twelve months earlier.
Never invents a number; any error leaves the file untouched (exit 0)."""
import re, sys, json
from place_util import *

API = "https://api-djppr.kemenkeu.go.id/web/api/v1/page?url=beranda"
ID = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
T = 10**12
def num(s): return float(s.strip().replace(".", "").replace(",", "."))

def build(p):
    d = json.loads(get(API))["Data"]["PageContentLive"]
    d = d.replace('\\"', '"')
    m = re.search(r'"text":"Per (\d{1,2}) ([A-Za-z]+) (\d{4})"', d)
    if not m or m.group(2) not in ID: raise RuntimeError("DJPPR: date label not found")
    date = f"{int(m.group(3)):04d}-{ID.index(m.group(2)) + 1:02d}-{int(m.group(1)):02d}"
    after = d[m.end():]
    tot = re.search(r'"htmlContent":"<p><sup>Rp</sup>([\d.,]+)</p>', after)
    sbn = re.search(r'"@point1":"Surat Berharga Negara \(SBN\)","@nominal-point1":"<p><sup>Rp</sup>([\d.,]+)</p>', after)
    loan = re.search(r'"@point2":"Pinjaman","@nominal-point2":"<p><sup>Rp</sup>([\d.,]+)</p>', after)
    ratio = re.search(r"Debt to GDP: ([\d,]+)\s*%", after)
    if not (tot and sbn and loan): raise RuntimeError("DJPPR: amounts not found")
    t, s, l = num(tot.group(1)), num(sbn.group(1)), num(loan.group(1))
    if abs(s + l - t) > 0.05 or not (5000 < t < 30000): raise RuntimeError(f"DJPPR: implausible amounts {t} {s} {l}")
    p = rebase(p, {date: t * T}, tol_days=40, keep_months=30)
    c = p["components"][0]
    c["breakdown"] = [{"label": "Government securities (SBN)", "value": int(s * T), "group": "Securities"}, {"label": "Loans (Pinjaman)", "value": int(l * T), "group": "Loans"}]
    for f in c.get("facts", []):
        if f["key"] == "pctgdp" and ratio: f.update(value=num(ratio.group(1)), as_of=date, kind="pct")
    p["next_update"] = ("DJPPR updates this position after each quarter-end, usually within about six weeks; "
                        "this page picks it up automatically on the next daily build after it appears.")
    return p

if __name__ == "__main__": sys.exit(run("indonesia", build))
