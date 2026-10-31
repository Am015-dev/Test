// Round-4 C3 (finish) screenshots: copy of docs/qa/shots.js with the step-4 button label fixed. Usage:
//   NODE_PATH=$(npm root -g) node docs/qa/finish/shots.js [outDir] [baseUrl]
// Needs the app running (default http://127.0.0.1:8501) against the published DB, with no
// GITHUB_TOKEN / ANTHROPIC_API_KEY in the app's environment. Writes <nn>-<name>-<viewport>.png
// (+ .txt page text) and overflow.json (horizontal overflow per shot) into outDir.
// Navigation: the pills at the top of every page (app.py SHORT_NAV): the home pill is the
// guide's title («Οδηγός»); NAV keys are guide.TITLE, «Πού να αγοράσω», «Αναζήτηση»,
// «Χάρτης», «Αγαπημένα», «Σύγκριση». The pill for «Πού να αγοράσω» reads «Περιοχές».
const { chromium } = require('playwright');
const fs = require('fs');
const OUT = process.argv[2] || 'docs/qa/final';
const BASE = process.argv[3] || 'http://127.0.0.1:8501';
// Sign-in is hidden without GITHUB_TOKEN (account.login_ui). For flow (e) a second app instance
// (BASE2) runs the same code with the gist stubbed in memory (docs/qa/final/qa_app.py).
const BASE2 = process.argv[5] || 'http://127.0.0.1:8502';
const PILL = { 'Οδηγός': 'Οδηγός', 'Πού να αγοράσω': 'Περιοχές', 'Αναζήτηση': 'Αναζήτηση',
  'Χάρτης': 'Χάρτης', 'Αγαπημένα': 'Αγαπημένα', 'Σύγκριση': 'Σύγκριση' };
fs.mkdirSync(OUT, { recursive: true });
// merge with earlier partial runs (flows can be run one at a time: node shots.js out base a,b)
const overflow = fs.existsSync(`${OUT}/overflow.json`) ? JSON.parse(fs.readFileSync(`${OUT}/overflow.json`, 'utf8')) : {};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...a) => console.log(...a);

async function settle(page, extra = 800) {
  await page.waitForLoadState('networkidle').catch(() => {});
  await sleep(1800);
  for (let i = 0; i < 80; i++) { // Streamlit's running indicator
    if (!(await page.locator('[data-testid="stStatusWidget"]').count())) break;
    await sleep(500);
  }
  await sleep(extra);
}
async function metrics(page) {
  return page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth,
    inner: Math.max(0, ...[...document.querySelectorAll('[data-testid="stMain"], section.main, .stMain')].map((e) => e.scrollWidth)),
    wide: [...document.querySelectorAll('[data-testid="stMain"] *')].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.right > window.innerWidth + 1; }).slice(0, 5).map((e) => e.tagName + '.' + String(e.className).slice(0, 40) + ' right=' + Math.round(e.getBoundingClientRect().right)),
    text: document.body.innerText,
  }));
}
// full: grow the viewport to the content height (Streamlit scrolls an inner container).
async function shot(page, name, { full = true, wait = true } = {}) {
  if (wait) await settle(page);
  const m = await metrics(page);
  overflow[name] = { overflow: m.scrollWidth > m.innerWidth, scrollWidth: m.scrollWidth, innerWidth: m.innerWidth, mainScrollWidth: m.inner, wideElements: m.wide };
  fs.writeFileSync(`${OUT}/${name}.txt`, m.text);
  if (full) {
    const vp = page.viewportSize();
    const h = await page.evaluate(() => Math.min(14000, Math.max(document.documentElement.scrollHeight,
      ...[...document.querySelectorAll('[data-testid="stMain"], .stMain, section.main')].map((e) => e.scrollHeight))));
    await page.setViewportSize({ width: vp.width, height: Math.max(vp.height, h) });
    await sleep(1200);
    await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
    overflow[name].pageHeight = h;
    await page.setViewportSize(vp); await sleep(500);
  } else await page.screenshot({ path: `${OUT}/${name}.png` });
  log(name, (overflow[name].overflow || m.wide.length) ? 'OVERFLOW ' + m.wide.join(' | ') : 'ok', m.scrollWidth, m.innerWidth);
}
const btn = (page, name, exact = true) => page.getByRole('button', { name, exact }).first();
async function tap(page, name, exact = true) { await btn(page, name, exact).click(); await settle(page); }
async function nav(page, label) { // st.pills render as role=radio buttons
  await page.locator('[data-testid="stMain"]').getByRole('radio', { name: PILL[label], exact: true }).first().click(); await settle(page); }
