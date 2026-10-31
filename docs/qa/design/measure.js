// Design measurements (round 5, C6). Assessment B of the impeccable critique: computed styles on
// the running app, not opinions. Usage:
//   NODE_PATH=$(npm root -g) node docs/qa/design/measure.js [label] [baseUrl] [only] [rentBaseUrl]
// The rent result screens (r1-r6) need a second instance: docs/qa/design/rent_app.py on 8502.
//   label = before | after (output: docs/qa/design/measure-<label>.json + .md, shots in <label>/)
//   only  = comma list of screen ids to run (default: all)
// Needs the app running (default http://127.0.0.1:8501) against the published DB, with no
// GITHUB_TOKEN / ANTHROPIC_API_KEY in the app's environment (session-only favourites; the
// «Ρώτα με» panel does not render without a key).
//
// Per screen and viewport (390×844 phone, 1280×900 desktop) it records:
//  - scrollWidth vs innerWidth and elements whose right edge passes the viewport;
//  - every visible interactive element (button, a, [role=button|radio|option|tab|switch|checkbox],
//    summary, input, select, textarea, label[for]) with its box and whether it is < 44 px tall;
//    a label[for] whose control is visible is skipped (the control is the measured target);
//    visually hidden native inputs (≤ 2 px or opacity 0, e.g. Streamlit's radio <input>) are
//    skipped because their visible label is the target and is measured itself;
//  - every visible text node: font-size, colour, the composited background behind it (nearest
//    non-transparent ancestors, alpha-blended), WCAG contrast; flags < 4.5:1 (< 3:1 for large
//    text: ≥ 24 px, or ≥ 18.66 px and bold) and font-size < 11 px. Material Symbols ligature
//    icons are counted separately (they are glyphs, not words);
//  - the sets of distinct font sizes (text), border radii, box-shadows, margins and paddings in
//    use on visible elements of the main area and the sidebar;
//  - keyboard focus: a real Tab walk (up to 60 stops); each focused control must show a ring
//    (outline or box-shadow) on itself or one of its three nearest ancestors.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const LABEL = process.argv[2] || 'before';
const BASE = process.argv[3] || 'http://127.0.0.1:8501';
const ONLY = process.argv[4] ? process.argv[4].split(',') : null;
const DIR = path.join('docs', 'qa', 'design');
const SHOTS = path.join(DIR, LABEL);
fs.mkdirSync(SHOTS, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...a) => console.log(...a);

async function settle(page, extra = 800) {
  await page.waitForLoadState('networkidle').catch(() => {});
  await sleep(1500);
  for (let i = 0; i < 80; i++) {
    if (!(await page.locator('[data-testid="stStatusWidget"]').count())) break;
    await sleep(500);
  }
  await sleep(extra);
}
const btn = (page, name, exact = true) => page.getByRole('button', { name, exact }).first();
async function tap(page, name, exact = true) { await btn(page, name, exact).click(); await settle(page); }
async function pill(page, label) {
  await page.locator('[data-testid="stMain"]').getByRole('radio', { name: label, exact: true }).first().click();
  await settle(page);
}
async function openSidebar(page) {
  const open = page.locator('[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapsedControl"] button').first();
  if (await open.count() && await open.isVisible().catch(() => false)) { await open.click().catch(() => {}); await sleep(900); }
}
async function closeSidebar(page) {
  const x = page.locator('[data-testid="stSidebarCollapseButton"] button, [data-testid="stSidebarHeader"] button').first();
  if (await x.count() && await x.isVisible().catch(() => false)) { await x.click().catch(() => {}); await sleep(800); }
}
async function sidebarPage(page, phone, name) {
  if (phone) await openSidebar(page);
  await page.locator('[data-testid="stSidebar"]').getByText(name, { exact: true }).first().click();
  await settle(page);
  if (phone) await closeSidebar(page);
}

