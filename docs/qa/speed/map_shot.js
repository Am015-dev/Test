// C13: 390×844 screenshots of «Χάρτης» on two servers (before / after) and their pixel diff.
//   NODE_PATH=$(npm root -g) node docs/qa/speed/map_shot.js <beforeUrl> <afterUrl>
// Writes docs/qa/speed/map-{before,after}.png and prints the share of differing pixels.
const { chromium } = require('playwright');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const [BEFORE, AFTER] = process.argv.slice(2);

async function shot(browser, url, name) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
  const p = await ctx.newPage();
  await p.goto(url); await p.locator('[data-testid="stMain"]').first().waitFor({ timeout: 120000 });
  await sleep(4000);
  await p.locator('[data-testid="stMain"]').getByRole('radio', { name: 'Χάρτης', exact: true }).first().click();
  await sleep(2000);
  for (let i = 0; i < 80 && (await p.locator('[data-testid="stStatusWidget"]').count()); i++) await sleep(250);
  await sleep(6000); // basemap tiles
  const path = `docs/qa/speed/map-${name}.png`;
  await p.screenshot({ path });
  const png = (await p.screenshot()).toString('base64');
  await ctx.close();
  return png;
}

(async () => {
  const b = await chromium.launch();
  const a = await shot(b, BEFORE, 'before');
  const c = await shot(b, AFTER, 'after');
  const page = await b.newPage();
  const diff = await page.evaluate(async ({ a, c }) => {
    const load = async (s) => { const i = new Image(); i.src = 'data:image/png;base64,' + s; await i.decode(); const cv = document.createElement('canvas'); cv.width = i.width; cv.height = i.height; const g = cv.getContext('2d'); g.drawImage(i, 0, 0); return g.getImageData(0, 0, i.width, i.height).data; };
    const x = await load(a), y = await load(c);
    let n = 0; for (let i = 0; i < x.length; i += 4) if (Math.abs(x[i] - y[i]) + Math.abs(x[i + 1] - y[i + 1]) + Math.abs(x[i + 2] - y[i + 2]) > 30) n++;
    return n / (x.length / 4);
  }, { a, c });
  console.log('differing pixels:', (diff * 100).toFixed(2) + ' %');
  await b.close();
})();
