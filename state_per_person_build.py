"""Comparison page: /states/debt-per-person/.

Census state-and-local debt outstanding (survey year on the state clock) divided by the
Census Vintage 2025 population on the same clock. The two dates are not the same day, and
the page says so. A state missing either figure is left off the table.
"""
import datetime as dt
import glob
import html
import json
import os

from debt_by_year_build import CSS

E = html.escape
ROOT = os.path.dirname(os.path.abspath(__file__))


def _usd0(n):
    return ("−$" if n < 0 else "$") + f"{abs(round(n)):,.0f}"


def _fdate(s):
    return dt.date.fromisoformat(s).strftime("%b %-d, %Y")


def rows(R):
    out, skipped = [], []
    for path in sorted(glob.glob(os.path.join(R, "places", "*.json"))):
        p = json.load(open(path))
        if p.get("kind") != "state" or p.get("status") != "live":
            continue
        comps = {c["key"]: c for c in p["components"]}
        pop = p.get("population") or {}
        if not pop.get("value") or not pop.get("as_of"):
            skipped.append({"slug": p["slug"], "reason": "no Census population on the state clock"})
            continue
        if p["slug"] == "district-of-columbia":
            if "local" not in comps:
                skipped.append({"slug": p["slug"], "reason": "no Census debt component"})
                continue
            total = int(comps["local"]["value"])
            debt_as_of = comps["local"]["as_of"]
        else:
            if "state" not in comps or "local" not in comps:
                skipped.append({"slug": p["slug"], "reason": "state and local debt are not both on the clock"})
                continue
            if comps["state"]["as_of"] != comps["local"]["as_of"]:
                skipped.append({"slug": p["slug"], "reason": "state and local as-of dates differ"})
                continue
            total = int(comps["state"]["value"]) + int(comps["local"]["value"])
            debt_as_of = comps["state"]["as_of"]
        per = total / pop["value"]
        out.append({
            "slug": p["slug"], "name": p["name"], "total": total, "debt_as_of": debt_as_of,
            "pop": int(pop["value"]), "pop_as_of": pop["as_of"], "per": per,
            "pop_source": pop.get("source_url") or "",
            "debt_source": comps["local"]["source_url"],
        })
    out.sort(key=lambda r: r["per"], reverse=True)
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out, skipped


def _bars(top):
    """Horizontal bars for the highest debt per person. Values are dollars per person."""
    if len(top) < 2:
        return ""
    W, H = 720, 28 * len(top) + 16
    hi = max(r["per"] for r in top) * 1.05 or 1
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img">',
             f'<title>Debt per person, highest states</title>']
    for i, r in enumerate(top):
        y = 8 + i * 28
        w = (W - 160) * (r["per"] / hi)
        parts.append(f'<text x="0" y="{y + 14}" fill="#c2ccda" font-size="12" font-family="sans-serif">{E(r["name"])}</text>')
        parts.append(f'<rect x="148" y="{y}" width="{w:.1f}" height="18" rx="3" fill="#ff4d5e"/>')
    parts.append("</svg>")
    return "".join(parts)