// ---- the in-page measurement ---------------------------------------------------------------
function measureInPage() {
  const W = window.innerWidth;
  const parse = (c) => {
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return [0, 0, 0, 0];
    const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
  };
  const lum = ([r, g, b]) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const over = (top, under) => { // alpha-composite top over an opaque colour
    const a = top[3];
    return [0, 1, 2].map((i) => top[i] * a + under[i] * (1 - a)).concat(1);
  };
  const bgCache = new Map();
  function backgroundOf(el) { // composited background colour behind el
    if (!el || el === document.documentElement) return [255, 255, 255, 1];
    if (bgCache.has(el)) return bgCache.get(el);
    const cs = getComputedStyle(el);
    const c = parse(cs.backgroundColor);
    let out;
    if (c[3] >= 0.999) out = c;
    else {
      const under = backgroundOf(el.parentElement);
      out = c[3] > 0 ? over(c, under) : under;
    }
    bgCache.set(el, out);
    return out;
  }
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    // content of a closed <details> (Streamlit expanders, the card's «Από πού βγαίνουν») keeps
    // a layout box in Chromium; checkVisibility() knows it is not rendered
    if (el.checkVisibility && !el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return false;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || Number(cs.opacity) === 0) return false;
    let p = el;
    while (p && p !== document.body) { // hidden ancestor (closed expander, collapsed sidebar)
      const s = getComputedStyle(p);
      if (s.display === 'none' || s.visibility === 'hidden' || Number(s.opacity) === 0) return false;
      p = p.parentElement;
    }
    if (r.right < -5 || r.left > W + 5) return false; // off-canvas drawer
    // visually hidden (screen-reader-only) wrappers: 1 px boxes that clip their content
    for (let a = el.parentElement, i = 0; a && i < 3; a = a.parentElement, i++) {
      const ar = a.getBoundingClientRect(), as = getComputedStyle(a);
      if (ar.width <= 1 && ar.height <= 1 && as.overflow === 'hidden') return false;
    }
    return true;
  };
  const desc = (el) => {
    const tid = el.closest('[data-testid]');
    const cls = [...el.classList].filter((c) => c.startsWith('hg-')).join('.');
    const txt = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 50);
    return `${el.tagName.toLowerCase()}${el.getAttribute('role') ? '[role=' + el.getAttribute('role') + ']' : ''}${cls ? '.' + cls : ''} in ${tid ? tid.getAttribute('data-testid') : '-'} «${txt}»`;
  };
  const roots = [...document.querySelectorAll('[data-testid="stMain"], [data-testid="stSidebar"]')];
  const inRoots = (el) => roots.some((r) => r.contains(el));

  // overflow
  const wide = [...document.querySelectorAll('[data-testid="stMain"] *')]
    .filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.right > W + 1 && visible(e); })
    .slice(0, 8).map((e) => desc(e) + ' right=' + Math.round(e.getBoundingClientRect().right));

  // interactive targets
  const SEL = 'button, a[href], [role=button], [role=radio], [role=option], [role=tab], [role=switch], [role=checkbox], summary, input, select, textarea, label[for]';
  const seen = new Set();
  const targets = [];
  for (const el of document.querySelectorAll(SEL)) {
    if (!inRoots(el) && !el.closest('[data-baseweb="popover"]')) continue;
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    if (el.tagName === 'INPUT' && (r.width <= 2 || r.height <= 2)) continue;
    // a <label for=…> whose control is visible is not a separate target: the control is
    // measured itself (WCAG 2.5.8 «equivalent control»)
    if (el.tagName === 'LABEL' && el.htmlFor) {
      const ctl = document.getElementById(el.htmlFor);
      if (ctl && visible(ctl) && ctl.getBoundingClientRect().height > 2) continue;
    }
    // a checkbox / toggle <input> wrapped by its <label>: the label is the touch target
    const wrapLabel = el.tagName === 'INPUT' && el.closest('label');
    if (wrapLabel) {
      const lr = wrapLabel.getBoundingClientRect();
      seen.add(el);
      targets.push({ what: desc(wrapLabel) + ' (label of input)', h: Math.round(lr.height * 10) / 10, w: Math.round(lr.width), small: lr.height < 44 });
      continue;
    }
    // nested target inside a measured one (e.g. <p> in a button is not selected; a <button> in
    // a [role=radio] wrapper is) — keep the outermost box only
    let anc = el.parentElement, nested = false;
    while (anc) { if (seen.has(anc)) { nested = true; break; } anc = anc.parentElement; }
    seen.add(el);
    if (nested) continue;
    targets.push({ what: desc(el), h: Math.round(r.height * 10) / 10, w: Math.round(r.width), small: r.height < 44 });
  }

  // text nodes
  const texts = [];
  let icons = 0;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const fontSizes = {};
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const s = n.nodeValue.trim();
    if (!s) continue;
    const el = n.parentElement;
    if (!el || !inRoots(el) || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(el.tagName)) continue;
    if (!visible(el)) continue;
    const cs = getComputedStyle(el);
    if (/Material Symbols/i.test(cs.fontFamily)) { icons++; continue; }
    const fg = parse(cs.color);
    const bg = backgroundOf(el);
    const fgc = fg[3] < 1 ? over(fg, bg) : fg;
    const size = parseFloat(cs.fontSize);
    const bold = Number(cs.fontWeight) >= 700;
    const large = size >= 24 || (size >= 18.66 && bold);
    const cr = Math.round(ratio(fgc, bg) * 100) / 100;
    const need = large ? 3 : 4.5;
    fontSizes[size] = (fontSizes[size] || 0) + 1;
    texts.push({ t: s.slice(0, 40), decorative: /^[·•|–—\-]+$/.test(s), size, weight: cs.fontWeight, color: cs.color, bg: `rgb(${bg.slice(0, 3).map(Math.round).join(',')})`, contrast: cr, fail: cr < need, tiny: size < 11, where: desc(el).split(' «')[0] });
  }

  // distinct design values on visible elements
  const radii = {}, shadows = {}, margins = {}, paddings = {};
  const bump = (o, k) => { o[k] = (o[k] || 0) + 1; };
  for (const root of roots) for (const el of root.querySelectorAll('*')) {
    if (!visible(el)) continue;
    const cs = getComputedStyle(el);
    if (cs.borderTopLeftRadius !== '0px') bump(radii, cs.borderRadius);
    if (cs.boxShadow !== 'none') bump(shadows, cs.boxShadow);
    for (const side of ['Top', 'Right', 'Bottom', 'Left']) {
      const m = cs['margin' + side], p = cs['padding' + side];
      if (m !== '0px') bump(margins, m);
      if (p !== '0px') bump(paddings, p);
    }
  }
  return {
    scrollWidth: document.documentElement.scrollWidth, innerWidth: W, wide,
    targets, texts, icons, fontSizes, radii, shadows, margins, paddings,
  };
}

