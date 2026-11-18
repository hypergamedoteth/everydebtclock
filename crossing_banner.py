"""$41 trillion crossing banner.

The claim that the debt has passed $41 trillion is not written into the HTML
until Treasury's Debt to the Penny close is actually at or above that level.
Before then the page only has an empty mount. cross41.js fills the sentence
in the browser after the live clock passes $41 trillion, or when the page is
opened with ?cross41=preview. A text extractor that does not run JavaScript
cannot quote a crossing that has not happened.
"""
import json
import os

LEVEL = 41 * 10 ** 12
ROOT = os.path.dirname(os.path.abspath(__file__))

# Phrases that assert the $41 trillion level has already been reached.
# Historical lines such as "at or above $40 trillion" are not in this list.
CLAIMS = (
    "past $41 trillion",
    "passed $41 trillion",
    "at or above $41 trillion",
)

SHELL = '<div id="cross41" class="banner" hidden role="status"></div>\n'


def _official_close():
    path = os.path.join(ROOT, "data", "data.json")
    if not os.path.exists(path):
        return None
    td = (json.load(open(path)).get("tickers") or {}).get("debt_total") or {}
    if td.get("status") != "ok" or td.get("base") is None:
        return None
    return float(td["base"]), td.get("as_of") or ""


def crossed():
    """True only when the official Treasury close is at or above $41 trillion."""
    got = _official_close()
    return bool(got and got[0] >= LEVEL)


def html():
    """Markup safe to ship. The claim is included only after a real Treasury close."""
    got = _official_close()
    if not got or got[0] < LEVEL:
        return SHELL
    amount, as_of = got
    # The confirming close is real, so the official sentence may be in the HTML.
    shown = f"${amount:,.2f}"
    return (
        '<div id="cross41" class="banner" role="status">'
        "<p><b>Treasury's figure is at or above $41 trillion.</b> "
        f"Debt to the Penny's {as_of} close was {shown}. That is the official total. "
        "The digits still moving on this page are the live projection from that close. "
        '<a href="/press/">Press figures</a>.</p></div>\n'
    )


# Pages import this name. It is computed from the Treasury close on disk, not from the build clock.
HTML = html()
