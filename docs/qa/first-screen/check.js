// First-screen check (round 6, C17). Usage:
//   NODE_PATH=$(npm root -g) node docs/qa/first-screen/check.js [outDir] [baseUrl] [--report]
// Needs the app running (default http://127.0.0.1:8501) against the published DB, with no
// GITHUB_TOKEN / ANTHROPIC_API_KEY in the app's environment. Phone viewport 390×844.
//
// Asserts, by element positions (getBoundingClientRect, no scrolling):
//   guide result — the counts line, the recommendation, the first card and its link to the ad
//                  are all inside the first screen, in that order;
//   listing page — the link to the ad, the price line and «Τι να κάνεις» are inside the
//                  first screen, in that order.
// Prints every position; exits 1 when an assertion fails unless --report is given (the
// «before» run, which only records). Writes guide-result.png and listing.png (viewport only)
// and positions.json into outDir.
const { chromium } = require('playwright');
const fs = require('fs');
const OUT = process.argv[2] || 'docs/qa/first-screen/after';
const BASE = process.argv[3] || 'http://127.0.0.1:8501';
const REPORT_ONLY = process.argv.includes('--report');
const W = 390, H = 844;
fs.mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const out = {};
let failed = false;

async function settle(page, extra = 800) {
  await page.waitForLoadState('networkidle').catch(() => {});
  await sleep(1500);
  for (let i = 0; i < 80; i++) {
    if (!(await page.locator('[data-testid="stStatusWidget"]').count())) break;
    await sleep(500);
  }
  await sleep(extra);
}
async function tap(page, name) { await page.getByRole('button', { name, exact: true }).first().click(); await settle(page); }
async function nav(page, label) {
  await page.locator('[data-testid="stMain"]').getByRole('radio', { name: label, exact: true }).first().click(); await settle(page);
}
// The box of the first element matching `selector` whose text matches `text` (if given),
// relative to the viewport at scroll top.
async function box(page, selector, text) {
  return page.evaluate(({ selector, text }) => {
    const main = document.querySelector('[data-testid="stMain"]') || document.body;
    const re = text ? new RegExp(text) : null;
    for (const el of main.querySelectorAll(selector)) {
      if (re && !re.test(el.innerText || '')) continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      return { top: Math.round(r.top), bottom: Math.round(r.bottom), height: Math.round(r.height),
        text: (el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 90) };
    }
    return null;
  }, { selector, text });
}
function check(screen, items) {
  const rows = [];
  let last = -1, ok = true;
  for (const [name, b] of items) {
    let verdict = 'ok';
    if (!b) { verdict = 'MISSING'; ok = false; }
    else if (b.bottom > H) { verdict = `BELOW FOLD (bottom ${b.bottom} > ${H})`; ok = false; }
    else if (b.top < last) { verdict = `OUT OF ORDER (top ${b.top} < ${last})`; ok = false; }
    if (b) last = Math.max(last, b.top);
    rows.push({ name, top: b ? b.top : null, bottom: b ? b.bottom : null, verdict, text: b ? b.text : '' });
  }
  out[screen] = { ok, rows };
  console.log(`\n== ${screen}: ${ok ? 'PASS' : 'FAIL'} (viewport ${W}×${H})`);
  for (const r of rows) console.log(`  ${r.verdict.padEnd(34)} ${String(r.top).padStart(5)}–${String(r.bottom).padEnd(5)} ${r.name}: «${r.text}»`);
  if (!ok) failed = true;
}
// Streamlit scrolls an inner container, not the window: reset every scrollable ancestor.
async function toTop(page) {
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    for (const el of document.querySelectorAll('[data-testid="stAppViewContainer"], [data-testid="stMain"], section.main, .stMain, [data-testid="stMainBlockContainer"]')) el.scrollTop = 0;
  });
  await sleep(400);
}
async function newPage(browser) {
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, hasTouch: true, isMobile: true });
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: 'domcontentloaded' }); await settle(page);
  return [ctx, page];
}

async function guideResult(browser) {
  const [ctx, page] = await newPage(browser);
  await tap(page, 'Να αγοράσω');
  await tap(page, '300 χιλ. €');
  await tap(page, 'Απόδοση ενοικίου');
  await tap(page, 'Κοντά σε μετρό/ΗΣΑΠ');
  await page.getByText('Νεόδμητο (έως 10 ετών)', { exact: true }).first().click(); await settle(page);
  await tap(page, 'Η πρότασή μου');
  await toTop(page);
  await page.screenshot({ path: `${OUT}/guide-result.png` });
  const md = '[data-testid="stMarkdownContainer"]';
  check('guide result', [
    ['counts line', await box(page, md, 'ακριβώς όπως ζήτησες|αγγελί')],
    ['recommendation', await box(page, md, 'Σου προτείνω|Πρόταση')],
    ['first card', await box(page, '.hg-card[data-rank="1"]')],
    ['link to the ad', await box(page, 'a[href*="xe.gr"], a[href*="goldenhome"], a[href*="remax"], a[href*="green-acres"]', 'Δες την αγγελία|Άνοιγμα στο')],
  ]);
  await ctx.close();
}

async function listingPage(browser) {
  const [ctx, page] = await newPage(browser);
  await nav(page, 'Αναζήτηση');
  await page.getByRole('button', { name: 'Λεπτομέρειες', exact: true }).first().click(); await settle(page, 1500);
  await toTop(page);
  await page.screenshot({ path: `${OUT}/listing.png` });
  check('listing page', [
    ['link to the ad', await box(page, 'a[href*="xe.gr"], a[href*="goldenhome"], a[href*="remax"], a[href*="green-acres"]', 'Δες την αγγελία|Άνοιγμα στο')],
    ['price line', await box(page, '.hg-card .hg-l1')],
    ['verdict («Τι να κάνεις»)', await box(page, '[data-testid="stMarkdownContainer"]', 'Τι να κάνεις')],
  ]);
  await ctx.close();
}

(async () => {
  const browser = await chromium.launch();
  for (const fn of [guideResult, listingPage]) {
    try { await fn(browser); } catch (e) { console.log('FAIL', fn.name, e.message.split('\n')[0]); failed = true; }
  }
  await browser.close();
  fs.writeFileSync(`${OUT}/positions.json`, JSON.stringify(out, null, 2));
  if (failed && !REPORT_ONLY) process.exit(1);
})();
