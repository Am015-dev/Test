// C15 — the owner's answers at 390×844: 250 χιλ. · απόδοση · κοντά σε μετρό · οποιαδήποτε
// ηλικία · 1 υπν. Usage: NODE_PATH=$(npm root -g) node docs/qa/wide/shots.js <outDir> [baseUrl]
// The app must run against the published DB with no GITHUB_TOKEN / ANTHROPIC_API_KEY.
const { chromium } = require('playwright');
const fs = require('fs');
const OUT = process.argv[2] || 'docs/qa/wide/after';
const BASE = process.argv[3] || 'http://127.0.0.1:8501';
fs.mkdirSync(OUT, { recursive: true });
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
async function shot(page, name, full = true) {
  await settle(page);
  const text = await page.evaluate(() => document.body.innerText);
  fs.writeFileSync(`${OUT}/${name}.txt`, text);
  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  if (full) {
    const vp = page.viewportSize();
    const h = await page.evaluate(() => Math.min(14000, Math.max(document.documentElement.scrollHeight,
      ...[...document.querySelectorAll('[data-testid="stMain"], .stMain, section.main')].map((e) => e.scrollHeight))));
    await page.setViewportSize({ width: vp.width, height: Math.max(vp.height, h) });
    await sleep(1200);
    await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
    await page.setViewportSize(vp); await sleep(500);
  } else await page.screenshot({ path: `${OUT}/${name}.png` });
  console.log(name, width > 390 ? `OVERFLOW ${width}` : 'ok');
}
async function tap(page, name) { await page.getByRole('button', { name, exact: true }).first().click(); await settle(page); }
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, hasTouch: true, isMobile: true });
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: 'domcontentloaded' }); await settle(page);
  await tap(page, 'Να αγοράσω');
  await tap(page, '250 χιλ. €');
  await tap(page, 'Απόδοση ενοικίου');
  await tap(page, 'Κοντά σε μετρό/ΗΣΑΠ');
  await page.getByText('Οτιδήποτε', { exact: true }).first().click(); await settle(page);
  await page.getByRole('radio', { name: '1', exact: true }).first().click(); await settle(page);
  await shot(page, '1-step4-answers', false);
  await tap(page, 'Η πρότασή μου');
  await shot(page, '2-result-fold', false);
  await shot(page, '3-result-full');
  await ctx.close(); await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
