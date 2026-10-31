// Visual QA screenshots. Usage:
//   NODE_PATH=$(npm root -g) node docs/qa/shots.js [outDir] [baseUrl]
// Needs the app running (default http://127.0.0.1:8501). Writes <nn>-<page>-<viewport>.png
// and overflow.json (horizontal-overflow per shot) into outDir.
const { chromium } = require('playwright');
const fs = require('fs');
const OUT = process.argv[2] || 'docs/qa/baseline';
const BASE = process.argv[3] || 'http://127.0.0.1:8501';
const PAGES = [ // app.py: NAV (detail is reached via «Λεπτομέρειες»)
  ['find', 'Βρες μου σπίτι'], ['areas', 'Πού να αγοράσω'], ['search', 'Αναζήτηση'],
  ['map', 'Χάρτης'], ['favs', 'Αγαπημένα'], ['saved', 'Αποθηκευμένες αναζητήσεις'],
  ['compare', 'Σύγκριση'],
];
const VIEWPORTS = [['phone', 390, 844], ['desktop', 1280, 800]];
const overflow = {};
fs.mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function settle(page) {
  await page.waitForLoadState('networkidle').catch(() => {});
  await sleep(2500);
  for (let i = 0; i < 40; i++) { // wait for Streamlit's running indicator to go away
    if (!(await page.locator('[data-testid="stStatusWidget"]').count())) break;
    await sleep(500);
  }
  await sleep(1000);
}
async function shot(page, name, vp) {
  await settle(page);
  const m = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth,
    inner: Math.max(0, ...[...document.querySelectorAll('[data-testid="stMain"], section.main, .stMain')].map((e) => e.scrollWidth)),
    wide: [...document.querySelectorAll('[data-testid="stMain"] *')].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.right > window.innerWidth + 1; }).slice(0, 5).map((e) => e.tagName + '.' + String(e.className).slice(0, 40) + ' right=' + Math.round(e.getBoundingClientRect().right)),
    text: document.body.innerText,
  }));
  const key = `${name}-${vp}`;
  overflow[key] = { overflow: m.scrollWidth > m.innerWidth, scrollWidth: m.scrollWidth, innerWidth: m.innerWidth, mainScrollWidth: m.inner, wideElements: m.wide };
  fs.writeFileSync(`${OUT}/${key}.txt`, m.text);
  // Streamlit scrolls an inner container, so fullPage alone only captures one screen:
  // grow the viewport to the content height, shoot, restore.
  const vpSize = page.viewportSize();
  const full = await page.evaluate(() => Math.min(12000, Math.max(
    document.documentElement.scrollHeight,
    ...[...document.querySelectorAll('[data-testid="stMain"], .stMain, section.main')].map((e) => e.scrollHeight))));
  await page.setViewportSize({ width: vpSize.width, height: Math.max(vpSize.height, full) });
  await sleep(1200);
  await page.screenshot({ path: `${OUT}/${key}.png`, fullPage: true });
  overflow[key].pageHeight = full;
  await page.setViewportSize(vpSize); await sleep(500);
  console.log(key, (overflow[key].overflow || m.wide.length) ? 'OVERFLOW' : 'ok', m.scrollWidth, m.innerWidth);
}
async function openNav(page, label, phone) {
  if (phone) {
    const btn = page.locator('[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapsedControl"] button, [data-testid="collapsedControl"]').first();
    if (await btn.count()) await btn.click().catch(() => {});
    await sleep(800);
  }
  await page.locator('[data-testid="stSidebar"]').getByText(label, { exact: true }).first().click();
  if (phone) { // the drawer stays open after a choice: close it like a phone user must
    await sleep(800);
    const x = page.locator('[data-testid="stSidebarCollapseButton"] button, [data-testid="stSidebarHeader"] button').first();
    if (await x.count()) await x.click().catch(() => {});
    await sleep(800);
  }
}
async function pick(page, label, option) { // Streamlit selectbox by label
  const box = page.getByLabel(label, { exact: true }).first();
  await box.scrollIntoViewIfNeeded();
  const opt = page.getByRole('option', { name: option, exact: true }).first();
  await box.click({ force: true });
  if (!(await opt.isVisible().catch(() => false))) { // touch taps can fail to open it
    await box.focus(); await page.keyboard.press('ArrowDown'); await sleep(500);
  }
  if (!(await opt.isVisible().catch(() => false))) { // last resort: type to filter + Enter
    await box.fill(option); await sleep(500); await page.keyboard.press('Enter');
  } else await opt.click();
  await sleep(2500);
}

(async () => {
  const browser = await chromium.launch();
  for (const [vp, w, h] of VIEWPORTS) {
    const phone = vp === 'phone';
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, hasTouch: phone, isMobile: phone });
    const page = await ctx.newPage();
    const go = async () => { await page.goto(BASE, { waitUntil: 'domcontentloaded' }); await settle(page); };
    if (phone) { await go(); await shot(page, '00-first-load', vp); }
    
    for (const [i, [slug, label]] of PAGES.entries()) {
      try { await go(); await openNav(page, label, phone); await shot(page, `${String(i + 1).padStart(2, '0')}-${slug}`, vp); }
      catch (e) { console.log('FAIL', slug, vp, e.message.split('\n')[0]); }
    }
    // interactions
    try { // 1. first listing «Λεπτομέρειες» (from the search page)
      await go(); await openNav(page, 'Αναζήτηση', phone);
      await settle(page);
      await page.getByRole('button', { name: 'Λεπτομέρειες' }).first().click();
      await shot(page, '08-detail', vp);
    } catch (e) { console.log('FAIL detail', vp, e.message.split('\n')[0]); }
    try { // 2. search filters: min year (age band) + floor >= 2
      await go(); await openNav(page, 'Αναζήτηση', phone); await settle(page);
      await pick(page, 'Ηλικία κτιρίου', 'Έως 10 ετών');
      await pick(page, 'Όροφος', 'Από 2ο');
      await shot(page, '09-search-filtered', vp);
    } catch (e) { console.log('FAIL filters', vp, e.message.split('\n')[0]); }
    try { // 3. reject first card on find page
      await go(); await settle(page);
      await page.getByRole('button', { name: /Δεν μου κάνει/ }).first().click();
      await shot(page, '10-find-rejected', vp);
    } catch (e) { console.log('FAIL reject', vp, e.message.split('\n')[0]); }
    try { // 4. first area «Δες τις αγγελίες»
      await go(); await openNav(page, 'Πού να αγοράσω', phone); await settle(page);
      await page.getByRole('button', { name: /Δες (τις )?αγγελίες/ }).first().click();
      await shot(page, '11-area-listings', vp);
    } catch (e) { console.log('FAIL area', vp, e.message.split('\n')[0]); }
    await ctx.close();
  }
  fs.writeFileSync(`${OUT}/overflow.json`, JSON.stringify(overflow, null, 2));
  await browser.close();
})();
