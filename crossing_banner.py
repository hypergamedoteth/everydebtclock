"""Pre-written $41 trillion crossing banner.

The sentences live here. Pages include the markup hidden. cross41.js turns the
matching sentence on when the live clock, or Treasury's official close, passes
$41 trillion. Nothing in the copy invents a debt total: the amounts are filled
from the page's clock data.
"""

HTML = """<div id="cross41" class="banner" hidden role="status">
<p id="cross41-preview" hidden><b>Preview.</b> This banner stays hidden until the live clock passes $41 trillion. The debt has not passed it. The sentence below is the prepared copy, not a report that the debt has crossed.</p>
<p id="cross41-live" hidden><b>Live estimate, not Treasury's figure.</b> This clock is past $41 trillion<span data-cross="live-wrap" hidden> (<span data-cross="live"></span>)</span>. Treasury has not posted a Debt to the Penny close at or above $41 trillion. The latest official close is still <span data-cross="official"></span> on <span data-cross="asof"></span>. Treasury posts the prior business day's close on the next business day, usually in the afternoon (around 3 PM Central). <a href="/press/">Press figures</a>.</p>
<p id="cross41-official" hidden><b>Treasury's figure is at or above $41 trillion.</b> Debt to the Penny's <span data-cross="asof"></span> close was <span data-cross="official"></span>. That is the official total. The digits still moving on this page are the live projection from that close. <a href="/press/">Press figures</a>.</p>
</div>
"""
