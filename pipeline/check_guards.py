#!/usr/bin/env python3
"""Fail the build when a known accuracy or ops failure is back.

Each check matches a fix: awards filter, stale clocks, Norway's hold, the IMF gap
note, one per-person basis, visible Census sampling error, projection copy, and labels.
A held clock (stale, fixed, or no rate) must not say that it projects or ticks.
"""
import html
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import places_build
import world_sources

FORBIDDEN_CAPTION = "Not most salaries or benefit checks"
MEDICARE = ("93.770", "93.773", "93.774")
SS = ("96.001", "96.002", "96.004", "96.006", "96.007")
ERRORS = []


def fail(msg):
    ERRORS.append(msg)


def load(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return json.load(f)


def page(rel):
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        fail(f"missing page {rel}")
        return ""
    return open(path, encoding="utf-8").read()


def money0(cents):
    n = int(round(cents / 100))
    return f"${n:,}"


def check_awards():
    doc = load("data/state_federal.json")["usaspending"]
    listed = doc.get("exclude_cfda") or []
    for code in MEDICARE + SS:
        if code not in listed:
            fail(f"USAspending denylist missing {code}")
    gross, net, med, excluded = (doc.get(k) or {} for k in (
        "states_gross_cents", "states_cents", "states_medicare_cents", "states_excluded_cents"))
    if len(net) != 51:
        fail(f"USAspending net states {len(net)}")
    golden = load("pipeline/awards_golden.json")
    for slug, g in gross.items():
        cut = excluded.get(slug)
        shown = net.get(slug)
        if cut is None or shown is None or shown != g - cut:
            fail(f"{slug}: displayed awards are not gross minus the CFDA denylist")
            continue
        share = (med.get(slug) or 0) / g if g else 0
        html = page(f"states/{slug}/index.html")
        if FORBIDDEN_CAPTION in html:
            fail(f"{slug}: caption still says benefit checks are excluded without the denylist")
        if "Excludes Medicare fee-for-service (CFDA 93.770, 93.773, 93.774)" not in html:
            fail(f"{slug}: awards caption does not name the Medicare fee-for-service exclusion")
        if "Social Security benefit payments (CFDA 96.001, 96.002, 96.004, 96.006, 96.007)" not in html:
            fail(f"{slug}: awards caption does not name the Social Security exclusion")
        if money0(shown) not in html:
            fail(f"{slug}: page is missing the filtered award total {money0(shown)}")
        if (med.get(slug) or 0) > (cut or 0):
            fail(f"{slug}: Medicare fee-for-service is not fully inside the excluded amount")
        if share >= 0.25 and "contractor's place of performance" not in html:
            fail(f"{slug}: Medicare is {share:.0%} of the unfiltered total and the page has no contractor place-of-performance note")
    for slug, spec in golden.items():
        if net.get(slug) != spec["cents"]:
            fail(f"golden {slug}: displayed {net.get(slug)} cents, snapshot {spec['cents']}")
        g = gross.get(slug) or 0
        share = (med.get(slug) or 0) / g if g else 0
        if share < spec["medicare_share_min"]:
            fail(f"golden {slug}: stored Medicare share {share:.1%} is below {spec['medicare_share_min']:.0%} (filter not applied to the snapshot)")


def check_stale_and_holds(places_api):
    by_slug = {p["slug"]: p for p in places_api["places"]}
    for fn in sorted(os.listdir(os.path.join(ROOT, "places"))):
        if not fn.endswith(".json"):
            continue
        place = json.load(open(os.path.join(ROOT, "places", fn), encoding="utf-8"))
        if place.get("status") != "live" or place.get("kind") != "country":
            continue
        fresh = places_build.freshness(place)
        row = by_slug.get(place["slug"])
        if not row:
            fail(f"api/places.json missing {place['slug']}")
            continue
        html = page(f"countries/{place['slug']}/index.html")
        if fresh["stale"]:
            if row["rate"] != 0:
                fail(f"{place['slug']} is stale ({fresh['age']} days, {fresh['freq']}) and still ticking at rate {row['rate']}")
            if "STALE" not in html:
                fail(f"{place['slug']} is stale and the page has no STALE label")
            if 'id="t-total"' in html:
                chunk = html[html.find('id="t-total"'):html.find('id="t-total"') + 400]
                if 'data-r="0"' not in chunk:
                    fail(f"{place['slug']} stale hero is still ticking")
        if place.get("hold_trend") and row["rate"] != 0:
            fail(f"{place['slug']} hold_trend is set and the clock rate is {row['rate']}")


def check_world_review():
    api = load("api/world.json")
    rows = {r["iso3"]: r for r in api["countries"]}
    review = api.get("review_over_25pct") or []
    if not review:
        fail("review_over_25pct is empty")
    for item in review:
        row = rows.get(item["iso3"])
        if not row:
            fail(f"review row {item['iso3']} missing from the world table")
            continue
        if row.get("trend") == "official" and row.get("trend_usd_per_sec"):
            fail(f"{item['iso3']} is on review_over_25pct and the world clock is still ticking it")
        if abs(row.get("trend_usd_per_sec") or 0) > 0 and row.get("trend") == "official":
            fail(f"{item['iso3']} official world trend is {row.get('trend_usd_per_sec')}")
    nor = rows.get("NOR")
    if nor and nor.get("projected_usd") != nor.get("debt_usd"):
        fail(f"Norway projected_usd {nor.get('projected_usd')} is not the anchored stock {nor.get('debt_usd')}")


def check_imf_explain():
    api = load("api/world.json")
    places = {}
    for fn in os.listdir(os.path.join(ROOT, "places")):
        if not fn.endswith(".json"):
            continue
        p = json.load(open(os.path.join(ROOT, "places", fn), encoding="utf-8"))
        iso = p.get("iso3")
        if iso:
            places[iso] = p
    for row in api["countries"]:
        gap = None
        # The review file stores gap on review rows only. Recompute from the two stocks on the row.
        imf = row.get("imf_debt_2026_usd")
        if imf:
            gap = row["debt_usd"] / imf - 1
        if gap is None or abs(gap) <= 0.15:
            continue
        place = places.get(row.get("iso3"))
        if not place:
            continue
        gg_clock = world_sources.is_gg_text(place.get("world_measure")) or world_sources.is_gg_text(place.get("headline_long"))
        measure = (row.get("measure") or "")
        if not (gg_clock and "general government" in measure.lower()):
            continue
        explain = (place.get("imf_explain") or "").strip()
        if not explain:
            fail(f"{place['slug']}: |IMF gap| {gap:.1%} and both sides are general government, but imf_explain is empty")
            continue
        raw = page(f"countries/{place['slug']}/index.html")
        visible = html.unescape(raw)
        if explain not in visible:
            fail(f"{place['slug']}: imf_explain is not on the page")
        if gg_clock and "when the clock is central or federal debt" in visible:
            fail(f"{place['slug']}: page still says the IMF figure is wider only when the clock is central")


def check_per_person():
    api = load("api/daily.json")
    if api.get("per_person_basis_code") != "official_census":
        fail(f"per_person_basis_code is {api.get('per_person_basis_code')!r}, expected official_census")
    official = api.get("debt_per_person_official")
    if not isinstance(official, (int, float)):
        fail("debt_per_person_official missing")
        return
    shown = f"${official:,.2f}"
    for fn in sorted(os.listdir(os.path.join(ROOT, "places"))):
        p = json.load(open(os.path.join(ROOT, "places", fn), encoding="utf-8"))
        if p.get("kind") != "state" or p.get("status") != "live":
            continue
        raw = page(f"states/{p['slug']}/index.html")
        start = raw.find('id="t-fed_pp"')
        end = raw.find('id="t-fed_share"', start if start >= 0 else 0)
        chunk = raw[start:end] if start >= 0 and end > start else ""
        if shown not in chunk:
            fail(f"{p['slug']}: federal debt per resident is not {shown}")
        if "data-r=" in chunk:
            fail(f"{p['slug']}: federal debt per resident is still ticking")


def check_sampling_and_copy(places_api):
    by_slug = {p["slug"]: p for p in places_api["places"]}
    for fn in sorted(os.listdir(os.path.join(ROOT, "places"))):
        p = json.load(open(os.path.join(ROOT, "places", fn), encoding="utf-8"))
        if p.get("kind") != "state" or p.get("status") != "live":
            continue
        html = page(f"states/{p['slug']}/index.html")
        hits = places_build._cv_hits(p)
        if hits and "High sampling error" not in html:
            fail(f"{p['slug']}: Census CV {hits} is not in a visible sampling-error note")
        row = by_slug.get(p["slug"])
        if row and row["rate"] and not p.get("hold_trend"):
            if "The large figure is the official" not in html or "does not tick" not in html:
                fail(f"{p['slug']}: ticking projection sits beside the official stock without saying the large figure does not tick")
        if "gross interest" not in html.lower():
            fail(f"{p['slug']}: interest share is not labelled gross")
        if "dated before the 2025 workforce cuts" not in html:
            fail(f"{p['slug']}: OPM federal civilian count is not dated before the 2025 workforce cuts")


def held_page_text(raw):
    """Visible copy plus attribute text. Scripts, styles, and the IMF comparison profile are set aside."""
    raw = re.sub(r'<section[^>]*\bid="profile"[\s\S]*?</section>', " ", raw)
    raw = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<style\b[^>]*>.*?</style>", " ", raw, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", text)


