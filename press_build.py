"""Press kit for the US debt reaching $41 trillion.

Every figure is computed from the homepage debt_total ticker (Treasury close,
90-day per-second rate, t0) or from Debt to the Penny closes. The 12-month and
3-year paces use the same least-squares slope as pipeline/fetch.py, on a longer
trailing window of the same daily series. Nothing on the page is typed in as a
projection.
"""
import datetime as dt
import html
import json
import math
import os
import urllib.request
from decimal import Decimal
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

import crossing_banner
import embed_build

ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")
TARGET = 41 * 10 ** 12
LEVEL = 41
API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny"
DTP = "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny"
FD = "/usr/share/fonts/truetype/dejavu/"
E = html.escape


def _font(name, size):
    return ImageFont.truetype(FD + name, size)


def eod_et(datestr):
    """End of an ET calendar day. Same instant pipeline/fetch.py uses as t0."""
    d = dt.date.fromisoformat(datestr)
    return dt.datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=ET).timestamp()


def ols_slope(xs, ys):
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        raise ValueError("least-squares window has no time spread")
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx


def hit_ts(base, rate, t0, freeze, target):
    """Unix time the straight projection base + rate*(t-t0) reaches target. None if it will not, or the debt limit binds first."""
    if not rate or rate <= 0 or base >= target:
        return None
    ts = t0 + (target - base) / rate
    if freeze and ts > freeze:
        return None
    return ts