// focus ring check: a real Tab walk, the way a keyboard user moves. Each focused control (in
// the main area or the sidebar) is checked for a visible ring on itself or on one of its three
// nearest ancestors (Streamlit draws input rings on a wrapper): a non-none outline with a
// visible colour, or a box-shadow.
function focusNow() {
  const el = document.activeElement;
  if (!el || el === document.body) return null;
  const inside = el.closest('[data-testid="stMain"], [data-testid="stSidebar"]');
  if (!inside) return { outside: true };
  if (!el.dataset.mid) el.dataset.mid = String(Math.random()).slice(2);
  const shows = (e) => {
    const cs = getComputedStyle(e);
    const outline = cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0 && !/rgba\(.*, 0\)$/.test(cs.outlineColor);
    return outline || cs.boxShadow !== 'none';
  };
  let ring = false;
  for (let e = el, i = 0; e && i < 4; e = e.parentElement, i++) if (shows(e)) { ring = true; break; }
  const txt = (el.innerText || el.getAttribute('aria-label') || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 40);
  return { id: el.dataset.mid, what: `${el.tagName.toLowerCase()}${el.getAttribute('role') ? '[role=' + el.getAttribute('role') + ']' : ''} «${txt}»`, ring };
}
async function focusWalk(page, n = 60) {
  await page.evaluate(() => { if (document.activeElement) document.activeElement.blur(); });
  const out = [], seen = new Set();
  let outside = 0;
  for (let i = 0; i < n + 20 && out.length < n; i++) {
    await page.keyboard.press('Tab');
    const r = await page.evaluate(focusNow);
    if (!r) continue;
    if (r.outside) { if (++outside > 20) break; continue; }
    if (seen.has(r.id)) break;
    seen.add(r.id); out.push(r);
  }
  return out;
}

