"""Per-page data dates for the sitemap, the visible Updated line, and JSON-LD.

Every date is taken from the figure the page shows (a Treasury record date, a
place's as-of, the day an IMF file was fetched, a fund's stated as-of, or a
date written on a legal page). The build clock is not used. A date after today
is dropped, so a projection end such as 2026-12-31 is not labeled as an update.
"""
import datetime as dt
import json
import os
import re

import places_build

LEVEL_RE = re.compile(r"<lastmod>([^<]+)</lastmod>")
LOC_RE = re.compile(r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>")
UPDATED_RE = re.compile(r'<p class="updated"[^>]*>.*?</p>')
DM_RE = re.compile(r'"dateModified"\s*:\s*"[^"]*"')
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S)
TAG_RE = re.compile(r"<[^>]+>")
ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Dates stated in the prose, not inferred from the clock.
CONTENT = {
    "/about/": "2026-11-17",
    "/contact/": "2026-11-17",
    "/advertise/": "2026-11-16",
    "/privacy/": "2026-11-18",
    "/404.html": "2026-11-17",
}

ALWAYS = ("/", "/41-trillion/", "/national-debt-per-person/")
SKIP_DIRS = {".git", "cache", "pipeline", "__pycache__", "dist", "node_modules", ".venv", "venv"}


def read_lastmods(path):
    if not path or not os.path.exists(path):
        return {}
    text = open(path, encoding="utf-8").read()
    return {loc.strip(): lm.strip() for loc, lm in LOC_RE.findall(text)}


def _month_end(y, m):
    if m == 12:
        return dt.date(y + 1, 1, 1) - dt.timedelta(days=1)
    return dt.date(y, m + 1, 1) - dt.timedelta(days=1)