def build(R, SITE, with_analytics, stamp):
    data, skipped = rows(R)
    if len(data) < 51:
        raise RuntimeError(f"debt per person by state: expected 51 places, got {len(data)}; skipped {skipped}")
    dates = {r["debt_as_of"] for r in data}
    pops = {r["pop_as_of"] for r in data}
    if len(dates) != 1 or len(pops) != 1:
        raise RuntimeError(f"debt per person by state: mixed as-of dates {dates} {pops}")
    debt_as_of, pop_as_of = data[0]["debt_as_of"], data[0]["pop_as_of"]
    top, bottom = data[0], data[-1]
    title = "Debt per Person by State"
    desc = (f"Debt per person by state: {top['name']} is highest at {_usd0(top['per'])}, {bottom['name']} is lowest at {_usd0(bottom['per'])}. "
            f"Census state and local debt as of {_fdate(debt_as_of)}, Census population as of {_fdate(pop_as_of)}.")
    url = f"{SITE}/states/debt-per-person/"
    body = []
    for r in data:
        body.append(
            f'<tr><td class="num">{r["rank"]}</td><td><a href="../{r["slug"]}/">{E(r["name"])}</a></td>'
            f'<td class="num">{_usd0(r["per"])}</td><td class="num">{_usd0(r["total"])}</td>'
            f'<td class="num">{r["pop"]:,}</td><td><a href="../{r["slug"]}/debt-by-year/">By year</a></td></tr>'
        )
    answer = (f"The highest state and local debt per person is {top['name']} at {_usd0(top['per'])}. "
              f"The lowest is {bottom['name']} at {_usd0(bottom['per'])}. "
              f"Debt is the Census Bureau total outstanding on {_fdate(debt_as_of)}. "
              f"Population is the Census Vintage 2025 estimate for {_fdate(pop_as_of)}. "
              f"Those dates are not the same day, so this is not debt per person on a single date. "
              f"It is not a share of the federal debt.")
    faqs = [
        ("Which state has the highest debt per person?", answer),
        ("What debt is counted?",
         "Census total debt outstanding of the state government and of local governments. For the District of Columbia, Census publishes one government and that total is used. Unfunded pensions and the federal debt are not included."),
        ("Why do the debt date and the population date differ?",
         f"Census debt in this table is as of {_fdate(debt_as_of)}. The population is the July 1 Vintage 2025 estimate, {_fdate(pop_as_of)}. The page does not move either figure onto the other date."),
    ]
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": "Debt per person by state",
          "description": desc, "url": url, "isAccessibleForFree": True,
          "creator": {"@type": "Organization", "name": "Every Debt Clock", "url": SITE + "/"},
          "dateModified": debt_as_of, "spatialCoverage": {"@type": "Place", "name": "United States"},
          "isBasedOn": sorted({r["debt_source"] for r in data} | {r["pop_source"] for r in data if r["pop_source"]}),
          "keywords": ["debt per person by state", "state debt per capita", "state and local debt"]}
    ld_faq = {"@context": "https://schema.org", "@type": "FAQPage",
              "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]}
    faq_html = "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in faqs)
    pop_src = data[0]["pop_source"]
    rel = (
        '<a href="../"><span class="rn">US state debt clocks</span><span class="rw">Every state and DC</span></a>'
        '<a href="../../national-debt-per-person/"><span class="rn">National debt per person</span><span class="rw">Federal debt, a different total</span></a>'
        f'<a href="../{top["slug"]}/debt-by-year/"><span class="rn">{E(top["name"])} debt by year</span><span class="rw">The highest debt per person</span></a>'
    )
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}"><link rel="canonical" href="{E(url)}">
<meta property="og:type" content="article"><meta property="og:site_name" content="Every Debt Clock"><meta property="og:url" content="{E(url)}">
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">
<meta property="og:image" content="{SITE}/og/home.png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{E(title)}">
<meta name="twitter:description" content="{E(desc)}"><meta name="twitter:image" content="{SITE}/og/home.png">
<meta name="theme-color" content="#07090d"><link rel="apple-touch-icon" href="../../apple-touch-icon.png"><style>{CSS}</style>
<script type="application/ld+json">{json.dumps(ld).replace("</", "<\\\\/")}</script>
<script type="application/ld+json">{json.dumps(ld_faq).replace("</", "<\\\\/")}</script>
<link rel="icon" href="/favicon.ico" sizes="16x16 32x32 48x48"><link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png"><link rel="icon" type="image/svg+xml" href="/icon.svg">
</head><body><main>
<a class="brand" href="../../">EVERY <b>DEBT</b> CLOCK</a><a class="navembed" href="../../embed/" style="margin-left:12px;font-size:13px;font-weight:650">Embed</a>
<p class="k"><a href="../../">US debt clock</a> · <a href="../">State debt clocks</a></p>
<h1>Debt per person by state</h1>
<p><b>Answer.</b> {E(answer)}</p>
<figure>{_bars(data[:10])}<figcaption>Ten highest, dollars of Census state and local debt per resident. Debt as of {_fdate(debt_as_of)}. Population as of {_fdate(pop_as_of)}.</figcaption></figure>
<h2>All 50 states and the District of Columbia</h2>
<div class="tw"><table><tr><th>Rank</th><th>State</th><th>Debt per person</th><th>Total debt</th><th>Population</th><th></th></tr>{"".join(body)}</table></div>
<p>Debt as of {_fdate(debt_as_of)}, from the Census Bureau Annual Survey of State and Local Government Finances, table GS00LOCALFIN, total debt outstanding. Population as of {_fdate(pop_as_of)}, from Census Vintage 2025 state population estimates. Amounts are published in thousands of dollars. This is not the federal debt per person, which is on <a href="../../national-debt-per-person/">national debt per person</a>.</p>
<h2>Sources</h2>
<ul class="sources">
<li><a href="https://www.census.gov/programs-surveys/gov-finances/data/tables.html" rel="noopener">US Census Bureau, State and Local Government Finance tables</a></li>
<li><a href="{E(pop_src)}" rel="noopener">Census Bureau, Vintage 2025 state population estimates</a></li>
</ul>
<h2>Questions</h2>
{faq_html}
<a class="cta" href="../">Open the state debt clocks →</a>
<section class="related" id="related"><h2>Related</h2><div class="rg">{rel}</div></section>
<footer>Every figure on this page is a Census number. Page built {E(stamp)}. · <a href="../../methodology/">Methodology</a> · <a href="../../privacy/">Privacy</a> · Independent site, not affiliated with the U.S. government. Not financial advice.</footer>
</main></body></html>"""
    dest = os.path.join(R, "states", "debt-per-person")
    os.makedirs(dest, exist_ok=True)
    open(os.path.join(dest, "index.html"), "w").write(with_analytics(page) if with_analytics else page)
    flags_path = os.path.join(R, "data", "longtail_flags.json")
    flags = json.load(open(flags_path)) if os.path.exists(flags_path) else {}
    flags["states_missing_from_per_person"] = skipped
    json.dump(flags, open(flags_path, "w"), indent=1)
    open(flags_path, "a").write("\n")
    print(f"debt per person by state: {len(data)} rows, highest {top['name']} {_usd0(top['per'])}")
    return [url]


def check(R, site):
    data, skipped = rows(R)
    text = open(os.path.join(R, "states", "debt-per-person", "index.html")).read()
    if len(data) != 51 or skipped:
        raise SystemExit(f"debt per person table is short: {len(data)} skipped {skipped}")
    for r in data:
        if _usd0(r["per"]) not in text:
            raise SystemExit(f"debt per person missing {r['slug']}")
        if f"../{r['slug']}/debt-by-year/" not in text:
            raise SystemExit(f"debt per person missing year link for {r['slug']}")
    if f"{site}/states/debt-per-person/" not in open(os.path.join(R, "sitemap.xml")).read():
        raise SystemExit("sitemap missing /states/debt-per-person/")
    if "/states/debt-per-person/" not in open(os.path.join(R, "llms.txt")).read():
        raise SystemExit("llms.txt missing /states/debt-per-person/")
    print("debt per person by state check ok")
