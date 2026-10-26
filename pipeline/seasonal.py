"""Projection helpers for the fiscal-year-to-date DTS tickers (revenue, spending, cash interest).

All three are cumulative cash flows that Treasury reports once per business day (Daily Treasury
Statement). They are lumpy: customs duties arrive in one monthly lump, Social Security and payroll
follow weekday cycles, and Treasury coupons are paid on the 15th and at month-end. A smooth 90-day
average pace misses those lumps, which is what the daily check measures. These helpers project the
flow to the NEXT business day's close from official history:

  * spending, non-customs revenue: the same weekday-aligned window one year earlier (364 days back),
    scaled by the trailing-year growth of that flow;
  * customs duties: the same business day of the previous month (tariff deposits come in one monthly
    lump and the tariff regime changes too fast for a year-ago match);
  * cash interest: a coupon calendar. Notes/bonds pay semiannually on the 15th and the last day of the
    month (next business day if that is a holiday/weekend); each upcoming payment is estimated from the
    payment for the same coupon date six months earlier, adjusted by half its six-month growth. Other
    days get the median non-coupon day.
Pure functions; no network. History rows: {date: {"rev": $, "out": $, "int": $, "cus": $}} (daily, dollars).
"""
import bisect, calendar, datetime as dt, statistics as st

# ---------------------------------------------------------------- business-day calendar (federal holidays)
def fed_holidays(y):
    def nth(m, wd, n):
        d = dt.date(y, m, 1); d += dt.timedelta((wd - d.weekday()) % 7); return d + dt.timedelta(7 * (n - 1))
    def last(m, wd):
        d = dt.date(y, m, calendar.monthrange(y, m)[1]); return d - dt.timedelta((d.weekday() - wd) % 7)
    out = {nth(1, 0, 3), nth(2, 0, 3), last(5, 0), nth(9, 0, 1), nth(10, 0, 2), nth(11, 3, 4)}
    for d in (dt.date(y, 1, 1), dt.date(y, 6, 19), dt.date(y, 7, 4), dt.date(y, 11, 11), dt.date(y, 12, 25)):
        out.add(d - dt.timedelta(1) if d.weekday() == 5 else d + dt.timedelta(1) if d.weekday() == 6 else d)
    return out
_HOL = {}
def is_bday(d):
    for y in (d.year, d.year + 1):
        if y not in _HOL: _HOL[y] = fed_holidays(y)
    return d.weekday() < 5 and d not in _HOL[d.year] and d not in _HOL[d.year + 1]
def next_bday(d):
    d += dt.timedelta(1)
    while not is_bday(d): d += dt.timedelta(1)
    return d
def on_or_after_bday(d):
    while not is_bday(d): d += dt.timedelta(1)
    return d
def month_bdays(y, m):
    return [dt.date(y, m, i) for i in range(1, calendar.monthrange(y, m)[1] + 1) if is_bday(dt.date(y, m, i))]

class History:
    def __init__(self, rows):
        self.rows = rows; self.dates = sorted(rows)
        self.cum = {}
        for k in ("rev", "out", "int", "cus", "revx"):
            s, c = 0.0, []
            for d in self.dates:
                r = rows[d]; s += (r["rev"] - r.get("cus", 0.0)) if k == "revx" else r.get(k, 0.0); c.append(s)
            self.cum[k] = c
        self.by_month = {}
        for d in self.dates: self.by_month.setdefault(d[:7], []).append(d)

    def first(self): return dt.date.fromisoformat(self.dates[0])
    def flow(self, k, a, b):
        """Sum of daily flow k on record dates in (a, b] (ISO dates or date objects)."""
        a, b = str(a), str(b)
        i = bisect.bisect_right(self.dates, a); j = bisect.bisect_right(self.dates, b)
        c = self.cum[k]
        return (c[j - 1] if j else 0.0) - (c[i - 1] if i else 0.0)
    def growth(self, k, d):
        """Trailing-365-day flow over the 365 days before that (1.0 if not enough history), clamped to [0.7, 1.5]."""
        if (d - self.first()).days < 731: return 1.0
        y = dt.timedelta(365)
        num, den = self.flow(k, d - y, d), self.flow(k, d - 2 * y, d - y)
        return max(0.7, min(1.5, num / den)) if den > 0 else 1.0
    def settle_hist(self, nd):
        """First DTS record date on/after nominal date nd."""
        i = bisect.bisect_left(self.dates, nd.isoformat())
        return self.dates[i] if i < len(self.dates) else None

