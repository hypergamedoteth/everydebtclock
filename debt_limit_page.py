"""X-date hub (/debt-limit/).

The live ceiling, debt subject to the limit, headroom, and the date the
ceiling would bind already live on the noindex tickers and on /41-trillion/.
This page links to those. It does not print the same dollars or another clock
for them. What it adds is the X-date record: outside forecasts, extraordinary
measures, what a missed X-date would affect, and past episodes.
"""
from __future__ import annotations

import json
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline"))
import debt_limit

E = __import__("html").escape
PAGE_STYLE = """
html{overflow-x:clip}body{overflow-x:clip;max-width:100%}
.status{border:1px solid #1c2533;border-radius:12px;padding:10px 12px;background:#101828;margin:8px 0 14px}
.status b{color:#fff}
.cite{border:1px solid #1c2533;border-radius:12px;padding:10px 12px;background:#101828;font-size:13.5px;margin:14px 0}
.cite p{margin:0 0 6px}
ul.lean{margin:6px 0 12px;padding-left:18px}ul.lean li{margin:7px 0}
"""


def _load_rows(R):
    path = os.path.join(R, "cache", "dts_dsl.json")
    if not os.path.exists(path):
        return []
    doc = json.load(open(path, encoding="utf-8"))
    return doc.get("data") or []


def _summary(R, T):
    """Same Table III-C totals the tickers already use. Used for status, not a second display."""
    rows = _load_rows(R)
    summary = debt_limit.summarize(rows) if rows else None
    subj = T.get("debt_subject_limit") or {}
    lim = T.get("debt_limit") or {}
    if summary and subj.get("status") == "ok" and summary["as_of"] == subj.get("as_of"):
        if abs(summary["subject"] - float(subj["base"])) > 1:
            raise SystemExit("debt subject to the limit does not match Daily Treasury Statement rows")
        if summary["status"] == "in_force" and lim.get("status") == "ok":
            if abs(summary["limit"] - float(lim["base"])) > 1:
                raise SystemExit("statutory limit ticker does not match Daily Treasury Statement rows")
        if summary["as_of"] == "2026-11-19":
            debt_limit.check_verified(rows)
    elif subj.get("status") == "ok" and lim.get("status") == "ok" and subj.get("as_of") == lim.get("as_of"):
        head = float(lim["base"]) - float(subj["base"])
        summary = {
            "as_of": subj.get("as_of"),
            "status": "in_force" if float(lim["base"]) > 0 else "unreported",
            "subject": float(subj["base"]),
            "limit": float(lim["base"]) if float(lim["base"]) > 0 else None,
            "limit_reported": float(lim["base"]),
            "headroom": head if float(lim["base"]) > 0 else None,
            "public": None, "intragov": None, "not_subject": None, "other": None,
            "not_parts": [], "other_parts": [],
            "source": debt_limit.DSL_URL, "source_api": debt_limit.DSL_API,
            "unit": "Table III-C amounts are published in millions of dollars and shown here in dollars.",
        }
    return summary, subj, lim


def _slope(subj):
    rate = float(subj.get("rate") or 0) if subj else 0.0
    if rate <= 0 and subj and subj.get("rate_trend"):
        rate = float(subj["rate_trend"])
    return rate or None