def parse(raw, today):
    """Return a sitemap lastmod, or None when the text is not a real date we can stand behind."""
    if raw is None:
        return None
    s = str(raw).strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
        if d > today:
            return None
        return d.isoformat()
    m = re.search(r"(\d{4})-Q([1-4])", s)
    if m:
        y, q = int(m.group(1)), int(m.group(2))
        end = _month_end(y, q * 3)
        if end > today:
            return None
        return end.isoformat()
    m = re.search(r"\bFY(\d{4})\b", s)
    if m:
        end = dt.date(int(m.group(1)), 9, 30)
        if end > today:
            return None
        return end.isoformat()
    m = re.search(r"(\d{4})-(\d{2})\b", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if not 1 <= mo <= 12:
            return None
        if (y, mo) > (today.year, today.month):
            return None
        return f"{y:04d}-{mo:02d}"
    m = re.search(r"\b((?:January|February|March|April|May|June|July|August|September|October|November|December)|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))[a-z]*\s+(\d{4})\b", s, re.I)
    if m:
        try:
            month = dt.datetime.strptime(m.group(1)[:3].title(), "%b").month
        except ValueError:
            return None
        y = int(m.group(2))
        if (y, month) > (today.year, today.month):
            return None
        return f"{y:04d}-{month:02d}"
    m = re.fullmatch(r"(\d{4})", s)
    if m:
        y = int(m.group(1))
        if y > today.year or y < 1900:
            return None
        return f"{y:04d}"
    return None


def display(lastmod):
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", lastmod):
        return dt.date.fromisoformat(lastmod).strftime("%b %-d, %Y")
    if re.fullmatch(r"\d{4}-\d{2}", lastmod):
        return dt.date.fromisoformat(lastmod + "-01").strftime("%b %Y")
    return lastmod


def _newer(a, b):
    """True when a is a later data date than b. Missing b counts as older."""
    if not a:
        return False
    if not b:
        return True

    def key(s):
        p = s.split("-")
        return (int(p[0]), int(p[1]) if len(p) > 1 else 0, int(p[2]) if len(p) > 2 else 0)

    return key(a) > key(b)


def _put(out, path, lastmod):
    if lastmod:
        out[path] = lastmod


def _max(dates):
    best = None
    for d in dates:
        if _newer(d, best):
            best = d
    return best


def _csv_date(path, today):
    if not os.path.exists(path):
        return None
    text = open(path, encoding="utf-8", errors="replace").read()
    return _max(parse(m, today) for m in ISO_RE.findall(text))


def _data_date(path, today):
    """The series date, not the day the file was written.

    JSON history files carry series_end. CSV files carry record_date or as_of.
    A last_updated stamp on every row is not a data date.
    """
    if not os.path.exists(path):
        return None
    if path.endswith(".json"):
        try:
            doc = json.load(open(path, encoding="utf-8"))
        except Exception:
            doc = None
        if isinstance(doc, dict) and doc.get("series_end"):
            return parse(doc["series_end"], today)
    if path.endswith(".csv"):
        import csv
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
            col = "record_date" if "record_date" in fields else "as_of" if "as_of" in fields else None
            if col:
                return _max(parse(row.get(col), today) for row in reader)
    return _csv_date(path, today)


def collect(R, off_d, world=None, today=None):
    """Map a site path ('/states/texas/') to a lastmod string."""
    today = today or dt.date.today()
    out = {}
    debt = parse(off_d, today)
    D = json.load(open(os.path.join(R, "data", "data.json")))
    T, M = D["tickers"], D["meta"]
    places = places_build.load(R)
    by_slug = {p["slug"]: p for p in places}

    def place_date(slug):
        p = by_slug.get(slug)
        if not p:
            return None
        return parse(places_build.calc(p)["as_of"], today)

    weo_fetched = None
    weo_published = None
    hist_path = os.path.join(R, "data", "world_weo_history.json")
    if os.path.exists(hist_path):
        weo_published = parse(json.load(open(hist_path)).get("published"), today)
    weo_path = os.path.join(R, "data", "world_weo_debt.json")
    economies = []
    if os.path.exists(weo_path):
        weo = json.load(open(weo_path))
        weo_fetched = parse(weo.get("fetched"), today)
        economies = weo.get("economies") or []

    upgrades = {}
    if economies:
        import weo_build
        import world_build
        import world_sources
        fx = world_build._load(os.path.join(R, "data", "world_fx.json"))
        applied = weo_build._apply_official(list(economies), places)
        upgrades, _rejected = world_sources.qpsd_choice(R, places, fx, applied)
        by_iso = {e["iso3"]: e for e in applied}
    else:
        by_iso = {}

    for slug, p in by_slug.items():
        sec = "states" if p["kind"] == "state" else "countries"
        _put(out, f"/{sec}/{slug}/", place_date(slug))

    for e in economies:
        slug = e.get("slug")
        if not slug or f"/countries/{slug}/" in out:
            continue
        u = upgrades.get(e.get("iso3"))
        # The quarterly stock's as-of date when that stock is the clock. Otherwise the WEO publication date.
        _put(out, f"/countries/{slug}/", parse(u["as_of"], today) if u and u.get("as_of") else (weo_published or weo_fetched))

    import debt_by_year_build
    for m in debt_by_year_build.models(R):
        if m.get("imf"):
            _put(out, m["path"], weo_fetched)
            continue
        dates = [parse(r.get("date"), today) for r in m["rows"]]
        _put(out, m["path"], _max(dates))

    for slug, info in T.items():
        d = parse(info.get("as_of"), today) or debt
        _put(out, f"/t/{slug}.html", d)
    for slug, info in (D.get("derived") or {}).items():
        _put(out, f"/t/{slug}.html", parse(info.get("as_of"), today) or debt)

    fy = M.get("debt_by_fy") or []
    fy_date = _max(parse(row[1], today) for row in fy if len(row) > 1)
    _put(out, "/national-debt-by-year/", _max([fy_date, debt]))

    import presidents_build
    published, _skipped, _H = presidents_build.records(R, off_d, None, M.get("debt_by_fy") or [])
    pres_dates = []
    for p in published:
        last = (p.get("last") or {}).get("date")
        d = parse(last, today) or debt
        pres_dates.append(d)
        _put(out, f"/national-debt-by-president/{p['slug']}/", d)
    _put(out, "/national-debt-by-president/", _max(pres_dates + [debt]))

    state_dates = [place_date(p["slug"]) for p in places if p["kind"] == "state"]
    country_dates = [out.get(f"/countries/{p['slug']}/") for p in places if p["kind"] == "country"]
    country_dates += [out[k] for k in out if k.startswith("/countries/") and k.count("/") == 3]
    _put(out, "/states/", _max(state_dates))
    _put(out, "/countries/", _max(country_dates))
    pop_dates = [parse((p.get("population") or {}).get("as_of"), today) for p in places if p["kind"] == "state"]
    _put(out, "/states/debt-per-person/", _max(state_dates + pop_dates))

    world_dates = [weo_fetched]
    if world:
        for row in world.get("rows") or []:
            if row.get("tier") == "imf":
                continue
            world_dates.append(parse(row.get("as_of"), today))
    world_date = _max(world_dates)
    _put(out, "/world/", world_date)
    _put(out, "/world-government-debt/", world_date)
    _put(out, "/global-debt-clock/", world_date)

    import wealth_build
    _d, funds = wealth_build.prep(places) if places else (None, [])
    fund_dates = []
    for f in funds or []:
        d = parse((f.get("assets") or {}).get("as_of"), today)
        fund_dates.append(d)
        _put(out, "/" + f["url"], d)
    _put(out, "/wealth/", _max(fund_dates))

    data_dir = os.path.join(R, "data")
    csv_dates = {}
    for name in (
        "us-debt-daily.csv", "us-debt-daily.json", "us-debt-annual.csv", "us-debt-annual.json",
        "us-debt-by-year.csv", "us-debt-by-president.csv", "us-debt-per-person.csv",
        "us-interest.csv", "us-state-debt.csv", "country-debt.csv",
    ):
        csv_dates[name] = _data_date(os.path.join(data_dir, name), today)
    # The per-person file carries the Treasury close. If a scan misses it, use that close.
    if debt and not _newer(csv_dates.get("us-debt-per-person.csv"), debt):
        csv_dates["us-debt-per-person.csv"] = _max([csv_dates.get("us-debt-per-person.csv"), debt])
    chart_for = {
        "us-debt-by-year": "us-debt-by-year.csv",
        "us-debt-by-president": "us-debt-by-president.csv",
        "us-interest-by-year": "us-interest.csv",
        "countries-debt-to-gdp": "country-debt.csv",
    }
    for name, d in csv_dates.items():
        _put(out, f"/data/{name}", d)
    for slug, csv_name in chart_for.items():
        for ext in ("png", "svg"):
            _put(out, f"/data/charts/{slug}.{ext}", csv_dates.get(csv_name))
    _put(out, "/data/", _max(csv_dates.values()))
    import monthly_report
    for path, day in monthly_report.lastmods(R, today).items():
        _put(out, path, parse(day, today))

    cash = (T.get("interest_cash") or {}).get("as_of")
    _put(out, "/interest-on-the-national-debt/", parse(cash, today) or debt)
    for path in ("/", "/how-much-is-the-national-debt/", "/national-debt-per-person/", "/your-share/",
                 "/41-trillion/", "/press/", "/methodology/", "/embed/", "/when-will-debt-hit-41-trillion/",
                 "/facts/", "/widget.html"):
        _put(out, path, debt)
    import debt_limit
    dsl_day = parse((T.get("debt_subject_limit") or {}).get("as_of"), today)
    checked = parse(debt_limit.EXTRAORDINARY_MEASURES.get("checked"), today)
    _put(out, "/debt-limit/", _max([dsl_day, checked, debt]))
    for path, day in CONTENT.items():
        _put(out, path, parse(day, today))
    return out


def lookup(dates, url_path):
    if url_path in dates:
        return dates[url_path]
    if url_path.startswith("/your-share/"):
        return dates.get("/your-share/")
    return None


def changed_urls(site, dates, old, sitemap_urls):
    """Homepage, the countdown, per person, and sitemap URLs whose data date moved forward."""
    site = site.rstrip("/")
    allowed = set()
    for row in sitemap_urls:
        allowed.add(row[0] if isinstance(row, (tuple, list)) else row)
    picked = []
    seen = set()

    def add(path):
        url = site + path
        if url in seen or url not in allowed or path not in dates:
            return
        seen.add(url)
        picked.append(url)

    for path in ALWAYS:
        add(path)
    for path, lastmod in sorted(dates.items()):
        prev = old.get(site + path)
        if _newer(lastmod, prev):
            add(path)
    return picked


def write_urls(path, urls):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write("\n".join(urls) + ("\n" if urls else ""))


def line(lastmod):
    return f'<p class="updated" data-updated="{lastmod}">Updated {display(lastmod)}</p>'


def _file_path(rel):
    rel = rel.replace("\\", "/")
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("index.html")]
    return "/" + rel


