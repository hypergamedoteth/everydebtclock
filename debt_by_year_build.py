#!/usr/bin/env python3
"""Debt-by-year pages: /states/<slug>/debt-by-year/ and /countries/<slug>/debt-by-year/.

Numbers come from data/debt_by_year.json (pipeline/fetch_debt_by_year.py) and, for Census
survey years 2017–2024, from places/<state>.json, the same figures the state clocks use.
A place listed under "skipped" in the JSON gets no page.

Called from build.py. `python3 debt_by_year_build.py` writes the pages and patches the
sitemap, llms.txt, and any clock pages already in the tree.
"""
import datetime as dt
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
E = html.escape
UP = "../../.."
DATA = "data/debt_by_year.json"

CSS = """body{margin:0;background:#07090d;color:#e8edf5;font-family:-apple-system,BlinkMacSystemFont,Inter,Segoe UI,Roboto,sans-serif;line-height:1.5}
main{max-width:760px;margin:0 auto;padding:22px 16px 60px}a{color:#5aa9ff;text-decoration:none}
.brand{font-weight:800;letter-spacing:.06em;font-size:14px;color:inherit}.brand b{color:#ff4d5e}h1{font-size:22px;margin:14px 0 4px}
.k{color:#8a97ab;font-size:13px;margin:0}p{color:#c2ccda;font-size:14.5px}
.cta{display:inline-block;margin:14px 0;background:#ff4d5e;color:#fff;border-radius:10px;padding:10px 16px;font-weight:700}
.rel a{display:inline-block;margin:4px 8px 4px 0;font-size:13px}footer{color:#5c687a;font-size:12px;margin-top:30px}
table{border-collapse:collapse;width:100%;font-size:13.5px;margin:8px 0 14px}th,td{border-bottom:1px solid #1c2533;padding:6px 8px;text-align:left;vertical-align:top}
th{color:#8a97ab;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.05em}td.num{font-family:ui-monospace,Menlo,monospace;text-align:right;white-space:nowrap}
h2{font-size:17px;margin:22px 0 6px}h3{font-size:15px;margin:16px 0 4px}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}
figure{margin:8px 0 16px}figure svg{width:100%;height:auto;background:#121925;border-radius:12px;display:block}
figcaption{color:#8a97ab;font-size:12.5px;margin-top:6px}
.related{margin:18px 0}.related h2{font-size:17px;margin:0 0 10px}.related .rg{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.related .rg a{display:flex;flex-direction:column;gap:4px;padding:14px 16px;border:1px solid #1c2533;border-radius:12px;background:#121925;color:#e8edf5}
.related .rn{font-size:15px;font-weight:600}.related .rw{font-size:13px;color:#8a97ab}
@media (max-width:700px){.related .rg{grid-template-columns:1fr}}
ul.sources{padding-left:18px}ul.sources li{font-size:13.5px;margin:3px 0}"""


def load(R=None):
    path = os.path.join(R or ROOT, DATA)
    if not os.path.exists(path):
        return {"places": {}, "skipped": []}
    return json.load(open(path))


def fdate(s):
    return dt.date.fromisoformat(s).strftime("%b %-d, %Y")


def money(sym, n):
    return ("−" if n < 0 else "") + sym + f"{abs(n):,.0f}"


def short(sym, n):
    a = abs(n)
    s = ("−" if n < 0 else "") + sym
    if a >= 1e12:
        return s + f"{a / 1e12:,.2f} trillion"
    if a >= 1e9:
        return s + f"{a / 1e9:,.2f} billion"
    if a >= 1e6:
        return s + f"{a / 1e6:,.1f} million"
    return s + f"{a:,.0f}"


def parent_link(slug, name):
    """Paragraph for the clock page summary. Empty when that place has no debt-by-year page."""
    if slug not in load().get("places", {}):
        return ""
    return f'<p><a href="debt-by-year/">{E(name)} debt by year</a>, from the same official source as this clock.</p>'


def _place(R, slug):
    return json.load(open(os.path.join(R, "places", slug + ".json")))


