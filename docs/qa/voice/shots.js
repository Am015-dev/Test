// C10 voice pass, phone shots. Usage (app on :8501):
//   NODE_PATH=$(npm root -g) node docs/qa/voice/shots.js
const { chromium } = require('playwright');
const OUT = 'docs/qa/voice', BASE = 'http://127.0.0.1:8501';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function settle(p) {
  await p.waitForLoadState('networkidle').catch(() => {}); await sleep(1500);
  for (let i = 0; i < 60 && (await p.locator('[data-testid="stStatusWidget"]').count()); i++) await sleep(500);
  await sleep(800);
}
const byKey = async (p, prefix) => { await p.locator(`[class*="st-key-${prefix}"] button`).first().click(); await settle(p); };
async function full(p, name) {
  const h = await p.evaluate(() => Math.min(9000, Math.max(...[...document.querySelectorAll('[data-testid="stMain"], .stMain, body')].map((e) => e.scrollHeight))));
  await p.setViewportSize({ width: 390, height: Math.max(844, h) }); await sleep(1500);
  await p.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
  await p.setViewportSize({ width: 390, height: 844 }); await sleep(400);
  console.log(name);
}
(async () => {
  const b = await chromium.launch();
  const p = await (await b.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })).newPage();
  await p.goto(BASE); await settle(p);
  for (const k of ['guide-mode-buy', 'guide-b300', 'guide-g-', 'guide-w-', 'guide-show']) {
    if (await p.locator(`[class*="st-key-${k}"] button`).count()) await byKey(p, k);
  }
  await full(p, 'guide-result-390');
  const pill = async (n) => { await p.locator('[data-testid="stMain"]').getByText(n, { exact: true }).first().click(); await settle(p); };
  await pill('Περιοχές');
  await full(p, 'area-card-390');
  await pill('Αναζήτηση');
  await p.getByRole('button', { name: /Λεπτομέρειες/ }).first().click({ timeout: 90000 }); await settle(p);
  await full(p, 'listing-390');
  await b.close();
})();