async function newPage(browser, w, h, phone) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, hasTouch: phone, isMobile: phone });
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: 'domcontentloaded' }); await settle(page);
  return [ctx, page];
}
async function openSidebar(page) { // phone: the sidebar is a drawer
  const open = page.locator('[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapsedControl"] button, [data-testid="collapsedControl"]').first();
  if (await open.count()) { await open.click().catch(() => {}); await sleep(900); }
}
async function closeSidebar(page) {
  const x = page.locator('[data-testid="stSidebarCollapseButton"] button, [data-testid="stSidebarHeader"] button').first();
  if (await x.count()) { await x.click().catch(() => {}); await sleep(800); }
}

// ---- (a) the guide: one shot per step, result, ten more, reopen by chip --------------------
async function flowGuide(browser) {
  const [ctx, page] = await newPage(browser, 390, 844, true);
  await shot(page, 'a1-guide-step1-budget');
  await tap(page, '300 χιλ. €'); await shot(page, 'a2-guide-step2-goal');
  await tap(page, 'Απόδοση ενοικίου'); await shot(page, 'a3-guide-step3-where');
  await tap(page, 'Κοντά σε μετρό/ΗΣΑΠ'); await shot(page, 'a4-guide-step4-kind');
  await page.getByText('Νεόδμητο (έως 10 ετών)', { exact: true }).first().click(); await settle(page);
  await tap(page, 'Η πρότασή μου'); await shot(page, 'a5-guide-result');
  const more = page.getByRole('button', { name: /^Δείξε άλλες/ }).first();
  if (await more.count()) { await more.scrollIntoViewIfNeeded(); await more.click(); await shot(page, 'a6-guide-ten-more'); }
  else log('NO «Δείξε άλλες» button');
  // an answer chip reopens its question
  const chip = page.getByRole('radio', { name: /^300 χιλ/ }).first();
  if (await chip.count()) { await chip.scrollIntoViewIfNeeded(); await chip.click(); await shot(page, 'a7-guide-chip-reopened'); }
  else log('NO answer chip «300 χιλ.»');
  await ctx.close();
}