def _fetch_rows(since):
    url = (f"{API}?filter=record_date:gte:{since}&sort=record_date&page[size]=10000"
           "&fields=record_date,tot_pub_debt_out_amt")
    req = urllib.request.Request(url, headers={"User-Agent": "everydebtclock-press/1.0"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.load(resp)
    pages = int(payload.get("meta", {}).get("total-pages") or 1)
    if pages != 1:
        raise RuntimeError(f"Debt to the Penny returned {pages} pages; press build expects one")
    rows = [(r["record_date"], r["tot_pub_debt_out_amt"]) for r in payload["data"]]
    if len(rows) < 100:
        raise RuntimeError(f"Debt to the Penny returned {len(rows)} rows")
    return rows


def _cache_path(R):
    return os.path.join(R, "cache", "dtp_press_series.json")


def load_series(R, as_of, base):
    """Daily closes through the clock's as-of date. Prefer a live Treasury pull; fall back to the committed cache if it matches the clock."""
    since = (dt.date.fromisoformat(as_of) - dt.timedelta(days=3 * 365 + 70)).isoformat()
    err = None
    rows = None
    try:
        rows = _fetch_rows(since)
    except Exception as exc:
        err = str(exc)[:300]
    if rows:
        rows = [(d, a) for d, a in rows if d <= as_of]
        hit = [a for d, a in rows if d == as_of]
        if hit and abs(float(hit[-1]) - float(base)) <= 0.02:
            path = _cache_path(R)
            fresh = {"source": API, "as_of": as_of, "rows": rows}
            old = None
            if os.path.exists(path):
                try:
                    old = json.load(open(path))
                except Exception:
                    old = None
            if not old or old.get("rows") != rows or old.get("as_of") != as_of:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                json.dump(fresh, open(path, "w"), separators=(",", ":"))
                fresh["retrieved"] = dt.datetime.now(CT).date().isoformat()
                json.dump(fresh, open(path, "w"), separators=(",", ":"))
            else:
                fresh = old
            return fresh["rows"], "Fiscal Data API", fresh.get("retrieved"), err
        err = f"API series has no close on {as_of} matching the clock base {base}"
    path = _cache_path(R)
    if os.path.exists(path):
        cached = json.load(open(path))
        rows = [(d, a) for d, a in cached.get("rows") or [] if d <= as_of]
        hit = [a for d, a in rows if d == as_of]
        if hit and abs(float(hit[-1]) - float(base)) <= 0.02:
            return rows, "cached Fiscal Data API series", cached.get("retrieved"), err
    raise SystemExit(f"press: no Debt to the Penny series matching the {as_of} clock close. {err or ''}")


def _window(rows, as_of, days):
    t_latest = eod_et(as_of)
    return [(d, a) for d, a in rows if 0 <= t_latest - eod_et(d) <= days * 86400]


def _crossings(rows):
    """First close at or above each whole trillion, prior close below it. Same rule as pipeline/series.py."""
    series = [(d, Decimal(a)) for d, a in rows]
    if len(series) < 2:
        raise ValueError("series too short for crossings")
    start = series[0][1]
    n = int(start // Decimal(10 ** 12)) + 1
    idx = 0
    last = series[-1][1]
    out = []
    while Decimal(n) * Decimal(10 ** 12) <= last:
        thr = Decimal(n) * Decimal(10 ** 12)
        while idx < len(series) and series[idx][1] < thr:
            idx += 1
        if idx <= 0 or idx >= len(series):
            break
        d, amt = series[idx]
        pd, pamt = series[idx - 1]
        if not (pamt < thr <= amt):
            raise ValueError(f"${n}T crossing is not a step up")
        out.append({"trillion": n, "date": d, "amount": amt, "prior_date": pd, "prior_amount": pamt})
        n += 1
    return out


def _fmt_ts(ts):
    if ts is None:
        return None
    rounded = math.floor(ts + 0.5)
    ct = dt.datetime.fromtimestamp(rounded, CT)
    et = dt.datetime.fromtimestamp(rounded, ET)
    pat = "%B %-d, %Y, %-I:%M:%S %p"
    return {
        "unix": ts,
        "rounded": rounded,
        "ct": ct.strftime(pat) + " CT",
        "et": et.strftime(pat) + " ET",
        "ct_date": ct.date(),
        "et_date": et.date(),
        "ct_day": ct.strftime("%B %-d, %Y"),
        "et_day": et.strftime("%B %-d, %Y"),
    }


def _money_dec(amount):
    q = Decimal(amount).quantize(Decimal("0.01"))
    sign = "−$" if q < 0 else "$"
    whole, frac = f"{abs(q):.2f}".split(".")
    return sign + f"{int(whole):,}" + "." + frac


def _money_float(amount, digits=2):
    if amount is None:
        return "—"
    sign = "−$" if amount < 0 else "$"
    return sign + f"{abs(amount):,.{digits}f}"


def _per_day(rate):
    return f"${abs(rate) * 86400 / 1e9:,.3f} billion"


def _per_sec(rate):
    return f"${abs(rate):,.2f}"


def _fdate(iso):
    return dt.date.fromisoformat(iso).strftime("%b %-d, %Y")


def _long_date(day):
    return day.strftime("%B %-d, %Y")


def next_business_publish(record_day):
    """Next day that is not a weekend and not January 1. Used only to say when a Dec 31 close would normally be posted."""
    d = record_day + dt.timedelta(days=1)
    while d.weekday() >= 5 or (d.month == 1 and d.day == 1):
        d += dt.timedelta(days=1)
    return d


def compute(R, td, history):
    base = float(td["base"])
    rate = float(td["rate"])
    t0 = float(td["t0"])
    freeze = td.get("freeze_t")
    as_of = td["as_of"]
    calc = td.get("calc") or {}
    if calc.get("type") != "ols":
        raise SystemExit("press: debt_total is not an OLS 90-day rate")
    if td.get("held_at_limit"):
        raise SystemExit("press: the clock is held at the debt limit, so it is not projecting a crossing")
    rows, origin, retrieved, fetch_err = load_series(R, as_of, base)
    by = {d: a for d, a in rows}
    if as_of not in by:
        raise SystemExit("press: series is missing the clock's as-of date")

    w90 = _window(rows, as_of, 90)
    if not w90 or w90[0][0] != calc["first"][0] or w90[-1][0] != calc["last"][0] or len(w90) != calc["n"]:
        raise SystemExit(
            f"press: 90-day window {w90[0][0] if w90 else None}..{w90[-1][0] if w90 else None} "
            f"n={len(w90)} does not match the clock ({calc.get('window')}, n={calc.get('n')})")
    if abs(float(w90[0][1]) - float(calc["first"][1])) > 0.02 or abs(float(w90[-1][1]) - base) > 0.02:
        raise SystemExit("press: 90-day window amounts do not match debt_total.calc")
    ols90 = ols_slope([eod_et(d) for d, _ in w90], [float(a) for _, a in w90])
    if abs(ols90 - float(calc["slope"])) > 1e-4:
        raise SystemExit(f"press: recomputed 90-day slope {ols90} != clock slope {calc['slope']}")

    straight_sec = eod_et(w90[-1][0]) - eod_et(w90[0][0])
    straight = (float(w90[-1][1]) - float(w90[0][1])) / straight_sec

    def pace(days, name, method, use_rate=None):
        w = _window(rows, as_of, days)
        slope = ols_slope([eod_et(d) for d, _ in w], [float(a) for _, a in w])
        used = slope if use_rate is None else use_rate
        return {
            "name": name, "method": method, "days": days, "n": len(w),
            "first": w[0][0], "last": w[-1][0], "first_amount": w[0][1], "last_amount": w[-1][1],
            "slope": slope, "rate": used, "when": _fmt_ts(hit_ts(base, used, t0, freeze, TARGET)),
        }

    p90 = pace(90, "90-day", "Least squares, the homepage clock's per-second rate", rate)
    p90["slope_of_total"] = ols90
    p365 = pace(365, "12-month", "Least squares on the trailing 365 days of closes")
    p3y = pace(3 * 365, "3-year", "Least squares on the trailing 1,095 days of closes")
    straight_when = _fmt_ts(hit_ts(base, straight, t0, freeze, TARGET))
    ctx = calc.get("context_1y") or {}
    ctx_when = _fmt_ts(hit_ts(base, float(ctx["rate"]), t0, freeze, TARGET)) if ctx.get("rate") else None

    found = _crossings(rows)
    by_n = {c["trillion"]: c for c in found}
    checked = []
    for c in history["crossings"]:
        if Decimal(c["trillion"]) * Decimal(10 ** 12) <= Decimal(rows[0][1]):
            continue
        got = by_n.get(c["trillion"])
        if not got or got["date"] != c["date"] or abs(got["amount"] - Decimal(str(c["amount"]))) > Decimal("0.02"):
            raise SystemExit(f"press: ${c['trillion']}T crossing {c['date']} does not match a fresh pass over the Debt to the Penny rows")
        checked.append(got)
    if not any(c["trillion"] == 40 for c in checked):
        raise SystemExit("press: $40 trillion is not in the checked crossings")

    milestones = []
    for prev, cur in zip(checked, checked[1:]):
        unders = [(d, a) for d, a in rows if d > cur["date"] and Decimal(a) < Decimal(cur["trillion"]) * Decimal(10 ** 12)]
        nxt = next(((d, a) for d, a in rows if d > cur["date"]), None)
        milestones.append({
            "trillion": cur["trillion"], "date": cur["date"], "amount": cur["amount"],
            "prior_date": cur["prior_date"], "prior_amount": cur["prior_amount"],
            "days": (dt.date.fromisoformat(cur["date"]) - dt.date.fromisoformat(prev["date"])).days,
            "from_trillion": prev["trillion"], "from_date": prev["date"],
            "dollar_change": cur["amount"] - prev["amount"],
            "next": nxt, "unders": unders,
        })
    # The chart starts at the step into $35 trillion when that crossing was re-checked.
    chart_rows = [m for m in milestones if m["trillion"] >= 35]

    year_ends = []
    dates = [d for d, _ in rows]
    for i, (d, a) in enumerate(rows):
        if not d.endswith("-12-31"):
            continue
        prev = rows[i - 1] if i else None
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        year_ends.append({"date": d, "amount": Decimal(a), "prev": prev, "next": nxt})

    record_day = dt.date(2026, 12, 31)
    publish_day = next_business_publish(record_day)
    gap = TARGET - base
    main_when = p90["when"]
    if not main_when or not straight_when:
        raise SystemExit("press: the 90-day pace does not reach $41 trillion before the debt limit")
    window_days = sorted({main_when["ct_date"], straight_when["ct_date"]})
    return {
        "base": base, "rate": rate, "t0": t0, "freeze": freeze, "as_of": as_of,
        "gap": gap, "seconds": gap / rate, "origin": origin, "retrieved": retrieved,
        "fetch_err": fetch_err, "n_rows": len(rows), "first_row": rows[0][0], "last_row": rows[-1][0],
        "p90": p90, "p365": p365, "p3y": p3y, "straight": straight, "straight_when": straight_when,
        "ctx": ctx, "ctx_when": ctx_when, "chart_rows": chart_rows, "year_ends": year_ends,
        "record_day": record_day, "publish_day": publish_day, "window_days": window_days,
        "ols_matches_clock": abs(rate - ols90) * 86400 < 1,
        "rate_vs_ols_per_day": (rate - ols90) * 86400,
        "calc_window": calc.get("window"), "calc_n": calc.get("n"),
    }


def _fit(draw, text, font_name, max_w, start, minimum=18):
    size = start
    while size > minimum:
        font = _font(font_name, size)
        if draw.textlength(text, font=font) <= max_w:
            return font
        size -= 2
    return _font(font_name, size)


def _brand(d, y=36):
    d.text((48, y), "EVERY ", font=_font("DejaVuSans-Bold.ttf", 28), fill="#e8edf5")
    x = 48 + d.textlength("EVERY ", font=_font("DejaVuSans-Bold.ttf", 28))
    d.text((x, y), "DEBT", font=_font("DejaVuSans-Bold.ttf", 28), fill="#ff4d5e")
    x += d.textlength("DEBT ", font=_font("DejaVuSans-Bold.ttf", 28))
    d.text((x, y), "CLOCK", font=_font("DejaVuSans-Bold.ttf", 28), fill="#e8edf5")


def write_og(path, facts):
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), "#07090d")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 8], fill="#ff4d5e")
    _brand(d, 36)
    d.text((48, 100), "WHEN THE US DEBT HITS $41 TRILLION", font=_font("DejaVuSans-Bold.ttf", 28), fill="#8a97ab")
    when = facts["p90"]["when"]
    big = when["ct_date"].strftime("%b %-d, %Y")
    d.text((48, 150), big, font=_fit(d, big, "DejaVuSans-Bold.ttf", 1100, 92), fill="#ffffff")
    clock = when["ct"].rsplit(", ", 1)[-1]
    d.text((48, 268), clock, font=_fit(d, clock, "DejaVuSansMono-Bold.ttf", 1100, 40), fill="#ffb547")
    d.text((48, 324), when["et"], font=_font("DejaVuSans.ttf", 26), fill="#c9d3e2")
    d.text((48, 368), "Projection, not a Treasury forecast · " + _money_float(facts["gap"], 0) + " left", font=_font("DejaVuSans.ttf", 22), fill="#8a97ab")
    chips = (
        ("90-DAY PACE", _per_day(facts["rate"]) + " a day"),
        ("12-MONTH PACE", facts["p365"]["when"]["ct_day"]),
        ("3-YEAR PACE", facts["p3y"]["when"]["ct_day"]),
    )
    x = 48
    for label, value in chips:
        d.rounded_rectangle([x, 430, x + 360, 520], 12, fill="#121925")
        d.text((x + 16, 444), label, font=_font("DejaVuSans-Bold.ttf", 16), fill="#5c687a")
        d.text((x + 16, 474), value, font=_fit(d, value, "DejaVuSansMono-Bold.ttf", 328, 26), fill="#e8edf5")
        x += 376
    d.text((48, H - 58), "everydebtclock.com/41-trillion/", font=_font("DejaVuSans-Bold.ttf", 24), fill="#5aa9ff")
    stamp = "Debt to the Penny, " + _fdate(facts["as_of"]) + " close"
    tw = d.textlength(stamp, font=_font("DejaVuSans.ttf", 20))
    d.text((W - 48 - tw, H - 54), stamp, font=_font("DejaVuSans.ttf", 20), fill="#5c687a")
    im.save(path, optimize=True)