def state_rows(R, slug, saved):
    p = _place(R, slug)
    comps = {c["key"]: {d: int(v) for d, v in c["history"]} for c in p["components"]}
    if "state" not in comps or "local" not in comps:
        raise RuntimeError(f"{slug}: clock file has no state and local history")
    rows = []
    for r in saved:
        total, state, local = int(r["total"]), int(r["state"]), int(r["local"])
        if abs(state + local - total) > 5000:
            raise RuntimeError(f"{slug} {r['year']}: state + local != total")
        rows.append({"year": int(r["year"]), "date": r["date"], "amount": total, "state": state, "local": local, "year_end": True})
    have = {r["year"] for r in rows}
    for d in sorted(set(comps["state"]) & set(comps["local"])):
        y = int(d[:4])
        if y in have:
            raise RuntimeError(f"{slug}: survey year {y} is in both the summary tables and the clock file")
        state, local = comps["state"][d], comps["local"][d]
        rows.append({"year": y, "date": d, "amount": state + local, "state": state, "local": local, "year_end": True})
    rows.sort(key=lambda r: r["date"])
    by_key = {c["key"]: c for c in p["components"]}
    d = by_key["state"]["as_of"]
    if d != by_key["local"]["as_of"]:
        raise RuntimeError(f"{slug}: state and local as-of dates differ")
    total = int(by_key["state"]["value"]) + int(by_key["local"]["value"])
    hit = next((r for r in rows if r["date"] == d), None)
    if hit is None or hit["amount"] != total:
        raise RuntimeError(f"{slug}: clock total {total} on {d} is not in the year table")
    return rows, p


def country_rows(R, slug, rec):
    p = _place(R, slug)
    c = p["components"][0]
    series = {pt["date"]: int(pt["amount"]) for pt in rec["points"]}
    hist = {d: int(v) for d, v in c["history"]}
    hist[c["as_of"]] = int(c["value"])
    for d, v in hist.items():
        if d in series and abs(series[d] - v) > 1:
            raise RuntimeError(f"{slug}: {d} is {series[d]} in the history file and {v} on the clock")
        series.setdefault(d, v)
    if c["as_of"] not in series or abs(series[c["as_of"]] - int(c["value"])) > 1:
        raise RuntimeError(f"{slug}: latest clock figure is not in the series")
    month = int(rec["year_end_month"])
    by = {}
    for d, amt in series.items():
        if int(d[5:7]) == month:
            by[int(d[:4])] = {"year": int(d[:4]), "date": d, "amount": amt, "year_end": True}
    rows = [by[y] for y in sorted(by)]
    last = max(series)
    if not rows or rows[-1]["date"] != last:
        rows.append({"year": int(last[:4]), "date": last, "amount": series[last], "year_end": int(last[5:7]) == month})
        rows.sort(key=lambda r: r["date"])
    return rows, p


def ten_year(rows):
    """Year-end row ten years before the latest year-end, or None."""
    ends = [r for r in rows if r.get("year_end")]
    if not ends:
        return None, None
    end = ends[-1]
    ago = next((r for r in ends if r["year"] == end["year"] - 10), None)
    return ago, end


def _verb(diff):
    return "up" if diff > 0 else "down" if diff < 0 else "unchanged"


def _be(measure):
    return "were" if measure.split()[-1] in ("liabilities", "securities", "holdings") else "was"