def same_window_last_year(H, k, d, n):
    """Flow k expected over (d, n]: the weekday-aligned window 364 days earlier x trailing-year growth."""
    s = dt.timedelta(364)
    return H.flow(k, d - s, n - s) * H.growth(k, d)

def customs_prev_month(H, d, n):
    """Customs expected over (d, n]: for each business day, the same business-day-of-month one month earlier."""
    tot, x = 0.0, next_bday(d)
    while x <= n:
        k = month_bdays(x.year, x.month).index(x)
        y, m = (x.year, x.month - 1) if x.month > 1 else (x.year - 1, 12)
        P = H.by_month.get(f"{y}-{m:02d}")
        if P: tot += H.rows[P[min(k, len(P) - 1)]].get("cus", 0.0)
        x = next_bday(x)
    return tot

def has_year_history(H, d): return (d - H.first()).days >= 731

def expected_flow(H, kind, d, n):
    """kind 'rev' (receipts) or 'out' (outlays): projected cash flow over (d, n]."""
    if kind == "rev":
        return same_window_last_year(H, "revx", d, n) + customs_prev_month(H, d, n)
    return same_window_last_year(H, "out", d, n)

# ---------------------------------------------------------------- coupon calendar for cash interest
def _nominal(y, m): return [dt.date(y, m, 15), dt.date(y, m, calendar.monthrange(y, m)[1])]
def _shift(nd, k):
    y, m = nd.year, nd.month - k
    while m <= 0: m += 12; y -= 1
    return dt.date(y, m, calendar.monthrange(y, m)[1]) if nd.day > 15 else dt.date(y, m, 15)

def coupon_settlement_dates(H):
    s = set()
    f = H.first(); y, m = f.year, f.month
    last = dt.date.fromisoformat(H.dates[-1])
    while (y, m) <= (last.year, last.month):
        for nd in _nominal(y, m):
            x = H.settle_hist(nd)
            if x: s.add(x)
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return s

def interest_drip(H, d, n_days=40):
    cs = coupon_settlement_dates(H)
    L = [H.rows[x]["int"] for x in H.dates if x <= d.isoformat() and x not in cs][-n_days:]
    return st.median(L) if L else 0.0

def coupon_forecast(H, nd, drip):
    """Projected cash interest for nominal coupon date nd (excess over an ordinary day)."""
    s6, s12 = H.settle_hist(_shift(nd, 6)), H.settle_hist(_shift(nd, 12))
    if not s6: return None
    p6 = H.rows[s6]["int"] - drip
    p12 = (H.rows[s12]["int"] - drip) if s12 else None
    g = ((p6 - p12) / p12 / 2) if p12 and p12 > 0 else 0.0
    return max(0.0, p6 * (1 + max(-0.25, min(0.25, g))))

def upcoming_coupons(H, d, until, months=4):
    """[(settlement_date, nominal_dates, amount)] for coupon settlements in (d, until]."""
    out = {}
    drip = interest_drip(H, d)
    y, m = d.year, d.month
    for _ in range(months):
        for nd in _nominal(y, m):
            s = on_or_after_bday(nd)
            if d < s <= until:
                a = coupon_forecast(H, nd, drip)
                if a is not None:
                    e = out.setdefault(s, [[], 0.0]); e[0].append(nd.isoformat()); e[1] += a
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return [(s, v[0], v[1]) for s, v in sorted(out.items())], drip

def expected_interest(H, d, n):
    cps, drip = upcoming_coupons(H, d, n)
    nb, x = 0, next_bday(d)
    while x <= n: nb += 1; x = next_bday(x)
    return nb * drip + sum(a for _, _, a in cps)

def growth_note(H, k, d): return round(H.growth(k, d), 4)
