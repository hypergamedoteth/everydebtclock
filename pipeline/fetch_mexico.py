#!/usr/bin/env python3
"""Monthly re-base of places/mexico.json from the Banco de México SIE (Sistema de Información Económica), table CG7
"Deuda Neta Total del Sector Público, saldo promedio y final" (official; keyless CSV export of the public table).

Series (month-end balances, thousand million pesos = 10^9 MXN):
  SG193  Deuda Total Neta del Sector Público Económico Amplio   <- the ticking hero (net, broad public sector)
  SG194  of which internal (Deuda Interna Neta)                  <- breakdown
  SG195  of which external (Deuda Externa Neta)                  <- breakdown
  SG199  Deuda Total Neta del Sector Público Consolidado con el Banco de México   <- shown as a fact
A date dd/mm/yyyy with day 01 is that month's month-end balance. The last three months are preliminary and Banxico revises them.
The trend is the official change over the latest 12 months (same month a year earlier -> latest month).

Rule: never invent a number. Any fetch error, a missing series, internal + external not adding to the total, or data older than
what the file already has leaves places/mexico.json untouched (exit 0 so the rest of the daily run continues).
"""
import json, os, sys, csv, io, calendar, datetime as dt, urllib.request, urllib.parse, http.cookiejar

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "places", "mexico.json")
BASE = "https://www.banxico.org.mx/SieInternet/consultarDirectorioInternetAction.do"
TOTAL, INTERNAL, EXTERNAL, CONSOL = "SG193", "SG194", "SG195", "SG199"
SERIES = [TOTAL, INTERNAL, EXTERNAL, CONSOL]
B = 10**9
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36 everydebtclock.com"}

def get_csv(y0, y1):
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    page = BASE + "?accion=consultarCuadro&idCuadro=CG7&locale=es"
    op.open(urllib.request.Request(page, headers=UA), timeout=45).read()  # session cookie
    form = [("idCuadro", "CG7"), ("sector", "9"), ("version", "3"), ("locale", "es"), ("anoInicial", str(y0)), ("anoFinal", str(y1)),
            ("tipoInformacion", "4,1"), ("formatoHorizontal", "false"), ("formatoCSV.x", "10"), ("formatoCSV.y", "10")] + [("series", s) for s in SERIES]
    req = urllib.request.Request(BASE + "?accion=consultarSeries", data=urllib.parse.urlencode(form).encode(),
                                 headers={**UA, "Content-Type": "application/x-www-form-urlencoded", "Referer": page})
    return op.open(req, timeout=45).read().decode("utf-8", errors="replace")

def parse(text):
    rows = list(csv.reader(io.StringIO(text)))
    hdr = next((r for r in rows if r and r[0].strip() == "Fecha"), None)
    if not hdr or any(s not in hdr for s in SERIES): raise RuntimeError("series header not found in the Banxico export")
    idx = {s: hdr.index(s) for s in SERIES}; out = {}
    for r in rows:
        if r and len(r[0]) == 10 and r[0][2] == "/" and r[0][5] == "/":
            d, m, y = int(r[0][:2]), int(r[0][3:5]), int(r[0][6:])
            if d != 1: raise RuntimeError("unexpected date " + r[0])
            try: vals = {s: int(round(float(r[idx[s]].replace(",", "")) * 100)) * (B // 100) for s in SERIES}
            except (ValueError, IndexError): continue  # incomplete row (series not yet published)
            out[f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"] = vals
    return out

def rebase(p, ser):
    ds = sorted(ser)
    if len(ds) < 13: raise RuntimeError("need 13 complete months")
    last, prior = ds[-1], ds[-13]
    if int(prior[:4]) != int(last[:4]) - 1 or prior[5:7] != last[5:7]: raise RuntimeError("prior month is not 12 months back or a month is missing")
    hist = ds[-13:]
    if any((dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days not in range(28, 32) for a, b in zip(hist, hist[1:])): raise RuntimeError("gap in the 13 months")
    L = ser[last]
    if abs(L[INTERNAL] + L[EXTERNAL] - L[TOTAL]) > B // 20: raise RuntimeError("internal + external does not add up to the total")
    c = p["components"][0]
    if last < c["as_of"]: raise RuntimeError(f"Banxico month {last} older than file {c['as_of']}")
    c.update(value=L[TOTAL], as_of=last, prior_value=ser[prior][TOTAL], prior_as_of=prior, history=[[d, ser[d][TOTAL]] for d in hist])
    c["breakdown"] = [{"label": "Internal net debt", "value": L[INTERNAL], "group": "Net debt by type"},
                      {"label": "External net debt", "value": L[EXTERNAL], "group": "Net debt by type"}]
    for f in c.get("facts", []):
        if f.get("key") == "consol":
            f.update(value=L[CONSOL], as_of=last)
            f["note"] = f["note"].split(" A year earlier")[0].strip() + f" A year earlier ({prior}) it was MX${ser[prior][CONSOL] / 1e12:,.2f} trillion."
    y, m = int(last[:4]), int(last[5:7]); ny, nm = (y + (m == 12), m % 12 + 1)
    p["next_update"] = (f"The {calendar.month_name[nm]} {ny} month-end figure is expected from Banco de México within about two months of the month-end; "
                        "this page re-bases to it automatically on the next daily build after it appears.")
    return p

def main():
    p = json.load(open(PATH))
    try:
        y1 = dt.date.today().year
        new = rebase(json.loads(json.dumps(p)), parse(get_csv(y1 - 2, y1)))
    except Exception as e:
        print("mexico: not updated:", e); return 0
    if new != p:
        json.dump(new, open(PATH, "w"), indent=1, ensure_ascii=False); open(PATH, "a").write("\n")
        c = new["components"][0]; print(f"mexico: {c['as_of']} MX${c['value']:,} (prior {c['prior_as_of']} MX${c['prior_value']:,})")
    else: print("mexico: unchanged")
    return 0

if __name__ == "__main__": sys.exit(main())