def answer_parts(name, measure, sym, rows):
    """(html, plain) one-line answer: latest stock, and the 10-year change when the series has it."""
    latest = rows[-1]
    ago, end = ten_year(rows)
    be = _be(measure)
    lead_h = f"{E(name)}'s {E(measure)} {be} <b>{money(sym, latest['amount'])}</b> ({short(sym, latest['amount'])}) on {fdate(latest['date'])}"
    lead_p = f"{name}'s {measure} {be} {money(sym, latest['amount'])} ({short(sym, latest['amount'])}) on {fdate(latest['date'])}"
    if ago:
        diff = end["amount"] - ago["amount"]
        pct = diff / ago["amount"] * 100
        verb = _verb(diff)
        if latest["date"] == end["date"]:
            html_s = (f"{lead_h}, {verb} {short(sym, abs(diff))} ({pct:+.1f}%) from {short(sym, ago['amount'])} on {fdate(ago['date'])}.")
            plain = (f"{lead_p}, {verb} {short(sym, abs(diff))} ({pct:+.1f}%) from {short(sym, ago['amount'])} on {fdate(ago['date'])}.")
        else:
            html_s = (f"{lead_h}. From {fdate(ago['date'])} to {fdate(end['date'])} the year-end total was {verb} "
                      f"{short(sym, abs(diff))} ({pct:+.1f}%), from {short(sym, ago['amount'])} to {short(sym, end['amount'])}.")
            plain = (f"{lead_p}. From {fdate(ago['date'])} to {fdate(end['date'])} the year-end total was {verb} "
                     f"{short(sym, abs(diff))} ({pct:+.1f}%), from {short(sym, ago['amount'])} to {short(sym, end['amount'])}.")
        return html_s, plain, True
    first = next((r for r in rows if r.get("year_end")), rows[0])
    diff = latest["amount"] - first["amount"]
    pct = diff / first["amount"] * 100 if first["amount"] else 0
    verb = _verb(diff)
    span = (f" From {fdate(first['date'])} to {fdate(latest['date'])} it was {verb} {short(sym, abs(diff))} ({pct:+.1f}%)."
            if first["date"] != latest["date"] else "")
    note = " This series does not cover 10 years, so that comparison is not shown."
    return lead_h + "." + span + note, lead_p + "." + span + note, False


