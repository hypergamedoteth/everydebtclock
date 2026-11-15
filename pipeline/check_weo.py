#!/usr/bin/env python3
"""Check the IMF world-government debt file and, after build.py, the pages it produces.

Expected values are the October 2026 World Economic Outlook panel this site is built from:
186 economies with both 2026 series sum to about $120.53T; economies with both 2025 series
sum to about $110.94T; the United States is about $41.39T (126.79% of GDP); China is about
$22.49T (104.37% of GDP). The DataMapper rounds ratios to 0.1 percentage point, so the
tolerances allow that rounding. The unrounded World Bank mirror lands inside a much tighter band.

Never invents a figure: it only reads data/world_weo_debt.json and the built HTML.
"""
import glob, html, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TOL_USD = 0.03e12          # $0.03 trillion
TOL_RATIO = 0.05           # percentage points (API rounding is 0.1; 126.8 is inside 0.05 of 126.79)

def fail(msg):
    print("check_weo:", msg, file=sys.stderr)
    sys.exit(1)

def near_usd(got, exp, label):
    if abs(got - exp) > TOL_USD:
        fail(f"{label} is {got/1e12:.4f}T, expected about {exp/1e12:.2f}T")

def near_ratio(got, exp, label):
    if abs(got - exp) > TOL_RATIO:
        fail(f"{label} is {got}, expected about {exp}")