def write_clock(path, facts):
    W, H = 1600, 900
    im = Image.new("RGB", (W, H), "#07090d")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 10], fill="#ff4d5e")
    _brand(d, 48)
    d.text((48, 120), "UNTIL $41 TRILLION", font=_font("DejaVuSans-Bold.ttf", 28), fill="#8a97ab")
    when = facts["p90"]["when"]
    big = when["ct"]
    d.text((48, 180), big, font=_fit(d, big, "DejaVuSansMono-Bold.ttf", W - 96, 64), fill="#ffffff")
    d.text((48, 280), when["et"], font=_font("DejaVuSans.ttf", 36), fill="#ffb547")
    left = _money_float(facts["gap"], 2) + " still to go"
    d.text((48, 380), left, font=_fit(d, left, "DejaVuSansMono-Bold.ttf", W - 96, 48), fill="#e8edf5")
    lines = [
        f"Homepage clock, 90-day pace: {_per_day(facts['rate'])} a day, {_per_sec(facts['rate'])} a second.",
        f"From Treasury's {_fdate(facts['as_of'])} Debt to the Penny close of {_money_float(facts['base'])}.",
        "A projection. Not a Treasury forecast. The Eastern-time date is the next calendar day.",
    ]
    y = 500
    for line in lines:
        d.text((48, y), line, font=_font("DejaVuSans.ttf", 28), fill="#c9d3e2")
        y += 46
    d.text((48, H - 70), "everydebtclock.com/41-trillion/", font=_font("DejaVuSans-Bold.ttf", 28), fill="#5aa9ff")
    im.save(path, optimize=True)


