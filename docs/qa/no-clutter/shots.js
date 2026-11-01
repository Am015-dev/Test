// C18 «no clutter»: the first screen (390×844, no scrolling) of the four pages the owner judged.
// Usage: NODE_PATH=$(npm root -g) node docs/qa/no-clutter/shots.js before|after [baseUrl]
// Needs the app on baseUrl against the published DB, GITHUB_TOKEN / ANTHROPIC_API_KEY unset.
// Writes <tag>-<page>.png (the viewport only) and <tag>-<page>.txt (the text within the
// first screen, top to bottom) into docs/qa/no-clutter/.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const TAG = process.argv[2] || 'after';
const BASE = process.argv[3] || 'http://127.0.0.1:8501';
const OUT = path.dirname(__filename);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function settle(page, extra = 800) {
  await page.waitForLoadState('networkidle').catch(() => {});
  await sleep(1800);
  for (let i = 0; i < 80; i++) {
    if (!(await page.locator('[data-testid="stStatusWidget"]').count())) break;
    await sleep(500);
  }
  await sleep(extra);
}
// Text of every element whose box starts inside the viewport (what the buyer sees unscrolled).
async function firstScreenText(page) {
  return page.evaluate(() => {
    const H = window.innerHeight;
    const out = [];
    const els = document.querySelectorAll('[data-testid="stMain"] [data-testid="stElementContainer"]');
    for (const el of els) {
      const r = el.getBoundingClientRect();
      if (r.height === 0 || r.top >= H) continue;
      const t = el.innerText.trim();
      if (t) out.push(`${Math.round(r.top)}: ${t.replace(/\s*\n\s*/g, ' / ')}`);
    }
    return out.join('\n');
  });
}
async function shot(page, name) {
  await settle(page);
  await page.screenshot({ path: `${OUT}/${TAG}-${name}.png` });
  fs.writeFileSync(`${OUT}/${TAG}-${name}.txt`, await firstScreenText(page));
  console.log(TAG, name, 'ok');
}
async function tap(page, name) { await page.getByRole('button', { name, exact: true }).first().click(); await settle(page); }
async function nav(page, pill) {
  await page.locator('[data-testid="stMain"]').getByRole('radio', { name: pill, exact: true }).first().click();
  await settle(page);
}
async function fresh(browser) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, hasTouch: true, isMobile: true });
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: 'domcontentloaded' }); await settle(page);
  return [ctx, page];
}

(async () => {
  const browser = await chromium.launch();
  let [ctx, page] = await fresh(browser);
  await tap(page, 'Να αγοράσω'); await tap(page, '300 χιλ. €'); await tap(page, 'Απόδοση ενοικίου');
  await tap(page, 'Κοντά σε μετρό/ΗΣΑΠ');
  await page.getByText('Νεόδμητο (έως 10 ετών)', { exact: true }).first().click(); await settle(page);
  await tap(page, 'Η πρότασή μου'); await shot(page, 'guide-result');
  await ctx.close();
  for (const [pill, name] of [['Αναζήτηση', 'search'], ['Χάρτης', 'map'], ['Περιοχές', 'areas']]) {
    [ctx, page] = await fresh(browser);
    await nav(page, pill); if (name === 'map') await sleep(2500);
    await shot(page, name);
    await ctx.close();
  }
  await browser.close();
})();
