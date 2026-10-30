#!/usr/bin/env python3
"""Monthly update of places/russia.json from the Ministry of Finance of the Russian Federation (Минфин России),
"Государственный внутренний долг Российской Федерации" - https://minfin.gov.ru/ru/perfomance/public_debt/internal/

  Total (всего), thousand roubles, as of the 1st of the month  <- the ticking hero (incl. guarantees in roubles)
  of which state guarantees in roubles                         <- fact
The page shows only the latest figure, so each new month is appended to the committed history; the 12-month trend needs the
value for the same date a year earlier to already be in that history. Rule: never invent a number. Any fetch or parse error,
an older date, or a missing year-ago value leaves places/russia.json untouched (exit 0).
"""
import json, os, re, sys, html, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "places", "russia.json")
URL = "https://minfin.gov.ru/ru/perfomance/public_debt/internal/"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 everydebtclock.com"})
    with urllib.request.urlopen(req, timeout=60) as r: return r.read().decode("utf-8", "replace")

def num(s): return int(round(float(re.sub(r"[\s\u00a0]", "", s).replace(",", ".")) * 1000))   # thousand roubles -> roubles

def parse(h):
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)).replace("\u00a0", " "))
    m = re.search(r"Объем государственного внутреннего долга Российской Федерации, тыс\. руб\. по состоянию на (\d\d)\.(\d\d)\.(\d{4})"
                  r" Государственный внутренний долг Российской Федерации, всего ([\d ]+,\d) в том числе государственные гарантии[^\d]*?([\d ]+,\d)", t)
    if not m: raise RuntimeError("internal debt block not found")
    d, mo, y = m.group(1), m.group(2), int(m.group(3))
    total, guar = num(m.group(4)), num(m.group(5))
    if not (0 < guar < total): raise RuntimeError("implausible total / guarantees")
    return f"{y:04d}-{mo}-{d}", total, guar

def rebase(p, h):
    date, total, guar = parse(h)
    c = p["components"][0]
    if date < c["as_of"]: raise RuntimeError(f"Minfin date {date} older than file {c['as_of']}")
    hist = [list(x) for x in c["history"]]
    if date > hist[-1][0]:
        hist.append([date, total])
    elif hist[-1] != [date, total]:
        raise RuntimeError("same date as the file but a different value; not overwriting")
    hist = hist[-13:]
    ago = f"{int(date[:4]) - 1}{date[4:]}"
    prior = dict((a, b) for a, b in hist).get(ago)
    if prior is None: raise RuntimeError(f"no value for {ago} in the committed history")
    c.update(value=total, as_of=date, prior_value=prior, prior_as_of=ago, history=hist)
    for f in c.get("facts", []):
        if f.get("key") == "guarantees": f.update(value=guar, as_of=date)
    y, mo = int(date[:4]), int(date[5:7])
    ny, nm = (y, mo + 1) if mo < 12 else (y + 1, 1)
    p["next_update"] = (f"Minfin updates the figure monthly, as of the 1st of the month ({ny:04d}-{nm:02d}-01 next); "
                        "this page picks it up automatically on the next daily build after it appears.")
    return p

def main():
    p = json.load(open(PATH))
    try: new = rebase(json.loads(json.dumps(p)), get(URL))
    except Exception as e:
        print("russia: not updated:", e); return 0
    if new != p:
        json.dump(new, open(PATH, "w"), indent=1, ensure_ascii=False); open(PATH, "a").write("\n")
        c = new["components"][0]; print(f"russia: {c['as_of']} ₽{c['value']:,} (prior {c['prior_as_of']} ₽{c['prior_value']:,})")
    else: print("russia: unchanged")
    return 0

if __name__ == "__main__": sys.exit(main())
