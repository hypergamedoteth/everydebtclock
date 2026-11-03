#!/usr/bin/env python3
"""Quarterly re-base of the Eurostat-sourced places (see PLACES: Germany, France, Italy, Spain, Netherlands, Belgium, Austria, Ireland, Poland, Sweden) from Eurostat's official dissemination API,
table gov_10q_ggdebt "Quarterly government debt" (national accounts, Maastricht definition, million euro, or million national currency for Poland and Sweden; quarter-end).

Series used per country:
  sector S1311 (central government), na_item GD  <- the ticking hero: consolidated gross debt of central government
  sector S13   (general government), na_item GD  <- shown as a fact (all levels of government)
  sector S1311, na_item F2, F31, F32, F41, F42   <- the breakdown by instrument; it must add up to the S1311 total
Also refreshes the population (demo_pjan, population on 1 January) if a newer year is published.
The trend is the official change over the latest four quarters.

Rule: never invent a number. Any fetch error, a missing series, a breakdown that doesn't add up, a gap in the quarters or data older
than what the file already has leaves that place's JSON untouched (exit 0 so the rest of the daily run continues).
"""
import json, os, re, sys, calendar, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
PLACES = {"germany": "DE", "france": "FR", "italy": "IT", "spain": "ES", "netherlands": "NL", "belgium": "BE", "austria": "AT", "ireland": "IE",
          "poland": "PL", "sweden": "SE", "denmark": "DK", "czechia": "CZ", "romania": "RO", "portugal": "PT", "finland": "FI", "hungary": "HU",
          "greece": "EL", "slovakia": "SK", "slovenia": "SI", "croatia": "HR", "lithuania": "LT"}
NAC = {"PL", "SE", "DK", "CZ", "RO", "HU"}   # reported in national currency (MIO_NAC: zloty, krona, krone, koruna, leu); the rest are euro (MIO_EUR)
CONSOLIDATION = {"NL", "IE", "CZ", "RO", "PT", "HU", "EL", "SK"}   # central government debt can exceed the general government total (intra-government holdings netted only in S13)
PARTS = [("F2", "Currency and deposits", "Deposits"), ("F31", "Short-term debt securities", "Debt securities"),
         ("F32", "Long-term debt securities", "Debt securities"), ("F41", "Short-term loans", "Loans"), ("F42", "Long-term loans", "Loans")]
M = 1_000_000

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 everydebtclock.com", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read().decode("utf-8"))

def cells(d):
    """JSON-stat -> {(dim values...): value} keyed by dict of dimension ids."""
    ids, sizes = d["id"], d["size"]
    cats = {k: {v: kk for kk, v in d["dimension"][k]["category"]["index"].items()} for k in ids}
    out = []
    for pos, val in d["value"].items():
        p, c = int(pos), {}
        for k, s in zip(reversed(ids), reversed(sizes)):
            c[k] = cats[k][p % s]; p //= s
        out.append((c, val))
    return out

def qend(k):  # "2026-Q2" -> 2026-06-30
    m = re.fullmatch(r"(\d{4})-Q([1-4])", k)
    if not m: raise RuntimeError(f"bad quarter key {k!r}")
    y, q = int(m.group(1)), int(m.group(2)); mo = q * 3
    return f"{y:04d}-{mo:02d}-{calendar.monthrange(y, mo)[1]:02d}"

def fetch_debt():
    items = "&".join("na_item=" + n for n in ["GD"] + [x[0] for x in PARTS])
    ser = {}
    for unit, grp in (("MIO_EUR", [g for g in PLACES.values() if g not in NAC]), ("MIO_NAC", sorted(NAC))):
        geos = "&".join("geo=" + g for g in grp)
        url = f"{API}gov_10q_ggdebt?format=JSON&lang=EN&{geos}&sector=S1311&sector=S13&unit={unit}&{items}&sinceTimePeriod=2024-Q1"
        for c, v in cells(get(url)):
            ser[(c["geo"], c["sector"], c["na_item"], c["time"])] = v
    return ser

