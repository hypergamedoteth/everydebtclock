#!/usr/bin/env python3
"""Inputs for the World Debt Clock (/world/) and the World Government Debt Clock (/world-government-debt/).
  data/world_fx.json       ECB euro foreign exchange reference rates (daily, keyless XML), and the Bank of Russia official
                           USD/RUB rate (neither the ECB nor the Fed H.10 publishes a rouble rate any more)
                           and the Federal Reserve Board H.10 weekly release, for currencies the ECB does not publish (Taiwan dollar),
                           and the US Treasury's quarterly Reporting Rates of Exchange (Egyptian pound, Ghanaian cedi, Kenyan shilling, Nigerian naira)
  data/world_gdp.json      IMF World Economic Outlook NGDPD (GDP, current US dollars, billions) for the current calendar year,
                           every country plus the world aggregate: https://www.imf.org/external/datamapper/api/v1/NGDPD
  data/world_weo_debt.json General government gross debt for every IMF economy with both series:
                           GGXWDG_NGDP (percent of GDP) times NGDPD (current US dollars).
                           DataMapper API first; the World Bank Data360 mirror supplies unrounded ratios when the API
                           rounds GGXWDG_NGDP to 0.1 percentage point.

Rule: never invent a number. Each source is fetched and checked on its own; any error, an unreadable or implausible file,
or a date older than what is stored leaves that file untouched (exit 0 so the rest of the daily run continues)."""
import csv, glob, io, json, math, os, re, sys, time, unicodedata, urllib.request, datetime as dt
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FX = os.path.join(ROOT, "data", "world_fx.json")
GDP = os.path.join(ROOT, "data", "world_gdp.json")
WEO = os.path.join(ROOT, "data", "world_weo_debt.json")
ECB = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
CBR = "https://www.cbr.ru/scripts/XML_daily.asp"
IMF = "https://www.imf.org/external/datamapper/api/v1/NGDPD"
H10 = "https://www.federalreserve.gov/releases/h10/current/"
H10_ROWS = {"TWD": "TAIWAN DOLLAR"}      # H.10 row label per currency code we use (units of currency per US dollar)
UA = {"User-Agent": "Mozilla/5.0 (compatible; everydebtclock.com data refresh)", "Accept": "*/*"}

def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r: return r.read()
        except Exception:
            if i == tries - 1: raise
            time.sleep(3)

def load(path):
    try: return json.load(open(path))
    except Exception: return {}

def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(obj, open(path, "w"), indent=1, ensure_ascii=False); open(path, "a").write("\n")

def ecb():
    root = ET.fromstring(get(ECB))
    ns = {"e": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}
    day = root.find(".//e:Cube[@time]", ns)
    date = day.get("time"); dt.date.fromisoformat(date)
    rates = {c.get("currency"): float(c.get("rate")) for c in day.findall("e:Cube", ns)}
    if not rates.get("USD") or any(not (v > 0) for v in rates.values()): raise RuntimeError("ECB: unreadable rates")
    return {"date": date, "per_eur": rates, "source": "European Central Bank, euro foreign exchange reference rates", "source_url": "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html", "feed": ECB}

def cbr():
    # The default feed jumps to the next day's rate once it is set (a date in the future); ask for today's rate in Moscow instead.
    today = dt.datetime.now(ZoneInfo("Europe/Moscow")).strftime("%d/%m/%Y")
    root = ET.fromstring(get(CBR + "?date_req=" + today))     # windows-1251 declared in the XML prolog; ElementTree handles it
    date = dt.datetime.strptime(root.get("Date"), "%d.%m.%Y").date().isoformat()
    usd = next(v for v in root.findall("Valute") if v.findtext("CharCode") == "USD")
    nominal, value = int(usd.findtext("Nominal")), float(usd.findtext("Value").replace(",", "."))
    if not (value > 0 and nominal > 0): raise RuntimeError("CBR: unreadable USD rate")
    return {"date": date, "rub_per_usd": value / nominal, "source": "Bank of Russia, official exchange rate of the rouble to the US dollar", "source_url": "https://www.cbr.ru/eng/currency_base/daily/", "feed": CBR}

