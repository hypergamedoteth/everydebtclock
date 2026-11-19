"""Monthly U.S. debt reports from data/us-debt-daily.json.

A month is written once the daily file has a close after that month, so the
latest completed month is regenerated on every build and the next month
appears on its own when Treasury's later closes are in the file. Figures are
the official closes. The next-trillion date is labelled as a projection from
the 90-day least-squares trend through the month's last close. Interest per
day is the official monthly interest-expense total divided by the days in that
month, and it is left out when that month is not in the interest-expense series.
"""
import calendar
import datetime as dt
import html
import json
import os
from decimal import Decimal
from zoneinfo import ZoneInfo

import quotable

ET = ZoneInfo("America/New_York")
E = html.escape
FIRST = dt.date(2026, 1, 1)
DTP = "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny"
INT_URL = "https://fiscaldata.treasury.gov/datasets/interest-expense-debt-outstanding/interest-expense"
SOURCE_NAME = "U.S. Treasury, Debt to the Penny"


def _eod(iso):
    d = dt.date.fromisoformat(iso)
    return dt.datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=ET).timestamp()


def _ols(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx


def _load_rows(R):
    path = os.path.join(R, "data", "us-debt-daily.json")
    doc = json.load(open(path, encoding="utf-8"))
    rows = []
    for r in doc["rows"]:
        raw = r.get("total_public_debt_outstanding_usd")
        if raw in (None, ""):
            continue
        rows.append((r["record_date"], Decimal(raw)))
    rows.sort()
    return doc, rows


def _interest_months(R):
    path = os.path.join(R, "data", "data.json")
    if not os.path.exists(path):
        return {}
    gross = (json.load(open(path, encoding="utf-8")).get("tickers") or {}).get("interest_gross") or {}
    if gross.get("status") != "ok":
        return {}
    out = {}
    for row in (gross.get("calc") or {}).get("months") or []:
        if not row or len(row) < 2:
            continue
        out[row[0][:7]] = {"date": row[0], "amount": Decimal(str(row[1])),
                           "source": gross.get("source") or INT_URL,
                           "source_name": gross.get("source_name") or "Treasury, Interest Expense on the Public Debt Outstanding"}
    return out


def _last_on_or_before(rows, day):
    hit = [r for r in rows if r[0] <= day]
    return hit[-1] if hit else None


def _completed(rows):
    """Calendar months from FIRST through the last month that already has a later close."""
    if not rows:
        return []
    latest = dt.date.fromisoformat(rows[-1][0])
    out = []
    y, m = FIRST.year, FIRST.month
    while True:
        nxt = dt.date(y + 1, 1, 1) if m == 12 else dt.date(y, m + 1, 1)
        if latest >= nxt:
            out.append((y, m))
        if dt.date(y, m, 1) >= dt.date(latest.year, latest.month, 1):
            break
        m += 1
        if m == 13:
            m, y = 1, y + 1
    return out


def _project(rows, end_iso, end_amt):
    t_end = _eod(end_iso)
    win = [r for r in rows if r[0] <= end_iso and t_end - _eod(r[0]) <= 90 * 86400]
    if len(win) < 10:
        return None
    end_f = float(end_amt)
    rate = _ols([_eod(r[0]) for r in win], [float(r[1]) for r in win])
    if rate <= 0:
        return None
    n = int(end_f // 10 ** 12) + 1
    target = n * 10 ** 12
    when = dt.datetime.fromtimestamp(t_end + (target - end_f) / rate, ET).date()
    return {"trillion": n, "date": when.isoformat(), "per_day": rate * 86400,
            "n": len(win), "from": win[0][0], "to": win[-1][0], "target": target}


def _facts(rows, interest, y, m):
    start_day = (dt.date(y, m, 1) - dt.timedelta(days=1)).isoformat()
    end_day = dt.date(y, m, calendar.monthrange(y, m)[1]).isoformat()
    start = _last_on_or_before(rows, start_day)
    end = _last_on_or_before(rows, end_day)
    if not start or not end or start[0] >= end[0]:
        return None
    if end[0] < dt.date(y, m, 1).isoformat():
        return None
    added = end[1] - start[1]
    days = (dt.date.fromisoformat(end[0]) - dt.date.fromisoformat(start[0])).days
    label = dt.date(y, m, 1).strftime("%B %Y")
    slug = f"{y:04d}-{m:02d}"
    sentence = quotable.month_change(added, start[1], start[0], end[1], end[0], label)
    intr = interest.get(slug)
    per_day = None
    if intr and intr["amount"] is not None:
        dim = calendar.monthrange(y, m)[1]
        per_day = {"amount": intr["amount"] / dim, "month_total": intr["amount"], "days": dim,
                   "date": intr["date"], "source": intr["source"], "source_name": intr["source_name"]}
    return {
        "slug": slug, "label": label, "y": y, "m": m,
        "start": start, "end": end, "added": added, "days": days,
        "avg": added / days if days else None,
        "sentence": sentence, "interest": per_day,
        "projection": _project(rows, end[0], end[1]),
    }


def compute(R):
    _doc, rows = _load_rows(R)
    interest = _interest_months(R)
    months = []
    for y, m in _completed(rows):
        fact = _facts(rows, interest, y, m)
        if fact:
            months.append(fact)
    return months


def lastmods(R, today=None):
    """Sitemap dates: the month's last Debt to the Penny close, which is not after today."""
    today = today or dt.date.today()
    out = {}
    try:
        months = compute(R)
    except Exception:
        return out
    latest = None
    for fact in months:
        day = fact["end"][0]
        if dt.date.fromisoformat(day) <= today:
            out[f"/reports/{fact['slug']}/"] = day
            if latest is None or day > latest:
                latest = day
    if latest:
        out["/reports/"] = latest
    return out


def _money(n, digits=0):
    sign = "−" if n < 0 else ""
    return sign + f"${abs(n):,.{digits}f}"


def _tri(n):
    return f"${abs(float(n)) / 1e12:,.2f} trillion"


def _page(site, prefix, fact, clock, with_analytics):
    end_iso, end_amt = fact["end"]
    start_iso, start_amt = fact["start"]
    sentence = fact["sentence"]
    proj = fact["projection"]
    intr = fact["interest"]
    cite_bits = [
        f"{SOURCE_NAME}, closes of {quotable._long(start_iso)} (${start_amt:,.2f}) and {quotable._long(end_iso)} (${end_amt:,.2f}). {DTP}",
    ]
    rows = [
        ("Debt at the previous close", _money(start_amt, 2), quotable._long(start_iso), "U.S. Treasury, Debt to the Penny"),
        ("Debt at the month's last close", _money(end_amt, 2), quotable._long(end_iso), "U.S. Treasury, Debt to the Penny"),
        ("Debt added in the month", _money(fact["added"], 2), f"{quotable._long(start_iso)} to {quotable._long(end_iso)}", "Difference of those two closes"),
        ("Average per calendar day", _money(fact["avg"], 2), f"{fact['days']} days between the closes", "The difference divided by the number of calendar days between the two record dates"),
    ]
    if intr:
        rows.append(("Interest expense in the month", _money(intr["month_total"], 2), quotable._long(intr["date"]), intr["source_name"]))
        rows.append(("Interest per day", _money(intr["amount"], 2), f"{intr['days']} days in the month", "That official month total divided by the days in the month. Not cash paid on one day."))
        cite_bits.append(f"{intr['source_name']}, {quotable._long(intr['date'])} ({_money(intr['month_total'], 2)}). {intr['source']}")
    proj_html = ""
    if proj:
        when = quotable._long(proj["date"])
        proj_html = (
            f"<p>The next trillion is a projection, not a Treasury forecast. "
            f"From the {quotable._long(end_iso)} close of {_tri(end_amt)}, "
            f"the 90-day least-squares trend of Debt to the Penny closes from {quotable._long(proj['from'])} "
            f"through {quotable._long(proj['to'])} ({proj['n']} closes, {_money(proj['per_day'] / 1e9, 2)} billion a day) "
            f"reaches ${proj['trillion']} trillion on {when}.</p>"
        )
        cite_bits.append(
            f"Next-trillion date: projection from that trailing trend, not a Treasury forecast. "
            f"Window {proj['from']} to {proj['to']}."
        )
    else:
        proj_html = ("<p>No date is given for the next trillion. The 90-day least-squares trend through "
                     "this month's last close is not upward, so this page does not project one.</p>")
    intr_html = ""
    if intr:
        intr_html = (
            f"<p>Interest in {fact['label']}: {intr['source_name']} recorded {_money(intr['month_total'], 2)} "
            f"for the month (record date {quotable._long(intr['date'])}). "
            f"Divided by the {intr['days']} days in the month, that is {_money(intr['amount'], 2)} per day. "
            f"It is the month's accrual total divided by the days in the month, not the cash paid on a single day.</p>"
        )
    table = "".join(
        f"<tr><td>{E(a)}</td><td class=\"num\">{E(b)}</td><td>{E(c)}</td><td>{E(d)}</td></tr>"
        for a, b, c, d in rows
    )
    citation = " ".join(cite_bits)
    url = f"{site}/reports/{fact['slug']}/"
    article = {
        "@context": "https://schema.org", "@type": "Article",
        "headline": sentence, "datePublished": end_iso, "dateModified": end_iso,
        "url": url, "isAccessibleForFree": True,
        "author": {"@type": "Organization", "name": "Every Debt Clock", "url": site + "/"},
        "publisher": {"@type": "Organization", "name": "Every Debt Clock", "url": site + "/"},
        "citation": citation,
        "isBasedOn": [DTP] + ([intr["source"]] if intr else []),
    }
    dataset = {
        "@context": "https://schema.org", "@type": "Dataset",
        "name": f"U.S. national debt in {fact['label']}",
        "description": sentence, "url": url, "dateModified": end_iso,
        "isAccessibleForFree": True,
        "creator": {"@type": "Organization", "name": "Every Debt Clock", "url": site + "/"},
        "isBasedOn": [DTP],
        "temporalCoverage": f"{start_iso}/{end_iso}",
        "creditText": citation,
    }
    ld = ("<script type=\"application/ld+json\">" + json.dumps(article).replace("</", "<\\/") + "</script>"
          + "<script type=\"application/ld+json\">" + json.dumps(dataset).replace("</", "<\\/") + "</script>")
    b, r, t0 = clock["base"], clock["rate"], clock["t0"]
    clock_html = (
        f'<div class="hero lead" id="t-total" data-b="{b}" data-r="{r}" data-t="{t0}">'
        f'<div class="big num" id="hv">{_money(b, 2)}</div></div>'
    )
    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>U.S. national debt in {E(fact['label'])}</title>
<meta name="description" content="{E(sentence[:150])}">
<link rel="canonical" href="{E(url)}">
<meta property="og:title" content="U.S. national debt in {E(fact['label'])}"><meta property="og:description" content="{E(sentence[:150])}">
<meta property="og:url" content="{E(url)}"><meta property="og:type" content="article">
<link rel="stylesheet" href="{prefix}style.css">
{ld}
</head><body class="srclead"><main>
{clock_html}
<h1 class="quote">{E(sentence)}</h1>
<p>The clock above is the latest Debt to the Penny close, which is after this month. The debt added in {E(fact['label'])} is the {quotable._long(end_iso)} close minus the {quotable._long(start_iso)} close, {_money(fact['added'], 2)}. The average per calendar day is that difference divided by {fact['days']}.</p>
{intr_html}
{proj_html}
<table class="v"><tr><th>Figure</th><th>Amount</th><th>Date</th><th>Source</th></tr>{table}</table>
<p class="cite"><b>Citation.</b> {E(citation)}</p>
<p><a href="{prefix}reports/">All monthly reports</a> · <a href="{prefix}">U.S. debt clock</a> · <a href="{prefix}data/">Data</a></p>
<footer class="site-foot">Every Debt Clock · <a href="{prefix}embed/">Embed a clock</a> · <a href="{prefix}data/">Data</a> · <a href="{prefix}reports/">Reports</a> · <a href="{prefix}press/">Press</a> · <a href="{prefix}about/">About</a> · <a href="{prefix}methodology/">Methodology</a> · <a href="{prefix}privacy/">Privacy</a> · <a href="{prefix}contact/">Contact</a> · Independent site, not affiliated with the U.S. government. Not financial advice.</footer>
</main>
<header class="top"><div class="topin"><a class="brand" href="{prefix}">EVERY <b>DEBT</b> CLOCK</a>
<nav class="plnav"><a href="{prefix}">United States</a><a href="{prefix}states/">States</a><a href="{prefix}world/">World</a><a href="{prefix}reports/">Reports</a><a href="{prefix}data/">Data</a></nav></div></header>
<script>(function(){{var H=document.getElementById('t-total'),hv=document.getElementById('hv');if(!H||!hv)return;var B=+H.dataset.b,R=+H.dataset.r,T0=+H.dataset.t;var nf=new Intl.NumberFormat('en-US',{{minimumFractionDigits:2,maximumFractionDigits:2}});
function f(){{var x=B+R*(Date.now()/1000-T0);hv.textContent=(x<0?'−$':'$')+nf.format(Math.abs(x));requestAnimationFrame(f)}}f()}})();</script>
</body></html>"""
    return with_analytics(body) if with_analytics else body


def _index(site, prefix, months, clock, with_analytics):
    latest = months[-1]
    url = f"{site}/reports/"
    items = []
    for fact in reversed(months):
        items.append(
            f'<li><a href="{E(fact["slug"])}/">{E(fact["label"])}</a> '
            f'{E(fact["sentence"])}</li>'
        )
    b, r, t0 = clock["base"], clock["rate"], clock["t0"]
    sentence = latest["sentence"]
    article = {
        "@context": "https://schema.org", "@type": "CollectionPage",
        "name": "Monthly U.S. national debt reports",
        "description": sentence, "url": url, "dateModified": latest["end"][0],
        "isAccessibleForFree": True,
        "isBasedOn": DTP,
    }
    ld = "<script type=\"application/ld+json\">" + json.dumps(article).replace("</", "<\\/") + "</script>"
    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Monthly U.S. national debt reports</title>
<meta name="description" content="{E(sentence[:150])}">
<link rel="canonical" href="{E(url)}">
<link rel="stylesheet" href="{prefix}style.css">
{ld}
</head><body class="srclead"><main>
<div class="hero lead" id="t-total" data-b="{b}" data-r="{r}" data-t="{t0}"><div class="big num" id="hv">{_money(b, 2)}</div></div>
<h1 class="quote">{E(sentence)}</h1>
<p>Each report uses Debt to the Penny closes already in the daily file. A month is added after a later close is in that file. Interest per day is included only when Treasury's interest-expense series has that month.</p>
<ul>{''.join(items)}</ul>
<p><a href="{prefix}">U.S. debt clock</a> · <a href="{prefix}data/us-debt-daily.json">Daily Treasury file</a></p>
<footer class="site-foot">Every Debt Clock · <a href="{prefix}embed/">Embed a clock</a> · <a href="{prefix}data/">Data</a> · <a href="{prefix}reports/">Reports</a> · <a href="{prefix}press/">Press</a> · <a href="{prefix}about/">About</a> · <a href="{prefix}methodology/">Methodology</a> · <a href="{prefix}privacy/">Privacy</a> · <a href="{prefix}contact/">Contact</a> · Independent site, not affiliated with the U.S. government. Not financial advice.</footer>
</main>
<header class="top"><div class="topin"><a class="brand" href="{prefix}">EVERY <b>DEBT</b> CLOCK</a>
<nav class="plnav"><a href="{prefix}">United States</a><a href="{prefix}states/">States</a><a href="{prefix}world/">World</a><a href="{prefix}reports/" class="on">Reports</a><a href="{prefix}data/">Data</a></nav></div></header>
<script>(function(){{var H=document.getElementById('t-total'),hv=document.getElementById('hv');if(!H||!hv)return;var B=+H.dataset.b,R=+H.dataset.r,T0=+H.dataset.t;var nf=new Intl.NumberFormat('en-US',{{minimumFractionDigits:2,maximumFractionDigits:2}});
function f(){{var x=B+R*(Date.now()/1000-T0);hv.textContent=(x<0?'−$':'$')+nf.format(Math.abs(x));requestAnimationFrame(f)}}f()}})();</script>
</body></html>"""
    return with_analytics(body) if with_analytics else body


def build(R, SITE, with_analytics, debt):
    months = compute(R)
    if not months:
        raise SystemExit("monthly reports: no completed month in us-debt-daily.json")
    clock = {"base": float(debt["base"]), "rate": float(debt.get("rate") or 0), "t0": float(debt["t0"])}
    urls = []
    index_dir = os.path.join(R, "reports")
    os.makedirs(index_dir, exist_ok=True)
    # Drop month directories the file no longer supports, so a rebuilt site does not keep a stale month.
    keep = {fact["slug"] for fact in months}
    for name in os.listdir(index_dir):
        path = os.path.join(index_dir, name)
        if os.path.isdir(path) and name not in keep:
            for fn in os.listdir(path):
                os.remove(os.path.join(path, fn))
            os.rmdir(path)
    open(os.path.join(index_dir, "index.html"), "w", encoding="utf-8").write(
        _index(SITE, "../", months, clock, with_analytics))
    urls.append(f"{SITE}/reports/")
    for fact in months:
        dest = os.path.join(index_dir, fact["slug"])
        os.makedirs(dest, exist_ok=True)
        open(os.path.join(dest, "index.html"), "w", encoding="utf-8").write(
            _page(SITE, "../../", fact, clock, with_analytics))
        urls.append(f"{SITE}/reports/{fact['slug']}/")
    latest = months[-1]
    intr = latest["interest"]
    proj = latest["projection"]
    print(f"reports: {len(months)} months, latest {latest['slug']}")
    print(f"  added {_money(latest['added'], 2)} from {latest['start'][0]} to {latest['end'][0]} ({latest['days']} days, avg {_money(latest['avg'], 2)}/day)")
    if intr:
        print(f"  interest {_money(intr['month_total'], 2)} on {intr['date']}, {_money(intr['amount'], 2)} per day")
    else:
        print("  interest omitted")
    if proj:
        print(f"  projection ${proj['trillion']} trillion on {proj['date']} at {_money(proj['per_day'], 0)}/day from {proj['from']} to {proj['to']}")
    return urls
