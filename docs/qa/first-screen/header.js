// C18 first-screen check (390×844): on the guide result the first card starts within the top
// 45 % of the screen; the pills are at most two rows; no sources/counts line above the pills;
// Streamlit's own chrome (status widget, decoration, deploy/host badges) is hidden.
// Usage: NODE_PATH=$(npm root -g) node docs/qa/first-screen/header.js [baseUrl]
// Exit code 1 when a check fails; the measurements are printed as JSON either way.
const { chromium } = require('playwright');
const BASE = process.argv[2] || 'http://127.0.0.1:8501';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function settle(page, extra = 800) {
  await page.waitForLoadState('networkidle').catch(() => {});
  await sleep(1800);
  for (let i = 0; i < 80; i++) {
    if (!(await page.locator('[data-testid="stStatusWidget"]:visible').count())) break;
    await sleep(500);
  }
  await sleep(extra);
}
async function tap(page, name) { await page.getByRole('button', { name, exact: true }).first().click(); await settle(page); }

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, hasTouch: true, isMobile: true });
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: 'domcontentloaded' }); await settle(page);
  await tap(page, 'Να αγοράσω'); await tap(page, '300 χιλ. €'); await tap(page, 'Απόδοση ενοικίου');
  await tap(page, 'Κοντά σε μετρό/ΗΣΑΠ');
  await page.getByText('Νεόδμητο (έως 10 ετών)', { exact: true }).first().click(); await settle(page);
  await tap(page, 'Η πρότασή μου');
  const m = await page.evaluate(() => {
    const H = window.innerHeight;
    const card = document.querySelector('[data-testid="stMain"] .hg-card');
    const pills = [...document.querySelectorAll('.st-key-nav_pill button')].map((b) => Math.round(b.getBoundingClientRect().top));
    const rows = new Set(pills).size;
    const pillsTop = Math.min(...pills);
    const above = [...document.querySelectorAll('[data-testid="stMain"] [data-testid="stElementContainer"]')]
      .filter((e) => e.getBoundingClientRect().height > 0 && e.getBoundingClientRect().bottom <= pillsTop + 1)
      .map((e) => e.innerText.trim()).filter(Boolean);
    const hidden = (sel) => [...document.querySelectorAll(sel)].every((e) => getComputedStyle(e).display === 'none' || e.getBoundingClientRect().height === 0);
    return {
      viewportHeight: H,
      firstCardTop: card ? Math.round(card.getBoundingClientRect().top) : null,
      firstCardShare: card ? Math.round((card.getBoundingClientRect().top / H) * 1000) / 1000 : null,
      pillRows: rows,
      textAbovePills: above,
      chromeHidden: {
        statusWidget: hidden('[data-testid="stStatusWidget"]'),
        decoration: hidden('[data-testid="stDecoration"]'),
        deployButton: hidden('[data-testid="stAppDeployButton"], .stDeployButton'),
        hostBadge: hidden('[class*="viewerBadge"], a[href*="streamlit.io/cloud"]'),
      },
    };
  });
  const fails = [];
  if (m.firstCardShare === null || m.firstCardShare > 0.45) fails.push(`first card starts at ${m.firstCardShare} of the screen (limit 0.45)`);
  if (m.pillRows > 2) fails.push(`pills take ${m.pillRows} rows`);
  if (m.textAbovePills.some((t) => /ενεργές|ελεγμένες|XE\.gr/.test(t))) fails.push('the sources/counts line is still above the pills');
  for (const [k, v] of Object.entries(m.chromeHidden)) if (!v) fails.push(`${k} is visible`);
  m.fails = fails;
  console.log(JSON.stringify(m, null, 2));
  await browser.close();
  process.exit(fails.length ? 1 : 0);
})();
