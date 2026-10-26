/* Shared ticker math for share pages and the embed widget (same formulas as app.js). */
window.DC = function (D) {
  const T = D.tickers, M = D.meta, OPENED = Date.now() / 1000;
  const val = (s, t) => { const x = T[s]; if (!x || x.status !== 'ok') return null;
    if (x.mode === 'fytd' && t >= M.fy_end_epoch) return x.rate * (t - M.fy_end_epoch);
    if (x.freeze_t && t > x.freeze_t) t = x.freeze_t;   // never project debt past the statutory limit
    return x.base + x.rate * (t - x.t0) + (x.steps || []).reduce((s, q) => s + q[2] * Math.min(1, Math.max(0, (t - q[0]) / (q[1] - q[0]))), 0); };   // steps: scheduled payment ramps [start, end, amount]
  const ia = t => { const a = val('debt_total', t), r = T.rate_all; return a && r ? a * r.base / 100 : null; };
  const DER = {
    debt_gdp_now: t => val('debt_total', t) / val('gdp', t) * 100,
    deficit_gdp_now: t => (T.spending.ttm - T.revenue.ttm) / val('gdp', t) * 100,
    interest_share: t => val('out_interest', t) / val('revenue', t) * 100,
    debt_per_household: t => val('debt_total', t) / T.households.base,
    interest_annual: ia, interest_per_day: t => ia(t) / 365.25, interest_per_sec: t => ia(t) / 31557600,
    interest_since_open: t => ia(t) * (t - OPENED) / 31557600,
    limit_headroom: t => T.debt_limit.base - val('debt_subject_limit', t),
    fed_share_public: t => val('fed_treasuries', t) / val('debt_public', t) * 100,
    m2_debt_ratio: t => val('debt_total', t) / val('m2', t) * 100,
  };
  const get = (s, t) => DER[s] ? DER[s](t) : val(s, t);
  const info = s => DER[s] ? Object.assign({status: 'ok', derived: true}, D.derived[s]) : T[s];
  const pop = t => val('population', t), tax = T.tax_returns && T.tax_returns.base;
  const nf0 = new Intl.NumberFormat('en-US', {maximumFractionDigits: 0});
  const usd = (v, d = 0) => v == null ? '—' : (v < 0 ? '−$' : '$') + new Intl.NumberFormat('en-US', {minimumFractionDigits: d, maximumFractionDigits: d}).format(Math.abs(v));
  const ppf = v => { if (v == null || !isFinite(v)) return '—'; const a = Math.abs(v), s = v < 0 ? '−$' : '$'; return a < 0.01 ? s + a.toFixed(6) : a < 100 ? s + a.toFixed(4) : usd(v, 2); };
  const fmt = (i, x) => i.kind === 'pct' ? x.toFixed(i.fixed ? 3 : 5) + '%' : i.kind === 'count' ? nf0.format(x) : usd(x);
  return {T, M, val, get, info, pop, tax, usd, ppf, fmt};
};
