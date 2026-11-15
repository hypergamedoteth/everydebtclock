#!/usr/bin/env python3
"""Quarterly public-sector debt stocks from the World Bank / IMF QPSD database (keyless API).

Saves local-currency series only. pipeline/world selection (world_sources.py) converts with the
official FX file and keeps a series only when the US-dollar stock is within 25% of the IMF WEO stock.
A failed fetch leaves data/world_qpsd.json untouched.

Never invents a number. Countries that already have a national or Eurostat clock are not stored here;
those clocks win.
"""
import calendar, json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "world_qpsd.json")
API = "https://api.worldbank.org/v2/country/all/indicator/{code}?format=json&date=2024Q1:2026Q4&per_page=20000"
UA = {"User-Agent": "Mozilla/5.0 (compatible; everydebtclock.com data refresh)", "Accept": "application/json"}
# iso3 -> (currency code, US Treasury label or None when ECB, Fed H.10, or the US dollar itself converts it).
# Only economies that do not already have a live clock on this site. The label is the Treasury Reporting
# Rates "country_currency_desc" when the ECB does not publish that currency.
CUR = {
    "ALB": ("ALL", "Albania-Lek"), "ARM": ("AMD", "Armenia-Dram"), "BIH": ("BAM", "Bosnia-Marka"),
    "BRB": ("BBD", "Barbados-Dollar"), "CIV": ("XOF", "Cote D'Ivoire-Cfa Franc"), "COL": ("COP", "Colombia-Peso"),
    "CRI": ("CRC", "Costa Rica-Colon"), "DOM": ("DOP", "Dominican Republic-Peso"), "GEO": ("GEL", "Georgia-Lari"),
    "GTM": ("GTQ", "Guatemala-Quetzal"), "HND": ("HNL", "Honduras-Lempira"), "ISL": ("ISK", "Iceland-Krona"),
    "ISR": ("ILS", None), "KAZ": ("KZT", "Kazakhstan-Tenge"), "KGZ": ("KGS", "Kyrgyzstan-Som"),
    "LCA": ("XCD", "St. Lucia-East Caribbean Dollar"), "LKA": ("LKR", "Sri Lanka-Rupee"),
    "MAR": ("MAD", "Morocco-Dirham"), "MDA": ("MDL", "Moldova-Leu"), "MDG": ("MGA", "Madagascar-Ariary"),
    "MKD": ("MKD", "Republic Of North Macedonia-Denar"), "MNG": ("MNT", "Mongolia-Tugrik"),
    "MUS": ("MUR", "Mauritius-Rupee"), "NIC": ("NIO", "Nicaragua-Cordoba"), "NZL": ("NZD", None),
    "PHL": ("PHP", "Philippines-Peso"), "PNG": ("PGK", "Papua New Guinea-Kina"), "PRY": ("PYG", "Paraguay-Guarani"),
    "RWA": ("RWF", "Rwanda-Franc"), "SLB": ("SBD", "Solomon Islands-Dollar"), "SLV": ("USD", None),
    "SUR": ("SRD", "Suriname-Dollar"), "TJK": ("TJS", "Tajikistan-Somoni"), "TON": ("TOP", "Tonga-Pa'Anga"),
    "UGA": ("UGX", "Uganda-Shilling"), "URY": ("UYU", "Uruguay-Peso"), "XKX": ("EUR", None),
    "ZMB": ("ZMW", "Zambia-New Kwacha"),
}
INDS = {"general": "DP.DOD.DECT.CR.GG", "central": "DP.DOD.DECT.CR.CG"}

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))

def qend(q):
    y, qq = int(q[:4]), int(q[-1])
    mo = qq * 3
    return f"{y:04d}-{mo:02d}-{calendar.monthrange(y, mo)[1]:02d}"

def main():
    try:
        raw = {sector: get(API.format(code=code)) for sector, code in INDS.items()}
    except Exception as e:
        print("qpsd: not updated:", e)
        return 0
    countries = {}
    for sector, payload in raw.items():
        if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
            print("qpsd: not updated: empty", sector)
            return 0
        for row in payload[1]:
            iso = row.get("countryiso3code")
            if iso not in CUR or row.get("value") in (None, 0):
                continue
            try:
                q = row["date"]
                if len(q) != 6 or q[4] != "Q":
                    continue
                val = float(row["value"])
            except (TypeError, ValueError, KeyError):
                continue
            if not val > 0:
                continue
            slot = countries.setdefault(iso, {"currency": CUR[iso][0], "fx_label": CUR[iso][1], "general": [], "central": []})
            slot[sector].append([qend(q), val])
    for slot in countries.values():
        for sector in ("general", "central"):
            # last point in a quarter wins; the API can repeat a quarter
            by = {}
            for d, v in slot[sector]:
                by[d] = v
            slot[sector] = [[d, by[d]] for d in sorted(by)]
    recent = 0
    for slot in countries.values():
        for sector in ("general", "central"):
            if any(d >= "2025-06-30" and v > 0 for d, v in slot[sector]):
                recent += 1
                break
    if recent < 30:
        print(f"qpsd: not updated: only {recent} recent series")
        return 0
    doc = {
        "_doc": "Local-currency gross debt stocks from the World Bank / IMF Quarterly Public Sector Debt database. "
                "general is DP.DOD.DECT.CR.GG and central is DP.DOD.DECT.CR.CG, nominal value, all maturities, all instruments. "
                "USD conversion and the 25% IMF screen happen at build time. Not used for economies that already have a live clock.",
        "source": "World Bank and IMF, Quarterly Public Sector Debt (QPSD)",
        "source_url": "https://www.worldbank.org/en/programs/debt-statistics/qpsd",
        "feed": "https://api.worldbank.org/v2/country/all/indicator/DP.DOD.DECT.CR.GG",
        "indicators": INDS,
        "fetched": time.strftime("%Y-%m-%d", time.gmtime()),
        "countries": countries,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(doc, open(OUT, "w"), indent=1, ensure_ascii=False)
    open(OUT, "a").write("\n")
    print(f"qpsd: {len(countries)} economies, {recent} with a stock from 2025-06-30")
    return 0

if __name__ == "__main__":
    sys.exit(main())