// ---- screens ---------------------------------------------------------------------------------
// Each step leaves the page on a state to measure. Steps run in order within one session per
// viewport; a failing step is logged and the remaining screens still run.
const SCREENS = [
  ['a0-guide-mode', async () => {}],
  ['a1-guide-budget', async (p) => tap(p, 'Να αγοράσω')],
  ['a2-guide-goal', async (p) => tap(p, '300 χιλ. €')],
  ['a3-guide-where', async (p) => tap(p, 'Απόδοση ενοικίου')],
  ['a4-guide-kind', async (p) => tap(p, 'Κοντά σε μετρό/ΗΣΑΠ')],
  ['a5-guide-result', async (p) => {
    await p.getByText('Νεόδμητο (έως 10 ετών)', { exact: true }).first().click(); await settle(p);
    await p.getByRole('button', { name: /^Η πρότασή μου/ }).first().click(); await settle(p, 2000);
  }],
  ['a6-guide-card-expander', async (p) => {
    const s = p.locator('summary', { hasText: 'Από πού βγαίνουν' }).first();
    await s.scrollIntoViewIfNeeded(); await s.click(); await settle(p, 600);
  }],
  ['c1-areas', async (p) => pill(p, 'Περιοχές')],
  ['d0-search', async (p) => pill(p, 'Αναζήτηση')],
  ['d1-listing', async (p) => { await p.getByRole('button', { name: 'Λεπτομέρειες' }).first().click(); await settle(p, 1500); }],
  ['b1-map', async (p) => { await pill(p, 'Χάρτης'); await sleep(2500); }],
  ['h1-favourites', async (p) => pill(p, 'Αγαπημένα')],
  ['h2-compare', async (p) => pill(p, 'Σύγκριση')],
  ['s1-saved-searches', async (p, phone) => sidebarPage(p, phone, 'Αποθηκευμένες αναζητήσεις')],
  ['e0-sidebar', async (p, phone) => { if (phone) await openSidebar(p); }],
];
// rent flow on the QA instance (docs/qa/design/rent_app.py: the test fixture's 36 rentals)
const RENT_SCREENS = [
  ['r1-rent-budget-fixture', async (p) => tap(p, 'Να νοικιάσω')],
  ['r2-rent-beds-fixture', async (p) => tap(p, '800 €')],
  ['r3-rent-where-fixture', async (p) => tap(p, '2')],
  ['r4-rent-kind-fixture', async (p) => tap(p, 'Όλες οι περιοχές')],
  ['r5-rent-result-fixture', async (p) => {
    await p.getByRole('button', { name: /^Η πρότασή μου/ }).first().click(); await settle(p, 1500);
  }],
  ['r6-rent-card-expander-fixture', async (p) => {
    const s = p.locator('summary', { hasText: 'Από πού βγαίνουν' }).first();
    await s.scrollIntoViewIfNeeded(); await s.click(); await settle(p, 600);
  }],
];
// rent, real DB (fresh session): no rental rows are published yet, so the flow shows its
// «coming» state
const R0_SCREENS = [['r0-rent-empty-realdb', async (p) => {
  const b = btn(p, 'Να νοικιάσω');  // disabled while no rental is stored (#90): step 0 is the state
  if (await b.isEnabled()) await tap(p, 'Να νοικιάσω');
}]];
const BASE2 = process.argv[5] || 'http://127.0.0.1:8502';

async function screenshot(page, file, phone) {
  const vp = page.viewportSize();
  const full = await page.evaluate((cap) => Math.min(cap, Math.max(document.documentElement.scrollHeight,
    ...[...document.querySelectorAll('[data-testid="stMain"]')].map((e) => e.scrollHeight))), phone ? 4200 : 3000);
  await page.setViewportSize({ width: vp.width, height: Math.max(vp.height, full) });
  await sleep(1000);
  await page.screenshot({ path: file, fullPage: false });
  await page.setViewportSize(vp); await sleep(400);
}

async function run(browser, phone, base = BASE, screens = SCREENS) {
  const [w, h] = phone ? [390, 844] : [1280, 900];
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, hasTouch: phone, isMobile: phone });
  const page = await ctx.newPage();
  await page.goto(base, { waitUntil: 'domcontentloaded' }); await settle(page);
  const res = {};
  for (const [id, step] of screens) {
    const key = `${id}@${w}`;
    try { await step(page, phone); } catch (e) { log('STEP FAIL', key, e.message.split('\n')[0]); res[key] = { error: e.message.split('\n')[0] }; continue; }
    if (ONLY && !ONLY.includes(id)) continue;
    await settle(page, 300);
    const m = await page.evaluate(measureInPage);
    m.focus = await focusWalk(page);
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    await screenshot(page, path.join(SHOTS, `${id}-${w}.png`), phone);
    res[key] = m;
    const small = m.targets.filter((t) => t.small).length;
    log(key, 'scrollWidth', m.scrollWidth, 'targets', m.targets.length, '<44', small,
      'contrast-fail', m.texts.filter((t) => t.fail).length, '<11px', m.texts.filter((t) => t.tiny).length,
      'sizes', Object.keys(m.fontSizes).length, 'no-ring', m.focus.filter((f) => !f.ring).length);
    if (id === 'e0-sidebar' && phone) await closeSidebar(page);
  }
  await ctx.close();
  return res;
}

