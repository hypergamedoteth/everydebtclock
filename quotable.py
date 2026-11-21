"""Short dated lines for the H1 under each live clock.

One sentence, for example "Official: $40.71 trillion on Nov 17, 2026 (U.S. Treasury)."
The next sentence on the page may be dated too. Do not pad the H1.
"""
import datetime as dt
import html
import re

_SECOND = re.compile(r"\.\s+(The|That|It|This|A|An|World|Source|Each|These)\s")


def _short(iso):
    return dt.date.fromisoformat(iso[:10]).strftime("%b %-d, %Y")


def _long(iso):
    return dt.date.fromisoformat(iso[:10]).strftime("%B %-d, %Y")


def official(figure, when, source):
    """One short dated sentence. No filler after the period."""
    figure = " ".join(str(figure).split())
    when = " ".join(str(when).split())
    source = " ".join(str(source).split()).strip(" .")
    sentence = f"Official: {figure} on {when} ({source})."
    if _SECOND.search(sentence):
        raise ValueError("quotable lead is more than one sentence: " + sentence)
    return sentence


def _sources(sources):
    names, links = [], []
    for name, url in sources:
        name = " ".join(str(name).split()).strip(" .")
        url = " ".join(str(url).split())
        if not name or not url:
            raise ValueError("cited source needs a name and a url")
        names.append(name)
        links.append(f'<a href="{html.escape(url, quote=True)}" rel="noopener">{html.escape(name)}</a>')
    return names, links


def _one_sentence(sentence, html_s):
    if _SECOND.search(sentence):
        raise ValueError("cited line is more than one sentence: " + sentence)
    if len(sentence) > 320:
        raise ValueError(f"cited line is {len(sentence)} characters: " + sentence)
    return sentence, html_s


def asof_pair(claim, when, sources):
    """One sentence a crawler can quote, plus the same sentence with linked sources.

    `claim` is the figure clause, for example "US federal debt is $40.71 trillion".
    `sources` is a list of (name, url). The plain sentence and the link text match.
    """
    claim = " ".join(str(claim).split()).rstrip(" .")
    when = " ".join(str(when).split())
    names, links = _sources(sources)
    sentence = f"As of {when}, {claim} ({'; '.join(names)})."
    html_s = f"As of {html.escape(when)}, {html.escape(claim)} ({'; '.join(links)})."
    return _one_sentence(sentence, html_s)


def cited_pair(claim, sources):
    """One sentence that names the figure first, then the linked source. No 'As of' date."""
    claim = " ".join(str(claim).split()).rstrip(" .")
    names, links = _sources(sources)
    sentence = f"{claim} ({'; '.join(names)})."
    html_s = f"{html.escape(claim)} ({'; '.join(links)})."
    return _one_sentence(sentence, html_s)


def finish(core, clause=None):
    """One sentence, unpadded. `clause` is ignored so old callers stay short."""
    core = " ".join(core.split()).rstrip(" .")
    sentence = core + "."
    if _SECOND.search(sentence):
        raise ValueError("quotable lead is more than one sentence: " + sentence)
    return sentence


def _figure(amount):
    sign = "−" if amount < 0 else ""
    n = abs(amount)
    if n >= 1e12:
        return sign + f"${n / 1e12:,.2f} trillion"
    if n >= 1e9:
        return sign + f"${n / 1e9:,.2f} billion"
    if n >= 1e6:
        return sign + f"${n / 1e6:,.2f} million"
    return sign + f"${n:,.0f}"


def us_close(amount, iso_date):
    """Debt to the Penny close. `amount` is the official total on `iso_date`."""
    return official(_figure(amount), _short(iso_date), "U.S. Treasury")


def fy_close(amount, iso_date, fy):
    return official(f"{_figure(amount)}, end of fiscal year {fy}", _short(iso_date), "U.S. Treasury")


def stock(name, kind_phrase, amount, iso_date, publisher, words=None):
    """A place's official stock. `words` overrides the short dollar form."""
    figure = words if words else _figure(amount)
    kind = " ".join(str(kind_phrase).split())
    return official(f"{name} {kind} was {figure}", _short(iso_date), publisher)


def world_sum(total, dmin, dmax, n):
    return official(
        f"world government debt for {n} economies was {_figure(total)}",
        f"{dmin} through {dmax}",
        "national sources, Eurostat, and IMF",
    )


def states_sum(total, iso_date):
    return official(
        f"state and local government debt was {_figure(total)}",
        _short(iso_date),
        "U.S. Census Bureau",
    )


def month_change(added, start_amt, start_iso, end_amt, end_iso, month_label):
    start_s, end_s = _short(start_iso), _short(end_iso)
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
    return finish(core)


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
    """The H1 is one short dated sentence. A second sentence may follow it on the page."""
    text = h1_inner(page)
    if not text.endswith("."):
        raise SystemExit(f"{label}: H1 does not end the sentence: {text[:180]}")
    if len(text) > 320:
        raise SystemExit(f"{label}: H1 is {len(text)} characters: {text[:180]}")
    if len(text) < 24:
        raise SystemExit(f"{label}: H1 is too short: {text}")
    if not re.search(r"\d{4}", text):
        raise SystemExit(f"{label}: H1 has no year: {text}")
    if _SECOND.search(text):
        parts = text.split(". ")
        clock = "The live clock projects each country forward from its figure."
        if not (len(parts) == 2 and parts[1] == clock):
            raise SystemExit(f"{label}: H1 is more than one sentence: {text[:240]}")
    if "as published by that source" in text:
        raise SystemExit(f"{label}: H1 is still padded: {text[:180]}")
    return text