def main():
    path = os.path.join(ROOT, "data", "world_weo_debt.json")
    if not os.path.exists(path):
        fail("data/world_weo_debt.json is missing; run pipeline/fetch_world.py")
    D = json.load(open(path))
    economies = D.get("economies") or []
    if len(economies) != 186:
        fail(f"panel has {len(economies)} economies, expected 186")
    if len({e["iso3"] for e in economies}) != 186:
        fail("duplicate iso3 in the panel")
    panel_2026 = sum(e["debt_2026_usd"] for e in economies)
    panel_2025 = sum(e["debt_2025_usd"] for e in economies)
    broader = panel_2025 + sum(e["debt_2025_usd"] for e in (D.get("year_2025_only") or []))
    if panel_2026 != D["panel_2026_usd"] or panel_2025 != D["panel_2025_usd"]:
        fail("stored panel sums do not match the economy rows")
    if broader != D["broader_2025_usd"]:
        fail("stored broader 2025 sum does not match the rows")
    if D["broader_2025_count"] != 186 + len(D.get("year_2025_only") or []):
        fail("broader 2025 count does not match")
    near_usd(panel_2026, 120.53e12, "2026 panel")
    near_usd(broader, 110.94e12, "2025 both-series total")
    usa = next((e for e in economies if e["iso3"] == "USA"), None)
    chn = next((e for e in economies if e["iso3"] == "CHN"), None)
    if not usa or not chn:
        fail("USA or China missing")
    near_usd(usa["debt_2026_usd"], 41.39e12, "US debt")
    near_ratio(usa["ratio_2026"], 126.79, "US debt/GDP")
    near_usd(chn["debt_2026_usd"], 22.49e12, "China debt")
    near_ratio(chn["ratio_2026"], 104.37, "China debt/GDP")
    # The data file's clock field is from the last fetch. A country added since then is still marked "weo" in the file.
    # The build uses the live place files, so the check does too.
    import world_build
    live = {}
    for f in glob.glob(os.path.join(ROOT, "places", "*.json")):
        p = json.load(open(f))
        if p.get("kind") == "country" and p.get("status") == "live":
            iso = p.get("iso3") or world_build.ISO3.get(p.get("country") or "")
            if iso:
                live[iso] = p["slug"]
    for e in economies:
        if e["iso3"] == "USA":
            e["clock"] = "us"
        elif e["iso3"] in live:
            e["clock"] = "official"
            e["slug"] = live[e["iso3"]]
        else:
            e["clock"] = "weo"
    if usa["clock"] != "us" or chn["clock"] != "official":
        fail("US must stay on the Treasury clock and China on its official clock")
    for e in economies:
        path = e.get("ratio_path") or {}
        if "2025" not in path or "2026" not in path:
            fail(f"{e['iso3']} is missing a 2025–2026 point on the debt-to-GDP path")
        if not e["rate_usd_per_sec"]:
            fail(f"{e['iso3']} has a zero ticker")
        if e["debt_2026_usd"] <= 0 or e["debt_2025_usd"] <= 0:
            fail(f"{e['iso3']} has a non-positive stock")
        stock = int(round(e["ratio_2026"] / 100.0 * e["gdp_2026_usd"]))
        if abs(stock - e["debt_2026_usd"]) > 1:
            fail(f"{e['iso3']} debt is not ratio times GDP")
    skipped = {e["iso3"] for e in (D.get("skipped") or [])}
    for code in ("MAC", "AFG", "ECU", "LBN", "SEN", "SOM", "VEN", "YEM"):
        if code not in skipped:
            fail(f"skipped list is missing {code}")
    if "PSE" not in skipped and "WBG" not in skipped:
        fail("West Bank and Gaza should be skipped; 2026 debt ratio is missing")
    print(f"data ok: {D.get('precision_source')} {len(economies)} economies, "
          f"2026 ${panel_2026/1e12:.3f}T, 2025 broader ${broader/1e12:.3f}T, "
          f"US {usa['ratio_2026']}% ${usa['debt_2026_usd']/1e12:.3f}T, "
          f"China {chn['ratio_2026']}% ${chn['debt_2026_usd']/1e12:.3f}T, "
          f"skipped {len(skipped)}")

    sm = open(os.path.join(ROOT, "sitemap.xml")).read()
    for folder in ("world-government-debt", "global-debt-clock"):
        redir = open(os.path.join(ROOT, folder, "index.html")).read()
        if 'rel="canonical" href="https://everydebtclock.com/world/"' not in redir:
            fail(f"{folder} redirect canonical is not /world/")
        if "noindex" not in redir or 'url=../world/' not in redir:
            fail(f"{folder} redirect is missing noindex or the refresh to /world/")
        if f"https://everydebtclock.com/{folder}/" in sm:
            fail(f"sitemap should not list the /{folder}/ redirect")
    llms = open(os.path.join(ROOT, "llms.txt")).read()
    if "Redirects to /world/" not in llms:
        fail("llms.txt does not say the old world URLs redirect to /world/")
    world = open(os.path.join(ROOT, "world", "index.html")).read()
    for phrase in ("What this page counts", "General government gross debt", 'id="imf"', "GGXWDG_NGDP",
                   "How much is world government debt?", "IMF estimate", "harmonized"):
        if phrase not in world and phrase.lower() not in world.lower():
            fail(f"the /world/ page is missing {phrase!r}")
    if "coming soon" in world.lower():
        fail("world page contains coming soon")
    weo_pages = [e for e in economies if e["clock"] == "weo"]
    n_clock = sum(e["clock"] in ("weo", "official", "us") for e in economies)
    if n_clock != 186:
        fail(f"clock labels cover {n_clock} economies, expected 186")
    noindex = []
    for e in weo_pages:
        doc = open(os.path.join(ROOT, "countries", e["slug"], "index.html")).read()
        _country_checks(doc, e)
        loc = f"https://everydebtclock.com/countries/{e['slug']}/"
        if 'name="robots" content="noindex"' in doc:
            noindex.append(e["slug"])
            if loc in sm:
                fail(f"noindex page is in the sitemap: {e['slug']}")
        elif loc not in sm:
            fail(f"sitemap missing {e['slug']}")
    print("noindex:", ", ".join(noindex) if noindex else "none")
    print(f"pages ok: world government debt, {len(weo_pages)} new country clocks, redirect, sitemap, llms.txt")