def rebase(p, geo, ser):
    q = sorted({t for (g, s, n, t) in ser if g == geo and s == "S1311" and n == "GD"})
    need = [("S1311", "GD"), ("S13", "GD")] + [("S1311", n) for n, _, _ in PARTS]
    q = [t for t in q if all((geo, s, n, t) in ser for s, n in need)]
    if len(q) < 9: raise RuntimeError(f"need 9 complete quarters, got {len(q)}")
    q = q[-9:]
    for a, b in zip(q, q[1:]):  # no gaps
        ya, qa = int(a[:4]), int(a[6]); nxt = f"{ya + (qa == 4)}-Q{qa % 4 + 1}"
        if nxt != b: raise RuntimeError(f"gap in quarters between {a} and {b}")
    last, prior = q[-1], q[-5]
    v = lambda t, s, n: int(round(ser[(geo, s, n, t)] * M))   # million with one decimal -> whole currency unit (exact to 100k)
    sym = p["currency"]["symbol"]
    tot = v(last, "S1311", "GD")
    if abs(sum(v(last, "S1311", n) for n, _, _ in PARTS) - tot) > 1 * M: raise RuntimeError("instruments do not add up to the total")
    if v(last, "S13", "GD") < tot and geo not in CONSOLIDATION: raise RuntimeError("general government debt below central government debt")
    c = p["components"][0]; as_of = qend(last)
    if as_of < c["as_of"]: raise RuntimeError(f"Eurostat quarter {as_of} older than file {c['as_of']}")
    c.update(value=tot, as_of=as_of, prior_value=v(prior, "S1311", "GD"), prior_as_of=qend(prior),
             history=[[qend(t), v(t, "S1311", "GD")] for t in q])
    c["breakdown"] = [{"label": lab, "value": v(last, "S1311", n), "group": g} for n, lab, g in PARTS if v(last, "S1311", n)]
    EXC = next((n for n in (json.load(open(os.path.join(ROOT, "places", "czechia.json"))).get("notes", [])) if n.startswith("Why central government can exceed")), None)
    if EXC:   # the explanation is on the page exactly when the central government figure is the larger one
        p["notes"] = [n for n in p.get("notes", []) if n != EXC] + ([EXC] if tot > v(last, "S13", "GD") else [])
    for f in c.get("facts", []):
        if f.get("key") == "gg":
            gg, gg0 = v(last, "S13", "GD"), v(prior, "S13", "GD")
            f.update(value=gg, as_of=as_of)
            f["note"] = (f["note"].split(" A year earlier")[0].strip() + f" A year earlier ({qend(prior)}) it was {sym}{gg0 / 1e9:,.1f} billion. "
                         + (f"Central government is {100 * tot / gg:.1f}% of it." if tot <= gg else
                            "Central government debt here is larger than the general government total because the general government figure nets out debt held between government units, which the central government figure does not."))
    y, qq = int(last[:4]), int(last[6]); ny, nq = (y + (qq == 4), qq % 4 + 1)
    p["next_update"] = (f"The Q{nq} {ny} quarter-end figure is expected from Eurostat roughly three months after the quarter ends; "
                        "this page re-bases to it automatically on the next daily build after it appears.")
    return p

def fetch_pop():
    """Population on 1 January: demo_pjan (final), then demo_gind indicator JAN (published sooner, later years are provisional/estimated).
    Returns {(geo, year): (value, table)}; a year from demo_pjan wins over the same year from demo_gind."""
    geos = "&".join("geo=" + g for g in PLACES.values())
    out = {}
    for c, v in cells(get(f"{API}demo_gind?format=JSON&lang=EN&{geos}&indic_de=JAN&sinceTimePeriod=2025")):
        out[(c["geo"], c["time"])] = (int(v), "demo_gind")
    for c, v in cells(get(f"{API}demo_pjan?format=JSON&lang=EN&{geos}&age=TOTAL&sex=T&unit=NR&sinceTimePeriod=2025")):
        out[(c["geo"], c["time"])] = (int(v), "demo_pjan")
    return out

def main():
    try: ser = fetch_debt()
    except Exception as e:
        print("eurostat: not updated:", e); return 0
    try: pops = fetch_pop()
    except Exception as e:
        pops = {}; print("eurostat: population not refreshed:", e)
    for slug, geo in PLACES.items():
        path = os.path.join(ROOT, "places", f"{slug}.json")
        if not os.path.exists(path): continue
        p = json.load(open(path))
        try:
            new = rebase(json.loads(json.dumps(p)), geo, ser)
            ys = sorted(int(t) for (g, t) in pops if g == geo)
            if ys and f"{ys[-1]}-01-01" >= new["population"]["as_of"]:
                v_, tab = pops[(geo, str(ys[-1]))]; pop = new["population"]
                pop["value"] = v_; pop["as_of"] = f"{ys[-1]}-01-01"
                nm = pop["source_name"].split(" (demo_")[0].rstrip()
                pop["source_name"] = (f"Eurostat, Population on 1 January by age and sex (demo_pjan), {p['name']}" if tab == "demo_pjan" else
                                      f"Eurostat, Population change, population on 1 January (demo_gind), {p['name']} (provisional)")
                pop["source_url"] = f"https://ec.europa.eu/eurostat/databrowser/view/{tab}/default/table"
                pop["method_short"] = "Eurostat population on 1 January, the latest published" + (" (provisional estimate)" if tab == "demo_gind" else "")
        except Exception as e:
            print(f"{slug}: not updated:", e); continue
        if new != p:
            json.dump(new, open(path, "w"), indent=1, ensure_ascii=False); open(path, "a").write("\n")
            c = new["components"][0]; sy = new["currency"]["symbol"]; print(f"{slug}: {c['as_of']} {sy}{c['value']:,} (prior {c['prior_as_of']} {sy}{c['prior_value']:,})")
        else: print(f"{slug}: unchanged")
    return 0

if __name__ == "__main__": sys.exit(main())
