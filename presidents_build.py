"""One page per US president: /national-debt-by-president/<slug>/.

Figures are the same Treasury records as /national-debt-by-president/: Debt to the Penny
on or before the date from 1993, and Historical Debt Outstanding before that. Per person
uses the Census July 1 population of the calendar year of that record, the same series
as /national-debt-per-person/. A year the Census series does not publish is left blank.

A president with no term that has two different Treasury records is not given a page.
"""
import datetime as dt
import html
import json
import os
import re
import sys

import topics_build
from debt_by_year_build import CSS, chart

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import series

E = html.escape
UP = "../.."
DTP = "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny"
HDO = "https://fiscaldata.treasury.gov/datasets/historical-debt-outstanding/historical-debt-outstanding"
POP_PAGE = "https://www.census.gov/data/tables/time-series/demo/popest/2020s-national-total.html"


def slug_for(name):
    s = name.lower().replace(".", "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def _round_dollar(n):
    """Nearest dollar, the same rounding the table prints."""
    return int(round(n))


def _usd0(n):
    if n is None:
        return "—"
    return ("−$" if n < 0 else "$") + f"{abs(_round_dollar(n)):,}"


def _footed_change(start_amount, end_amount):
    """Change the table can subtract: rounded end minus rounded start."""
    change = _round_dollar(end_amount) - _round_dollar(start_amount)
    pct = change / _round_dollar(start_amount) * 100 if _round_dollar(start_amount) else None
    return change, pct


def _usd2(n):
    if n is None:
        return "—"
    return ("−$" if n < 0 else "$") + f"{abs(n):,.2f}"


def _fdate(s):
    return dt.date.fromisoformat(s).strftime("%b %-d, %Y")


def _official_close(R):
    D = json.load(open(os.path.join(R, "data", "data.json")))
    T, M = D["tickers"], D["meta"]
    td = T.get("debt_total") or {}
    cl = sorted((M.get("debt_closes") or []), key=lambda c: c[0], reverse=True)
    if td.get("status") == "ok" and cl and cl[0][0] == td.get("as_of"):
        return cl[0][0], float(cl[0][1]), M.get("debt_by_fy") or []
    if td.get("status") == "ok":
        return td.get("as_of"), td.get("base"), M.get("debt_by_fy") or []
    return None, None, M.get("debt_by_fy") or []


def _pop_map(H):
    return {p["year"]: p for p in H["population_by_year"]}


def _per(amount, date, pops):
    """Debt divided by Census July 1 population of that calendar year, or None."""
    if amount is None or not date:
        return None
    rec = pops.get(int(date[:4]))
    if not rec or not rec.get("population"):
        return None
    return amount / rec["population"], rec


def _term_row(name, n, start, end, H, hdo, off_d, off_v, pops):
    a = topics_build._point(start, H, hdo)
    open_term = end is None
    if open_term:
        b = {"date": off_d, "amount": off_v, "basis": "dtp", "requested": off_d} if off_d and off_v is not None else None
    else:
        b = topics_build._point(end, H, hdo)
    same = a and b and a["date"] == b["date"]
    change = pct = None
    if a and b and not same and a.get("amount"):
        change, pct = _footed_change(a["amount"], b["amount"])
    return {
        "name": name, "n": n, "start": start, "end": end, "open": open_term,
        "a": a, "b": b, "change": change, "pct": pct,
        "per_a": _per(a["amount"], a["date"], pops) if a else None,
        "per_b": _per(b["amount"], b["date"], pops) if b else None,
    }


def records(R, off_d=None, off_v=None, hdo=None):
    """(published, skipped). published is one dict per president, terms in order."""
    if off_d is None or off_v is None or hdo is None:
        d, v, fy = _official_close(R)
        off_d = off_d or d
        off_v = off_v if off_v is not None else v
        hdo = fy if hdo is None else hdo
    H = topics_build._load(R)
    pops = _pop_map(H)
    by_name = []
    order = []
    grouped = {}
    for name, n, start, end in series.TERMS:
        if name not in grouped:
            order.append(name)
            grouped[name] = []
        grouped[name].append(_term_row(name, n, start, end, H, hdo, off_d, off_v, pops))
    published, skipped = [], []
    slugs = {}
    for name in order:
        terms = grouped[name]
        slug = slug_for(name)
        if slug in slugs:
            raise RuntimeError(f"president slug collision: {slug}")
        slugs[slug] = name
        usable = [t for t in terms if t["change"] is not None]
        if not usable:
            skipped.append({
                "name": name,
                "slug": slug,
                "reason": "The Treasury series used here does not have two different records inside the term, so the change is not shown and no page is published.",
            })
            continue
        first = next((t["a"] for t in terms if t["a"]), None)
        last = next((t["b"] for t in reversed(terms) if t["b"]), None)
        span_change = span_pct = None
        if first and last and first["date"] != last["date"] and first.get("amount"):
            span_change, span_pct = _footed_change(first["amount"], last["amount"])
        published.append({
            "name": name, "slug": slug, "terms": terms,
            "first": first, "last": last, "change": span_change, "pct": span_pct,
            "per_first": _per(first["amount"], first["date"], pops) if first else None,
            "per_last": _per(last["amount"], last["date"], pops) if last else None,
            "open": terms[-1]["open"],
        })
    by_name = published
    for i, p in enumerate(by_name):
        p["prev"] = by_name[i - 1] if i else None
        p["next"] = by_name[i + 1] if i + 1 < len(by_name) else None
    return by_name, skipped, H


def _cell(p, fdate, open_=False):
    if not p:
        return "<td>No record on or before this date</td>"
    return f"<td class=\"num\">{_usd0(p['amount'])}<span class=\"when\">{E(topics_build._basis_label(p, fdate, open_))}</span></td>"


def _per_cell(pair):
    if not pair:
        return "<td class=\"num\">—</td>"
    val, rec = pair
    return f"<td class=\"num\">{_usd2(val)}<span class=\"when\">Census July 1, {rec['year']}</span></td>"


def _page(R, SITE, with_analytics, stamp, p, H):
    fdate = _fdate
    name = p["name"]
    first, last = p["first"], p["last"]
    if p["change"] is None:
        raise RuntimeError(f"{name}: no span to publish")
    verb = "higher" if p["change"] > 0 else "lower" if p["change"] < 0 else "unchanged"
    end_label = "the latest Treasury close" if p["open"] else "the end of the last term"
    answer = (f"The Treasury total was {_usd0(first['amount'])} on {fdate(first['date'])} and {_usd0(last['amount'])} on {fdate(last['date'])} "
              f"({end_label}). The difference is {_usd0(p['change'])} ({p['pct']:+.1f}%), so the debt was {verb}. "
              f"That is the change between those two Treasury figures. It is not a measure of what the president added: "
              f"Congress writes tax and spending laws, and terms are not the same length.")
    per_bits = []
    if p["per_first"]:
        per_bits.append(f"{_usd2(p['per_first'][0])} per person at the first record (Census July 1, {p['per_first'][1]['year']})")
    if p["per_last"]:
        per_bits.append(f"{_usd2(p['per_last'][0])} per person at the last record (Census July 1, {p['per_last'][1]['year']})")
    per_sentence = (" Per person: " + ", and ".join(per_bits) + ".") if per_bits else ""
    per_gap = (" Per person divides the Treasury figure by the Census Bureau's July 1 resident population of that calendar year. "
               "It is not the population on the exact day. This site's July 1 series starts in 1900, and it has no July 1 figure for a later year until Census publishes it, so those cells are blank.")
    title = f"National Debt under {name}"
    desc = (f"National debt under {name}: {_usd0(first['amount'])} on {fdate(first['date'])}, {_usd0(last['amount'])} on {fdate(last['date'])}, "
            f"a change of {_usd0(p['change'])} ({p['pct']:+.1f}%). Treasury figures.")
    if len(desc) > 170:
        desc = f"National debt under {name}: {_usd0(last['amount'])} on {fdate(last['date'])}, {p['pct']:+.1f}% from {fdate(first['date'])}. Treasury figures."
    url = f"{SITE}/national-debt-by-president/{p['slug']}/"
    rows = []
    for t in p["terms"]:
        term = f"{fdate(t['start'])} – " + ("in progress" if t["open"] else fdate(t["end"]))
        ch = "—" if t["change"] is None else _usd0(t["change"])
        pct = "—" if t["pct"] is None else f"{t['pct']:+.1f}%"
        rows.append(
            f"<tr><td>{topics_build._ord(t['n'])} term</td><td>{term}</td>{_cell(t['a'], fdate)}{_per_cell(t['per_a'])}"
            f"{_cell(t['b'], fdate, t['open'])}{_per_cell(t['per_b'])}<td class=\"num\">{ch}</td><td class=\"num\">{pct}</td></tr>"
        )
    ends = [t for t in p["terms"] if t["b"]]
    chart_rows = [{"year": int(t["b"]["date"][:4]), "date": t["b"]["date"], "amount": t["b"]["amount"]} for t in ends]
    chart_title = f"US national debt at the end of each {name} term"
    if len(chart_rows) >= 2:
        chart_html = (f"<figure>{chart(chart_rows, chart_title)}"
                      f"<figcaption>{E(chart_title)}. Each point is the Treasury record at the end of that term, or the latest close if the term is in progress.</figcaption></figure>")
    else:
        chart_html = ""
    related = [
        ("National debt by president", "../", "Every term in one table"),
        ("US national debt by year", f"{UP}/national-debt-by-year/", "Treasury totals by fiscal year"),
        ("National debt per person", f"{UP}/national-debt-per-person/", "The same total, per resident"),
    ]
    if p["prev"]:
        related[2] = (f"National debt under {p['prev']['name']}", f"../{p['prev']['slug']}/", "The previous president in this table")
    extra_link = ""
    if p["next"]:
        extra_link = f'<p><a href="../{p["next"]["slug"]}/">National debt under {E(p["next"]["name"])}</a></p>'
    rel_html = "".join(f'<a href="{E(href)}"><span class="rn">{E(n)}</span><span class="rw">{E(w)}</span></a>' for n, href, w in related)
    faqs = [
        (f"What was the national debt under {name}?", answer),
        ("Does the change show what the president added to the debt?",
         "No. It is the difference between the Treasury total at the start and at the end. Term lengths differ, and spending and tax laws are passed by Congress."),
        ("Is the per-person figure the population on that day?",
         "No. It is the Treasury figure divided by the Census Bureau's July 1 resident population of that calendar year, when that year is in the series this site uses. The series starts in 1900."),
    ]
    ld = {
        "@context": "https://schema.org", "@type": "Dataset",
        "name": f"National debt under {name}", "description": desc, "url": url,
        "isAccessibleForFree": True,
        "creator": {"@type": "Organization", "name": "Every Debt Clock", "url": SITE + "/"},
        "dateModified": dt.date.today().isoformat(),
        "temporalCoverage": f"{first['date'][:4]}/{last['date'][:4]}",
        "isBasedOn": [DTP, HDO],
        "keywords": [f"national debt under {name}", f"{name} national debt", "US debt by president"],
    }
    ld_faq = {"@context": "https://schema.org", "@type": "FAQPage",
              "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]}
    faq_html = "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in faqs)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}"><link rel="canonical" href="{E(url)}">
<meta property="og:type" content="article"><meta property="og:site_name" content="Every Debt Clock"><meta property="og:url" content="{E(url)}">
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">
<meta property="og:image" content="{SITE}/og/home.png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{E(title)}">
<meta name="twitter:description" content="{E(desc)}"><meta name="twitter:image" content="{SITE}/og/home.png">
<meta name="theme-color" content="#07090d"><link rel="apple-touch-icon" href="{UP}/apple-touch-icon.png"><style>{CSS}
td .when{{display:block;color:#8a97ab;font-size:12px;font-weight:400;white-space:normal}}</style>
<script type="application/ld+json">{json.dumps(ld).replace("</", "<\\\\/")}</script>
<script type="application/ld+json">{json.dumps(ld_faq).replace("</", "<\\\\/")}</script>
<link rel="icon" href="/favicon.ico" sizes="16x16 32x32 48x48"><link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png"><link rel="icon" type="image/svg+xml" href="/icon.svg">
</head><body><main>
<a class="brand" href="{UP}/">EVERY <b>DEBT</b> CLOCK</a><a class="navembed" href="{UP}/embed/" style="margin-left:12px;font-size:13px;font-weight:650">Embed</a>
<p class="k"><a href="{UP}/">US debt clock</a> · <a href="../">National debt by president</a></p>
<h1>National debt under {E(name)}</h1>
<p><b>Answer.</b> {E(answer)}{E(per_sentence)}</p>
{chart_html}
<h2>By term</h2>
<div class="tw"><table><tr><th>Term</th><th>Dates</th><th>Debt at start</th><th>Per person</th><th>Debt at end</th><th>Per person</th><th>Change</th><th>Change %</th></tr>{"".join(rows)}</table></div>
<p>From {fdate(H['series_start']['date'])} on, a figure is the last Debt to the Penny close on or before the date. Earlier, it is the last <a href="{H['sources']['debt_outstanding']}" rel="noopener">Historical Debt Outstanding</a> record on or before the date, an annual total, not the debt on inauguration day. A dash means those two dates fall on the same Treasury record, so there is nothing to subtract.</p>
<p>{E(per_gap.strip())} Source for the population: <a href="{POP_PAGE}" rel="noopener">Census Bureau population estimates</a>, the same files as the national per-person page.</p>
{extra_link}
<h2>Sources</h2>
<ul class="sources"><li><a href="{DTP}" rel="noopener">Treasury, Debt to the Penny</a></li>
<li><a href="{HDO}" rel="noopener">Treasury, Historical Debt Outstanding</a></li></ul>
<h2>Questions</h2>
{faq_html}
<a class="cta" href="{UP}/">Open the live national debt clock →</a>
<section class="related" id="related"><h2>Related</h2><div class="rg">{rel_html}</div></section>
<footer>Every figure on this page is a Treasury or Census record. The change is not attributed to the person in office. Page built {E(stamp)}. · <a href="{UP}/methodology/">Methodology</a> · <a href="{UP}/privacy/">Privacy</a> · Independent site, not affiliated with the U.S. government. Not financial advice.</footer>
</main></body></html>"""
    dest = os.path.join(R, "national-debt-by-president", p["slug"])
    os.makedirs(dest, exist_ok=True)
    open(os.path.join(dest, "index.html"), "w").write(with_analytics(page) if with_analytics else page)
    return url


def build(ctx):
    R, SITE = ctx["R"], ctx["SITE"]
    published, skipped, H = records(R, ctx.get("OFF_D"), ctx.get("OFF_V"), ctx.get("hdo"))
    urls = []
    for p in published:
        urls.append(_page(R, SITE, ctx.get("with_analytics"), ctx.get("STAMP") or "", p, H))
    ctx["president_pages"] = {p["name"]: p["slug"] for p in published}
    flags_path = os.path.join(R, "data", "longtail_flags.json")
    flags = json.load(open(flags_path)) if os.path.exists(flags_path) else {}
    flags["presidents_not_published"] = skipped
    json.dump(flags, open(flags_path, "w"), indent=1)
    open(flags_path, "a").write("\n")
    print(f"presidents: {len(urls)} pages, {len(skipped)} not published")
    for s in skipped:
        print(f"  skipped {s['name']}: {s['reason']}")
    return urls


def llms_lines(R):
    try:
        published, skipped, _H = records(R)
    except Exception as e:
        return ["## National debt under each president", "", f"President pages were not built: {e}", ""]
    lines = ["## National debt under each president", ""]
    for p in published:
        lines.append(f"- /national-debt-by-president/{p['slug']}/ : National debt under {p['name']}. Treasury total at the start and end, the change, and per person where Census publishes a July 1 population.")
    for s in skipped:
        lines.append(f"- Skipped {s['name']}: {s['reason']}")
    lines.append("")
    return lines


def _parse_displayed_dollars(cell):
    """Whole-dollar figure printed in a table cell, ignoring the basis note."""
    cell = re.sub(r"<span class=\"when\">.*?</span>", "", cell, flags=re.S)
    text = re.sub(r"<[^>]+>", "", cell).strip()
    if text in ("—", "-", "") or text.startswith("No record"):
        return None
    neg = text.startswith("−") or text.startswith("-")
    m = re.search(r"\$(\d[\d,]*)", text)
    if not m:
        raise SystemExit(f"president table cell has no dollar amount: {text!r}")
    n = int(m.group(1).replace(",", ""))
    return -n if neg else n


def _assert_rows_foot(slug, html):
    """Displayed change must equal the displayed end minus the displayed start."""
    checked = 0
    for row in re.findall(r"<tr>(.*?)</tr>", html, flags=re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)
        if len(cells) < 8:
            continue
        start = _parse_displayed_dollars(cells[2])
        end = _parse_displayed_dollars(cells[4])
        change = _parse_displayed_dollars(cells[6])
        if change is None:
            continue
        if start is None or end is None:
            raise SystemExit(f"{slug}: a change is shown without a start and an end")
        if change != end - start:
            raise SystemExit(f"{slug}: change {change} does not equal end {end} minus start {start}")
        checked += 1
    if checked < 1:
        raise SystemExit(f"{slug}: no term row to foot")


def check(R, site):
    published, skipped, _H = records(R)
    sm = open(os.path.join(R, "sitemap.xml")).read()
    llms = open(os.path.join(R, "llms.txt")).read()
    index = open(os.path.join(R, "national-debt-by-president", "index.html")).read()
    for p in published:
        path = os.path.join(R, "national-debt-by-president", p["slug"], "index.html")
        text = open(path).read()
        _assert_rows_foot(p["slug"], text)
        if _usd0(p["last"]["amount"]) not in text or _usd0(p["first"]["amount"]) not in text:
            raise SystemExit(f"{p['slug']}: Treasury amounts are not on the page")
        if f"{p['pct']:+.1f}%" not in text:
            raise SystemExit(f"{p['slug']}: percent change is not on the page")
        if DTP not in text or HDO not in text:
            raise SystemExit(f"{p['slug']}: source not cited")
        if f"{site}/national-debt-by-president/{p['slug']}/" not in sm:
            raise SystemExit(f"sitemap missing /national-debt-by-president/{p['slug']}/")
        if f"/national-debt-by-president/{p['slug']}/" not in llms:
            raise SystemExit(f"llms.txt missing {p['slug']}")
        if f'href="{p["slug"]}/"' not in index:
            raise SystemExit(f"president index does not link to {p['slug']}")
    for s in skipped:
        if os.path.exists(os.path.join(R, "national-debt-by-president", s["slug"], "index.html")):
            raise SystemExit(f"skipped president {s['name']} still has a page")
        if f'href="{s["slug"]}/"' in index:
            raise SystemExit(f"president index links to skipped {s['name']}")
    print("president pages check ok")