def check_held_copy():
    """A held clock must not say it projects or ticks. The world table must say which rows are held."""
    for fn in sorted(os.listdir(os.path.join(ROOT, "places"))):
        if not fn.endswith(".json"):
            continue
        place = json.load(open(os.path.join(ROOT, "places", fn), encoding="utf-8"))
        if place.get("status") != "live":
            continue
        if places_build.calc(place)["rate"]:
            continue
        sec = "states" if place.get("kind") == "state" else "countries"
        raw = page(f"{sec}/{place['slug']}/index.html")
        if not raw:
            continue
        hits = places_build.projection_claims(held_page_text(raw))
        if hits:
            fail(f"{place['slug']}: held clock still says it projects or ticks ({hits[0]})")
        embed = f"embed/{sec}/{place['slug']}/index.html"
        embed_raw = page(embed) if os.path.exists(os.path.join(ROOT, embed)) else ""
        embed_hits = places_build.projection_claims(held_page_text(embed_raw)) if embed_raw else []
        if embed_hits:
            fail(f"{place['slug']}: held embed still says it projects or ticks ({embed_hits[0]})")
    world_path = os.path.join(ROOT, "api", "world.json")
    if not os.path.exists(world_path):
        fail("api/world.json is missing")
        return
    world = json.load(open(world_path, encoding="utf-8"))
    fixed = [r for r in (world.get("countries") or []) if r.get("trend") == "fixed"]
    if not fixed:
        return
    html_world = page("world/index.html")
    if "held fixed at the last official value" not in html_world or "not projected" not in html_world:
        fail("world table has held rows but does not say they stay fixed and are not projected")