def _bar_chart(path, title, subtitle, rows, value_of, value_label, axis):
    """rows: list of (label, number). Horizontal bars."""
    W = 1200
    n = len(rows)
    H = 150 + n * 64 + 70
    im = Image.new("RGB", (W, H), "#07090d")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 6], fill="#ff4d5e")
    d.text((36, 22), title, font=_font("DejaVuSans-Bold.ttf", 24), fill="#e8edf5")
    d.text((36, 56), subtitle, font=_font("DejaVuSans.ttf", 16), fill="#8a97ab")
    plot_l = 280
    top = 110
    val_font = _font("DejaVuSansMono-Bold.ttf", 18)
    label_w = max(d.textlength(value_label(raw), font=val_font) for _, raw in rows)
    plot_r = W - 36 - label_w - 16
    vmax = max(value_of(v) for _, v in rows) * 1.08
    for i, (lab, raw) in enumerate(rows):
        y = top + i * 64
        val = value_of(raw)
        w = (val / vmax) * (plot_r - plot_l) if vmax else 0
        lab_font = _font("DejaVuSans.ttf", 18)
        tw = d.textlength(lab, font=lab_font)
        d.text((plot_l - 16 - tw, y + 8), lab, font=lab_font, fill="#c9d3e2")
        d.rounded_rectangle([plot_l, y, plot_l + max(w, 2), y + 36], 4, fill="#5aa9ff")
        d.text((plot_l + w + 12, y + 6), value_label(raw), font=val_font, fill="#e8edf5")
    d.text((plot_l, H - 36), axis, font=_font("DejaVuSans.ttf", 14), fill="#5c687a")
    credit = "EveryDebtClock.com · Treasury Debt to the Penny"
    cw = d.textlength(credit, font=_font("DejaVuSans.ttf", 14))
    d.text((W - 36 - cw, H - 36), credit, font=_font("DejaVuSans.ttf", 14), fill="#5aa9ff")
    im.save(path, optimize=True)


def _page(ctx, facts):
    site = ctx["SITE"]
    as_of = facts["as_of"]
    when = facts["p90"]["when"]
    sw = facts["straight_when"]
    days = facts["window_days"]
    if len(days) == 1:
        window = _long_date(days[0]) + " (Central)"
    else:
        window = _long_date(days[0]) + " through " + _long_date(days[1]) + " (Central)"
    rate = facts["rate"]
    gap = facts["gap"]
    code = embed_build.snippet(site, "embed/41-trillion/", f"{site}/41-trillion/",
                               "$41 trillion countdown", "$41 trillion countdown by EveryDebtClock.com")
    pace_rows = []
    for key, label in (("p90", "90-day least squares, homepage clock"), ("p365", "12-month least squares"), ("p3y", "3-year least squares")):
        p = facts[key]
        w = p["when"]
        pace_rows.append(
            "<tr>"
            f"<td>{E(label)}<span class=\"when\">{E(p['method'])}. {p['n']} closes, {_fdate(p['first'])} to {_fdate(p['last'])}.</span></td>"
            f"<td class=\"num\">{E(_per_day(p['rate']))}</td>"
            f"<td class=\"num\">{E(_per_sec(p['rate']))}</td>"
            f"<td>{E(w['ct']) if w else 'Not before the debt limit'}<span class=\"when\">{E(w['et']) if w else ''}</span></td>"
            "</tr>")
    mile_rows = []
    for m in facts["chart_rows"]:
        nxt = m["next"]
        if nxt and Decimal(nxt[1]) < Decimal(m["trillion"]) * Decimal(10 ** 12):
            nxt_s = f"Next close {_fdate(nxt[0])} was back under, {_money_dec(nxt[1])}"
        elif nxt:
            nxt_s = f"Next close {_fdate(nxt[0])} stayed at or above, {_money_dec(nxt[1])}"
        else:
            nxt_s = "No later close in this series"
        mile_rows.append(
            "<tr>"
            f"<td>${m['trillion']} trillion</td>"
            f"<td>{_fdate(m['date'])}</td>"
            f"<td class=\"num\">{E(_money_dec(m['amount']))}</td>"
            f"<td class=\"num\">{E(_money_dec(m['prior_amount']))}<span class=\"when\">prior close {_fdate(m['prior_date'])}</span></td>"
            f"<td class=\"num\">{m['days']} days<span class=\"when\">from ${m['from_trillion']}T on {_fdate(m['from_date'])}</span></td>"
            f"<td>{E(nxt_s)}</td>"
            "</tr>")
    ye_rows = []
    for block in facts["year_ends"]:
        cluster = []
        if block["prev"]:
            cluster.append(("previous close", block["prev"][0], Decimal(block["prev"][1]), None))
        cluster.append(("December 31", block["date"], block["amount"], None if not block["prev"] else block["amount"] - Decimal(block["prev"][1])))
        if block["next"]:
            cluster.append(("next close", block["next"][0], Decimal(block["next"][1]), Decimal(block["next"][1]) - block["amount"]))
        for name, d, amt, delta in cluster:
            delta_s = "—" if delta is None else _money_dec(delta)
            ye_rows.append(f"<tr><td>{E(name)}</td><td>{_fdate(d)}</td><td class=\"num\">{E(_money_dec(amt))}</td><td class=\"num\">{E(delta_s)}</td></tr>")
        ye_rows.append("<tr><td colspan=\"4\"></td></tr>")
    dip_notes = []
    for m in facts["chart_rows"]:
        if m["trillion"] not in (38, 39, 40):
            continue
        unders = m["unders"]
        if not unders:
            dip_notes.append(f"<li>Every Debt to the Penny close after the ${m['trillion']} trillion crossing, through {_fdate(facts['as_of'])}, stayed at or above ${m['trillion']} trillion.</li>")
        elif len(unders) == 1:
            dip_notes.append(
                f"<li>The first ${m['trillion']} trillion close was {_fdate(m['date'])}. "
                f"The next close, {_fdate(unders[0][0])}, was back under, at {E(_money_dec(unders[0][1]))}. "
                f"Every later close in this series, through {_fdate(facts['as_of'])}, was at or above ${m['trillion']} trillion.</li>")
        else:
            dip_notes.append(
                f"<li>The first ${m['trillion']} trillion close was {_fdate(m['date'])}. "
                f"The next close, {_fdate(unders[0][0])}, was back under, at {E(_money_dec(unders[0][1]))}. "
                f"The last close in this series that was back under ${m['trillion']} trillion was {_fdate(unders[-1][0])}, at {E(_money_dec(unders[-1][1]))}.</li>")
    one_year = facts["ctx"]
    one_year_when = facts["ctx_when"]
    ctx_note = ""
    if one_year and one_year_when:
        ctx_note = (
            f"<p>The clock already stores a separate one-year context rate, and it is not the 12-month column above. "
            f"It is the {_fdate(facts['as_of'])} close minus the {_fdate(one_year['from'][0])} close, divided by the seconds between those two end-of-day instants: "
            f"{E(_per_sec(one_year['rate']))} a second, {E(_per_day(one_year['rate']))} a day. "
            f"At that two-point rate, $41 trillion falls on {E(one_year_when['ct'])} ({E(one_year_when['et'])}). "
            f"The homepage ticks at the 90-day least-squares rate, not this one.</p>")
    match = "The homepage per-second rate matches a least-squares fit of the total itself over those same 61 closes."
    if not facts["ols_matches_clock"]:
        match = ("The homepage rate is the sum of the public and intragovernmental 90-day slopes. "
                 f"A fit of the total alone differs by about ${facts['rate_vs_ols_per_day']:,.0f} a day. "
                 "The projection on this page uses the homepage rate.")
    freeze_s = ""
    if facts["freeze"]:
        fr = _fmt_ts(facts["freeze"])
        freeze_s = f" The homepage clock stops projecting at the statutory limit, {E(fr['ct'])}. Each projected crossing on this page is before that."
    title = "Press kit: when the US debt reaches $41 trillion"
    desc = (f"Projected $41 trillion crossing: {when['ct']}, from Treasury's {_fdate(as_of)} close and the 90-day pace. "
            f"Central-time window {window}. 12-month and 3-year paces are slower.")
    if len(desc) > 300:
        desc = desc[:297].rsplit(" ", 1)[0] + "."
    blob = {
        "base": facts["base"], "rate": facts["rate"], "t0": facts["t0"], "freeze": facts["freeze"],
        "as_of": as_of, "target": TARGET,
    }
    data = json.dumps(blob, separators=(",", ":")).replace("<", "\\u003c")
    official_sentence = (
        f"Live estimate, not Treasury's figure. This clock is past $41 trillion. Treasury has not posted a Debt to the Penny close at or above $41 trillion. "
        f"The latest official close is still {_money_float(facts['base'])} on {_fdate(as_of)}. Treasury posts the prior business day's close on the next business day, usually in the afternoon (around 3 PM Central).")
    confirmed_sentence = (
        f"Treasury's figure is at or above $41 trillion. Debt to the Penny's close was {_money_float(facts['base'])} on {_fdate(as_of)}. "
        f"That is the official total. The digits still moving on this page are the live projection from that close.")
    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)} | Every Debt Clock</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{site}/press/">