def _skip_file(rel):
    rel = rel.replace("\\", "/")
    if rel.startswith("dist/") or rel.startswith("embed/") and rel != "embed/index.html":
        return True
    if rel.endswith("analytics.html"):
        return True
    return False


def stamp_html(page, lastmod, url):
    block = line(lastmod)
    if UPDATED_RE.search(page):
        page = UPDATED_RE.sub(block, page, count=1)
    elif "</h1>" in page:
        # After the first real paragraph. Skip the install prompt, which sits right after the H1.
        h1 = page.find("</h1>")
        search_from = h1
        end_a2 = page.find("<!--/A2HS-->", h1)
        if 0 < end_a2 - h1 < 4000:
            search_from = end_a2
        p = page.find("</p>", search_from)
        if p >= 0:
            page = page[:p + 4] + block + page[p + 4:]
        else:
            page = page.replace("</h1>", "</h1>" + block, 1)
    elif "<footer" in page:
        page = page.replace("<footer", block + "<footer", 1)
    else:
        page = page.replace("</body>", block + "</body>", 1)
    page = DM_RE.sub(f'"dateModified": "{lastmod}"', page)
    if '"dateModified"' not in page and "</head>" in page:
        ld = ('<script type="application/ld+json">{"@context":"https://schema.org","@type":"WebPage",'
              f'"dateModified":"{lastmod}","url":"{url}"}}</script>')
        page = page.replace("</head>", ld + "</head>", 1)
    if 'rel="manifest"' not in page and "</head>" in page:
        page = page.replace("</head>", '<link rel="manifest" href="/manifest.json"></head>', 1)
    return page


