"""One-sentence leads for the pages answer engines quote from the H1.

ChatGPT stores about 200 characters starting at the H1 and ignores the meta
description. The H1 is one sentence of at least 220 characters, so that window
stays inside the sentence. The live clock number may precede it. Labels, nav,
and placeholder text may not.
"""
import datetime as dt
import html
import re

MIN_LEAD = 205
_SECOND = re.compile(r"\.\s+(The|That|It|This|A|An|World|Source|Each|These)\s")


def finish(core, clause):
    """One sentence. `clause` is inserted before the period when the core is short."""
    core = " ".join(core.split()).rstrip(" .")
    clause = " ".join(clause.split()).strip(" .,")
    sentence = core + "."
    if len(sentence) < MIN_LEAD:
        sentence = core + ", " + clause + "."
    if len(sentence) < MIN_LEAD:
        sentence = sentence[:-1] + ", as published by that source on the date named here" + "."
    if not sentence.endswith("."):
        raise ValueError("quotable lead does not end a sentence: " + sentence)
    if _SECOND.search(sentence):
        raise ValueError("quotable lead is more than one sentence: " + sentence)
    if len(sentence) < MIN_LEAD:
        raise ValueError(f"quotable lead is {len(sentence)} characters: " + sentence)
    return sentence


def _long(iso):
    return dt.date.fromisoformat(iso).strftime("%B %-d, %Y")


def _per(publisher):
    who = " ".join(publisher.split()).strip()
    if who.lower().startswith("the "):
        return who
    return "the " + who


def us_close(amount, iso_date):
    """Debt to the Penny close. `amount` is the official total on `iso_date`."""
    shown = _long(iso_date)
    tri = f"${amount / 1e12:,.2f} trillion"
    full = f"${amount:,.2f}"
    core = f"The U.S. national debt was {tri} on {shown}, per the U.S. Treasury Debt to the Penny"
    clause = f"which is {full} of total public debt outstanding in the Debt to the Penny daily series"
    return finish(core, clause)


def fy_close(amount, iso_date, fy):
    shown = _long(iso_date)
    tri = f"${amount / 1e12:,.2f} trillion"
    full = f"${amount:,.2f}"
    core = (f"The U.S. national debt was {tri} ({full}) on {shown}, "
            f"the end of fiscal year {fy}, per the U.S. Treasury Historical Debt Outstanding")
    clause = "the official fiscal-year-end total of public debt outstanding"
    return finish(core, clause)


def stock(name, kind_phrase, amount, iso_date, publisher, words=None):
    """A place's official stock. `amount` is the number; `words` overrides the short form."""
    shown = _long(iso_date)
    if words:
        short = words
    elif abs(amount) >= 1e12:
        short = f"${abs(amount) / 1e12:,.2f} trillion"
    elif abs(amount) >= 1e9:
        short = f"${abs(amount) / 1e9:,.2f} billion"
    else:
        short = f"${amount:,.0f}"
    full = f"${amount:,.0f}" if words is None else words
    # Local-currency pages pass `words` as the formatted official figure and no separate dollar short form.
    if words is not None:
        figure = words
    else:
        figure = f"{short} ({full})" if short != full else full
    core = f"The {kind_phrase} of {name} was {figure} on {shown}, per {_per(publisher)}"
    clause = "the official published stock of debt outstanding, not a projection and not an estimate"
    return finish(core, clause)


def world_sum(total, dmin, dmax, n):
    core = (f"World government debt on this page, the sum of the latest general-government gross debt "
            f"for {n} economies, was ${total / 1e12:,.2f} trillion (${total:,.0f}), "
            f"with stock dates from {dmin} through {dmax}, per the national, Eurostat, World Bank, and IMF sources named here")
    clause = "each economy is counted once, and a narrower central or federal series is not added in"
    return finish(core, clause)


def states_sum(total, iso_date):
    shown = _long(iso_date)
    core = (f"State and local government debt for the 50 states and the District of Columbia totaled "
            f"${total / 1e12:,.2f} trillion (${total:,.0f}) on {shown}, per the U.S. Census Bureau")
    clause = "the Annual Survey of State and Local Government Finances, total debt outstanding, summed across those 51 governments"
    return finish(core, clause)


def month_change(added, start_amt, start_iso, end_amt, end_iso, month_label):
    start_s, end_s = _long(start_iso), _long(end_iso)
    if added > 0:
        verb, noun = "rose", "by"
    elif added < 0:
        verb, noun = "fell", "by"
    else:
        verb, noun = "was unchanged", "at"
    move = abs(added)
    core = (f"The U.S. national debt {verb} {noun} ${float(move) / 1e9:,.2f} billion in {month_label}, "
            f"from ${float(start_amt) / 1e12:,.2f} trillion on {start_s} to ${float(end_amt) / 1e12:,.2f} trillion on {end_s}, "
            f"per the U.S. Treasury Debt to the Penny")
    clause = f"which is ${move:,.2f} between those two official closes"
    return finish(core, clause)


def h1_inner(page):
    m = re.search(r"<h1\b[^>]*>(.*?)</h1>", page, re.S | re.I)
    if not m:
        return ""
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def before_h1(page):
    """Visible text from the start of <body> up to the first H1. Scripts and styles are skipped."""
    m = re.search(r"<body\b[^>]*>", page, re.I)
    h = re.search(r"<h1\b", page, re.I)
    if not m or not h or h.start() < m.end():
        return ""
    chunk = page[m.end():h.start()]
    chunk = re.sub(r"<script\b[^>]*>.*?</script>", " ", chunk, flags=re.S | re.I)
    chunk = re.sub(r"<style\b[^>]*>.*?</style>", " ", chunk, flags=re.S | re.I)
    chunk = re.sub(r"<[^>]+>", " ", chunk)
    chunk = html.unescape(chunk)
    return re.sub(r"\s+", " ", chunk).strip()


_BAD_BEFORE = (
    "live estimate",
    "since you opened",
    "find a clock",
    "per person",
    "per tax return",
    "per household",
    "answer.",
    "projected",
    "what this page counts",
    "every debt clock",
    "embed",
    "add this live clock",
    "add to home screen",
)


def check_page(page, label):
    """Fail when the H1 window is not one dated sentence, or junk precedes it."""
    text = h1_inner(page)
    if len(text) < 200:
        raise SystemExit(f"{label}: H1 is {len(text)} characters, under 200: {text[:180]}")
    if not text.endswith("."):
        raise SystemExit(f"{label}: H1 does not end the sentence: {text[:180]}")
    if _SECOND.search(text):
        raise SystemExit(f"{label}: H1 is more than one sentence: {text[:240]}")
    window = text[:200]
    if _SECOND.search(window + ("." if not window.endswith(".") else "")):
        raise SystemExit(f"{label}: first 200 characters leave the sentence: {window}")
    pre = before_h1(page).lower()
    for bad in _BAD_BEFORE:
        if bad in pre:
            raise SystemExit(f"{label}: {bad!r} appears before the H1: {before_h1(page)[:240]}")
    return text
