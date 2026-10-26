# Every Debt Clock (everydebtclock.com) — US clock v1

Every number ticks like usdebtclock.org, but each one starts from an **official figure**, ticks at the **official trend**, is **re-based daily**, and is **checked daily** against the next official release. Nothing is hand-typed.

## Files
| Path | What |
|---|---|
| `pipeline/fetch.py` | Pulls official data (no API keys), computes base + per-second rate per ticker, runs validation, writes `data/data.json` and appends `data/validation_log.csv` |
| `pipeline/run_daily.sh` | fetch → validate → build (cron entry point) |
| `build.py` | Inlines CSS/JS/data into `dist/debtclock-standalone.html`; writes per-ticker share pages `t/<slug>.html` |
| `index.html`, `style.css`, `app.js` | Static front end, no build step. `requestAnimationFrame` loop updates every ticker every frame |
| `api/daily.json`, `api/daily.txt` | Small stable feed for the daily X post (official Debt to the Penny close, 1/7/30-day official changes, 90-day average, projected now, per person/household) and one plain-English post line. Crawlable, not in the sitemap. Null when a value cannot be computed. |
| `widget.html?t=<slug>` | Embeddable single-ticker widget (iframe) |
| `cache/` | Last good response per source (used if a source is down; tile shows "cached") |
| `analytics.html` (optional) or `ANALYTICS_HTML` env | Analytics snippet injected before `</head>` on every page; empty by default |