def fed():
    """Federal Reserve Board H.10 (weekly; daily noon buying rates in New York, currency units per US dollar). Latest non-ND value in each row."""
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", get(H10).decode("utf-8", "replace")))
    rel = re.search(r"Release Date:\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", t)
    hdr = re.search(r"COUNTRY CURRENCY((?:\s+[A-Z][a-z]{2}\.\s+\d{1,2}){3,7})", t)
    if not rel or not hdr: raise RuntimeError("Fed H.10: layout changed")
    rm = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"].index(rel.group(1)) + 1
    mons = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    cols = []
    for mm, dd in re.findall(r"([A-Z][a-z]{2})\.\s+(\d{1,2})", hdr.group(1)):
        mi = mons.index(mm) + 1; y = int(rel.group(3)) - (1 if mi > rm else 0)
        cols.append(dt.date(y, mi, int(dd)).isoformat())
    out, dates = {}, {}
    for code, label in H10_ROWS.items():
        m = re.search(re.escape(label) + r"((?:\s+(?:[\d.]+|ND)){%d})" % len(cols), t)
        if not m: raise RuntimeError(f"Fed H.10: no row for {label}")
        vals = m.group(1).split()
        pairs = [(c, float(v)) for c, v in zip(cols, vals) if v != "ND"]
        if not pairs or not pairs[-1][1] > 0: raise RuntimeError(f"Fed H.10: no rate for {label}")
        dates[code], out[code] = pairs[-1]
    date = max(dates.values())
    return {"date": date, "per_usd": out, "dates": dates, "source": "Federal Reserve Board, H.10 Foreign Exchange Rates (weekly release; noon buying rates in New York)", "source_url": H10, "feed": H10}

UST = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/rates_of_exchange"
UST_ROWS = {"EGP": "Egypt-Pound", "GHS": "Ghana-Cedi", "KES": "Kenya-Shilling", "NGN": "Nigeria-Naira",
            "CLP": "Chile-Peso", "PEN": "Peru-Sol", "BDT": "Bangladesh-Taka"}   # US Treasury label per currency code (units per US dollar)

def ust():
    """US Treasury Reporting Rates of Exchange (quarterly, as of quarter-end; currency units per US dollar) for currencies the ECB and Fed H.10 do not publish."""
    since = (dt.date.today() - dt.timedelta(days=200)).isoformat()
    q = (UST + "?filter=country_currency_desc:in:(" + ",".join(UST_ROWS.values()) + "),record_date:gte:" + since +
         "&sort=-record_date&page%5Bsize%5D=100&fields=record_date,country_currency_desc,exchange_rate")
    rows = json.loads(get(q))["data"]
    out, dates = {}, {}
    for code, label in UST_ROWS.items():
        r = [x for x in rows if x["country_currency_desc"] == label]
        if not r: raise RuntimeError("US Treasury rates: no row for " + label)
        r.sort(key=lambda x: x["record_date"]); v = float(r[-1]["exchange_rate"])
        if not v > 0: raise RuntimeError("US Treasury rates: bad rate for " + label)
        out[code], dates[code] = v, r[-1]["record_date"]
    return {"date": max(dates.values()), "per_usd": out, "dates": dates, "source": "US Treasury, Treasury Reporting Rates of Exchange (quarterly, as of quarter-end)",
            "source_url": "https://fiscaldata.treasury.gov/datasets/treasury-reporting-rates-exchange/treasury-reporting-rates-of-exchange", "feed": UST}

def imf(year):
    vals = json.loads(get(IMF))["values"]["NGDPD"]
    y = str(year)
    world = vals.get("WEOWORLD", {}).get(y)
    if not world or world <= 0: raise RuntimeError("IMF: no world aggregate for " + y)
    countries = {k: v[y] for k, v in vals.items() if k != "WEOWORLD" and y in v and len(k) == 3}
    if not all(k in countries for k in ("USA", "CHN", "DEU", "JPN", "IND")): raise RuntimeError("IMF: major economies missing for " + y)
    return {"year": year, "unit": "billions of current US dollars", "world": world, "countries": countries,
            "source": "IMF World Economic Outlook, NGDPD (GDP, current prices, US dollars), DataMapper API", "source_url": "https://www.imf.org/external/datamapper/NGDPD@WEO", "feed": IMF,
            "fetched": dt.datetime.now(dt.timezone.utc).date().isoformat()}