def check_egypt_source():
    import fetch_egypt
    import fetch_taiwan
    if not getattr(fetch_taiwan, "URLS", None):
        fail("Taiwan fetcher has no URL list")
    if not getattr(fetch_egypt, "PAGES", None):
        fail("Egypt fetcher has no fallback URL list")
        return
    errors = []
    for url in fetch_egypt.PAGES:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "everydebtclock-ci"})
            with urllib.request.urlopen(req, timeout=25) as r:
                body = r.read().decode("utf-8", "replace")
            if "Budget_Sector_Statistical_Debt_Bulletin_" in body:
                return
            errors.append(f"{url}: no bulletin links")
        except Exception as e:
            errors.append(f"{url}: {e}")
    fail("Egypt bulletin URLs failed: " + "; ".join(errors))


# A URL token ending in an encoded quote. Crawlers that unescape &quot; request that path.
QUOTE_GLUE = re.compile(
    r"https?://[^\s<>\"']*(?:&quot;|&#34;|&#x22;|%22)(?=$|[\s<>\"'])",
    re.I,
)
LD_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.I | re.S)
SKIP_WALK = {".git", "cache", "pipeline", "__pycache__", "node_modules", ".venv", "venv", "wealth_src"}
AGENT_PAGES = (
    "index.html",
    "national-debt-by-year/index.html",
    "world/index.html",
    "countries/india/index.html",
    "how-much-is-the-national-debt/index.html",
    "countries/japan/index.html",
    "countries/egypt/index.html",
    "countries/russia/index.html",
    "national-debt-by-president/index.html",
    "national-debt-per-person/index.html",
)


def _walk_generated():
    for dirpath, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_WALK and not d.startswith(".")]
        for name in files:
            if name.endswith((".html", ".xml", ".txt", ".json")):
                yield os.path.join(dirpath, name)


