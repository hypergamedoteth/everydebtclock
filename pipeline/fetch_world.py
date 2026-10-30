#!/usr/bin/env python3
"""Inputs for the World Debt Clock (/world/): daily exchange rates and the IMF GDP weights.
  data/world_fx.json   ECB euro foreign exchange reference rates (daily, keyless XML), and the Bank of Russia official
                       USD/RUB rate (neither the ECB nor the Fed H.10 publishes a rouble rate any more)
  data/world_gdp.json  IMF World Economic Outlook NGDPD (GDP, current US dollars, billions) for the current calendar year,
                       every country plus the world aggregate: https://www.imf.org/external/datamapper/api/v1/NGDPD

Rule: never invent a number. Each source is fetched and checked on its own; any error, an unreadable or implausible file,
or a date older than what is stored leaves that file untouched (exit 0 so the rest of the daily run continues)."""
import json, os, re, sys, time, urllib.request, datetime as dt
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FX = os.path.join(ROOT, "data", "world_fx.json")
GDP = os.path.join(ROOT, "data", "world_gdp.json")
ECB = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
CBR = "https://www.cbr.ru/scripts/XML_daily.asp"
IMF = "https://www.imf.org/external/datamapper/api/v1/NGDPD"
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

def newer_or_same(new, old, key="date"): return not old.get(key) or new[key] >= old[key]

def main():
    fx = load(FX); changed = False
    for name, fn in (("ecb", ecb), ("cbr", cbr)):
        try:
            new = fn(); old = fx.get(name, {})
            if not newer_or_same(new, old): raise RuntimeError(f"{name} date {new['date']} older than stored {old['date']}")
            if name == "ecb" and old.get("per_eur") and old["date"] != new["date"]:      # implausible one-day move (> 25%) in the dollar rate: keep the last good file
                jump = abs(new["per_eur"]["USD"] / old["per_eur"]["USD"] - 1)
                if jump > 0.25: raise RuntimeError(f"EUR/USD moved {jump:.0%} in one fetch; not trusted")
            if name == "cbr" and old.get("rub_per_usd") and old["date"] != new["date"]:
                jump = abs(new["rub_per_usd"] / old["rub_per_usd"] - 1)
                if jump > 0.5: raise RuntimeError(f"RUB/USD moved {jump:.0%} in one fetch; not trusted")
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
    return 0

if __name__ == "__main__": sys.exit(main())