# --- World Government Debt Clock: GGXWDG_NGDP x NGDPD ---------------------------------
IMF_RATIO = "https://www.imf.org/external/datamapper/api/v1/GGXWDG_NGDP"
IMF_GDP = "https://www.imf.org/external/datamapper/api/v1/NGDPD"
IMF_COUNTRIES = "https://www.imf.org/external/datamapper/api/v1/countries"
WB_WEO = "https://data360files.worldbank.org/data360-data/data/IMF_WEO/IMF_WEO.csv"
# IMF group codes that share the DataMapper with economies. Not countries.
AGGREGATES = {"ADVEC", "AFQ", "SSQ", "AS5", "APQ", "AZQ", "CBQ", "CMQ", "CAQ", "EAQ", "EEQ", "DA", "EDE", "OEMDC", "EURO", "EUQ", "EU", "WE", "MAE", "MEQ", "MECA", "NAQ", "NMQ", "OAE", "PIQ", "SMQ", "SAQ", "SEQ", "SSA", "WEQ", "WHQ", "WEOWORLD", "ATI", "ATL"}
# Kosovo is UVK in the DataMapper and XKX in the World Bank mirror. One economy.
ISO_ALIAS = {"UVK": "XKX"}
# Display names and slugs. World Bank labels are terse ("Korea, Rep.", "Naoero"); the slug matches an existing
# country URL when this site already has an official clock for that economy.
NAMES = {
    "BHS": "The Bahamas", "BRN": "Brunei", "CHN": "China", "CIV": "Côte d'Ivoire", "COD": "Democratic Republic of the Congo",
    "COG": "Republic of the Congo", "CZE": "Czechia", "EGY": "Egypt", "GMB": "The Gambia", "HKG": "Hong Kong", "IRN": "Iran",
    "KGZ": "Kyrgyzstan", "KNA": "Saint Kitts and Nevis", "KOR": "South Korea", "LAO": "Laos", "LCA": "Saint Lucia",
    "FSM": "Micronesia", "MKD": "North Macedonia", "NRU": "Nauru", "PSE": "West Bank and Gaza", "RUS": "Russia",
    "STP": "São Tomé and Príncipe", "SVK": "Slovakia",     "MAC": "Macao", "SOM": "Somalia", "TWN": "Taiwan", "TUR": "Turkey", "USA": "United States",
    "VCT": "Saint Vincent and the Grenadines", "VEN": "Venezuela", "WBG": "West Bank and Gaza", "XKX": "Kosovo",
    "YEM": "Yemen",
}
SLUGS = {
    "BHS": "bahamas", "BRN": "brunei", "CIV": "cote-divoire", "COD": "democratic-republic-of-the-congo",
    "COG": "republic-of-the-congo", "CZE": "czechia", "FSM": "micronesia", "GMB": "gambia", "HKG": "hong-kong",
    "KGZ": "kyrgyzstan", "KNA": "saint-kitts-and-nevis", "KOR": "south-korea", "LAO": "laos", "LCA": "saint-lucia",
    "NRU": "nauru", "RUS": "russia", "STP": "sao-tome-and-principe", "SVK": "slovakia", "TWN": "taiwan", "TUR": "turkey",
    "USA": "united-states", "VCT": "saint-vincent-and-the-grenadines", "XKX": "kosovo",
}
# Search words that the display name does not already contain.
ALIASES = {
    "BHS": "the bahamas", "BRN": "brunei darussalam", "CIV": "ivory coast cote divoire", "COD": "drc dr congo congo kinshasa",
    "COG": "congo brazzaville", "CPV": "cape verde", "CZE": "czech republic", "FSM": "federated states of micronesia",
    "GMB": "the gambia", "HKG": "hk hksar hong kong sar", "IRN": "persia islamic republic of iran", "KGZ": "kyrgyz republic",
    "KNA": "st kitts nevis", "LAO": "lao pdr lao", "LCA": "st lucia", "MKD": "macedonia", "MMR": "burma", "NRU": "naoero",
    "STP": "sao tome principe", "SWZ": "swaziland", "TLS": "east timor", "TUR": "turkiye", "VCT": "st vincent grenadines",
    "XKX": "uvk",
}
REGIONS = {}
for _reg, _codes in {
    "Europe": "ALB AND AUT BEL BLR BIH BGR HRV CYP CZE DNK EST FIN FRA DEU GRC HUN ISL IRL ITA XKX LVA LIE LTU LUX MLT MDA MNE NLD MKD NOR POL PRT ROU RUS SMR SRB SVK SVN ESP SWE CHE UKR GBR",
    "Asia-Pacific": "ARM AUS AZE BGD BRN BTN KHM CHN FJI GEO HKG IND IDN JPN KAZ KIR KGZ LAO MYS MDV MHL FSM MNG MMR NRU NPL NZL PAK PLW PNG PHL WSM SGP SLB KOR LKA TWN TJK THA TLS TON TKM TUV UZB VUT VNM",
    "Middle East": "BHR IRN IRQ ISR JOR KWT OMN QAT SAU ARE TUR",
    "Africa": "DZA AGO BEN BWA BFA BDI CPV CMR CAF TCD COM COD COG CIV DJI EGY GNQ SWZ ETH GAB GMB GHA GIN GNB KEN LSO LBR LBY MDG MWI MLI MRT MUS MAR MOZ NAM NER NGA RWA STP SYC SLE ZAF SSD SDN TZA TGO TUN UGA ZMB ZWE",
    "the Americas": "ATG ARG ABW BHS BRB BLZ BOL BRA CAN CHL COL CRI DMA DOM SLV GRD GTM GUY HTI HND JAM MEX NIC PAN PRY PER PRI KNA LCA VCT SUR TTO URY USA",
}.items():
    for _c in _codes.split(): REGIONS[_c] = _reg