// ---- (b) «Χάρτης»: card under map, Επόμενο, tap on the deck.gl canvas ----------------------
const mapHeader = (p) => p.locator('[data-testid="stMarkdownContainer"] strong', { hasText: / από / }).first().innerText().catch(() => '(no «n από N» header)');
async function findDot(p, box) { // most saturated non-blue pixel away from the centre (docs/qa/maplist/tap.js)
  const png = (await p.screenshot({ clip: box })).toString('base64');
  return p.evaluate(async ({ png, w, h }) => {
    const img = new Image(); img.src = 'data:image/png;base64,' + png; await img.decode();
    const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
    const g = c.getContext('2d'); g.drawImage(img, 0, 0);
    const px = g.getImageData(0, 0, c.width, c.height).data;
    let best = null;
    for (let y = 40; y < c.height - 40; y += 2) for (let x = 40; x < c.width - 60; x += 2) {
      if (Math.hypot(x - c.width / 2, y - c.height / 2) < 40) continue;
      const i = (y * c.width + x) * 4, r = px[i], g2 = px[i + 1], bl = px[i + 2];
      const chroma = Math.max(r, g2, bl) - Math.min(r, g2, bl);
      if (bl > r && bl > g2) continue;
      if (chroma > 45 && (!best || chroma > best.chroma)) best = { x: x * w / c.width, y: y * h / c.height, chroma };
    }
    return best;
  }, { png, w: box.width, h: box.height });
}
async function flowMap(browser) {
  const [ctx, page] = await newPage(browser, 390, 844, true);
  await nav(page, 'Χάρτης'); await sleep(3000);
  await shot(page, 'b1-map-card-under-map');
  const h0 = await mapHeader(page);
  const next = btn(page, 'Επόμενο ›');
  if (await next.count()) { await next.click(); await settle(page, 2500); } else log('NO «Επόμενο ›»');
  const h1 = await mapHeader(page);
  await shot(page, 'b2-map-after-next', { wait: false });
  const deck = page.locator('[data-testid="stDeckGlJsonChart"]').first();
  let h2 = h1, tapped = false;
  if (await deck.count()) {
    await deck.scrollIntoViewIfNeeded(); await sleep(1500);
    const box = await deck.boundingBox();
    const dot = await findDot(page, box);
    if (dot) {
      tapped = true;
      await page.touchscreen.tap(box.x + dot.x, box.y + dot.y); await settle(page, 2500);
      h2 = await mapHeader(page);
      if (h2 === h1) { await page.mouse.click(box.x + dot.x, box.y + dot.y); await settle(page, 2500); h2 = await mapHeader(page); }
    } else log('no dot found on the map');
  } else log('NO deck.gl chart');
  await shot(page, 'b3-map-after-tap-point', { wait: false });
  fs.writeFileSync(`${OUT}/b-map-selection.json`, JSON.stringify({ initial: h0, afterNext: h1, afterTap: h2, tapped, tapSelectsCard: tapped && h2 !== h1 }, null, 2));
  log('map header:', h0, '->', h1, '->', h2);
  await ctx.close();
}

// ---- (c) «Πού να αγοράσω»: decision box + first card expanded ------------------------------
async function flowAreas(browser) {
  const [ctx, page] = await newPage(browser, 390, 844, true);
  await nav(page, 'Πού να αγοράσω');
  await shot(page, 'c1-areas-decision');
  const first = page.locator('[data-testid="stExpander"] summary').first();
  if (await first.count()) {
    // the first expander may be the method box: open the first one whose text names an area card
    const all = page.locator('[data-testid="stExpander"] summary');
    const n = await all.count();
    for (let i = 0; i < n; i++) {
      const t = await all.nth(i).innerText();
      if (/Πώς βαθμολογούμε|Όλες οι περιοχές/.test(t)) continue;
      await all.nth(i).scrollIntoViewIfNeeded(); await all.nth(i).click(); await settle(page); break;
    }
  }
  await shot(page, 'c2-areas-first-card-open');
  await ctx.close();
}

// ---- (d) listing page from search -----------------------------------------------------------
async function flowDetail(browser) {
  const [ctx, page] = await newPage(browser, 390, 844, true);
  await nav(page, 'Αναζήτηση'); await shot(page, 'd0-search');
  await page.getByRole('button', { name: 'Λεπτομέρειες' }).first().click(); await settle(page, 2000);
  await shot(page, 'd1-listing-page');
  await ctx.close();
}

