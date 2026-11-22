"""Debt subject to the statutory limit, from Daily Treasury Statement Table III-C.

The Fiscal Data rows are the same feed pipeline/fetch.py already caches
(`dts/debt_subject_to_limit`). Amounts in that feed are millions of dollars.
This module turns one day's rows into the dollars the site shows, and it says
when the statutory-limit line is missing, zero, or inconsistent.

Nothing here is a forecast. The days-to-limit figure is headroom divided by
the 90-day least-squares slope of debt subject to the limit.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
MILLION = 1_000_000.0

CAT_PUBLIC = "Debt Held by the Public"
CAT_INTRA = "Intragovernmental Holdings"
CAT_NOT = "Debt Not Subject to Limit"
CAT_OTHER = "Other Debt Subject to Limit"
CAT_LIMIT = "Statutory Debt Limit"

DSL_URL = "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/debt-subject-to-limit"
DSL_API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/debt_subject_to_limit"
TREASURY_PAGE = "https://home.treasury.gov/policy-issues/financial-markets-financial-institutions-and-fiscal-service/debt-limit"
MEASURES_PDF = "https://home.treasury.gov/system/files/136/DescriptionofExtraordinaryMeasures20250117.pdf"
FY2025_REPORT = "https://fiscal.treasury.gov/system/files/2026-03/executive-summary-2025.pdf"
STATUTE = "https://www.law.cornell.edu/uscode/text/31/3101"
PLAW_119_21 = "https://www.congress.gov/119/plaws/publ21/PLAW-119publ21.pdf"

# Read on 2026-11-22 from Treasury's debt-limit page. The newest extraordinary-measures
# items there are the July 2025 wind-down of the debt issuance suspension period that
# ended July 4, 2025. The page lists no later announcement that measures are in use.
# Set in_use True only when that page lists a new announcement, and put its URL in announcement.
EXTRAORDINARY_MEASURES = {
    "in_use": False,
    "label": "not in use",
    "checked": "2026-11-22",
    "page": TREASURY_PAGE,
    "description": MEASURES_PDF,
    "disp_ended": "2025-07-04",
    "discontinued": "2025-07-07",
    "discontinued_source": FY2025_REPORT,
    "announcement": None,
}

# Forecasts read from the linked pages on 2026-11-22. Not recomputed by the refresh.
# CBO's February 2026 baseline does not publish an X-date. Treasury's debt-limit page
# has no X-date letter for this limit. Those two still belong in the "who publishes" note.
FORECASTS = (
    {
        "who": "Congressional Budget Office",
        "published": "February 2026",
        "published_iso": "2026-02",
        "xdate": None,
        "says": "Treasury would reach the statutory limit sometime in 2027. The baseline does not give an X-date. It describes the limit as $41.1 trillion and assumes Congress raises it.",
        "title": "The Budget and Economic Outlook: 2026 to 2036",
        "url": "https://www.cbo.gov/publication/62105",
    },
    {
        "who": "Bipartisan Policy Center",
        "published": "November 18, 2026",
        "published_iso": "2026-11-18",
        "xdate": None,
        "says": "The debt limit is most likely reached in February or March 2027. Cash and extraordinary measures would then last roughly six to nine months. BPC does not name a single X-date.",
        "title": "The Debt Limit Returns in 2027: What to Expect",
        "url": "https://bipartisanpolicy.org/issue-brief/the-debt-limit-returns-in-2027-what-to-expect/",
    },
    {
        "who": "National Taxpayers Union",
        "published": "November 12, 2026",
        "published_iso": "2026-11-12",
        "xdate": "by the beginning of December 2027",
        "says": "Central estimate: the limit is reached in February 2027, and the X-date is by the beginning of December 2027. A lower-receipts case puts the X-date in November 2027. A higher-receipts case puts debt-limit contact in March 2027 and the X-date in February 2028.",
        "title": "Debt Limit Likely to Be Hit in February, with the X-Date Reached by December 2027",
        "url": "https://www.ntu.org/publications/detail/debt-limit-likely-to-be-hit-in-february-with-the-x-date-reached-by-december-2027",
    },
)


def _money(raw):
    if raw is None or raw == "":
        return 0.0
    return float(raw) * MILLION


def fold_rows(rows):
    """One dict per record date. `limit` is the last Statutory Debt Limit line that day, matching the longstanding sum in fetch.py."""
    by = {}
    for r in rows or []:
        day = by.setdefault(r["record_date"], {
            "public": 0.0, "intragov": 0.0, "not_subject": 0.0, "other": 0.0,
            "limit": None, "limit_values": [], "not_parts": [], "other_parts": [],
        })
        cat = r.get("debt_catg")
        v = _money(r.get("close_today_bal"))
        desc = r.get("debt_catg_desc") or ""
        if desc in ("", "null", "None"):
            desc = ""
        if cat == CAT_PUBLIC:
            day["public"] += v
        elif cat == CAT_INTRA:
            day["intragov"] += v
        elif cat == CAT_NOT:
            day["not_subject"] += v
            day["not_parts"].append((desc or "Debt not subject to limit", v))
        elif cat == CAT_OTHER:
            day["other"] += v
            day["other_parts"].append((desc or "Other debt subject to limit", v))
        elif cat == CAT_LIMIT:
            day["limit"] = v
            day["limit_values"].append(v)
    for day in by.values():
        day["subject"] = day["public"] + day["intragov"] + day["other"] - day["not_subject"]
    return by


def limit_status(day):
    """in_force, suspended, unreported, or ambiguous. Ambiguous wins over the others."""
    if not day:
        return "unreported"
    values = day.get("limit_values") or []
    distinct = {round(v, 2) for v in values}
    if len(distinct) > 1:
        return "ambiguous"
    if day["public"] <= 0 and day["intragov"] <= 0:
        return "ambiguous"
    if day["subject"] < 0:
        return "ambiguous"
    if not values or day.get("limit") is None:
        return "unreported"
    if day["limit"] <= 0:
        return "suspended"
    if day["subject"] > day["limit"] * 1.02:
        return "ambiguous"
    return "in_force"


def summarize(rows):
    """Latest Table III-C day. `limit` is None unless the status is a usable dollar ceiling."""
    by = fold_rows(rows)
    if not by:
        return None
    last = max(by)
    day = by[last]
    status = limit_status(day)
    usable = status == "in_force"
    limit = day["limit"] if usable else None
    headroom = (limit - day["subject"]) if usable else None
    return {
        "as_of": last,
        "status": status,
        "subject": day["subject"],
        "limit": limit,
        "limit_reported": day["limit"],
        "headroom": headroom,
        "public": day["public"],
        "intragov": day["intragov"],
        "not_subject": day["not_subject"],
        "other": day["other"],
        "not_parts": day["not_parts"],
        "other_parts": day["other_parts"],
        "source": DSL_URL,
        "source_api": DSL_API,
        "unit": "Table III-C amounts are published in millions of dollars and shown here in dollars.",
        "by": by,
    }


def days_to_limit(headroom, rate_per_second, as_of, t0=None):
    """Calendar days from the record's close until headroom hits zero at `rate_per_second`.

    `t0` is the Unix time of that close (end of the record date, ET). The date
    returned is the America/New_York calendar date of the crossing. None when
    the trend is flat or down, or there is no headroom to divide.
    """
    if headroom is None or rate_per_second is None or rate_per_second <= 0 or headroom <= 0:
        return None
    per_day = rate_per_second * 86400.0
    days = headroom / per_day
    if t0 is None:
        d = dt.date.fromisoformat(as_of)
        t0 = dt.datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=ET).timestamp()
    hit = dt.datetime.fromtimestamp(t0 + days * 86400.0, ET)
    return {
        "days": round(days, 1),
        "projected_date": hit.date().isoformat(),
        "per_day": round(per_day, 2),
        "from_date": as_of,
        "method": (
            "Estimate, not a Treasury forecast. Headroom (statutory limit minus debt subject to the limit) "
            "divided by the 90-day least-squares daily change in debt subject to the limit, from Daily Treasury "
            "Statement Table III-C. Debt does not rise in a straight line. This ignores the Treasury cash balance, "
            "tax season, and extraordinary measures, so it is not an X-date."
        ),
    }


def api_fields(summary, rate_per_second=None, t0=None, extraordinary=None):
    """Additive /api/daily.json fields. Missing inputs become null, never a guessed dollar amount."""
    extraordinary = extraordinary if extraordinary is not None else EXTRAORDINARY_MEASURES
    if not summary:
        return {
            "debt_subject_to_limit": None,
            "statutory_limit": None,
            "dts_record_date": None,
            "debt_limit_headroom": None,
            "debt_limit_reported_status": None,
            "days_to_limit_estimate": None,
            "extraordinary_measures": extraordinary["label"],
        }
    est = days_to_limit(summary.get("headroom"), rate_per_second, summary.get("as_of"), t0) if summary.get("status") == "in_force" else None
    return {
        "debt_subject_to_limit": round(summary["subject"], 2) if summary.get("subject") is not None else None,
        "statutory_limit": round(summary["limit"], 2) if summary.get("limit") is not None else None,
        "dts_record_date": summary.get("as_of"),
        "debt_limit_headroom": round(summary["headroom"], 2) if summary.get("headroom") is not None else None,
        "debt_limit_reported_status": summary.get("status"),
        "days_to_limit_estimate": est,
        "extraordinary_measures": extraordinary["label"],
    }


# Verified against the live Fiscal Data response for record_date 2026-11-19 on 2026-11-22.
# close_today_bal values are millions. Kept so a formula change fails this check.
VERIFIED_2026_11_19 = {
    "public_millions": 32901460,
    "intragov_millions": 7808321,
    "not_subject_millions": 474 + 198266 + 3591,
    "other_millions": 0,
    "limit_millions": 41103996,
    "subject": 40507450000000.0,
    "limit": 41103996000000.0,
    "headroom": 596546000000.0,
}


def check_verified(rows, expect=VERIFIED_2026_11_19, day="2026-11-19"):
    by = fold_rows(rows)
    if day not in by:
        return
    got = by[day]
    problems = []
    for key, attr in (
        ("public_millions", "public"),
        ("intragov_millions", "intragov"),
        ("not_subject_millions", "not_subject"),
        ("other_millions", "other"),
        ("limit_millions", "limit"),
    ):
        if abs(got[attr] - expect[key] * MILLION) > 0.5:
            problems.append(f"{attr} {got[attr]} != {expect[key]} million")
    if abs(got["subject"] - expect["subject"]) > 0.5:
        problems.append(f"subject {got['subject']}")
    if problems:
        raise SystemExit("DTS Table III-C no longer matches the verified 2026-11-19 lines: " + "; ".join(problems))
    if limit_status(got) != "in_force":
        raise SystemExit("verified 2026-11-19 day is not an in-force limit")
    if abs((got["limit"] - got["subject"]) - expect["headroom"]) > 0.5:
        raise SystemExit("verified headroom drifted")