# 2026 is not a leap year. The clock runs from 2026-01-01 00:00 UTC to 2027-01-01 00:00 UTC.
SECONDS_2026 = 365 * 24 * 60 * 60
ANCHOR = "2026-01-01T00:00:00+00:00"
# Debt-to-GDP path shown on each country page. 2025 and 2026 are inside this window; the ticker still uses only those two.
PATH_YEARS = tuple(str(y) for y in range(2020, 2032))
WORLD_CODES = {"WEOWORLD", "WLD", "WORLD"}

def _slugify(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")

def _num(v):
    if v is None or v == "": return None
    try: x = float(v)
    except (TypeError, ValueError): return None
    if not math.isfinite(x): return None
    return x

# ISO 3166 alpha-2 used in places/*.json when the file has no iso3. Greece's Eurostat code is EL.
ISO2 = {"US": "USA", "CA": "CAN", "MX": "MEX", "SG": "SGP", "GB": "GBR", "DE": "DEU", "JP": "JPN", "CN": "CHN", "IN": "IND", "FR": "FRA", "RU": "RUS",
        "IT": "ITA", "BR": "BRA", "KR": "KOR", "AU": "AUS", "ES": "ESP", "NL": "NLD", "CH": "CHE", "TR": "TUR", "ID": "IDN", "SA": "SAU", "AR": "ARG",
        "ZA": "ZAF", "PL": "POL", "SE": "SWE", "BE": "BEL", "NO": "NOR", "AT": "AUT", "IE": "IRL", "IL": "ISR", "PT": "PRT", "GR": "GRC", "EL": "GRC", "DK": "DNK",
        "FI": "FIN", "NZ": "NZL", "CZ": "CZE", "HK": "HKG", "TH": "THA", "MY": "MYS", "PH": "PHL", "NG": "NGA", "EG": "EGY", "CL": "CHL", "BD": "BGD", "HU": "HUN",
        "RO": "ROU", "SK": "SVK", "SI": "SVN", "HR": "HRV", "LT": "LTU"}

def _official_slugs():
    """iso3 -> slug for live country clocks already on the site. USA is the homepage, not a places file."""
    out = {}
    for f in glob.glob(os.path.join(ROOT, "places", "*.json")):
        try: p = json.load(open(f))
        except Exception: continue
        if p.get("kind") != "country" or p.get("status") != "live": continue
        iso = p.get("iso3") or ISO2.get(p.get("country") or "")
        if iso: out[iso] = p["slug"]
    return out

def _economy_name(code, label):
    if code in NAMES: return NAMES[code]
    return re.sub(r"\s+", " ", (label or code)).strip()

def _row(code, label, ratio, gdp_usd):
    return {"iso3": code, "name": _economy_name(code, label), "ratio": ratio, "gdp_usd": gdp_usd}

def _year_map(raw, scale=1.0):
    out = {}
    for y in PATH_YEARS:
        v = _num((raw or {}).get(y))
        if v is None: continue
        out[y] = v * scale
    return out

def _from_api():
    """DataMapper values. NGDPD is billions of current US dollars. GGXWDG_NGDP is rounded to 0.1 percentage point."""
    countries = json.loads(get(IMF_COUNTRIES))["countries"]
    ratio = json.loads(get(IMF_RATIO))["values"]["GGXWDG_NGDP"]
    gdp = json.loads(get(IMF_GDP))["values"]["NGDPD"]
    world = _year_map(gdp.get("WEOWORLD"), 1e9)
    rows = {}
    for raw, meta in countries.items():
        code = ISO_ALIAS.get(raw, raw)
        if len(code) != 3 or code in AGGREGATES: continue
        rv, gv = ratio.get(raw) or {}, gdp.get(raw) or {}
        r, g = _year_map(rv), _year_map(gv, 1e9)
        if not any(v is not None for v in list(r.values()) + list(g.values())): continue
        if code in rows: continue
        rows[code] = _row(code, (meta or {}).get("label"), r, g)
    return rows, world

def _from_wb():
    """World Bank Data360 mirror of the WEO. OBS_VALUE for NGDPD is current US dollars; GGXWDG_NGDP is unrounded."""
    text = io.TextIOWrapper(urllib.request.urlopen(urllib.request.Request(WB_WEO, headers=UA), timeout=180), encoding="utf-8", newline="")
    ratio, gdp, names, world_raw = {}, {}, {}, {}
    for row in csv.DictReader(text):
        ind = row.get("INDICATOR")
        if ind not in ("IMF_WEO_GGXWDG_NGDP", "IMF_WEO_NGDPD"): continue
        if row.get("COMP_BREAKDOWN_1") not in (None, "", "V_LST"): continue
        year = row.get("TIME_PERIOD")
        if year not in PATH_YEARS: continue
        raw = row.get("REF_AREA") or ""
        code = ISO_ALIAS.get(raw, raw)
        val = _num(row.get("OBS_VALUE"))
        if val is None: continue
        if code in WORLD_CODES and ind == "IMF_WEO_NGDPD":
            world_raw[year] = val
            continue
        if len(code) != 3 or code in AGGREGATES: continue
        names[code] = (row.get("REF_AREA_LABEL") or "").strip()
        (ratio if ind == "IMF_WEO_GGXWDG_NGDP" else gdp).setdefault(code, {})[year] = val
    # If the mirror ever reports NGDPD in billions, the US figure falls near 3e4 instead of 3e13.
    usa = gdp.get("USA", {}).get("2026")
    scale = 1e9 if usa is not None and usa < 1e9 else 1.0
    rows = {}
    for code in set(ratio) | set(gdp):
        r = {y: ratio.get(code, {}).get(y) for y in PATH_YEARS if y in ratio.get(code, {})}
        g = {y: gdp[code][y] * scale for y in PATH_YEARS if y in gdp.get(code, {})}
        rows[code] = _row(code, names.get(code), r, g)
    world = {y: v * scale for y, v in world_raw.items()}
    return rows, world

def _debt(ratio, gdp):
    if ratio is None or gdp is None or not (ratio > 0 and gdp > 0): return None
    return int(round(ratio / 100.0 * gdp))

def _assemble(rows, source, world=None):
    """Keep economies with a positive 2026 ratio and GDP and a positive 2025 pair (the ticker needs both ends)."""
    official = _official_slugs()
    economies, year_2025_only, skipped = [], [], []
    used_slugs = set(official.values())
    for code, row in sorted(rows.items(), key=lambda kv: kv[1]["name"]):
        r, g = row["ratio"], row["gdp_usd"]
        d26, d25 = _debt(r.get("2026"), g.get("2026")), _debt(r.get("2025"), g.get("2025"))
        # A published 0 is not a usable gross-debt stock. Missing years are not guessed.
        if d26 is not None and d25 is not None and d26 != d25:
            pass  # falls through into the panel
        elif d25 is not None and d26 is None:
            why = []
            if not (r.get("2026") and r["2026"] > 0): why.append("2026 GGXWDG_NGDP is missing")
            if not (g.get("2026") and g["2026"] > 0): why.append("2026 NGDPD is missing")
            year_2025_only.append({"iso3": code, "name": row["name"], "ratio_2025": r["2025"], "gdp_2025_usd": int(round(g["2025"])), "debt_2025_usd": d25,
                                    "reason": "both 2025 series are present; " + "; ".join(why)})
            skipped.append({"iso3": code, "name": row["name"], "reason": "; ".join(why) or "2026 debt stock cannot be computed"})
            continue
        elif r.get("2026") == 0 or r.get("2025") == 0:
            skipped.append({"iso3": code, "name": row["name"], "reason": "GGXWDG_NGDP is 0, which is not a plausible general-government gross debt ratio"})
            continue
        else:
            bits = []
            if not (r.get("2026") and r["2026"] > 0): bits.append("2026 GGXWDG_NGDP is missing or not positive")
            if not (g.get("2026") and g["2026"] > 0): bits.append("2026 NGDPD is missing or not positive")
            if d26 is not None: bits.append("no positive 2025 stock to anchor the clock")
            elif not (r.get("2025") and r["2025"] > 0): bits.append("2025 GGXWDG_NGDP is missing or not positive")
            skipped.append({"iso3": code, "name": row["name"], "reason": "; ".join(bits) or "2025 and 2026 debt stocks cannot both be computed"})
            continue
        if d26 == d25:
            skipped.append({"iso3": code, "name": row["name"], "reason": "end-2026 stock equals end-2025 stock, so the ticker would be zero"})
            continue
        slug = official.get(code) or SLUGS.get(code) or _slugify(row["name"])
        if code not in official:
            if not slug or slug in used_slugs: raise RuntimeError(f"WEO slug collision for {code} {row['name']}: {slug}")
            used_slugs.add(slug)
        clock = "us" if code == "USA" else "official" if code in official else "weo"
        rate = (d26 - d25) / SECONDS_2026
        if rate == 0: raise RuntimeError("zero rate slipped through for " + code)
        economies.append({
            "iso3": code, "name": row["name"], "slug": slug, "region": REGIONS.get(code, ""), "clock": clock,
            "aliases": ALIASES.get(code, ""),
            "ratio_2025": r["2025"], "ratio_2026": r["2026"],
            "gdp_2025_usd": int(round(g["2025"])), "gdp_2026_usd": int(round(g["2026"])),
            "debt_2025_usd": d25, "debt_2026_usd": d26, "rate_usd_per_sec": rate,
            "ratio_path": {y: round(v, 6) for y, v in sorted((r or {}).items()) if v is not None and y in PATH_YEARS},
        })
    if len(economies) < 170: raise RuntimeError(f"only {len(economies)} economies with both years; not trusted")
    panel_2026 = sum(e["debt_2026_usd"] for e in economies)
    panel_2025 = sum(e["debt_2025_usd"] for e in economies)
    broader_2025 = panel_2025 + sum(e["debt_2025_usd"] for e in year_2025_only)
    if not (80e12 < panel_2026 < 180e12): raise RuntimeError(f"2026 panel sum {panel_2026} is implausible")
    usa = next((e for e in economies if e["iso3"] == "USA"), None)
    chn = next((e for e in economies if e["iso3"] == "CHN"), None)
    if not usa or not chn: raise RuntimeError("USA or China missing from the WEO panel")
    missing_region = [e["iso3"] for e in economies if not e["region"]]
    if missing_region: print("world weo: no region for", " ".join(missing_region))
    return {
        "_doc": "General government gross debt = GGXWDG_NGDP / 100 x NGDPD, current US dollars, IMF World Economic Outlook. "
                "The clock interpolates from the end-2025 stock on 2026-01-01 00:00 UTC to the end-2026 stock on 2027-01-01 00:00 UTC. "
                "Not a live ledger. The dollar change includes exchange-rate effects. US figures here are the IMF estimate, not Treasury Debt to the Penny.",
        "vintage": "October 2026",
        "precision_source": source,
        "indicator_ratio": "GGXWDG_NGDP",
        "indicator_gdp": "NGDPD",
        "source": "IMF World Economic Outlook, October 2026",
        "source_url": "https://www.imf.org/external/datamapper/GGXWDG_NGDP@WEO",
        "gdp_source_url": "https://www.imf.org/external/datamapper/NGDPD@WEO",
        "feed_ratio": IMF_RATIO,
        "feed_gdp": IMF_GDP,
        "fallback_feed": WB_WEO,
        "fetched": dt.datetime.now(dt.timezone.utc).date().isoformat(),
        "anchor": ANCHOR,
        "seconds_2026": SECONDS_2026,
        "panel_count": len(economies),
        "panel_2026_usd": panel_2026,
        "panel_2025_usd": panel_2025,
        "broader_2025_count": len(economies) + len(year_2025_only),
        "broader_2025_usd": broader_2025,
        "rate_usd_per_sec": (panel_2026 - panel_2025) / SECONDS_2026,
        "world_gdp_2026_usd": (int(round(world["2026"])) if world and world.get("2026") else None),
        "usa": {"debt_2026_usd": usa["debt_2026_usd"], "ratio_2026": usa["ratio_2026"]},
        "china": {"debt_2026_usd": chn["debt_2026_usd"], "ratio_2026": chn["ratio_2026"]},
        "economies": economies,
        "year_2025_only": year_2025_only,
        "skipped": skipped,
    }

def _close(a, b, tol):
    return a is not None and b is not None and abs(a - b) <= tol * max(abs(b), 1)

def weo():
    """Write data/world_weo_debt.json. Leaves the previous file in place if this fetch cannot be checked."""
    api = api_world = wb = wb_world = None
    try: api, api_world = _from_api()
    except Exception as e: print("world weo api:", e)
    try: wb, wb_world = _from_wb()
    except Exception as e: print("world weo world bank mirror:", e)
    chosen = None
    # The DataMapper rounds GGXWDG_NGDP to 0.1 percentage point (US 126.790% arrives as 126.8), so the dollar
    # stock is off by a few billion. The mirror is the same WEO file with the unrounded ratio. Prefer it when
    # it agrees with the API on the US ratio within 0.2 percentage points and on the 2026 panel within 1%.
    if wb and api and "USA" in wb and "USA" in api:
        try:
            a, b = _assemble(api, "imf_api", api_world), _assemble(wb, "worldbank", wb_world)
            if abs(a["usa"]["ratio_2026"] - b["usa"]["ratio_2026"]) <= 0.2 and _close(a["panel_2026_usd"], b["panel_2026_usd"], 0.01):
                chosen = b
                print(f"world weo: unrounded mirror kept (API US ratio {a['usa']['ratio_2026']}, mirror {b['usa']['ratio_2026']})")
            else:
                print("world weo: mirror disagrees with the API; keeping the API")
                chosen = a
        except Exception as e:
            print("world weo assemble:", e)
    if chosen is None and wb:
        try: chosen = _assemble(wb, "worldbank", wb_world)
        except Exception as e: print("world weo mirror assemble:", e)
    if chosen is None and api:
        try: chosen = _assemble(api, "imf_api", api_world)
        except Exception as e: print("world weo api assemble:", e)
    if chosen and not chosen.get("world_gdp_2026_usd") and api_world and api_world.get("2026"):
        chosen["world_gdp_2026_usd"] = int(round(api_world["2026"]))
        chosen["world_gdp_source"] = "imf_api"
    elif chosen and chosen.get("world_gdp_2026_usd"):
        chosen["world_gdp_source"] = chosen.get("precision_source")
    if not chosen:
        print("world weo: not updated")
        return
    old = load(WEO)
    if old.get("panel_2026_usd") and not _close(chosen["panel_2026_usd"], old["panel_2026_usd"], 0.15):
        print(f"world weo: panel moved from {old['panel_2026_usd']:.3e} to {chosen['panel_2026_usd']:.3e}; not trusted")
        return
    slim = {k: v for k, v in chosen.items() if k != "fetched"}
    old_slim = {k: v for k, v in old.items() if k != "fetched"}
    if slim != old_slim:
        save(WEO, chosen)
        print(f"world weo: {chosen['precision_source']} {chosen['panel_count']} economies, "
              f"2026 ${chosen['panel_2026_usd']/1e12:.3f}T, 2025 panel ${chosen['panel_2025_usd']/1e12:.3f}T, "
              f"2025 broader ${chosen['broader_2025_usd']/1e12:.3f}T, "
              f"US ${chosen['usa']['debt_2026_usd']/1e12:.3f}T ({chosen['usa']['ratio_2026']}%), "
              f"China ${chosen['china']['debt_2026_usd']/1e12:.3f}T ({chosen['china']['ratio_2026']}%), "
              f"skipped {len(chosen['skipped'])}")
    else:
        print("world weo: unchanged")

def newer_or_same(new, old, key="date"): return not old.get(key) or new[key] >= old[key]

def main():
    fx = load(FX); changed = False
    for name, fn in (("ecb", ecb), ("cbr", cbr), ("fed", fed), ("ust", ust)):
        try:
            new = fn(); old = fx.get(name, {})
            if not newer_or_same(new, old): raise RuntimeError(f"{name} date {new['date']} older than stored {old['date']}")
            if name == "ecb" and old.get("per_eur") and old["date"] != new["date"]:      # implausible one-day move (> 25%) in the dollar rate: keep the last good file
                jump = abs(new["per_eur"]["USD"] / old["per_eur"]["USD"] - 1)
                if jump > 0.25: raise RuntimeError(f"EUR/USD moved {jump:.0%} in one fetch; not trusted")
            if name == "cbr" and old.get("rub_per_usd") and old["date"] != new["date"]:
                jump = abs(new["rub_per_usd"] / old["rub_per_usd"] - 1)
                if jump > 0.5: raise RuntimeError(f"RUB/USD moved {jump:.0%} in one fetch; not trusted")
            if name in ("fed", "ust") and old.get("per_usd") and old["date"] != new["date"]:
                jump = max(abs(new["per_usd"][k] / old["per_usd"][k] - 1) for k in new["per_usd"] if k in old["per_usd"])
                if jump > (0.25 if name == "fed" else 0.6): raise RuntimeError(f"{name} rate moved {jump:.0%} in one fetch; not trusted")
            if new != old: fx[name] = new; changed = True; print(f"world fx {name}: {new['date']}")
            else: print(f"world fx {name}: unchanged")
        except Exception as e:
            print(f"world fx {name}: not updated:", e)
    if changed: save(FX, fx)
    year = dt.datetime.now(dt.timezone.utc).year
    try:
        new = imf(year); old = load(GDP)
        if new != old and {k: v for k, v in new.items() if k != "fetched"} != {k: v for k, v in old.items() if k != "fetched"}:
            save(GDP, new); print(f"world gdp: IMF NGDPD {year}, world {new['world']:,.1f} bn, {len(new['countries'])} countries")
        else: print("world gdp: unchanged")
    except Exception as e:
        print("world gdp: not updated:", e)
    try: weo()
    except Exception as e: print("world weo: not updated:", e)
    return 0

if __name__ == "__main__":
    if "--weo-only" in sys.argv:
        try: weo()
        except Exception as e: print("world weo: not updated:", e)
        sys.exit(0)
    sys.exit(main())