// ---- (e) sidebar login block, sign-in, signed-in sidebar -----------------------------------
async function flowAccount(browser) {
  let [ctx, page] = await newPage(browser, 390, 844, true);
  await openSidebar(page);
  await shot(page, 'e0-sidebar-no-token-real-config', { full: false });
  await ctx.close();
  const ctx2 = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  page = await ctx2.newPage(); ctx = ctx2;
  await page.goto(BASE2, { waitUntil: 'domcontentloaded' }); await settle(page);
  await openSidebar(page);
  await shot(page, 'e1-sidebar-signed-out', { full: false });
  const exp = page.locator('[data-testid="stSidebar"] [data-testid="stExpander"] summary').first();
  if (await exp.count()) { await exp.click(); await sleep(800); }
  await shot(page, 'e2-sidebar-login-form', { full: false });
  const side = page.locator('[data-testid="stSidebar"]');
  const nameBox = side.getByLabel('Όνομα', { exact: true }); await nameBox.fill('Δοκιμή QA'); await nameBox.press('Enter'); await sleep(1200);
  const pinBox = side.getByLabel('PIN (4 ψηφία)', { exact: true }); await pinBox.fill('4821'); await pinBox.press('Enter'); await sleep(1500);
  await side.getByRole('button', { name: 'Νέο προφίλ', exact: true }).click(); await settle(page, 1500);
  await shot(page, 'e3-sidebar-after-new-profile', { full: false });
  await closeSidebar(page);
  await shot(page, 'e4-signed-in-home', { full: false });
  await ctx.close();
}

// ---- (f) «Αναζήτηση» after setting a filter ------------------------------------------------
async function pick(page, label, option) { // Streamlit selectbox by label
  const box = page.getByLabel(label, { exact: true }).first();
  await box.scrollIntoViewIfNeeded();
  const opt = page.getByRole('option', { name: option, exact: true }).first();
  await box.click({ force: true });
  if (!(await opt.isVisible().catch(() => false))) { await box.focus(); await page.keyboard.press('ArrowDown'); await sleep(500); }
  if (!(await opt.isVisible().catch(() => false))) { await box.fill(option); await sleep(500); await page.keyboard.press('Enter'); }
  else await opt.click();
  await sleep(2500);
}
async function setNum(page, label, value) { // st.number_input: type + Enter
  const box = page.getByLabel(label, { exact: true }).first();
  await box.scrollIntoViewIfNeeded(); await box.fill(String(value)); await box.press('Enter'); await settle(page, 1500);
}
async function flowSearch(browser) {
  const [ctx, page] = await newPage(browser, 390, 844, true);
  await nav(page, 'Αναζήτηση');
  await shot(page, 'f0-search-default', { full: false });
  try {
    await page.locator('[data-testid="stExpander"] summary', { hasText: 'Φίλτρα' }).first().click(); await sleep(800);
    await setNum(page, 'Κτίριο από (έτος)', 2015); await setNum(page, 'Από όροφο', 2); await setNum(page, 'Τιμή έως (€)', 300000);
  } catch (e) { log('filter set failed:', e.message.split('\n')[0]); }
  await shot(page, 'f1-search-filtered');
  await ctx.close();
}

// ---- (g) desktop home + areas ---------------------------------------------------------------
async function flowDesktop(browser) {
  const [ctx, page] = await newPage(browser, 1280, 800, false);
  await shot(page, 'g1-guide-desktop');
  await nav(page, 'Πού να αγοράσω'); await shot(page, 'g2-areas-desktop');
  await ctx.close();
}

// ---- extra: every other main-nav page on the phone (overflow check) -------------------------
async function flowPages(browser) {
  const [ctx, page] = await newPage(browser, 390, 844, true);
  await shot(page, 'h0-first-load');
  for (const [i, label] of ['Αγαπημένα', 'Σύγκριση'].entries()) {
    await nav(page, label); await shot(page, `h${i + 1}-${label === 'Σύγκριση' ? 'compare' : 'favourites'}`);
  }
  await ctx.close();
}

(async () => {
  const browser = await chromium.launch();
  const only = process.argv[4] ? process.argv[4].split(',') : null;
  const flows = { a: flowGuide, b: flowMap, c: flowAreas, d: flowDetail, e: flowAccount, f: flowSearch, g: flowDesktop, h: flowPages };
  for (const [k, fn] of Object.entries(flows)) {
    if (only && !only.includes(k)) continue;
    try { await fn(browser); } catch (e) { log('FAIL flow', k, e.message.split('\n')[0]); }
    fs.writeFileSync(`${OUT}/overflow.json`, JSON.stringify(overflow, null, 2));
  }
  await browser.close();
})();