def stamp_tree(R, site, dates):
    site = site.rstrip("/")
    n = 0
    for dirpath, dirnames, filenames in os.walk(R):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if not fn.endswith(".html"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, R)
            if _skip_file(rel):
                continue
            url_path = _file_path(rel)
            lastmod = lookup(dates, url_path)
            if not lastmod:
                continue
            raw = open(path, encoding="utf-8").read()
            page = stamp_html(raw, lastmod, site + url_path)
            if page != raw:
                open(path, "w", encoding="utf-8").write(page)
                n += 1
    return n


def visible_lead(html, n=200):
    m = H1_RE.search(html)
    if not m:
        return ""
    chunk = html[m.start():m.start() + 1200]
    text = TAG_RE.sub(" ", chunk)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:n]


def check(R, site, dates, urls, off_d):
    site = site.rstrip("/")
    missing = []
    for url, _p, _c in urls:
        path = url[len(site):] if url.startswith(site) else url
        if path != "/" and not path.endswith("/") and not path.endswith(".html") and "." not in os.path.basename(path):
            path = path if path.endswith("/") else path
        if lookup(dates, path) is None:
            missing.append(path)
    if missing:
        raise SystemExit("sitemap lastmod missing a data date for: " + ", ".join(missing[:12]))
    home = dates.get("/")
    if home != off_d:
        raise SystemExit(f"homepage lastmod {home} is not the Treasury record date {off_d}")
    sm = open(os.path.join(R, "sitemap.xml"), encoding="utf-8").read()
    if f"<loc>{site}/</loc><lastmod>{off_d}</lastmod>" not in sm:
        raise SystemExit("sitemap homepage lastmod is not the Treasury record date")
    # One state and one country must not share the homepage's date unless that is really their as-of.
    tx = dates.get("/states/texas/")
    if tx == off_d:
        raise SystemExit("Texas lastmod was set to the Treasury date")
    page = open(os.path.join(R, "index.html"), encoding="utf-8").read()
    if 'class="updated"' not in page or f'data-updated="{off_d}"' not in page:
        raise SystemExit("homepage is missing Updated <Treasury date>")
    if f'"dateModified": "{off_d}"' not in page:
        raise SystemExit("homepage JSON-LD dateModified is not the Treasury date")
    lead = visible_lead(page)
    if not lead.startswith("As of ") or "U.S. Treasury, Debt to the Penny" not in lead or off_d[0:4] not in lead:
        raise SystemExit("homepage lead is not the dated official total: " + lead)
    print(f"freshness: {len(dates)} data dates, homepage {home}")