def build(ctx):
    R, SITE, T = ctx["R"], ctx["SITE"], ctx["T"]
    fdate, usd0, usd2 = ctx["fdate"], ctx["usd0"], ctx["usd2"]
    answer_page, faq_ld, dataset_ld = ctx["answer_page"], ctx["faq_ld"], ctx["dataset_ld"]
    OFF_V, OFF_D = ctx["OFF_V"], ctx["OFF_D"]
    summary, subj, lim = _summary(R, T)
    td = T.get("debt_total") or {}
    measures = debt_limit.EXTRAORDINARY_MEASURES
    # Drop a headroom widget from an earlier draft. The headroom ticker already counts that gap.
    old_widget = os.path.join(R, "embed", "debt-limit")
    if os.path.isdir(old_widget):
        shutil.rmtree(old_widget)

    checked = fdate(measures["checked"])
    h1_plain, h1_html = ctx["quotable"].asof_pair(
        "Treasury has not posted an X-date for the current debt limit",
        checked,
        [("U.S. Department of the Treasury", debt_limit.TREASURY_PAGE)],
    )
    answer = ("An X-date is the later day when cash and extraordinary measures would no longer cover every payment on time. "
              "It is not the day the debt reaches the ceiling. That projection is on the <a href=\"../41-trillion/\">$41 trillion countdown</a>.")

    hero = ""
    tick = ""
    if td.get("status") == "ok" and OFF_V:
        hero = (f'<div class="hero lead" id="lead" data-b="{td.get("base")}" data-r="{td.get("rate") or 0}" data-t="{td.get("t0") or 0}">'
                f'<div class="k">Live estimate · US national debt</div>'
                f'<div class="big num" id="hv">{usd2(OFF_V)}</div>'
                f'<div class="sub">Starts at the official {E(fdate(OFF_D))} close. The ceiling and the room under it are linked below.</div></div>')
        tick = """<script>(function(){var H=document.getElementById('lead'),v=document.getElementById('hv');if(!H||!v)return;
var b=+H.dataset.b,r=+H.dataset.r,t0=+H.dataset.t,nf=new Intl.NumberFormat('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
function go(){var x=b+r*(Date.now()/1000-t0);v.textContent=(x<0?'−$':'$')+nf.format(Math.abs(x));requestAnimationFrame(go)}go()})();</script>"""

    record = fdate(summary["as_of"]) if summary else ""
    if summary and summary["status"] == "suspended":
        status_p = (f"<p class=\"status\"><b>Suspended, as printed.</b> The Statutory Debt Limit line on the {E(record)} statement is "
                    f"{usd0(summary['limit_reported'])}. There is no separate ticker for that line. "
                    f"<a href=\"{debt_limit.DSL_URL}\" rel=\"noopener\">Daily Treasury Statement, Table III-C</a>.</p>")
    elif summary and summary["status"] == "unreported":
        status_p = (f"<p class=\"status\"><b>No dollar ceiling on the {E(record)} statement.</b> Table III-C has no Statutory Debt Limit amount. "
                    f"<a href=\"{debt_limit.DSL_URL}\" rel=\"noopener\">Daily Treasury Statement, Table III-C</a>.</p>")
    elif summary and summary["status"] == "ambiguous":
        status_p = (f"<p class=\"status\"><b>Ambiguous on {E(record)}.</b> The limit lines on this statement do not agree. "
                    f"The tickers are not used while that is true. <a href=\"{debt_limit.DSL_URL}\" rel=\"noopener\">Daily Treasury Statement, Table III-C</a>.</p>")
    elif summary:
        status_p = (f"<p class=\"status\"><b>Limit in force</b> on the {E(record)} statement. Treasury printed one dollar ceiling. "
                    "The live figures are the tickers linked here.</p>")
    else:
        status_p = "<p class=\"status\"><b>The Daily Treasury Statement table is not in this build.</b></p>"

    links = f"""<ul class="lean">
<li><a href="../t/debt_subject_limit.html">Debt subject to the limit</a>, the live ticker.</li>
<li><a href="../t/debt_limit.html">Statutory debt limit</a>, the live ticker.</li>
<li><a href="../t/limit_headroom.html">Room left under the debt limit</a>, the live ticker.</li>
<li><a href="../41-trillion/">$41 trillion countdown</a>. That page has the projection for when the ceiling would bind, from the same debt-subject-to-limit trend.</li>
<li><a href="../how-much-is-the-national-debt/">How much is the national debt?</a></li>
</ul>
<p>Those pages already show the dollars. This page does not copy them.</p>"""

    if measures["in_use"] and measures.get("announcement"):
        em_html = (f"<p class=\"status\"><b>In use.</b> Treasury has announced extraordinary measures. "
                   f"<a href=\"{E(measures['announcement'])}\" rel=\"noopener\">Announcement</a>.</p>")
    else:
        em_html = (f"<p class=\"status\"><b>Not in use.</b> Treasury's debt-limit page lists no extraordinary-measures announcement after the "
                   f"debt issuance suspension period that ended July 4, 2025. Checked {E(checked)}. "
                   f"This line stays \"not in use\" until <a href=\"{measures['page']}\" rel=\"noopener\">that page</a> lists a new announcement.</p>")
    em_html += (f"<p>Extraordinary measures are accounting steps Treasury can take after the limit binds, so it can keep paying bills for a while without new borrowing. "
                f"The January 17, 2025 description lists the Civil Service Retirement and Disability Fund, the Postal Service Retiree Health Benefits Fund, "
                f"the G Fund, the Exchange Stabilization Fund, a pause in State and Local Government Series sales, and a Federal Financing Bank swap. "
                f"<a href=\"{measures['description']}\" rel=\"noopener\">Description of the Extraordinary Measures, January 17, 2025</a>. "
                f"Treasury's FY2025 financial report says those measures stopped on July 7, 2025, after Public Law 119-21 raised the limit. "
                f"<a href=\"{measures['discontinued_source']}\" rel=\"noopener\">FY2025 Financial Report, executive summary</a>.</p>")

    forecast_items = []
    for row in debt_limit.FORECASTS:
        xbit = f" X-date: {E(row['xdate'])}." if row.get("xdate") else " No single X-date."
        forecast_items.append(
            f"<li><b>{E(row['who'])}</b> · {E(row['published'])}.{xbit} {E(row['says'])} "
            f"<a href=\"{E(row['url'])}\" rel=\"noopener\">{E(row['title'])}</a>.</li>")
    forecasts = ("<ul class=\"lean\">" + "".join(forecast_items) + "</ul>"
                 "<p>These are the publishers' forecasts. CBO's February 2026 baseline, linked above, says the limit would be reached sometime in 2027 and does not give an X-date. "
                 f"Treasury publishes a letter on <a href=\"{debt_limit.TREASURY_PAGE}\" rel=\"noopener\">its debt-limit page</a> when it projects one. None is posted for this limit.</p>")

    ga = "https://www.gao.gov/products/gao-25-107089"
    consequences = f"""<ul class="lean">
<li><b>Social Security and Medicare.</b> Treasury says the limit is what lets the government borrow to pay existing obligations, including Social Security and Medicare benefits. GAO says missing the X-date would hinder nondebt payments such as program benefits. Trust-fund holdings of Treasury securities count toward the limit. <a href="{debt_limit.TREASURY_PAGE}" rel="noopener">Treasury, Debt Limit</a> · <a href="{ga}" rel="noopener">GAO-25-107089</a>.</li>
<li><b>Federal pay and military pay.</b> Treasury lists military salaries among those existing obligations. GAO lists federal employees' salaries among payments a default would hinder. Neither source says which bills would be paid first.</li>
<li><b>Treasury bonds and markets.</b> GAO calls it a default if Treasury misses a timely payment on Treasury debt, and says a default would disrupt financial markets. Impasses have already made the safety of Treasury securities less certain, GAO says. <a href="{ga}" rel="noopener">GAO-25-107089</a>.</li>
</ul>"""

    episodes = f"""<ul class="lean">
<li><b>2011.</b> August 2, 2011: the Budget Control Act (Public Law 112-25) was signed. It raised the limit in three steps. <a href="https://www.congress.gov/crs-product/R43389" rel="noopener">CRS R43389, The Debt Limit Since 2011</a>.</li>
<li><b>2013.</b> October 17, 2013: Public Law 113-46 suspended the limit through February 7, 2014. On September 25, 2013, Treasury told Congress borrowing capacity would run out around October 17. <a href="https://www.congress.gov/crs-product/R43389" rel="noopener">CRS R43389</a> · <a href="{debt_limit.TREASURY_PAGE}" rel="noopener">Treasury debt-limit page, Lew letter of September 25, 2013</a>.</li>
<li><b>2023.</b> June 3, 2023: the Fiscal Responsibility Act (Public Law 118-5) suspended the limit through January 1, 2025. It was reinstated on January 2, 2025. Extraordinary measures ran from January 21, 2025 until Treasury stopped them on July 7, 2025, after Public Law 119-21 raised the limit by $5 trillion on July 4, 2025. <a href="https://www.congress.gov/crs-product/IN11829" rel="noopener">CRS IN11829</a> · <a href="{debt_limit.STATUTE}" rel="noopener">31 U.S.C. § 3101 note</a> · <a href="{debt_limit.FY2025_REPORT}" rel="noopener">FY2025 Financial Report</a>.</li>
</ul>"""

    cite = (f"<aside class=\"cite\"><p><b>Cite this.</b> Every Debt Clock, \"Debt limit and the X-date,\" updated {E(checked)}, "
            f"<a href=\"{SITE}/debt-limit/\">{SITE.replace('https://', '')}/debt-limit/</a>.</p>"
            f"<p>X-date forecasts: the linked CBO, Bipartisan Policy Center, and National Taxpayers Union pages. "
            f"Whether the limit is in force: <a href=\"{debt_limit.DSL_URL}\" rel=\"noopener\">Daily Treasury Statement Table III-C</a>"
            + (f", record date {E(summary['as_of'])}." if summary else ".")
            + " The dollar figures are on the linked tickers.</p></aside>")

    faqs = [
        (
            "What is the X-date?",
            "The X-date is the day Treasury would no longer have enough cash and extraordinary measures to pay all obligations on time. It comes after the debt hits the limit. "
            "BPC's November 18, 2026 brief does not name a single day. NTU's November 12, 2026 central estimate is the beginning of December 2027. "
            "CBO's February 2026 baseline says the limit would be reached sometime in 2027 and does not give an X-date.",
        ),
        (
            "Has Treasury posted an X-date for this limit?",
            f"No. As of {checked}, Treasury's debt-limit page lists no X-date letter for the current limit. "
            "Source: U.S. Department of the Treasury.",
        ),
        (
            "Are extraordinary measures in use?",
            "Not in use. Treasury's debt-limit page lists no extraordinary-measures announcement after the debt issuance suspension period that ended July 4, 2025. "
            "Source: U.S. Department of the Treasury." if not measures["in_use"] else
            "Treasury has announced that extraordinary measures are in use. Source: U.S. Department of the Treasury.",
        ),
        (
            "Where are the live debt-limit figures?",
            "On the tickers for the statutory limit, debt subject to the limit, and room left under the limit, and on the $41 trillion countdown, which includes when this site projects the ceiling would bind. This page links to those and does not repeat the dollars.",
        ),
        (
            "What happens if the X-date hits?",
            "Treasury says the limit finances existing obligations, including Social Security and Medicare benefits and military salaries. "
            "GAO says a missed X-date would hinder program benefits and federal employees' salaries, and that missing a payment on Treasury debt would disrupt financial markets. "
            "Neither source says which bills would be paid first.",
        ),
    ]
    if not 3 <= len(faqs) <= 6:
        raise SystemExit(f"debt-limit FAQ has {len(faqs)} questions")

    # Guard: the hub must not restate the ticker bases. The countdown page owns that projection.
    body_check_later = []
    if summary and summary.get("status") == "in_force":
        body_check_later = [usd0(summary["subject"]), usd0(summary["limit"]), usd0(summary["headroom"])]

    body = f"""<style>{PAGE_STYLE}</style>
<p class="answer">{answer}</p>
<h2>Live figures</h2>
{status_p}
{links}
<h2>X-date forecasts</h2>
<p>Only forecasts read at the linked page are listed.</p>
{forecasts}
<h2>Extraordinary measures</h2>
{em_html}
<h2>If the X-date hits</h2>
{consequences}
<h2>2011, 2013, and 2023</h2>
{episodes}
{cite}
{tick}"""
    for banned in body_check_later:
        if banned in body:
            raise SystemExit("debt-limit page repeats a ticker figure: " + banned)

    answer_page(
        "debt-limit",
        "US X-Date and the Debt Limit",
        "X-date forecasts from CBO, the Bipartisan Policy Center, and the National Taxpayers Union. Extraordinary measures are not in use. Live limit and headroom figures are linked, not repeated.",
        h1_plain,
        body,
        faqs=faqs,
        hero=hero,
        h1_html=f'<h1 class="quote asof">{h1_html}</h1>',
        ld=(dataset_ld(
            "US debt-limit X-date forecasts",
            "Published X-date and debt-limit forecasts from CBO, the Bipartisan Policy Center, and the National Taxpayers Union, with Treasury's extraordinary-measures status.",
            f"{SITE}/debt-limit/",
            based=[debt_limit.TREASURY_PAGE, "https://www.cbo.gov/publication/62105",
                   "https://bipartisanpolicy.org/issue-brief/the-debt-limit-returns-in-2027-what-to-expect/"],
            source=("U.S. Department of the Treasury", "https://home.treasury.gov/",
                    "U.S. Department of the Treasury, debt limit"),
            modified=measures["checked"],
        ) + faq_ld(faqs)),
    )