def chart(rows, title):
    vals = [r["amount"] for r in rows]
    W, H = 720, 220
    pl, pr, pt, pb = 12, 12, 16, 28
    hi = max(vals) * 1.06 or 1
    def x(i):
        return pl + (W - pl - pr) * (i / (len(rows) - 1 if len(rows) > 1 else 1))
    def y(v):
        return pt + (H - pt - pb) * (1 - v / hi)
    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
    dots = "".join(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="2.4" fill="#ff4d5e"/>' for i, v in enumerate(vals))
    labels = []
    seen = set()
    for i in (0, len(rows) // 2, len(rows) - 1):
        lab = str(rows[i]["year"])
        if lab in seen:
            continue
        seen.add(lab)
        anchor = "start" if i == 0 else "end" if i == len(rows) - 1 else "middle"
        labels.append(f'<text x="{x(i):.0f}" y="{H - 8}" text-anchor="{anchor}" fill="#8a97ab" font-size="12" font-family="sans-serif">{lab}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img">'
            f'<title>{E(title)}</title>'
            f'<polyline points="{pts}" fill="none" stroke="#ff4d5e" stroke-width="2.5"/>{dots}{"".join(labels)}</svg>')


def change_text(sym, rows, i):
    if i == 0:
        return "—"
    diff = rows[i]["amount"] - rows[i - 1]["amount"]
    gap = rows[i]["year"] - rows[i - 1]["year"]
    body = ("+" if diff > 0 else "−" if diff < 0 else "") + short(sym, abs(diff))
    if gap > 1:
        body += f" over {gap} years"
    return body


def missing_years(rows):
    years = {r["year"] for r in rows}
    if not years:
        return []
    return [y for y in range(min(years), max(years) + 1) if y not in years]


def models(R):
    doc = load(R)
    out = []
    for slug, rec in doc.get("places", {}).items():
        if rec.get("kind") == "state":
            rows, p = state_rows(R, slug, rec["rows"])
            sym = "$"
            measure = "state and local debt"
            sec = "states"
            count_note = (f"Each figure is total debt outstanding of the {p['name']} state government and of local governments "
                          f"(counties, cities, school districts and special districts), as the Census Bureau defines it. "
                          f"It is the same total as the {p['name']} debt clock. It is not the state's own annual report, and it does not include unfunded pensions or a share of the federal debt. "
                          f"Census dates each survey year June 30. Amounts are published in thousands of dollars, so the state and local parts can miss the total by a thousand or two.")
            year_note = "Survey years 2017–2024 are Census's current time-series table, the same figures as the debt clock. Earlier years are the summary table Census published for that survey year."
            sources = [(rec["api_source"]["name"], rec["api_source"]["url"]),
                       ("US Census Bureau, State and Local Government Finance tables", rec["release_page"])]
            sources += [(s["name"], s["url"]) for s in rec["sources"]]
        else:
            rows, p = country_rows(R, slug, rec)
            sym = (p.get("currency") or {}).get("symbol") or ""
            measure = p.get("headline") or "government debt"
            sec = "countries"
            count_note = p.get("sum_note") or p.get("scope_note") or measure
            month = int(rec["year_end_month"])
            if month == 3:
                year_note = "A row dated March 31 is the fiscal year-end stock. If a later quarter of that year has been published, it is shown as well."
            elif month == 6:
                year_note = "Completed years use the June 30 figure. The latest row is the newest month if the year is not finished."
            else:
                year_note = "Completed years use the December figure. The latest row is the newest published figure if that year is not finished."
            sources = []
            comp = p["components"][0]
            for s in rec["sources"]:
                sources.append((s["name"], s["url"]))
            if comp.get("source_url") and comp["source_url"] not in {u for _, u in sources}:
                sources.append((comp.get("source_name") or "Official source", comp["source_url"]))
        if len(rows) < 2:
            raise RuntimeError(f"{slug}: fewer than two annual figures")
        ago, end = ten_year(rows)
        ans_h, ans_p, has10 = answer_parts(p["name"], measure, sym, rows)
        y0, y1 = rows[0]["year"], rows[-1]["year"]
        gaps = missing_years(rows)
        out.append({
            "slug": slug, "name": p["name"], "kind": rec.get("kind"), "sec": sec, "sym": sym,
            "measure": measure, "rows": rows, "sources": sources, "count_note": count_note,
            "year_note": year_note, "answer_html": ans_h, "answer_plain": ans_p, "has10": has10,
            "y0": y0, "y1": y1, "gaps": gaps, "ago": ago, "end": end,
            "path": f"/{sec}/{slug}/debt-by-year/",
            "url_path": f"{sec}/{slug}/debt-by-year/",
        })
    out.sort(key=lambda m: (m["sec"], m["name"]))
    return out


def _row_html(sym, rows, state):
    body = []
    for i in range(len(rows) - 1, -1, -1):
        r = rows[i]
        cells = f'<td>{r["year"]}</td><td>{fdate(r["date"])}</td>'
        if state:
            cells += f'<td class="num">{money(sym, r["state"])}</td><td class="num">{money(sym, r["local"])}</td>'
        cells += f'<td class="num">{money(sym, r["amount"])}</td><td class="num">{E(change_text(sym, rows, i))}</td>'
        body.append(f'<tr id="y{r["date"]}">{cells}</tr>')
    return "".join(body)


def _page(R, SITE, with_analytics, stamp, modified, m, models_all):
    sym, rows = m["sym"], m["rows"]
    state = m["kind"] == "state"
    title = f"{m['name']} Debt by Year ({m['y0']}–{m['y1']})"
    if m["has10"] and m["end"] and m["rows"][-1]["date"] == m["end"]["date"]:
        desc = (f"{m['name']} {m['measure']} by year: {short(sym, rows[-1]['amount'])} on {fdate(rows[-1]['date'])}, "
                f"{_verb(m['end']['amount'] - m['ago']['amount'])} {short(sym, abs(m['end']['amount'] - m['ago']['amount']))} from {fdate(m['ago']['date'])}.")
    else:
        desc = f"{m['name']} {m['measure']} by year, {m['y0']}–{m['y1']}: {short(sym, rows[-1]['amount'])} on {fdate(rows[-1]['date'])}."
    if state and len(desc) + 18 <= 165:
        desc += " US Census Bureau."
    if len(desc) > 170:
        desc = f"{m['name']} debt by year ({m['y0']}–{m['y1']}): {short(sym, rows[-1]['amount'])} on {fdate(rows[-1]['date'])}."
    url = f"{SITE}{m['path']}"
    sibs = [o for o in models_all if o["sec"] == m["sec"] and o["slug"] != m["slug"]]
    sib = sibs[0] if sibs else None
    related = [
        (f"{m['name']} debt clock", "../", "The live clock for this total"),
        ("US national debt by year", f"{UP}/national-debt-by-year/", "Treasury totals, FY1790 to now"),
    ]
    if sib:
        related.append((f"{sib['name']} debt by year", f"{UP}/{sib['url_path']}", f"{sib['y0']}–{sib['y1']}"))
    elif len(related) < 3:
        related.append(("All state debt clocks" if state else "All country debt clocks", f"{UP}/{m['sec']}/", "Every clock on this site"))
    q_count = m["count_note"]
    q_source = "The figures are copied from " + "; ".join(n for n, _ in m["sources"][:2]) + "."
    if not m["has10"]:
        q10 = m["answer_plain"]
    else:
        q10 = m["answer_plain"]
    faqs = [
        (f"How much is {m['name']} debt?", m["answer_plain"]),
        (f"How has {m['name']} debt changed over 10 years?", q10 if m["has10"] else m["answer_plain"]),
        (f"What does the {m['name']} debt-by-year table count?", q_count),
        (f"Where do the {m['name']} debt-by-year figures come from?", q_source),
    ]
    ld_ds = {"@context": "https://schema.org", "@type": "Dataset",
             "name": f"{m['name']} debt by year",
             "description": desc, "url": url, "isAccessibleForFree": True,
             "creator": {"@type": "Organization", "name": "Every Debt Clock", "url": SITE + "/"},
             "dateModified": modified or dt.date.today().isoformat(),
             "spatialCoverage": {"@type": "Place", "name": m["name"]},
             "temporalCoverage": f"{m['y0']}/{m['y1']}",
             "isBasedOn": [u for _, u in m["sources"]],
             "keywords": [f"{m['name']} debt by year", f"{m['name']} debt", "debt clock"],
             "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json",
                               "contentUrl": f"{SITE}/data/debt_by_year.json"}]}
    ld_faq = {"@context": "https://schema.org", "@type": "FAQPage",
              "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]}
    heads = "<th>Year</th><th>Date</th>" + ("<th>State debt</th><th>Local debt</th>" if state else "") + "<th>Total debt</th><th>Change</th>"
    gap = ""
    if m["gaps"]:
        shown = ", ".join(str(y) for y in m["gaps"])
        gap = (f"<p>Not in this table: {shown}. Census published a national summary for "
               f"{'those survey years' if len(m['gaps']) > 1 else 'that survey year'}, not the by-state workbook used for the other years, "
               f"so {'they are' if len(m['gaps']) > 1 else 'it is'} left out rather than estimated. A change that crosses a missing year says how many years it covers.</p>")
    src_html = "".join(f'<li><a href="{E(u)}" rel="noopener">{E(n)}</a></li>' for n, u in m["sources"])
    rel_html = "".join(f'<a href="{E(href)}"><span class="rn">{E(n)}</span><span class="rw">{E(w)}</span></a>' for n, href, w in related)
    faq_html = "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in faqs)
    chart_title = f"{m['name']} {m['measure']} by year, {m['y0']} to {m['y1']}"
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}"><link rel="canonical" href="{E(url)}">
<meta property="og:type" content="article"><meta property="og:site_name" content="Every Debt Clock"><meta property="og:url" content="{E(url)}">
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">
<meta property="og:image" content="{SITE}/og/debt_total.png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{E(title)}">
<meta name="twitter:description" content="{E(desc)}"><meta name="twitter:image" content="{SITE}/og/debt_total.png">
<meta name="theme-color" content="#07090d"><link rel="apple-touch-icon" href="{UP}/apple-touch-icon.png"><style>{CSS}</style>
<script type="application/ld+json">{json.dumps(ld_ds).replace("</", "<\\\\/")}</script>
<script type="application/ld+json">{json.dumps(ld_faq).replace("</", "<\\\\/")}</script>
<link rel="icon" href="/favicon.ico" sizes="16x16 32x32 48x48"><link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png"><link rel="icon" type="image/svg+xml" href="/icon.svg">
</head><body><main>
<a class="brand" href="{UP}/">EVERY <b>DEBT</b> CLOCK</a><a class="navembed" href="{UP}/embed/" style="margin-left:12px;font-size:13px;font-weight:650">Embed</a>
<p class="k"><a href="{UP}/">US debt clock</a> · <a href="../">{E(m['name'])} debt clock</a></p>
<h1>{E(m['name'])} debt by year</h1>
<p><b>Answer.</b> {m['answer_html']}</p>
<figure>{chart(rows, chart_title)}<figcaption>{E(chart_title)}. Amounts are the official stock, not a projection.</figcaption></figure>
<h2>By year, {m['y0']} to {m['y1']}</h2>
<div class="tw"><table><tr>{heads}</tr>{_row_html(sym, rows, state)}</table></div>
<p>{E(m['count_note'])}</p>
<p>{E(m['year_note'])}</p>
{gap}
<p>The live clock is the <a href="../">{E(m['name'])} debt clock</a>. The same kind of table for the United States is <a href="{UP}/national-debt-by-year/">US national debt by year</a>. Machine-readable copy: <a href="{UP}/data/debt_by_year.json">debt_by_year.json</a>.</p>
<h2>Sources</h2>
<ul class="sources">{src_html}</ul>
<h2>Questions</h2>
{faq_html}
<a class="cta" href="../">Open the {E(m['name'])} debt clock →</a>
<section class="related" id="related"><h2>Related clocks</h2><div class="rg">{rel_html}</div></section>
<footer>Every figure on this page is an official published number. Page built {E(stamp)}. · <a href="{UP}/embed/">Embed a clock</a> · <a href="{UP}/data/">Data</a> · <a href="{UP}/methodology/">Methodology</a> · <a href="{UP}/privacy.html">Privacy</a> · Independent site, not affiliated with any government. Not financial advice.</footer>
</main></body></html>"""
    if "coming soon" in page.lower():
        raise RuntimeError(f"{m['slug']}: page contains coming soon")
    dest = os.path.join(R, m["sec"], m["slug"], "debt-by-year")
    os.makedirs(dest, exist_ok=True)
    open(os.path.join(dest, "index.html"), "w").write(with_analytics(page) if with_analytics else page)
    return url


def llms_lines(R):
    doc = load(R)
    lines = ["## Debt by year", ""]
    try:
        built = models(R)
    except Exception as e:
        return ["## Debt by year", "", f"Debt-by-year pages were not built: {e}", ""]
    for m in built:
        lines.append(f"- {m['path']} : {m['name']} {m['measure']} by year, {m['y0']}–{m['y1']}. {m['sources'][0][0]}.")
    for s in doc.get("skipped") or []:
        lines.append(f"- Skipped {s.get('slug')}: {s.get('reason')}")
    lines.append("")
    return lines


def build(R, SITE, with_analytics, stamp, modified):
    built = models(R)
    urls = []
    for m in built:
        urls.append(_page(R, SITE, with_analytics, stamp, modified, m, built))
    print(f"debt-by-year: {len(urls)} pages")
    for m in built:
        ten = "10-year" if m["has10"] else "shorter than 10 years"
        print(f"  {m['path']} {m['y0']}–{m['y1']} ({ten})")
    return urls


def patch_clocks(R):
    """Add the debt-by-year link to clock pages already on disk, under the summary."""
    doc = load(R)
    n = 0
    for slug in doc.get("places", {}):
        kind = doc["places"][slug].get("kind")
        sec = "states" if kind == "state" else "countries"
        path = os.path.join(R, sec, slug, "index.html")
        if not os.path.exists(path):
            continue
        text = open(path).read()
        if "debt-by-year/" in text:
            continue
        name = json.load(open(os.path.join(R, "places", slug + ".json")))["name"]
        link = parent_link(slug, name)
        if '<aside class="embedbox"' in text:
            text = text.replace('<aside class="embedbox"', link + '<aside class="embedbox"', 1)
        elif 'id="intro"' in text:
            at = text.find('id="intro"')
            end = text.find("</section>", at)
            if end < 0:
                continue
            text = text[:end] + link + text[end:]
        else:
            continue
        open(path, "w").write(text)
        n += 1
    if n:
        print(f"debt-by-year: linked from {n} clock pages")


def _analytics(R):
    raw = os.environ.get("ANALYTICS_HTML")
    path = os.path.join(R, "analytics.html")
    if raw is None and os.path.exists(path):
        raw = open(path).read()
    raw = (raw or "").strip()
    block = f"<!--ANALYTICS-->{raw}<!--/ANALYTICS-->"
    def apply(page):
        if "<!--ANALYTICS-->" in page:
            return re.sub(r"<!--ANALYTICS-->.*?<!--/ANALYTICS-->", lambda m: block, page, flags=re.S)
        return page.replace("</head>", block + "\n</head>", 1)
    return apply


def patch_sitemap(R, site, urls):
    path = os.path.join(R, "sitemap.xml")
    if not os.path.exists(path):
        return
    text = open(path).read()
    lm = (re.search(r"<lastmod>([^<]+)</lastmod>", text) or [None, dt.date.today().isoformat()])[1]
    for u in urls:
        if f"<loc>{u}</loc>" in text:
            continue
        row = f"<url><loc>{u}</loc><lastmod>{lm}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>\n"
        if "</urlset>" not in text:
            raise RuntimeError("sitemap has no urlset close")
        text = text.replace("</urlset>", row + "</urlset>", 1)
    open(path, "w").write(text)


def patch_llms(R):
    path = os.path.join(R, "llms.txt")
    if not os.path.exists(path):
        return
    text = open(path).read()
    block = "\n".join(llms_lines(R)).rstrip() + "\n"
    start = text.find("## Debt by year\n")
    if start >= 0:
        end = text.find("\n## ", start + 4)
        text = text[:start] + block + (text[end + 1:] if end >= 0 else "")
    else:
        key = "## Data\n"
        i = text.find(key)
        if i < 0:
            text = text.rstrip() + "\n\n" + block
        else:
            text = text[:i] + block + "\n" + text[i:]
    open(path, "w").write(text)


def check(R, site):
    doc = load(R)
    for m in models(R):
        path = os.path.join(R, m["sec"], m["slug"], "debt-by-year", "index.html")
        text = open(path).read()
        if "coming soon" in text.lower():
            raise SystemExit(f"{m['slug']}: coming soon")
        visible = re.sub(r"<[^>]+>", "", text)
        if "FAQPage" not in text or "Dataset" not in text:
            raise SystemExit(f"{m['slug']}: missing structured data")
        if money(m["sym"], m["rows"][-1]["amount"]) not in text:
            raise SystemExit(f"{m['slug']}: latest amount is not on the page")
        if m["answer_plain"].split(".")[0][:48] not in visible:
            raise SystemExit(f"{m['slug']}: answer text is not on the page")
        for _, u in m["sources"]:
            if u not in text:
                raise SystemExit(f"{m['slug']}: source not cited: {u}")
        if f"{site}{m['path']}" not in open(os.path.join(R, "sitemap.xml")).read():
            raise SystemExit(f"sitemap missing {m['path']}")
        if m["path"] not in open(os.path.join(R, "llms.txt")).read():
            raise SystemExit(f"llms.txt missing {m['path']}")
        clock = os.path.join(R, m["sec"], m["slug"], "index.html")
        if os.path.exists(clock):
            host = open(clock).read()
            hero, intro = host.find('class="hero lead"'), host.find('id="intro"')
            link = host.find("debt-by-year/")
            if not (hero >= 0 and intro > hero and link > intro):
                raise SystemExit(f"{m['slug']}: debt-by-year link is not under the summary, below the ticker")
    for s in doc.get("skipped") or []:
        slug = s.get("slug")
        for sec in ("states", "countries"):
            if os.path.exists(os.path.join(R, sec, slug, "debt-by-year", "index.html")):
                raise SystemExit(f"skipped place {slug} still has a page")
    print("debt-by-year check ok")


def main():
    site = os.environ.get("DEBTCLOCK_SITE_URL", "https://everydebtclock.com").rstrip("/")
    stamp = dt.datetime.now().strftime("%b %-d, %Y")
    modified = load().get("fetched") or dt.date.today().isoformat()
    urls = build(ROOT, site, _analytics(ROOT), stamp, modified)
    patch_clocks(ROOT)
    patch_sitemap(ROOT, site, urls)
    patch_llms(ROOT)
    check(ROOT, site)


if __name__ == "__main__":
    main()