function summarize(all) {
  const rows = [];
  const allSizes = new Set(), allRadii = new Set(), allShadows = new Set(), allSpace = new Set();
  for (const [key, m] of Object.entries(all)) {
    if (m.error) { rows.push(`| ${key} | step failed: ${m.error.replace(/\|/g, '/')} |||||||||`); continue; }
    Object.keys(m.fontSizes).forEach((s) => allSizes.add(Number(s)));
    Object.keys(m.radii).forEach((s) => allRadii.add(s));
    Object.keys(m.shadows).forEach((s) => allShadows.add(s));
    [...Object.keys(m.margins), ...Object.keys(m.paddings)].forEach((s) => allSpace.add(s));
    const small = m.targets.filter((t) => t.small).length;
    rows.push(`| ${key} | ${m.scrollWidth}/${m.innerWidth} | ${m.targets.length} | ${small} | ${m.texts.length} | ${m.texts.filter((t) => t.fail).length} (${m.texts.filter((t) => t.fail && !t.decorative).length}) | ${m.texts.filter((t) => t.tiny).length} | ${Object.keys(m.fontSizes).length} | ${Object.keys(m.radii).length} | ${Object.keys(m.shadows).length} | ${m.focus.filter((f) => !f.ring).length}/${m.focus.length} |`);
  }
  const offScale = [...allSpace].filter((v) => { const n = parseFloat(v); return v.endsWith('px') && Math.round(n) % 4 !== 0; });
  return [
    `# measure.js — ${LABEL}`, '',
    `Generated ${new Date().toISOString()} against ${BASE}. Per screen@width: scrollWidth/innerWidth, interactive targets, targets < 44 px tall, visible text nodes, text below WCAG AA contrast (in brackets: excluding decorative separators such as «·»), text < 11 px, distinct font sizes, distinct border radii, distinct box-shadows, controls without a :focus-visible change / controls checked.`, '',
    '| screen | scrollWidth | targets | < 44 px | text nodes | contrast fail (words) | < 11 px | font sizes | radii | shadows | no focus ring |',
    '|---|---|---|---|---|---|---|---|---|---|---|',
    ...rows, '',
    `**Across all screens:** ${allSizes.size} distinct font sizes (${[...allSizes].sort((a, b) => a - b).join(', ')} px); ${allRadii.size} distinct radii; ${allShadows.size} distinct shadows; ${allSpace.size} distinct margin/padding values, ${offScale.length} off the 4-pt scale (${offScale.slice(0, 20).join(', ')}).`,
    '',
  ].join('\n');
}

(async () => {
  const browser = await chromium.launch();
  // VIEWPORTS=390 runs the phone only (quick iteration); the reported runs use both
  const phoneOnly = process.env.VIEWPORTS === '390';
  const run2 = async (phone, ...rest) => (!phone && phoneOnly ? {} : run(browser, phone, ...rest));
  const all = { ...(await run2(true)), ...(await run2(false)),
    ...(await run2(true, BASE, R0_SCREENS)), ...(await run2(false, BASE, R0_SCREENS)) };
  const up = await fetch(BASE2).then((r) => r.ok).catch(() => false);
  if (up) Object.assign(all, await run2(true, BASE2, RENT_SCREENS), await run2(false, BASE2, RENT_SCREENS));
  else log('rent QA instance not running at', BASE2, '— r1-r6 skipped');
  await browser.close();
  const out = path.join(DIR, `measure-${LABEL}.json`);
  if (ONLY && fs.existsSync(out)) Object.assign(all, { ...JSON.parse(fs.readFileSync(out, 'utf8')), ...all });
  fs.writeFileSync(out, JSON.stringify(all, null, 1));
  fs.writeFileSync(path.join(DIR, `measure-${LABEL}.md`), summarize(all));
  log('wrote', path.join(DIR, `measure-${LABEL}.json`));
})();