<meta property="og:type" content="article"><meta property="og:site_name" content="Every Debt Clock">
<meta property="og:url" content="{site}/press/">
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">
<meta property="og:image" content="{site}/og/41-trillion.png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Projected date the US debt reaches $41 trillion">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{E(title)}">
<meta name="twitter:description" content="{E(desc)}"><meta name="twitter:image" content="{site}/og/41-trillion.png">
<meta name="theme-color" content="#07090d">
<link rel="icon" href="/favicon.ico" sizes="16x16 32x32 48x48"><link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png"><link rel="icon" type="image/svg+xml" href="/icon.svg">
<style>
:root{{--bg:#07090d;--line:#1c2533;--txt:#e8edf5;--mut:#8a97ab;--dim:#5c687a;--red:#ff4d5e;--blue:#5aa9ff;--amber:#ffb547}}
body{{margin:0;background:#07090d;color:var(--txt);font-family:-apple-system,BlinkMacSystemFont,Inter,Segoe UI,Roboto,sans-serif;line-height:1.5}}
main{{max-width:920px;margin:0 auto;padding:8px 16px 64px}}a{{color:#5aa9ff;text-decoration:none}}
.brand{{font-weight:800;letter-spacing:.06em;font-size:14px;display:inline-block;margin:8px 0 4px;color:#e8edf5}}.brand b{{color:#ff4d5e}}
h1{{font-size:28px;line-height:1.2;margin:8px 0 8px}}h2{{font-size:18px;margin:28px 0 8px}}
p,li{{color:#c2ccda;font-size:15.5px}}p{{margin:0 0 12px}}
.hero{{border:1px solid var(--line);background:linear-gradient(180deg,#101828,#0b0f16);border-radius:18px;padding:18px 18px 14px;margin:12px 0}}
.k{{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--mut);margin:0}}
.big{{font:700 clamp(22px,4.6vw,40px)/1.15 ui-monospace,Menlo,monospace;color:#fff;margin:8px 0 0}}
.sub{{color:#ffb547;font-size:18px;margin:6px 0 0}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:14px}}
.grid div{{background:rgba(255,255,255,.03);border:1px solid var(--line);border-radius:12px;padding:8px 10px}}
.l{{display:block;font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em}}
.n{{font:600 clamp(16px,2.4vw,22px) ui-monospace,Menlo,monospace}}
table{{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0 14px}}
th,td{{border-bottom:1px solid #1c2533;padding:8px;text-align:left;vertical-align:top}}
th{{color:#8a97ab;font-size:12px;text-transform:uppercase;letter-spacing:.04em}}
td.num{{font-family:ui-monospace,Menlo,monospace;text-align:right;white-space:nowrap}}
td .when, .when{{display:block;color:#8a97ab;font-size:12px;font-weight:400}}
.tw{{overflow-x:auto}}
.note{{border:1px solid #5a3a12;background:#20170a;color:#ffb547;border-radius:10px;padding:10px 12px;font-size:14px}}
.banner{{border:1px solid #5a3a12;background:#20170a;color:#ffb547;border-radius:10px;padding:10px 12px;font-size:14.5px;margin:8px 0}}
.banner[hidden]{{display:none}}
figure{{margin:12px 0}}figcaption{{color:#8a97ab;font-size:13px;margin-top:4px}}
img{{max-width:100%;height:auto;border-radius:12px;border:1px solid var(--line)}}
.dl{{display:inline-block;margin:4px 8px 4px 0}}
textarea{{width:100%;box-sizing:border-box;background:#0a0e15;color:#e8edf5;border:1px solid #1c2533;border-radius:8px;padding:8px;font:12px/1.45 ui-monospace,Menlo,monospace}}
footer{{color:#5c687a;font-size:12px;margin-top:28px}}
code{{font-family:ui-monospace,Menlo,monospace;font-size:13px}}
@media (max-width:640px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body>
<main>
<a class="brand" href="../">EVERY <b>DEBT</b> CLOCK</a><a class="navembed" href="../embed/" style="margin-left:12px;font-size:13px;font-weight:650">Embed</a>
{crossing_banner.HTML}
<h1>Press kit: the US debt and $41 trillion</h1>
<p>At the same 90-day pace as the <a href="../">homepage clock</a>, the projection reaches $41 trillion on <b id="exact-ct">{E(when['ct'])}</b> (<b id="exact-et">{E(when['et'])}</b>). That instant is computed from Treasury's <b>{_fdate(as_of)}</b> Debt to the Penny close and the homepage per-second rate. It is a projection, not a Treasury forecast. The Central-time date window from the two fits of that same 90-day stretch is <b>{E(window)}</b>.</p>
<div class="hero" id="lead">
<p class="k">Exact projected time · 90-day pace</p>
<p class="big" id="exact-ct-2">{E(when['ct'])}</p>
<p class="sub" id="exact-et-2">{E(when['et'])}</p>
<div class="grid">
<div><span class="l">Countdown</span><span class="n" id="cd">…</span></div>
<div><span class="l">Still to go</span><span class="n" id="left">{E(_money_float(gap, 0))}</span></div>
<div><span class="l">Live projection now</span><span class="n" id="live">{E(_money_float(facts['base'], 0))}</span></div>
</div>
<p class="when">The countdown and the two running totals update in the browser from the clock's base, rate and t0. With JavaScript off, the countdown is the gap at the moment this page was built ({E(ctx["STAMP"])}). The projected clock time does not tick; it changes when Treasury's next close resets the base.</p>
</div>
<h2>The date window</h2>
<p>Both ends use the closes in the homepage's 90-day window ({E(facts['calc_window'])}, {facts['calc_n']} closes). The least-squares slope is the rate the clock ticks at, {E(_per_day(rate))} a day. {E(match)} A straight line from the first close in that window ({_fdate(facts['p90']['first'])}, {E(_money_dec(facts['p90']['first_amount']))}) to the last ({_fdate(facts['p90']['last'])}, {E(_money_dec(facts['p90']['last_amount']))}) is {E(_per_day(facts['straight']))} a day and reaches $41 trillion on <b>{E(sw['ct'])}</b> ({E(sw['et'])}).</p>
<p class="note">The window is those two fits, {E(window)}. It is not a confidence interval. The least-squares instant is late on December 31 in Central time and already January 1 in Eastern time, so the calendar date reporters print depends on the time zone, and the next Debt to the Penny closes can move it.</p>
<h2>Three paces, side by side</h2>
<p>Each row starts from the same official close, {E(_money_float(facts['base']))} on {_fdate(as_of)}, and runs forward at its own per-second rate. Only the 90-day row is the homepage clock. The 12-month row is the trailing 365 days. The 3-year row is the trailing 1,095 days. All three are least-squares slopes of Debt to the Penny closes, the same method as the 90-day rate.</p>
<div class="tw"><table>
<tr><th>Pace</th><th>$ / day</th><th>$ / second</th><th>Projected crossing</th></tr>
{''.join(pace_rows)}
</table></div>
{ctx_note}
<p>{freeze_s}</p>
<h2>Official figure versus the live clock</h2>
<p>Debt to the Penny is the debt at the close of business. This site's <a href="../methodology/">methodology</a> says each record is published the next business day, usually in the afternoon (around 3 PM Central in recent weeks). That is this site's description of recent timing, not a clock time Treasury publishes as a rule. Between posts, the homepage keeps moving at the 90-day pace. That running total is an estimate until the next close.</p>
<p>December 31, 2026 is a {facts['record_day'].strftime('%A')}. January 1, 2027 is a Friday and a federal holiday, and January 2 and 3 are the weekend. The next day that is not a weekend and not January 1 is <b>{facts['publish_day'].strftime('%A, %B %-d, %Y')}</b>. If Treasury follows the usual next-business-day pattern, the December 31 close would be posted then. This check skips only weekends and January 1.</p>
<p>The last business day of December has been a large up day, and part of the jump reversed on the next close. Interest credited to trust funds at the end of June and December is one reason the daily series is lumpy; the table is the measured change, not a split of how much was interest, and it is not a forecast for December 31, 2026.</p>
<div class="tw"><table>
<tr><th></th><th>Close date</th><th>Amount</th><th>Change from the row above</th></tr>
{''.join(ye_rows)}
</table></div>
<p class="when">As of the Debt to the Penny rows through {_fdate(as_of)}. Source: <a href="{DTP}" rel="noopener">Treasury, Debt to the Penny</a>.</p>
<h2>Days from one trillion to the next</h2>
<p>A crossing is the first Debt to the Penny close at or above that trillion, with the prior close below it. That is the rule on the <a href="../41-trillion/">$41 trillion countdown</a>. The dates below were recomputed from the daily rows and match the crossings stored for that page. Days are the calendar days from the previous trillion's first close to this one, not a count of business days. The dollar change is the difference of those two closes, so it is not exactly $1 trillion.</p>
<div class="tw"><table>
<tr><th>Level</th><th>First close at or above</th><th>Amount</th><th>Prior close</th><th>Days</th><th>The next close</th></tr>
{''.join(mile_rows)}
</table></div>
<ul>{''.join(dip_notes)}</ul>
<figure>
<img src="charts/days-per-trillion.png" alt="Days from one trillion crossing to the next, $35 trillion through $40 trillion" width="1200" height="520">
<figcaption>Days from one first-close to the next. Debt to the Penny, through {_fdate(as_of)}.</figcaption>
</figure>
<p><a class="dl" href="charts/days-per-trillion.png" download>Download the days chart (PNG)</a>
<a class="dl" href="charts/paces.png" download>Download the pace chart (PNG)</a></p>
<figure>
<img src="charts/paces.png" alt="Dollars per day at the 90-day, 12-month and 3-year paces" width="1200" height="360">
<figcaption>The three least-squares paces, in billions of dollars a day.</figcaption>
</figure>
<h2>Clock image and share image</h2>
<p>The clock image is a still of the 90-day projection for a story. The share image is what <a href="../41-trillion/">/41-trillion/</a> uses for Open Graph and Twitter. Both were drawn from the same projection as the table.</p>
<figure>
<img src="41-trillion-clock.png" alt="Until $41 trillion: {E(when['ct'])}" width="1600" height="900">
<figcaption>Screenshot-ready clock. <a href="41-trillion-clock.png" download>Download PNG</a>.</figcaption>
</figure>
<figure>
<img src="../og/41-trillion.png" alt="Share card for the $41 trillion projection" width="1200" height="630">
<figcaption>Share image, 1200 by 630. <a href="../og/41-trillion.png" download>Download PNG</a>.</figcaption>
</figure>
<h2>Countdown embed</h2>
<p>The widget below counts down to $41 trillion. It does not set a cookie and it does not load analytics. The page it links to is the <a href="../41-trillion/">$41 trillion countdown</a>.</p>
<div class="embedbox">
<iframe src="{site}/embed/41-trillion/" title="$41 trillion countdown" width="100%" height="160" style="border:0;background:#0e131b;border-radius:10px" loading="lazy"></iframe>
<textarea readonly rows="4" spellcheck="false" aria-label="Embed code">{E(code)}</textarea>
</div>
<h2>Banner that turns on at $41 trillion</h2>
<p>The homepage, this page and the countdown page already contain two sentences. Neither is showing, because the live projection and Treasury's {_fdate(as_of)} close are both still under $41 trillion. The live sentence turns on by itself when the clock passes $41 trillion and Treasury's latest close is still under it. The official sentence replaces it when a Debt to the Penny close is at or above $41 trillion. Add <code>?cross41=preview</code> to the <a href="../?cross41=preview">homepage</a> to preview the live sentence. The preview says it is a preview.</p>
<div class="banner"><b>Prepared copy, live estimate.</b> {E(official_sentence)}</div>
<p class="when">Shown only while the clock is past $41 trillion and the latest Debt to the Penny close is still under it. The amount in parentheses is the live projection at that moment. It is not filled in here, so this specimen does not invent a total.</p>
<div class="banner"><b>Prepared copy, after Treasury posts a close at or above $41 trillion.</b> {E(confirmed_sentence)}</div>
<p class="when">The date and amount in the live banner will be the confirming close. They are filled here with the latest close, which is still under $41 trillion, so this sentence is not being shown on the site as fact.</p>
<h2>The arithmetic</h2>
<p>The homepage formula is <code>value = base + rate × (now − t0)</code>. t0 is the end of the record date in Eastern time, 11:59:59 PM. The crossing time is <code>t0 + ($41 trillion − base) / rate</code>.</p>
<ul>
<li>Base, Debt to the Penny close of {_fdate(as_of)}: {E(_money_float(facts['base']))}.</li>
<li>t0: {facts['t0']:.0f} seconds since the Unix epoch ({E(_fmt_ts(facts['t0'])['et'])}).</li>
<li>Rate: {rate:.8f} dollars per second ({E(_per_day(rate))} a day).</li>
<li>Gap: {E(_money_float(gap))}.</li>
<li>Seconds from t0 to the crossing: {facts['seconds']:,.3f}.</li>
<li>Crossing, unrounded Unix time: {facts['t0'] + facts['seconds']:.3f}. The times above are that instant rounded to the nearest second.</li>
</ul>
<p>Series used for the longer paces and the crossing table: {facts['n_rows']} Debt to the Penny closes from {_fdate(facts['first_row'])} through {_fdate(facts['last_row'])}, read from the {E(facts['origin'])}{(' on ' + facts['retrieved']) if facts['retrieved'] else ''}. Rows after the clock's as-of date are not used.{(' Live retrieval failed (' + E(facts['fetch_err']) + ') and the page used the cache.') if facts['origin'].startswith('cached') and facts['fetch_err'] else ''}</p>
<h2>Sources</h2>
<ul>
<li><a href="{DTP}" rel="noopener">Treasury, Debt to the Penny</a>. Latest close used here: {_fdate(as_of)}, {E(_money_float(facts['base']))}. As of {_fdate(as_of)}.</li>
<li><a href="{API}" rel="noopener">Fiscal Data API, debt_to_penny</a>. Daily totals from {_fdate(facts['first_row'])} through {_fdate(facts['last_row'])}.</li>
<li><a href="../methodology/">Every Debt Clock methodology</a>. The 90-day least-squares rate, the 3 PM Central publication note, and the next-business-day rule.</li>
<li><a href="../41-trillion/">$41 trillion countdown</a>. Same base and per-second rate as this page.</li>
</ul>
<h2>Contact</h2>
<p>Questions and corrections: <a href="mailto:hello@everydebtclock.com">hello@everydebtclock.com</a>.</p>
<footer class="site-foot">Every Debt Clock · <a href="../embed/">Embed a clock</a> · <a href="../data/">Data</a> · <a href="../press/">Press</a> · <a href="../about/">About</a> · <a href="../advertise/">Advertise</a> · <a href="../methodology/">Methodology</a> · <a href="../privacy/">Privacy</a> · <a href="../contact/">Contact</a> · Independent site, not affiliated with the U.S. government. Not financial advice.</footer>
</main>
<script type="application/json" id="press-data">{data}</script>
<script src="../cross41.js"></script>
<script>
(function(){{
  var P = JSON.parse(document.getElementById("press-data").textContent);
  var target = P.target;
  function val(t){{ if (P.freeze && t > P.freeze) t = P.freeze; return P.base + P.rate * (t - P.t0); }}
  function hit(rate){{
    if (!(rate > 0) || P.base >= target) return null;
    var ts = P.t0 + (target - P.base) / rate;
    if (P.freeze && ts > P.freeze) return null;
    return ts;
  }}
  function money(n){{ return (n < 0 ? "−$" : "$") + Math.abs(Math.round(n)).toLocaleString("en-US"); }}
  function cd(sec){{
    if (!(sec >= 0)) return "at $41 trillion";
    var s = Math.floor(sec), dd = Math.floor(s / 86400), hh = Math.floor(s % 86400 / 3600), mm = Math.floor(s % 3600 / 60), ss = s % 60;
    return dd + "d " + hh + "h " + mm + "m " + ss + "s";
  }}
  var ts0 = hit(P.rate), when = window.cross41When(ts0);
  if (when) {{
    ["exact-ct", "exact-ct-2"].forEach(function(id){{ var n = document.getElementById(id); if (n) n.textContent = when.ct; }});
    ["exact-et", "exact-et-2"].forEach(function(id){{ var n = document.getElementById(id); if (n) n.textContent = when.et; }});
  }}
  function frame(){{
    var t = Date.now() / 1000, v = val(t), ts = hit(P.rate);
    document.getElementById("left").textContent = money(Math.max(target - v, 0));
    document.getElementById("live").textContent = money(v);
    document.getElementById("cd").textContent = ts ? cd(ts - t) : "—";
    if (window.cross41Update) window.cross41Update(v, P.base, P.as_of);
    requestAnimationFrame(frame);
  }}
  frame();
}})();
</script>
</body></html>"""
    return body


def _checks():
    assert next_business_publish(dt.date(2026, 12, 31)) == dt.date(2027, 1, 4)
    assert dt.date(2026, 12, 31).weekday() == 3
    assert abs((TARGET - 100) / 2 - (hit_ts(100, 2, 0, None, TARGET))) < 1e-6
    assert hit_ts(100, 2, 0, 10, TARGET) is None


def build(ctx):
    _checks()
    td = ctx["T"]["debt_total"]
    if td.get("status") != "ok":
        raise SystemExit("press: debt_total ticker is not ok")
    history = json.load(open(os.path.join(ctx["R"], "cache", "history_pages.json")))["data"]
    if history["series_end"]["date"] != td["as_of"] or abs(history["series_end"]["amount"] - float(td["base"])) > 0.02:
        raise SystemExit("press: history_pages.json does not end on the clock's Debt to the Penny close")
    facts = compute(ctx["R"], td, history)
    R = ctx["R"]
    os.makedirs(os.path.join(R, "press", "charts"), exist_ok=True)
    os.makedirs(os.path.join(R, "og"), exist_ok=True)
    write_og(os.path.join(R, "og", "41-trillion.png"), facts)
    write_clock(os.path.join(R, "press", "41-trillion-clock.png"), facts)
    _bar_chart(
        os.path.join(R, "press", "charts", "days-per-trillion.png"),
        "Days from one trillion to the next",
        "First Debt to the Penny close at each level. Through " + _fdate(facts["as_of"]) + ".",
        [(f"${m['trillion']}T  {_fdate(m['date'])}", m) for m in facts["chart_rows"]],
        lambda m: m["days"], lambda m: f"{m['days']} days", "Calendar days since the previous trillion",
    )
    _bar_chart(
        os.path.join(R, "press", "charts", "paces.png"),
        "Three paces toward $41 trillion",
        "Least-squares slope of Debt to the Penny closes, ending " + _fdate(facts["as_of"]) + ".",
        [("90-day", facts["p90"]), ("12-month", facts["p365"]), ("3-year", facts["p3y"])],
        lambda p: p["rate"] * 86400 / 1e9, lambda p: _per_day(p["rate"]) + "/day", "Billion dollars a day",
    )
    doc = ctx["with_analytics"](_page(ctx, facts))
    open(os.path.join(R, "press", "index.html"), "w").write(doc)
    w = facts["p90"]["when"]
    print(f"press: ${LEVEL}T at {w['ct']} / {w['et']}; window {facts['window_days'][0]} .. {facts['window_days'][-1]}; "
          f"12m {facts['p365']['when']['ct']}; 3y {facts['p3y']['when']['ct']}; series {facts['origin']} {facts['n_rows']} rows")
    return facts