def check_stray_quotes():
    """Fail if a generated href, src, or url ends with a stray quote."""
    from html.parser import HTMLParser

    class Attrs(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.bad = []

        def handle_starttag(self, tag, attrs):
            d = {}
            for key, value in attrs:
                if key and value is not None:
                    d[key.lower()] = value
            for key in ("href", "src", "url"):
                value = d.get(key) or ""
                if value.endswith('"') or value.endswith("%22") or value.endswith("&quot;"):
                    self.bad.append(f"{tag} {key}={value[:160]}")
            prop = (d.get("property") or d.get("name") or "").lower()
            if prop in ("og:image", "og:url", "twitter:image") and d.get("content"):
                value = d["content"]
                if value.endswith('"') or value.endswith("%22") or value.endswith("&quot;"):
                    self.bad.append(f"{prop}={value[:160]}")

    for path in _walk_generated():
        rel = os.path.relpath(path, ROOT)
        # Daily snapshots are archives, not the pages crawlers read for links.
        if rel.startswith("data/data-"):
            continue
        text = open(path, encoding="utf-8", errors="replace").read()
        for glue in QUOTE_GLUE.finditer(text):
            pre = text[max(0, glue.start() - 80):glue.start()]
            # Percent-encoded SVG favicons contain xmlns=%22http://www.w3.org/2000/svg%22.
            if "data:" in pre or "%3C" in pre or "xmlns=" in pre:
                continue
            fail(f"{rel}: URL ends with a stray quote ({glue.group(0)[:140]})")
            return
        if not rel.endswith(".html"):
            continue
        parser = Attrs()
        try:
            parser.feed(text)
        except Exception as exc:
            fail(f"{rel}: could not read attributes ({exc})")
            return
        if parser.bad:
            fail(f"{rel}: {parser.bad[0]}")
            return


def check_jsonld():
    """Every JSON-LD block must parse. The pages agents quote must carry a figure, a date, and a source."""
    for path in _walk_generated():
        if not path.endswith(".html"):
            continue
        rel = os.path.relpath(path, ROOT)
        text = open(path, encoding="utf-8", errors="replace").read()
        for block in LD_RE.findall(text):
            try:
                json.loads(block)
            except Exception as exc:
                fail(f"{rel}: JSON-LD does not parse ({exc})")
                return
    for rel in AGENT_PAGES:
        text = page(rel)
        if not text:
            continue
        if 'rel="canonical"' not in text:
            fail(f"{rel}: missing canonical")
        desc = re.search(r'<meta name="description" content="([^"]*)"', text)
        if not desc or not re.search(r"\d", html.unescape(desc.group(1))):
            fail(f"{rel}: meta description has no figure")
        blocks = LD_RE.findall(text)
        if not blocks:
            fail(f"{rel}: missing JSON-LD")
            continue
        kinds = []
        for block in blocks:
            try:
                kinds.append(json.loads(block).get("@type"))
            except Exception:
                kinds.append(None)
        if not any(k in ("Dataset", "FAQPage") for k in kinds):
            fail(f"{rel}: JSON-LD is not Dataset or FAQPage")
        visible = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.S | re.I)
        visible = re.sub(r"<style\b[^>]*>.*?</style>", " ", visible, flags=re.S | re.I)
        visible = html.unescape(re.sub(r"<[^>]+>", " ", visible))
        if not re.search(r"\bas of\b", visible, re.I):
            fail(f"{rel}: no as-of date in server-rendered text")
        if not re.search(r"\b(source|treasury|imf|census)\b", visible, re.I):
            fail(f"{rel}: no source in server-rendered text")
    for rel in (
        "national-debt-by-year/index.html",
        "national-debt-by-president/index.html",
    ):
        text = page(rel)
        if text and "Dataset" not in text:
            fail(f"{rel}: missing Dataset JSON-LD")
    pres_dir = os.path.join(ROOT, "national-debt-by-president")
    if os.path.isdir(pres_dir):
        for name in os.listdir(pres_dir):
            path = os.path.join(pres_dir, name, "index.html")
            if os.path.isfile(path) and "Dataset" not in open(path, encoding="utf-8").read():
                fail(f"national-debt-by-president/{name}/: missing Dataset JSON-LD")


def main():
    places_api = load("api/places.json")
    check_awards()
    check_stale_and_holds(places_api)
    check_world_review()
    check_imf_explain()
    check_per_person()
    check_sampling_and_copy(places_api)
    check_held_copy()
    check_egypt_source()
    check_stray_quotes()
    check_jsonld()
    if ERRORS:
        print(f"check_guards: {len(ERRORS)} failure(s)", file=sys.stderr)
        for msg in ERRORS[:40]:
            print("check_guards:", msg, file=sys.stderr)
        sys.exit(1)
    print("check_guards ok")


if __name__ == "__main__":
    main()
