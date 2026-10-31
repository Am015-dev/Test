// C13: split each map tap into the server part and the browser part. Usage:
//   NODE_PATH=$(npm root -g) node docs/qa/speed/map_split.js [baseUrl] [runs]
// Server part = tap → the last websocket frame of the rerun (Streamlit's script-finished
// message); browser part = that → the last DOM change (deck.gl / mapbox set-up, basemap).
// Same fresh-session protocol as measure_speed.js. Writes docs/qa/speed/map_split.json.
const { chromium } = require('playwright');
const fs = require('fs');
const BASE = process.argv[2] || 'http://127.0.0.1:8501';
const RUNS = Number(process.argv[3] || 3);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const median = (xs) => { const s = [...xs].sort((a, b) => a - b); return s[Math.floor(s.length / 2)]; };

async function fresh(browser) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
  await ctx.addInitScript(() => {
    window.__last = performance.now(); window.__t0 = null;
    new MutationObserver(() => { window.__last = performance.now(); }).observe(document, { subtree: true, childList: true, attributes: true, characterData: true });
    addEventListener('pointerdown', (e) => { if (window.__arm && window.__t0 === null) window.__t0 = e.timeStamp; }, true);
  });
  const page = await ctx.newPage();
  page.__frames = [];
  page.on('websocket', (ws) => ws.on('framereceived', () => page.__frames.push(Date.now())));
  await page.goto(BASE); await page.locator('[data-testid="stMain"]').first().waitFor({ timeout: 120000 });
  await quiet(page);
  return [ctx, page];
}
async function quiet(page) {
  for (;;) {
    await sleep(100);
    const idle = await page.evaluate(() => performance.now() - window.__last);
    if (idle >= 500 && !(await page.locator('[data-testid="stStatusWidget"]').count())) return;
  }
}
const main = (p) => p.locator('[data-testid="stMain"]');
const tap = async (p, n) => { await main(p).getByRole('button', { name: n, exact: true }).first().click(); await quiet(p); };

const TAPS = {
  'pill-Χάρτης': { act: (p) => main(p).getByRole('radio', { name: 'Χάρτης', exact: true }).first().click() },
  'pill-Περιοχές': { act: (p) => main(p).getByRole('radio', { name: 'Περιοχές', exact: true }).first().click() },
  'guide-map': {
    prep: async (p) => {
      await tap(p, 'Να αγοράσω'); await tap(p, '250 χιλ. €'); await tap(p, 'Απόδοση ενοικίου');
      await tap(p, 'Όπου βγαίνει ο καλύτερος αριθμός');
      await main(p).getByText('Οτιδήποτε', { exact: true }).first().click(); await quiet(p);
      await tap(p, 'Η πρότασή μου');
    },
    act: (p) => main(p).locator('.st-key-guide_map label').first().click(),
  },
};

(async () => {
  const browser = await chromium.launch();
  const out = {};
  for (const [id, t] of Object.entries(TAPS)) {
    const server = [], total = [];
    for (let i = 0; i < RUNS; i++) {
      const [ctx, p] = await fresh(browser);
      if (t.prep) await t.prep(p);
      await p.evaluate(() => { window.__arm = true; window.__t0 = null; });
      const wall0 = Date.now(); const perf0 = await p.evaluate(() => performance.now());
      p.__frames = [];
      await t.act(p); await quiet(p);
      const { t0, last } = await p.evaluate(() => ({ t0: window.__t0, last: window.__last }));
      const tapWall = wall0 + (t0 - perf0); // the tap on the wall clock
      const lastFrame = Math.max(...p.__frames);
      server.push(Math.round(lastFrame - tapWall)); total.push(Math.round(last - t0));
      await ctx.close();
    }
    out[id] = { server, total, server_median: median(server), total_median: median(total) };
    console.log(id.padEnd(14), 'server', median(server), JSON.stringify(server), 'total', median(total), JSON.stringify(total));
  }
  fs.writeFileSync('docs/qa/speed/map_split.json', JSON.stringify(out, null, 1));
  await browser.close();
})();
