/* Every Debt Clock — every ticker = official base + rate × (now − t0). */
(async function () {
  const D = window.DEBTCLOCK_DATA || await (await fetch('data/data.json', {cache: 'no-store'})).json();
  const T = D.tickers, M = D.meta;
  const now = () => Date.now() / 1000;
  const OPENED = now();
  const fyRolled = () => now() >= M.fy_end_epoch;      // client-side Oct 1 reset if data not refreshed yet
  const curFY = () => fyRolled() ? M.fy + 1 : M.fy;

  function val(slug, t = now()) {
    const x = T[slug];
    if (!x || x.status !== 'ok') return null;
    if (x.mode === 'fytd' && t >= M.fy_end_epoch) return x.rate * (t - M.fy_end_epoch);
    if (x.freeze_t && t > x.freeze_t) t = x.freeze_t;   // never project debt past the statutory limit
    return x.base + x.rate * (t - x.t0);
  }
  const DER = {
    debt_gdp_now: t => { const a = val('debt_total', t), b = val('gdp', t); return a && b ? a / b * 100 : null; },
    deficit_gdp_now: t => { const s = T.spending, r = T.revenue, g = val('gdp', t); return s && r && s.ttm && g ? (s.ttm - r.ttm) / g * 100 : null; },
    interest_share: t => { const a = val('out_interest', t), b = val('revenue', t); return a && b ? a / b * 100 : null; },
    interest_annual: t => { const a = val('debt_total', t), r = T.rate_all; return a && r ? a * r.base / 100 : null; },
    interest_per_day: t => { const a = DER.interest_annual(t); return a == null ? null : a / 365.25; },
    interest_per_sec: t => { const a = DER.interest_annual(t); return a == null ? null : a / 31557600; },
    interest_since_open: t => { const a = DER.interest_annual(t); return a == null ? null : a * (t - OPENED) / 31557600; },
    limit_headroom: t => { const l = T.debt_limit, s = val('debt_subject_limit', t); return l && s != null ? l.base - s : null; },
    fed_share_public: t => { const a = val('fed_treasuries', t), b = val('debt_public', t); return a && b ? a / b * 100 : null; },
    m2_debt_ratio: t => { const a = val('debt_total', t), b = val('m2', t); return a && b ? a / b * 100 : null; },
    debt_per_household: t => { const a = val('debt_total', t); return a ? a / T.households.base : null; },
  };
  const drate = slug => { const t = now(); const a = DER[slug](t), b = DER[slug](t + 60); return a == null || b == null ? null : (b - a) / 60; };
  const eodTs = d => Date.parse(d + 'T23:59:59-04:00') / 1000;
  const get = (slug, t) => DER[slug] ? DER[slug](t) : val(slug, t);
  const info = slug => DER[slug] ? Object.assign({status: 'ok', slug, derived: true}, D.derived[slug]) : (T[slug] || {slug, status: 'unavailable', label: slug});

  // ---------- formatting
  const nf0 = new Intl.NumberFormat('en-US', {maximumFractionDigits: 0});
  const nf2 = new Intl.NumberFormat('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const usd = (v, d = 0) => v == null ? '—' : (v < 0 ? '−$' : '$') + (d ? nf2 : nf0).format(Math.abs(v));
  const pct = (v, d = 4) => v == null ? '—' : v.toFixed(d) + '%';
  const short = v => { const a = Math.abs(v), s = v < 0 ? '−$' : '$';
    return a >= 1e12 ? s + (a / 1e12).toFixed(2) + 'T' : a >= 1e9 ? s + (a / 1e9).toFixed(2) + 'B' : a >= 1e6 ? s + (a / 1e6).toFixed(1) + 'M' : s + nf0.format(a); };
  const rateTxt = r => { if (!r) return 'fixed'; const a = Math.abs(r), sg = r > 0 ? '+' : '−';
    return a >= 1 ? `${sg}${short(a).slice(1)}/sec · ${sg}${short(a * 86400).slice(1)}/day` : `${sg}$${(a * 86400).toFixed(2)}/day`; };
  const fmtDate = s => { if (/^\d{4}-\d\d$/.test(s || '')) { const [y, m] = s.split('-'); return new Date(+y, m - 1, 1).toLocaleDateString('en-US', {month: 'short', year: 'numeric'}); }
    if (!s || !/^\d{4}-\d\d-\d\d$/.test(s)) return s; const [y, m, d] = s.split('-'); return new Date(+y, m - 1, +d).toLocaleDateString('en-US', {month: 'short', day: 'numeric', year: 'numeric'}); };
  const ppf = v => { if (v == null || !isFinite(v)) return '—'; const a = Math.abs(v); return a < 0.01 ? usd(v, 0).replace(/[\d,]+$/, '') + a.toFixed(6) : a < 100 ? (v < 0 ? '−$' : '$') + a.toFixed(4) : usd(v, 2); };
  const shortDate = s => { const f = fmtDate(s); return /^\d{4}-\d\d-\d\d$/.test(s || '') ? f.replace(/, \d{4}$/, '') : f; };
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));

  // ---------- layout definition
  const dtsNote = () => T.spending?.basis === 'dts' ? `re-based every business day from the Daily Treasury Statement (through ${fmtDate(T.spending.as_of)}), calibrated to the Monthly Treasury Statement` : 'Monthly Treasury Statement projection (DTS unavailable)';
  const S = [
    {id: 'debt', title: 'National debt & the debt limit', note: () => `Treasury Debt to the Penny + DTS Table III-C · official as of ${fmtDate(T.debt_total?.as_of)} · re-based every business day`, color: 'var(--red)',
      tiles: ['debt_public', 'debt_intragov', 'debt_subject_limit', 'debt_limit', 'limit_headroom', 'debt_gdp_now']},
    {id: 'fy', title: () => `FY${curFY()} so far`, note: () => `Fiscal year to date · resets every Oct 1 · ${dtsNote()}`, color: 'var(--amber)', tiles: ['spending', 'revenue', 'deficit', 'interest_cash']},
    {id: 'interest', title: 'Interest on the debt', note: () => `Live debt × Treasury's average interest rate (${T.rate_all?.base?.toFixed(3)}%, ${fmtDate(T.rate_all?.as_of)})`, color: 'var(--orange)',
      tiles: ['interest_annual', 'interest_per_day', 'interest_per_sec', 'interest_since_open', 'interest_gross', 'interest_share']},
    {id: 'spend', dense: 1, title: 'Where the money goes', note: 'Outlays by budget function, FY to date', color: 'var(--blue)',
      tiles: ['out_socsec', 'out_medicare', 'out_health', 'out_interest', 'out_defense', 'out_income', 'out_veterans', 'out_justice', 'out_transport', 'out_education', 'out_community', 'out_nature', 'out_agri', 'out_intl', 'out_science', 'out_govt', 'out_energy', 'out_commerce', 'out_offsets']},
    {id: 'rev', dense: 1, title: 'Where the money comes from', note: 'Receipts by source, FY to date', color: 'var(--green)', tiles: ['rev_individual', 'rev_payroll', 'rev_corporate', 'rev_customs', 'rev_excise', 'rev_misc', 'rev_estate']},
    {id: 'trust', dense: 1, title: 'Social Security & Medicare trust funds', note: () => `Treasury securities held by each fund · Federal Investments Program, month-end ${fmtDate(T.tf_socsec?.as_of)}`, color: 'var(--violet)',
      tiles: ['tf_socsec', 'tf_medicare', 'tf_oasi', 'tf_di', 'tf_hi', 'tf_smi']},
    {id: 'money', dense: 1, title: 'The Fed & money supply', note: 'NY Fed SOMA (weekly) · Federal Reserve H.6 (monthly)', color: 'var(--teal)', tiles: ['fed_treasuries', 'fed_share_public', 'm2', 'm2_debt_ratio']},
    {id: 'ratios', dense: 1, title: 'Ratios & economy', note: 'Computed live from the tickers above', color: 'var(--teal)', tiles: ['debt_per_household', 'deficit_gdp_now', 'gdp', 'rate_marketable', 'rate_all', 'population', 'tax_returns', 'households']},
  ];
  const ACC = {debt: 'var(--red)', fy: 'var(--amber)', interest: 'var(--orange)', spend: 'var(--blue)', rev: 'var(--green)', trust: 'var(--violet)', money: 'var(--teal)', ratios: 'var(--teal)'};

  // ---------- render
  const app = document.getElementById('app');
  app.querySelectorAll('.ssr').forEach(e => e.remove());   // build-time static fallback (for crawlers / no-JS); replaced by the live clock
  const DLS = M.debt_limit_status || {};
  const live = []; // {el, fn}
  const pop = t => val('population', t), tax = () => T.tax_returns?.base;
  const PPB = `Debt ÷ US population projected to now from the Census Vintage 2025 estimate (${nf0.format(T.population?.base || 0)} on Jul 1, 2025) at Census's stated growth rate. Official-basis figure: debt ÷ that Jul 1, 2025 estimate.`;
  const isUSD = i => (i.kind === 'usd');
  const NOPP = new Set(['debt_per_household']);

  function modeBadge(i, short) {
    const d = short ? shortDate(i.as_of) : fmtDate(i.as_of);
    if (i.historical) return `<span class="badge hist" title="Fixed historical figure (OMB Historical Tables)">HISTORICAL · fixed</span>`;
    if (i.derived) return `<span class="badge calc" title="${esc(i.method || '')}">LIVE CALC</span>`;
    if (i.fixed) return `<span class="badge fix" title="Official figure that does not change until the next official release">FIXED · ${esc(d)}</span>`;
    return `<span class="badge proj" title="Projected every frame from the official figure of ${esc(fmtDate(i.as_of))}">PROJECTED · from ${esc(d)}</span>`;
  }
  function badges(i, opts = {}) {
    let b = modeBadge(i, opts.short);
    const v = i.validation;
    if (v && v.last_error_pct != null) {
      const cls = v.flag ? 'bad' : Math.abs(v.last_error_pct) > v.threshold_pct / 2 ? 'warn' : 'ok';
      const who = /Daily Treasury/.test(v.against || '') ? 'DTS' : 'Treasury';
      b += `<span class="badge ${cls}" title="Yesterday's projection vs ${esc(v.against)}">${v.flag ? '⚠' : '✓'} vs ${who} ${v.last_error_pct >= 0 ? '+' : ''}${(+v.last_error_pct).toFixed(2)}%</span>`;
    }
    if (i.stale) b += `<span class="badge warn" title="Source failed on the last run; showing the last good official figure">cached</span>`;
    return b;
  }
  function tile(slug, sec) {
    const i = info(slug);
    const el = document.createElement('div');
    el.className = 'tile'; el.id = 't-' + slug; el.style.setProperty('--acc', ACC[sec]);
    if (i.status !== 'ok') {
      el.classList.add('na');
      el.innerHTML = `<div class="lab"><span>${esc(i.label)}</span></div><div class="val">source unavailable</div><div class="meta"><span class="badge bad">${esc(i.note || '')}</span></div>`;
      return el;
    }
    if (i.fixed) el.classList.add('fixed');
    const lbl = typeof i.label === 'function' ? i.label() : i.label;
    const rate = i.derived ? (i.kind === 'usd' ? drate(slug) : null) : i.rate;
    const fy = i.mode === 'fytd' ? `<span>FY${curFY()} to date</span>` : '';
    el.innerHTML = `<div class="lab"><span>${esc(lbl)}</span>${fy}</div>
      <div class="val num">—</div>
      ${isUSD(i) && !NOPP.has(slug) ? `<div class="pp"><div><span class="l" title="${esc(PPB)}">Per person (proj. pop.)</span><span class="num pp1">—</span></div><div><span class="l">Per tax return filed</span><span class="num pp2">—</span></div></div>` : ''}
      <div class="meta"><span class="rate ${/^(debt|deficit|interest|out_interest)/.test(slug) ? (rate > 0 ? 'up' : rate < 0 ? 'dn' : '') : ''}">${i.kind === 'count' && rate ? '+' + (rate * 86400).toFixed(0) + ' people/day' : i.kind === 'usd' && rate != null ? rateTxt(rate) : i.derived ? 'live ratio' : 'fixed'}</span>${badges(i, {short: 1})}</div>${slug === 'limit_headroom' ? '<div class="sub2" id="htl"></div>' : ''}`;
    const v = el.querySelector('.val'), p1 = el.querySelector('.pp1'), p2 = el.querySelector('.pp2');
    const kind = i.kind;
    live.push(t => {
      const x = get(slug, t);
      v.textContent = kind === 'pct' ? pct(x, i.fixed ? 3 : 5) : kind === 'count' ? nf0.format(x) : usd(x);
      if (p1) { p1.textContent = ppf(x / pop(t)); p2.textContent = ppf(x / tax()); }
    });
    if (slug === 'limit_headroom') { const h = el.querySelector('#htl'), r = T.debt_subject_limit?.rate;
      live.push(t => { const x = get(slug, t); h.textContent = x > 0 && r > 0 ? `At the 90-day pace, the limit is reached in about ${Math.round(x / r / 86400)} days (projection, not a Treasury estimate; extraordinary measures can extend it)` : x <= 0 ? 'Projected at or above the limit' : ''; }); }
    el.onclick = () => openModal(slug);
    return el;
  }

  // header status
  const age = (now() - M.generated_epoch) / 3600;
  const st = document.getElementById('status');
  st.textContent = `Recalibrated ${new Date(M.generated_epoch * 1000).toLocaleString('en-US', {month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short'})}`;
  if (age > 36) app.insertAdjacentHTML('beforeend', `<div class="banner">Data last recalibrated ${Math.floor(age / 24)} day(s) ago. Tickers are still projecting from the last official figures.</div>`);
  if (fyRolled()) app.insertAdjacentHTML('beforeend', `<div class="banner">New fiscal year FY${curFY()} started Oct 1 — fiscal-year counters reset to $0 and are projecting until the next official update.</div>`);
  if (DLS.at_limit) app.insertAdjacentHTML('beforeend', `<div class="banner">At the debt limit: Treasury is using extraordinary measures. Debt subject to the limit was ${usd(DLS.subject_to_limit)} on ${fmtDate(DLS.as_of)}, ${usd(DLS.headroom)} under the ${usd(DLS.limit)} limit, so the debt counters hold at Treasury's latest official figures instead of projecting growth.</div>`);
  if ((M.flags || []).length) app.insertAdjacentHTML('beforeend', `<div class="banner">Drift alert: ${M.flags.join(', ')} exceeded the validation threshold on the last check.</div>`);

  // lead hero: total national debt
  const d = info('debt_total');
  const hero = document.createElement('div'); hero.className = 'hero lead'; hero.id = 't-debt_total';
  if (d.status === 'ok') {
    hero.innerHTML = `<div class="k">US national debt · ${d.held_at_limit ? 'held at the debt limit (official figure)' : 'live'}</div><div class="big num" id="hv">—</div>
    <div class="sub"><span>${rateTxt(d.rate)}</span><span class="note">rate: 90-day least-squares trend (${d.calc?.n || '—'} daily closes), backtested vs next Treasury close, avg error ${d.validation?.mean_abs_error_pct != null ? d.validation.mean_abs_error_pct.toFixed(3) + '%' : 'n/a'}</span><span>Since you opened this page: <span class="num" id="hs">$0</span> more debt · <span class="num" id="hi">$0</span> in interest</span></div>
    <div class="trio"><div><span class="l" title="${esc(PPB)}">Per person (projected population)</span><span class="num" id="h1">—</span></div><div><span class="l">Per tax return filed</span><span class="num" id="h2">—</span></div><div><span class="l">Per household</span><span class="num" id="h3">—</span></div></div>
    <div class="meta" style="margin-top:10px">${badges(d)}<span class="badge">source: Treasury Debt to the Penny</span></div>`;
    const hv = hero.querySelector('#hv'), hs = hero.querySelector('#hs'), h1 = hero.querySelector('#h1'), h2 = hero.querySelector('#h2'), h3 = hero.querySelector('#h3'), hi = hero.querySelector('#hi');
    live.push(t => { const x = val('debt_total', t); hv.textContent = usd(x); hs.textContent = '+' + usd(x - val('debt_total', OPENED), 0); hi.textContent = usd(DER.interest_since_open(t), 0);
      h1.textContent = usd(x / pop(t), 2); h2.textContent = usd(x / tax(), 2); h3.textContent = usd(x / T.households.base, 2); });
    hero.onclick = () => openModal('debt_total');
  } else hero.innerHTML = `<div class="k">US national debt</div><div class="big">source unavailable</div>`;
  app.appendChild(hero);

  // ---------- "Your state" card (server-rendered with the default place; see build.py place_card)
  const pc = document.getElementById('placecard');
  if (pc) {
    const hub = pc.nextElementSibling; app.appendChild(pc); if (hub && hub.classList.contains('pchub')) app.appendChild(hub);
    let IX = null; try { IX = JSON.parse(document.getElementById('placesix').textContent); } catch (e) {}
    const P = IX ? IX.places : [], by = s => P.find(x => x.slug === s), KEY = 'edc.place';
    const $ = id => pc.querySelector('#' + id), sel = $('pcsel');
    let cur = by(IX && IX.default), how = 'default';
    const kindWord = x => x.kind === 'country' ? 'country' : 'state';
    function show(p, why) {
      if (!p) return; cur = p; how = why;
      $('pck').textContent = why === 'default' ? 'Featured ' + kindWord(p) : 'Your ' + kindWord(p);
      $('pcn').textContent = p.name; $('pclab').textContent = p.label; $('pcd').textContent = p.demonym; $('pcg').textContent = p.name;
      $('pcb').textContent = p.rate ? 'projected from official ' + fmtDate(p.base_date) + ' figures' : 'official, ' + fmtDate(p.base_date);
      $('pcl').href = p.url; sel.value = p.slug;
    }
    let saved = null; try { saved = by(localStorage.getItem(KEY)); } catch (e) {}
    if (saved) show(saved, 'saved');
    else if (P.length > 1 && /^https?:$/.test(location.protocol)) {
      // /api/geo is a Cloudflare Worker: {"country":"US","region_code":"TX"}. Any failure, a slow answer (800 ms) or a place without a page keeps the default.
      const ac = typeof AbortController === 'function' ? new AbortController() : null, to = setTimeout(() => ac && ac.abort(), 800);
      fetch('/api/geo', {cache: 'no-store', signal: ac ? ac.signal : undefined}).then(r => r.ok ? r.json() : null).then(g => {
        if (!g || !g.country) return;
        const c = String(g.country).toUpperCase(), r = String(g.region_code || '').toUpperCase();
        const m = P.find(x => x.kind === 'state' && x.country === c && x.region_code === r) || P.find(x => x.kind === 'country' && x.country === c);
        if (m && how === 'default') show(m, 'geo');
      }).catch(() => {}).finally(() => clearTimeout(to));
    }
    sel.onchange = () => { const p = by(sel.value); if (!p) return; try { localStorage.setItem(KEY, p.slug); } catch (e) {} show(p, 'saved'); };
    const pv = $('pcv'), pp = $('pcp');
    const cu = (v, d) => { const s = usd(v, d), c = cur.sym || '$'; return c === '$' ? s : s.replace('$', c); };
    live.push(t => { if (!cur) return; const x = cur.base + cur.rate * (t - cur.t0); pv.textContent = cu(x); pp.textContent = cu(x / cur.population, 2); });
  }

  // secondary hero: debt-limit headroom (below the national debt)
  const sl = T.debt_subject_limit, lim = T.debt_limit;
  if (sl?.status === 'ok' && lim?.status === 'ok' && sl.rate > 0) {
    const lh = document.createElement('div'); lh.className = 'hero second'; lh.id = 't-limit_headroom_hero';
    lh.innerHTML = `<div class="k">Room left under the debt limit · live</div><div class="big num" id="lhv">—</div>
    <div class="sub"><span>Limit hit in <b class="num" id="lhd">—</b> days · around <b id="lhx">—</b></span><span class="note">our projection, before extraordinary measures</span></div>
    <div class="sub3">$${(lim.base / 1e12).toFixed(3)}T limit − debt subject to limit (${usd(sl.base, 0)} at the ${esc(fmtDate(sl.as_of))} close, rising ${rateTxt(sl.rate)} on its 90-day trend). Tap for the math.</div>`;
    const lhv = lh.querySelector('#lhv'), lhd = lh.querySelector('#lhd'), lhx = lh.querySelector('#lhx');
    live.push(t => { const h = DER.limit_headroom(t); lhv.textContent = usd(h, 0); const dd = h / sl.rate / 86400; lhd.textContent = dd.toFixed(1);
      lhx.textContent = new Date((t + h / sl.rate) * 1000).toLocaleDateString('en-US', {month: 'short', day: 'numeric', year: 'numeric', timeZone: 'America/Chicago'}); });
    lh.onclick = () => openModal('limit_headroom');
    app.appendChild(lh);
  }


  // ---------- "What changed": recent official Debt to the Penny closes
  const RC = M.recent_closes || [];
  if (RC.length) {
    const wc = document.createElement('section'); wc.id = 'changed';
    const dl = (v, cls = 1) => `<span class="${cls ? (v > 0 ? 'up' : v < 0 ? 'dn' : '') : ''}">${v >= 0 ? '+' : '−'}${short(Math.abs(v)).replace('$', '$')}</span>`;
    wc.innerHTML = `<div class="sh"><span class="bar" style="background:var(--red)"></span><h2>What changed</h2><span class="h2n">Official Debt to the Penny closes, newest first · Treasury publishes each business day around 3 p.m. ET</span></div>
    <div class="wc"><div class="wcc now" id="t-wc_now"><div class="d">NOW · projected</div><div class="v num" id="wcn">—</div><div class="x">vs last close <span class="num" id="wcd">—</span></div><div class="x">per person <span class="num" id="wcp">—</span></div></div>
    ${RC.map(r => `<div class="wcc"><div class="d">${esc(fmtDate(r.date))}</div><div class="v num">$${(r.total / 1e12).toFixed(3)}T</div><div class="x">day ${dl(r.d_total)}</div><div class="x">public ${dl(r.d_public)}</div><div class="x">intragov ${dl(r.d_intragov)}</div><div class="x">per person <span class="${r.d_total > 0 ? 'up' : 'dn'}">${r.d_total >= 0 ? '+' : '−'}${ppf(Math.abs(r.d_total / val('population', eodTs(r.date))))}</span></div></div>`).join('')}</div>
    <div class="legend">Daily moves are lumpy: debt jumps on auction settlement days (often the 15th and month-end) and dips when trust-fund securities mature. That is why we tick at the 90-day trend and show the official closes here.</div>`;
    app.appendChild(wc);
    const wcn = wc.querySelector('#wcn'), wcd = wc.querySelector('#wcd'), wcp = wc.querySelector('#wcp');
    live.push(t => { const x = val('debt_total', t); wcn.textContent = '$' + (x / 1e12).toFixed(6) + 'T'; const dd = x - RC[0].total; wcd.textContent = (dd >= 0 ? '+' : '−') + usd(Math.abs(dd)); wcp.textContent = ppf(x / pop(t)); });
  }

  const secEls = {};
  for (const s of S) {
    const sec = document.createElement('section'); sec.id = s.id;
    const title = typeof s.title === 'function' ? s.title() : s.title;
    sec.innerHTML = `<div class="sh"><span class="bar" style="background:${s.color}"></span><h2>${esc(title)}</h2><span class="h2n">${esc(typeof s.note === 'function' ? s.note() : s.note)}</span></div><div class="grid"></div>`;
    const g = sec.querySelector('.grid');
    if (s.dense) g.classList.add('dense');
    s.tiles.forEach(x => g.appendChild(tile(x, s.id)));
    app.appendChild(sec); secEls[s.id] = sec;
    if (s.id === 'rev') app.appendChild(sankeySection());
    if (s.id === 'fy' && M.explainer) app.appendChild(explainer(M.explainer));
  }

  function explainer(E) {
    const sec = document.createElement('section'); sec.id = 'why';
    const B = v => short(v), gap = E.debt_growth - E.deficit;
    const parts = [['Deficit (MTS)', E.deficit, 'var(--red)'], ['Treasury cash pile grew (TGA)', E.tga_change || 0, 'var(--amber)'], ['Other financing (net, residual)', E.other_financing, '#8a97ab'], ['Intragovernmental debt (trust funds)', E.intragov_growth, 'var(--violet)']];
    const tot = parts.reduce((a, p) => a + Math.max(p[1], 0), 0);
    sec.innerHTML = `<div class="sh"><span class="bar" style="background:var(--violet)"></span><h2>Why the debt grew more than the deficit</h2><span class="h2n">FY${E.fy} (${fmtDate(E.from)} → ${fmtDate(E.to)}) · fixed official figures · our calculation</span></div>
    <div class="sk why">
      <div class="whyhead"><div><span class="l">Debt grew</span><span class="num">${B(E.debt_growth)}</span></div><div><span class="l">Deficit was</span><span class="num">${B(E.deficit)}</span></div><div><span class="l">Gap</span><span class="num up">${B(gap)}</span></div></div>
      <div class="stack">${parts.map(p => `<span style="flex:${Math.max(p[1], 0) / tot};background:${p[2]}" title="${esc(p[0])}: ${B(p[1])}"></span>`).join('')}</div>
      <ul class="whyl">${parts.map(p => `<li><i style="background:${p[2]}"></i><b>${B(p[1])}</b> ${esc(p[0])}</li>`).join('')}</ul>
      <p><b>The deficit</b> is what the government spent minus what it took in on a budget basis: <b>${B(E.deficit)}</b> in FY${E.fy}. <b>Debt held by the public</b> rose <b>${B(E.public_growth)}</b>: the deficit, plus <b>${B(E.tga_change || 0)}</b> Treasury added to its cash account at the Fed, plus <b>${B(E.other_financing)}</b> of other net financing (mainly federal loan programs such as student loans, which lend cash that is not counted as outlays, plus timing and discount effects; computed as the remainder).</p>
      <p><b>Intragovernmental debt</b> rose <b>${B(E.intragov_growth)}</b>. That is Treasury IOUs issued to federal trust funds and accounts (Medicare, military and civil-service retirement and others) for their surpluses and the interest credited to them. It is money the government owes itself, so it adds to the total debt but never shows up in the deficit.</p>
      <p class="foot">Sources: ${Object.entries(E.sources).map(([n, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(n)}</a>`).join(' · ')}. Debt growth = Debt to the Penny close ${fmtDate(E.to)} − close ${fmtDate(E.from)}. Other financing = Δ debt held by the public − deficit − Δ operating cash.</p>
    </div>`;
    return sec;
  }

  // history (fixed)
  const hs = document.createElement('section'); hs.id = 'history';
  const years = ['1960', '1980', '1990', '2000', '2010', '2020', '2025'];
  hs.innerHTML = `<div class="sh"><span class="bar" style="background:var(--violet)"></span><h2>History</h2><span class="h2n">Fixed official figures · OMB Historical Tables · these do not tick</span></div>
  <div class="histgrid">${years.map(y => { const a = T['hist_debt_gdp_' + y], b = T['hist_def_gdp_' + y];
    return `<div class="htile" data-s="hist_debt_gdp_${y}"><div class="y">FY${y} · HISTORICAL</div><div class="t">Debt-to-GDP</div><div class="num">${a ? a.base.toFixed(1) + '%' : 'n/a'}</div>
      <div class="t">Deficit-to-GDP</div><div class="num" style="font-size:15px;color:${b && b.base < 0 ? 'var(--green)' : '#d9d2ff'}">${b ? (b.base < 0 ? 'surplus ' + Math.abs(b.base).toFixed(1) : b.base.toFixed(1)) + '%' : 'n/a'}</div></div>`; }).join('')}</div>`;
  hs.querySelectorAll('.htile').forEach(e => e.onclick = () => openModal(e.dataset.s));
  app.appendChild(hs);

  // validation + sources
  const vs = document.createElement('section'); vs.id = 'method';
  const vrows = Object.values(T).filter(x => x.validation).map(x => `<tr><td>${esc(x.label)}</td><td class="num">${x.validation.last_error_pct >= 0 ? '+' : ''}${(+x.validation.last_error_pct).toFixed(3)}%</td><td class="num">${x.validation.mean_abs_error_pct != null ? x.validation.mean_abs_error_pct.toFixed(3) + '%' : '—'}</td><td>${esc(x.validation.against)}</td><td>${x.validation.flag ? '⚠ drift' : 'ok'}</td></tr>`).join('');
  const srcs = [...new Map(Object.values(T).filter(x => x.source).map(x => [x.source, x.source_name])).entries()];
  vs.innerHTML = `<div class="sh"><span class="bar" style="background:var(--mut)"></span><h2>How it works</h2><span class="h2n">Recalibrated daily · checked daily against official numbers</span></div>
  <div class="sk foot">
  <p><b>Every number</b> = latest official figure + (official trend per second × seconds since that figure). The pipeline re-bases every ticker each morning and after Treasury's afternoon release, then compares yesterday's projection with the new official figure. If the gap exceeds the threshold (0.25% for total and public debt, 0.5% for intragovernmental debt, 3% for the DTS-rebased fiscal-year totals, 5% for monthly figures), the ticker is flagged.</p>
  <p><b>Fiscal-year totals</b> use the Daily Treasury Statement every business day. Cash deposits and withdrawals, excluding debt issues and redemptions, are converted to the official budget basis with last year's ratio: revenue ×${(M.dts_ratio?.revenue?.ratio_prev_fy || 0).toFixed(4)}, spending ×${(M.dts_ratio?.spending?.ratio_prev_fy || 0).toFixed(4)}. Backtest: applying the year-before ratio to last year's cash missed the official total by ${(M.dts_ratio?.revenue?.backtest_err_pct ?? 0).toFixed(2)}% for revenue and ${(M.dts_ratio?.spending?.backtest_err_pct ?? 0).toFixed(2)}% for spending. Once a monthly statement for the current year exists, it becomes the anchor and DTS only fills in the days since.</p>
  <table class="v"><tr><th>Ticker</th><th>Last check</th><th>Avg |error| (20 days)</th><th>Checked against</th><th></th></tr>${vrows}</table>
  <p><b>Per person</b> uses one Census population figure everywhere on the site (${nf0.format(val('population') || 0)} now): the Vintage 2025 official estimate for July 1, 2025, projected forward at Census's own stated growth rate. <b>Per tax return filed</b> divides by ${nf0.format(T.tax_returns?.base || 0)} individual income tax returns filed in FY2025 (IRS Data Book, Table 1-2). That counts returns, not people: a joint return counts once, and returns with zero tax liability are included.</p>
  <p><b>Sources:</b> ${srcs.map(([u, n]) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(n)}</a>`).join(' · ')}</p>
  ${Object.keys(M.errors || {}).length ? `<p style="color:var(--amber)">Source problems on last run: ${esc(Object.keys(M.errors).join(', '))}</p>` : ''}
  <p>Prototype · data generated ${esc(M.generated_iso)}</p></div>`;
  app.appendChild(vs);

  // ---------- live Sankey
  function sankeySection() {
    const sec = document.createElement('section'); sec.id = 'flow';
    sec.innerHTML = `<div class="sh"><span class="bar" style="background:linear-gradient(var(--green),var(--blue))"></span><h2>Follow the money</h2><span class="h2n" id="skn"></span></div><div class="sk"><svg id="sk"></svg></div>
    <div class="legend">Flow widths and dollar labels tick live (FY-to-date). <span style="color:var(--red)">Red = borrowed</span>. Tap a flow to jump to its ticker.</div>`;
    return sec;
  }
  const L = [
    {k: 'rev_individual', n: 'Individual income tax', c: '#38d39f'}, {k: 'rev_payroll', n: 'Payroll / social insurance', c: '#2fd0d0'},
    {k: 'rev_corporate', n: 'Corporate tax', c: '#7be08f'}, {k: 'rev_customs', n: 'Customs / tariffs', c: '#c2e05a'},
    {k: ['rev_excise', 'rev_estate', 'rev_misc'], n: 'Other revenue', c: '#8fb3a5', go: 'rev_excise'},
    {k: 'deficit', n: 'Borrowing (deficit)', c: '#ff4d5e'}];
  const R = [
    {k: 'out_socsec', n: 'Social Security', c: '#5aa9ff'}, {k: 'out_medicare', n: 'Medicare', c: '#7d8bff'},
    {k: 'out_health', n: 'Medicaid & other health', c: '#a98bff'}, {k: 'out_interest', n: 'Net interest', c: '#ff8f5a'},
    {k: 'out_defense', n: 'Defense', c: '#4fc3e8'}, {k: 'out_income', n: 'Income security', c: '#6fd6ff'},
    {k: 'out_veterans', n: 'Veterans', c: '#9fb6ff'}, {k: 'OTHER', n: 'Everything else (net)', c: '#6b7a90', go: 'out_justice'}];
  const svg = document.getElementById('sk');
  const sv = k => Array.isArray(k) ? k.reduce((a, x) => a + (val(x) || 0), 0) : (val(k) || 0);
  let skLabels = [];
  function drawSankey() {
    if (!svg || T.spending?.status !== 'ok') { if (svg) svg.outerHTML = '<p class="foot">Sankey: source unavailable</p>'; return; }
    const W = Math.max(svg.parentNode.clientWidth - 20, 340), mob = W < 640, H = mob ? 620 : 520;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.style.height = H + 'px';
    const t = now(), total = val('spending', t), nw = 10, pad = mob ? 12 : 10;
    const rv = R.map(r => r.k === 'OTHER' ? 0 : sv(r.k)); const oi = R.findIndex(r => r.k === 'OTHER');
    rv[oi] = total - rv.reduce((a, b) => a + b, 0);
    const lv = L.map(l => sv(l.k));
    const usable = H - 20 - pad * (Math.max(L.length, R.length) - 1), sc = usable / total;
    const xL = 0, xM = W / 2 - nw / 2, xR = W - nw;
    let out = '', labels = [];
    // middle node
    const midH = total * sc, midY = (H - midH) / 2;
    out += `<rect x="${xM}" y="${midY}" width="${nw}" height="${midH}" fill="#e8edf5" rx="2"/>`;
    const link = (x0, y0, h, x1, y1, c, go, op) => {
      const mx = (x0 + x1) / 2;
      return `<path data-go="${go}" d="M${x0},${y0}C${mx},${y0} ${mx},${y1} ${x1},${y1}L${x1},${y1 + h}C${mx},${y1 + h} ${mx},${y0 + h} ${x0},${y0 + h}Z" fill="${c}" opacity="${op}"/>`; };
    let yl = (H - (usable + pad * (L.length - 1))) / 2, ym = midY;
    L.forEach((l, i) => { const h = lv[i] * sc;
      out += link(xL + nw, yl, h, xM, ym, l.c, l.go || l.k, l.k === 'deficit' ? .75 : .45);
      out += `<rect x="${xL}" y="${yl}" width="${nw}" height="${h}" fill="${l.c}" rx="2"/>`;
      labels.push({x: xL + nw + 6, y: yl + h / 2, a: 'start', n: l.n, k: l.k, c: l.c}); yl += h + pad; ym += h; });
    let yr = (H - (usable + pad * (R.length - 1))) / 2; ym = midY;
    R.forEach((r, i) => { const h = Math.max(rv[i] * sc, 0);
      out += link(xM + nw, ym, h, xR, yr, r.c, r.go || r.k, .45);
      out += `<rect x="${xR}" y="${yr}" width="${nw}" height="${h}" fill="${r.c}" rx="2"/>`;
      labels.push({x: xR - 6, y: yr + h / 2, a: 'end', n: r.n, k: r.k, c: r.c}); yr += h + pad; ym += h; });
    out += `<text x="${xM + nw / 2}" y="${midY - 22}" text-anchor="middle" font-size="12" font-weight="700">FEDERAL BUDGET</text><text class="sv" x="${xM + nw / 2}" y="${midY - 8}" text-anchor="middle" id="skmid"></text>`;
    for (const side of ['start', 'end']) { const g = labels.filter(b => b.a === side); const gap = mob ? 28 : 30;
      for (let j = 1; j < g.length; j++) if (g[j].y - g[j - 1].y < gap) g[j].y = g[j - 1].y + gap;
      const over = g.length ? g[g.length - 1].y + 16 - H : 0; if (over > 0) for (let j = g.length - 1; j >= 0; j--) { g[j].y -= over; if (j && g[j].y - g[j - 1].y >= gap) break; } }
    labels.forEach((b, i) => { out += `<text x="${b.x}" y="${b.y - 2}" text-anchor="${b.a}" font-size="${mob ? 11 : 12.5}" font-weight="600">${esc(b.n)}</text><text class="sv" id="skl${i}" x="${b.x}" y="${b.y + 12}" text-anchor="${b.a}"></text>`; });
    svg.innerHTML = out;
    skLabels = labels.map((b, i) => ({el: document.getElementById('skl' + i), k: b.k}));
    skLabels.mid = document.getElementById('skmid');
    svg.querySelectorAll('path').forEach(p => p.onclick = () => jump(p.dataset.go));
    document.getElementById('skn').textContent = `FY${curFY()} to date · ${T.spending.basis === 'dts' ? 'Daily Treasury Statement through ' + fmtDate(T.spending.as_of) + ', budget basis, then projected' : 'Treasury MTS projection'} · splits from MTS shares`;
  }
  function tickSankey(t) {
    if (!skLabels.length) return;
    const total = val('spending', t);
    const other = total - R.filter(r => r.k !== 'OTHER').reduce((a, r) => a + sv(r.k), 0);
    skLabels.forEach(s => { if (s.el) s.el.textContent = usd(s.k === 'OTHER' ? other : sv(s.k)); });
    if (skLabels.mid) skLabels.mid.textContent = usd(total);
  }
  drawSankey();
  setInterval(drawSankey, 5000);      // re-layout (widths) every 5 s; labels tick every frame
  addEventListener('resize', () => { clearTimeout(window._rz); window._rz = setTimeout(drawSankey, 150); });

  // ---------- modal / share / embed
  const dlg = document.getElementById('dlg');
  function openModal(slug) {
    const i = info(slug); if (!i) return;
    const base = location.href.split('#')[0].replace(/[^/]*$/, '');
    const share = i.historical ? `${base}national-debt-by-year/#fy${String(i.as_of || '').replace('FY', '')}` : `${base}t/${slug}.html`;
    const embed = `<iframe src="${base}widget.html?t=${slug}" width="360" height="150" style="border:0" loading="lazy" title="${esc(i.label)} — live"></iframe><br><a href="${base}?ref=embed" rel="nofollow">Every Debt Clock</a>`;
    const v = i.validation;
    dlg.innerHTML = `<h3>${esc(i.label)}</h3><div class="big num" id="mv">—</div>
      <div class="meta">${badges(i)}</div>
      ${isUSD(i) && !NOPP.has(slug) ? `<div class="pp"><div><span class="l" title="${esc(PPB)}">Per person (proj. pop.)</span><span class="num" id="m1"></span></div><div><span class="l">Per tax return filed</span><span class="num" id="m2"></span></div></div>` : ''}
      <p><b>Method.</b> ${esc(i.method || '')}</p>
      ${mathHTML(slug, i)}
      ${i.rate ? `<p><b>Rate.</b> ${rateTxt(i.rate)}</p>` : ''}
      ${i.source ? `<p><b>Source.</b> <a href="${esc(i.source)}" target="_blank" rel="noopener">${esc(i.source_name || i.source)}</a>${i.as_of ? ' · official as of ' + esc(fmtDate(i.as_of)) : ''}</p>` : ''}
      ${v && v.last_error_pct != null ? `<p><b>Check.</b> Last projection vs ${esc(v.against)}: ${(+v.last_error_pct).toFixed(3)}% (threshold ±${v.threshold_pct}%)${v.mean_abs_error_pct != null ? `; average |error| over ${v.n} days ${v.mean_abs_error_pct.toFixed(3)}%` : ''}. ${esc(v.note || '')}</p>` : ''}
      <p><b>Share:</b> <a href="${share}">${share}</a></p>
      <p class="shr"><button id="cp">Copy link</button><a class="btn" target="_blank" rel="noopener" href="https://x.com/intent/post?text=${encodeURIComponent(i.label + ': ' + (i.kind === 'usd' ? short(get(slug, now())) : i.kind === 'pct' ? pct(get(slug, now()), 2) : nf0.format(get(slug, now()))) + ' and ticking (official data, checked daily)')}&url=${encodeURIComponent(share)}">Post on X</a><a class="btn" href="${base}og/${slug}.png" target="_blank">Share image</a></p>
      <p><b>Embed:</b></p><textarea readonly>${esc(embed)}</textarea>
      <p><button id="cl">Close</button></p>`;
    const mv = dlg.querySelector('#mv'), m1 = dlg.querySelector('#m1'), m2 = dlg.querySelector('#m2');
    modalTick = t => { const x = get(slug, t); mv.textContent = i.kind === 'pct' ? pct(x, 5) : i.kind === 'count' ? nf0.format(x) : usd(x, 2);
      if (m1) { m1.textContent = ppf(x / pop(t)); m2.textContent = ppf(x / tax()); }
      const mf = dlg.querySelector('#mf');
      if (mf && !i.derived) { const dtt = Math.min(t, i.freeze_t || Infinity) - i.t0; mf.textContent = `${fv(i, i.base)} + ${i.kind === 'count' ? (+i.rate).toFixed(6) : usd(i.rate, 4)} × ${nf0.format(Math.round(dtt))} s = ${fv(i, i.base + i.rate * dtt)}`; }
      if (i.derived) { dlg.querySelectorAll('[data-c]').forEach(e => { const c = e.dataset.c; e.textContent = fv(T[c] || {}, val(c, t)); });
        if (mf) mf.textContent = '= ' + fv(i, x);
        const md = dlg.querySelector('#mdays'); if (md) md.textContent = (x / T.debt_subject_limit.rate / 86400).toFixed(1); } };
    dlg.querySelector('#cl').onclick = () => dlg.close();
    dlg.querySelector('#cp').onclick = () => navigator.clipboard?.writeText(share);
    history.replaceState(null, '', '#t=' + slug);
    dlg.showModal();
  }
  let modalTick = null;
  const ct = ts => new Date(ts * 1000).toLocaleString('en-US', {month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', second: '2-digit', timeZone: 'America/Chicago'}) + ' CT';
  const fv = (i, x) => x == null ? '—' : i.kind === 'pct' ? (+x).toFixed(3) + '%' : i.kind === 'count' ? nf0.format(x) : usd(x, 0);
  const DF = {   // derived formulas: [text, components]
    debt_gdp_now: ['debt_total ÷ gdp × 100', ['debt_total', 'gdp']],
    deficit_gdp_now: ['(spending TTM − revenue TTM) ÷ gdp × 100', ['gdp']],
    interest_share: ['out_interest ÷ revenue × 100', ['out_interest', 'revenue']],
    interest_annual: ['debt_total × avg rate on all interest-bearing debt', ['debt_total', 'rate_all']],
    interest_per_day: ['debt_total × rate_all ÷ 365.25', ['debt_total', 'rate_all']],
    interest_per_sec: ['debt_total × rate_all ÷ 31,557,600 s', ['debt_total', 'rate_all']],
    interest_since_open: ['debt_total × rate_all × seconds since you opened ÷ 31,557,600', ['debt_total', 'rate_all']],
    limit_headroom: ['debt_limit − debt_subject_limit', ['debt_limit', 'debt_subject_limit']],
    fed_share_public: ['fed_treasuries ÷ debt_public × 100', ['fed_treasuries', 'debt_public']],
    m2_debt_ratio: ['debt_total ÷ m2 × 100', ['debt_total', 'm2']],
    debt_per_household: ['debt_total ÷ households', ['debt_total', 'households']],
  };
  function mathHTML(slug, i) {
    if (i.derived) {
      const f = DF[slug]; if (!f) return '';
      return `<div class="math"><b>Show the math</b><p>${esc(i.label)} = ${esc(f[0])}</p><table>${f[1].map(c => `<tr><td>${esc(T[c]?.label || c)}</td><td class="num" data-c="${c}">—</td></tr>`).join('')}</table>
        ${slug === 'limit_headroom' && T.debt_subject_limit?.rate ? `<p>Days to the limit = headroom ÷ ${rateTxt(T.debt_subject_limit.rate)} ÷ 86,400 = <span class="num" id="mdays">—</span> days (our projection, before extraordinary measures).</p>` : ''}
        <p class="num" id="mf">—</p>${f[1].map(c => T[c]?.calc ? `<p class="small">${esc(T[c].label)}: tap its own tile for its inputs.</p>` : '').join('')}</div>`;
    }
    if (i.status !== 'ok') return '';
    const c = i.calc || {}; let inp = '';
    const pt = (p) => `${esc(fmtDate(p[0]))}: ${fv(i, p[1])}`;
    if (c.type === 'ols') {
      inp = `<p>Rate = least-squares slope through ${c.n} official values, ${esc(c.window)}. First: ${pt(c.first)} · last: ${pt(c.last)}. Slope = ${usd(c.slope, 2)}/s (straight-line first→last would be ${usd((c.last[1] - c.first[1]) / Math.max(1, (eodTs(c.last[0]) - eodTs(c.first[0]))), 2)}/s).</p>`
        + (c.points ? `<table>${c.points.map(p => `<tr><td>${esc(fmtDate(p[0]))}</td><td class="num">${fv(i, p[1])}</td></tr>`).join('')}</table>` : '')
        + (c.context_1y ? `<p><b>Context:</b> 1-year average rate ${usd(c.context_1y.rate, 0)}/s (${pt(c.context_1y.from)} → ${pt(c.context_1y.to)}). We tick at the 90-day trend, not this.</p>` : '');
    } else if (c.type === 'dts_ratio') {
      inp = `<p>Budget/cash ratio ${c.ratio.toFixed(4)} = ${esc(c.ratio_src[0])} ${usd(c.ratio_src[1], 0)} ÷ ${esc(c.ratio_src[2])} ${usd(c.ratio_src[3], 0)}.</p>
        <p>DTS cash (FYTD, excl. debt issues/redemptions): ${pt(c.cash_from)} → ${pt(c.cash_to)}; 90-day cash flow ${usd(c.cash_flow_90d, 0)} over ${nf0.format(c.seconds)} s.</p>
        <p>Rate = ${c.ratio.toFixed(4)} × ${usd(c.cash_flow_90d, 0)} ÷ ${nf0.format(c.seconds)} s = ${usd(i.rate, 2)}/s.</p>`
        + (c.base_parts?.mts_month ? `<p>Base = MTS FYTD through ${esc(fmtDate(c.base_parts.mts_month))} ${usd(c.base_parts.mts_fytd, 0)} + ${c.ratio.toFixed(4)} × (DTS cash ${usd(c.base_parts.dts_cash_latest, 0)} − ${usd(c.base_parts.dts_cash_at_month_end, 0)}).</p>` : `<p>Base = ${c.ratio.toFixed(4)} × DTS cash ${usd(c.base_parts?.dts_cash_latest, 0)}.</p>`);
    } else if (c.type === 'share') {
      const P = T[c.parent];
      inp = `<p>Share of ${esc(P?.label || c.parent)} = ${(c.share * 100).toFixed(3)}% (${esc(c.basis || 'MTS')}, MTS lines ${esc((c.mts_lines || []).join(', '))}). Base = ${(c.share * 100).toFixed(3)}% × ${usd(P?.base, 0)}; rate = ${(c.share * 100).toFixed(3)}% × ${usd(P?.rate, 2)}/s = ${usd(i.rate, 2)}/s.</p>`;
    } else if (c.type === 'difference') {
      inp = `<p>${esc(T[c.of[0]].label)} − ${esc(T[c.of[1]].label)}: base ${usd(T[c.of[0]].base, 0)} − ${usd(T[c.of[1]].base, 0)}; rate ${usd(T[c.of[0]].rate, 2)} − ${usd(T[c.of[1]].rate, 2)} = ${usd(i.rate, 2)}/s.</p>`;
    } else if (c.type === 'two_point') {
      const sec = eodTs(c.to[0]) - eodTs(c.from[0]);
      inp = `<p>Rate = 90-day change ÷ seconds: ${pt(c.from)} → ${pt(c.to)}; flow ${usd(c.flow, 0)} ÷ ${nf0.format(sec)} s = ${usd(i.rate, 2)}/s. ${esc(c.note || '')}</p>`;
    } else if (c.type === 'ttm') {
      inp = `<p>Rate = last 12 months ÷ 31,557,600 s = ${usd(c.ttm, 0)} ÷ 31,557,600 = ${usd(i.rate, 2)}/s.</p><table>${c.months.map(m => `<tr><td>${esc(fmtDate(m[0]))}</td><td class="num">${usd(m[1], 0)}</td></tr>`).join('')}</table>`;
    } else if (c.type === 'anchor_rate') {
      inp = `<p>Base: ${pt(c.base_src)} (<a href="${esc(c.base_src[2])}" target="_blank" rel="noopener">source file</a>). Rate: ${esc(c.rate_src || '')}${c.alt_rate_v2025_annual ? `. (At V2025's own latest annual change, ${nf0.format(c.alt_rate_v2025_annual)}/yr, today would be ${nf0.format(i.base + c.alt_rate_v2025_annual / 31557600 * (now() - i.t0))}.)` : ''}</p>`;
    } else if (c.type === 'fixed' || !i.rate) {
      inp = `<p>Fixed official value: ${fv(i, i.base)}${i.as_of ? ' (' + esc(fmtDate(i.as_of)) + ')' : ''}. It does not tick; it changes only when the source publishes a new figure.</p>`;
    }
    return `<div class="math"><b>Show the math</b><table>
      <tr><td>Base (official)</td><td class="num">${fv(i, i.base)}</td></tr>
      <tr><td>t0</td><td>${esc(ct(i.t0))}</td></tr>
      <tr><td>Rate per second</td><td class="num">${i.kind === 'count' ? (+i.rate).toFixed(6) : i.kind === 'pct' ? (+i.rate).toExponential(3) : usd(i.rate, 4)}</td></tr></table>
      ${inp}<p><b>Now</b> = base + rate × (now − t0) = <span class="num" id="mf">—</span></p></div>`;
  }
  dlg.addEventListener('close', () => { modalTick = null; history.replaceState(null, '', location.pathname); });
  function jump(slug) { const e = document.getElementById('t-' + slug); if (!e) return; e.scrollIntoView({behavior: 'smooth', block: 'center'}); e.classList.remove('hl'); void e.offsetWidth; e.classList.add('hl'); }
  const h = location.hash.match(/t=([\w]+)/); if (h) setTimeout(() => { jump(h[1]); openModal(h[1]); }, 300);

  // ---------- animation loop
  function frame() { const t = now(); for (const f of live) f(t); tickSankey(t); if (modalTick) modalTick(t); requestAnimationFrame(frame); }
  requestAnimationFrame(frame);
})();