def _page_checks(page, D, usa, economies):
    if "coming soon" in page.lower():
        fail("world government debt page contains coming soon")
    for phrase in ("What this page counts", "not a live ledger", "exchange-rate effects", "IMF World Economic Outlook", "GGXWDG_NGDP",
                   "World Government Debt Clock: IMF Estimate for 186 Economies", "FAQPage",
                   "How much is world government debt?", "Which countries owe the most?", "What share of world GDP?",
                   "How is this estimated?", "How is this different from the World Debt Clock?"):
        if phrase not in page:
            fail(f"world government debt page is missing {phrase!r}")
    if "Page built from IMF data read " not in page:
        fail("world government debt page is missing the stable data-read line")
    if 'href="../world/"' not in page:
        fail("world government debt page does not link to the official world clock")
    if page.count('data-iso="') != 186:
        fail(f"table has {page.count('data-iso=\"')} rows, expected 186")
    if f'{usa["ratio_2026"]:.2f}%' not in page:
        fail("US debt-to-GDP ratio is not shown from the data file")
    m = re.search(r'id="t-total"[^>]*data-r="([^"]+)"', page)
    if not m or float(m.group(1)) == 0:
        fail("world government debt ticker is missing or zero")
    if abs(float(m.group(1)) - D["rate_usd_per_sec"]) / abs(D["rate_usd_per_sec"]) > 1e-4:
        fail("world ticker rate does not match the data file")
    rel = re.search(r'<section class="related".*?</section>', page, re.S)
    if not rel or len(re.findall(r"<a ", rel.group(0))) != 3:
        fail("world government debt page does not have exactly 3 related links")

def _country_checks(doc, e):
    if "coming soon" in doc.lower():
        fail(f"{e['slug']} contains coming soon")
    if "does not publish a daily debt stock" in doc:
        fail(f"{e['slug']} still claims the country publishes no daily debt stock")
    if "source tier: harmonized" in doc:
        for phrase in ("Quarterly Public Sector Debt", "As of", 'id="path"', "FAQPage", 'id="t-total"',
                       f"<title>{html.escape(e['name'])} National Debt Clock</title>"):
            if phrase not in doc:
                fail(f"{e['slug']} upgraded page is missing {phrase!r}")
        if "This site has no official-source clock" in doc:
            fail(f"{e['slug']} still says it has no official-source clock")
        rel = re.search(r'<section class="related".*?</section>', doc, re.S)
        if not rel or len(re.findall(r"<a ", rel.group(0))) != 3:
            fail(f"{e['slug']} does not have exactly 3 related links")
        return
    for phrase in ("This site has no official-source clock", 'id="path"', 'id="peers"', "ranks "):
        if phrase not in doc:
            fail(f"{e['slug']} is missing {phrase!r}")
    if f"<title>{html.escape(e['name'])} National Debt Clock</title>" not in doc:
        fail(f"{e['slug']} title is not the search title")
    for phrase in ("not a live ledger", "exchange-rate effects", "IMF World Economic Outlook", "GGXWDG_NGDP", 'class="src"', "FAQPage"):
        if phrase not in doc:
            fail(f"{e['slug']} is missing {phrase!r}")
    if 'id="qf"' not in doc:
        fail(f"{e['slug']} is missing the search box")
    m = re.search(r'id="t-total"[^>]*data-r="([^"]+)"', doc)
    if not m:
        fail(f"{e['slug']} ticker is missing")
    got = float(m.group(1))
    if got == 0 or abs(got - e["rate_usd_per_sec"]) / abs(e["rate_usd_per_sec"]) > 1e-4:
        fail(f"{e['slug']} ticker {got} does not match {e['rate_usd_per_sec']}")
    rel = re.search(r'<section class="related".*?</section>', doc, re.S)
    if not rel or len(re.findall(r"<a ", rel.group(0))) != 3:
        fail(f"{e['slug']} does not have exactly 3 related links")
    if f'countries/{e["slug"]}/' in rel.group(0):
        fail(f"{e['slug']} related block links to itself")

if __name__ == "__main__":
    main()