## Ticker model
`value(t) = base + rate × (t − t0)`
- **Debt (total / public / intragovernmental):** base = Treasury Debt to the Penny latest close of business; rate = least-squares slope of the trailing 90 days of daily records.
- **Fiscal-year-to-date (spending, revenue, deficit, every budget function, every revenue source, gross interest):** base = latest Monthly Treasury Statement FYTD figure (or $0 at Oct 1 if the new FY has no statement yet); rate = current-FY average pace once ≥3 months are published, otherwise trailing-12-month pace. The browser also resets FYTD tickers to $0 at Oct 1 00:00 ET if the data hasn't been refreshed yet.
- **Per person** = value ÷ US population (Census Vintage 2025 Jul 1, 2025 estimate, projected at Census's stated rate). **Per tax return filed** = value ÷ 162,754,810 individual returns filed (IRS Data Book FY2025, Table 1-2). **Per household** = ÷ 134.79M (Census CPS ASEC 2025).
- **GDP:** BEA NIPA Table 1.1.5 nominal GDP (SAAR) via the DBnomics mirror (BEA's own API needs a key; FRED's CSV endpoint timed out from this box). Ticks at the 4-quarter trend.
- **Ratios** (debt-to-GDP now, deficit-to-GDP trailing 12 months, interest ÷ revenue, debt per household) are computed live in the browser from the ticking parts.
- **History** (debt-to-GDP and deficit-to-GDP for FY1960–2025) comes from OMB Historical Tables 7.1 and 1.2 and **does not tick**.

## Daily validation
1. **Backtest (debt):** each of the last 20 business days is projected from the previous day's base and its trailing-90-day slope, then compared with the official figure. Current mean |error| ≈ 0.06% total debt.
2. **Day-over-day:** when a source publishes a new figure, yesterday's `data.json` projection for that time is compared with it.
3. **DTS cross-check (FYTD revenue/spending):** compares the projection with the Daily Treasury Statement's cash deposits/withdrawals (excluding debt issues/redemptions). Cash basis ≠ budget basis, so the threshold is loose (15%).
Thresholds: 0.25% debt, 5% monthly figures, 15% DTS. Breaches set `flag` on the ticker, show ⚠ on the tile and a banner, and are listed in `meta.flags` (hook an alert to this).

## Phase 2 (launch build)
**Daily DTS re-base.** FY-to-date revenue, spending and deficit are re-based every business day from the Daily Treasury Statement (`dts/deposits_withdrawals_operating_cash`). Cash deposits and withdrawals exclude public-debt issues and redemptions and are converted to the budget basis with last fiscal year's MTS÷DTS ratio (FY2026: revenue 0.8238, spending 0.8972). The rate is the ratio × the trailing-90-day cash pace. Once a current-FY MTS month exists, MTS becomes the anchor and DTS covers only the days after it. Budget functions and revenue sources = MTS share × the daily total, which keeps the Sankey consistent. Interest paid in cash comes from the DTS "Interest on Treasury Securities" line.
Validation adds:
- `daily_vs_dts`: yesterday's projection vs today's DTS-rebased value (3% threshold).
- `dts_ratio_backtest`: the FY-2 ratio applied to FY-1 cash vs the official FY-1 total. Revenue was off +4.01% and spending +1.03%, so treat revenue as roughly ±4%.
- `method_switch_*` rows: logged once when the method changed, not flagged.

**New official tickers** (each with ticking per-person and per-tax-return columns):

| Ticker | Source | Rate |
|---|---|---|
| Debt subject to limit; statutory limit; headroom plus days-to-limit | DTS Table III-C `dts/debt_subject_to_limit` | 90-day OLS slope |
| Fed Treasury holdings | NY Fed SOMA `markets.newyorkfed.org/api/soma/summary.json` | 13-week slope |
| Fed share of public debt | Derived | — |
| M2; debt as % of M2 | Fed H.6 CSV (Data Download Program) | 6-month slope, mid-month anchor |
| SS trust funds (OASI, DI, combined); Medicare (HI, SMI, combined) | Treasury FIP `od/fip_principal_outstanding_table1`, summed by account | 12-month slope |
| Implied annual interest, interest per day, per second, since page open | Live debt × average rate on all interest-bearing debt | Derived |

FIP gotcha: requesting a `fields=` subset makes the API collapse identical rows. Always include `src_line_nbr`.

**What changed strip.** `meta.recent_closes` holds the last 10 Debt to the Penny closes with daily Δ total, public and intragov, plus per person. A live "NOW" card shows the gap from the last close.

**Badges.** Every tile carries one of: `PROJECTED · from <official date>`, `FIXED · <date>`, `LIVE CALC`, or `HISTORICAL · fixed`. Tiles can also show a daily-check badge (✓/⚠ vs Treasury/DTS) and `cached` when the source failed and the last good value is in use. One Census population function is used everywhere (app, widget and share pages via `core.js`).

**Explainer.** "Why the debt grew more than the deficit" for FY2026: Δdebt $2.534T vs deficit $1.992T. Of the $541.8B gap, $387.0B is intragovernmental, $93.2B is TGA cash build and $61.6B is other financing (residual). Sources: Debt to the Penny, MTS and DTS operating cash.

**Share and SEO** (build.py):
- `og/<slug>.png` + `og/home.png` (1200×630, Pillow, DejaVu fonts).
- Real indexable `t/<slug>.html` pages: snapshot value in the HTML, live ticking via `core.js`, method, source, daily check, related links, canonical, OG/Twitter, JSON-LD Dataset.
- `index.html` meta block refreshed each build with today's numbers.
- `sitemap.xml` and `robots.txt`.
- The modal adds "Post on X" (intent link the visitor clicks) and "Share image".
- Site URL defaults to `https://everydebtclock.com` (override with `DEBTCLOCK_SITE_URL` for previews).

## Cron plan (America/Chicago)
- `0 6 * * *` — morning recalibration (Census, BEA, MTS on release days ~8th business day, OMB).
- `30 15 * * 1-5` — after Treasury's ~4 PM ET release of Debt to the Penny + Daily Treasury Statement.
Run as a GitHub Actions scheduled workflow (free) that commits `data/` and redeploys.

## Hosting
Static files only: Cloudflare Pages or GitHub Pages (free), Cloudflare CDN in front. Approx. cost: $0 plus a domain (~$10–15/yr). Treasury APIs are free and keyless.

## Traffic plan (nothing has been posted)
- **One URL per ticker** (`/t/<slug>`, 57 today) with its own title/description → long-tail search ("US interest on debt today", "Social Security spending 2027").
- **Embeds:** one-line iframe for every ticker; pitch to bloggers, newsletters, teachers, local news. Each embed links back.
- **Milestone auto-posts to X** (e.g. debt crosses $40.5T, interest passes defense FYTD): the pipeline can detect crossings and queue a draft post + share image. Needs an approval step; not built and nothing posted.
- **Daily "debt today" share card** (OG image per ticker), weekly email digest, and a "verified vs Treasury" track record page as the trust differentiator vs usdebtclock.
- Next tickers to add (official sources exist): state & local debt (Census), Social Security/Medicare trust fund balances (Treasury/SSA), Fed holdings of Treasuries (H.4.1), debt per worker (BLS), debt subject to the limit.

## Phase 3: pre-launch fixes (Oct 25, 2026)

- **interest_gross.** The old version mixed an 11-month sum (a 400-row page dropped Oct 2025) with a 12-month label. It now filters by date, reads every page, and uses the TTM of 12 distinct months, which equals the FY2026 total ($1,360.4B) and is checked every run.
- **Population.** Census Vintage 2025 base (341,784,857 on Jul 1, 2025), ticking at Census's stated rate. The popclock is only a cross-check.
- **"Per tax return filed"** replaces "per taxpayer" everywhere. The IRS count includes zero-liability returns, and a joint return counts once.
- **Debt.** One 90-day OLS window for total, public, and intragov, so the parts sum exactly. The hero shows the window plus backtest error; the modal shows the 1-year average rate for context.
- **Show the math** on every ticker: base, t0 (CT), rate per second, inputs, and the formula with live numbers.
- **Lead hero:** debt-limit headroom, days left, and projected date ("our projection, before extraordinary measures").
- **Audit.** `../audit/audit.py` compares each base with its source. Pipeline data contract and sources: `../handoff/SOURCES.md`.
