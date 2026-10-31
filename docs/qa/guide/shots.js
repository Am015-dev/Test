// «Οδηγός» phone walk-through. Usage (app running on :8501):
//   NODE_PATH=$(npm root -g) node docs/qa/guide/shots.js [outDir] [baseUrl]
// Writes <nn>-<step>.png (390×844, above the fold) and <nn>-<step>-full.png + overflow.json.
const { chromium } = require('playwright');
const fs = require('fs');
const OUT = process.argv[2] || 'docs/qa/guide';
const BASE = process.argv[3] || 'http://127.0.0.1:8501';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const overflow = {};

async function settle(page) {
  await page.waitForLoadState('networkidle').catch(() => {});
  await sleep(1500);
  for (let i = 0; i < 60; i++) {
    if (!(await page.locator('[data-testid="stStatusWidget"]').count())) break;
    await sleep(500);
  }
  await sleep(800);
}
async function shot(page, name, full = false) {
  await settle(page);
  const m = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth,
    wide: [...document.querySelectorAll('[data-testid="stMain"] *')].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.right > window.innerWidth + 1; }).slice(0, 5).map((e) => e.tagName + '.' + String(e.className).slice(0, 40)),
  }));
  overflow[name] = { overflow: m.scrollWidth > m.innerWidth || m.wide.length > 0, wide: m.wide };
  await page.screenshot({ path: `${OUT}/${name}.png` });
  if (full) {
    const vp = page.viewportSize();
    const h = await page.evaluate(() => Math.min(14000, Math.max(document.documentElement.scrollHeight,
      ...[...document.querySelectorAll('[data-testid="stMain"], .stMain')].map((e) => e.scrollHeight))));
    await page.setViewportSize({ width: vp.width, height: Math.max(vp.height, h) });
    await sleep(1200);
    await page.screenshot({ path: `${OUT}/${name}-full.png`, fullPage: true });
    await page.setViewportSize(vp); await sleep(500);
  }
  console.log(name, overflow[name].overflow ? 'OVERFLOW ' + m.wide.join(',') : 'ok');
}
const tap = async (page, name) => {
  await page.getByRole('button', { name, exact: true }).first().click(); await settle(page);
};

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, hasTouch: true, isMobile: true });
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: 'domcontentloaded' }); await settle(page);
  await shot(page, '01-budget');
  await page.getByText('Με δάνειο', { exact: true }).click(); await settle(page);
  await shot(page, '01-budget-loan');
  await tap(page, '300 χιλ. €'); await shot(page, '02-goal');
  await tap(page, 'Απόδοση ενοικίου'); await shot(page, '03-where');
  await tap(page, 'Κοντά σε μετρό/ΗΣΑΠ'); await shot(page, '04-kind');
  await page.getByText('Νεόδμητο (έως 10 ετών)', { exact: true }).first().click(); await settle(page);
  await tap(page, 'Η πρότασή μου →'); await shot(page, '05-result', true);
  const more = page.getByRole('button', { name: /^Δείξε άλλες/ }).first();
  if (await more.count()) { await more.click(); await shot(page, '06-ten-more', true); }
  await page.getByRole('button', { name: '✗ Δεν μου κάνει' }).first().click(); await shot(page, '07-dropped');
  fs.writeFileSync(`${OUT}/overflow.json`, JSON.stringify(overflow, null, 2));
  await browser.close();
})();
