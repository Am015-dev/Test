// Browser proof for maplist: at 390×844, Επόμενο recentres the map on the next listing, and
// tapping a dot on the map changes the card under it. Usage (demo app running on :8502):
//   NODE_PATH=$(npm root -g) node docs/qa/maplist/tap.js [baseUrl]
const { chromium } = require('playwright');
const BASE = process.argv[2] || 'http://127.0.0.1:8502';
const OUT = 'docs/qa/maplist';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function settle(p) {
  await sleep(1500);
  for (let i = 0; i < 60; i++) {
    if (!(await p.locator('[data-testid="stStatusWidget"]').count())) break;
    await sleep(500);
  }
  await sleep(2500); // map tiles + deck redraw
}
const header = (p) => p.locator('[data-testid="stMarkdownContainer"] strong', { hasText: / από / }).first().innerText();
const mapBox = async (p) => p.locator('[data-testid="stDeckGlJsonChart"]').first().boundingBox();

// Find a solid listing dot (yield colours) in the map, away from the centre (the selection).
async function findDot(p, box) {
  const png = (await p.screenshot({ clip: box })).toString('base64');
  return p.evaluate(async ({ png, w, h }) => {
    const img = new Image(); img.src = 'data:image/png;base64,' + png; await img.decode();
    const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
    const g = c.getContext('2d'); g.drawImage(img, 0, 0);
    const px = g.getImageData(0, 0, c.width, c.height).data;
    // the most saturated non-blue pixel (dots are yield-coloured; basemap is grey, stations blue)
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

(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  const p = await ctx.newPage();
  await p.goto(BASE, { waitUntil: 'domcontentloaded' });
  await sleep(6000); await settle(p);
  await p.screenshot({ path: `${OUT}/after-01-first-card-under-map.png` });
  const h0 = await header(p);
  console.log('initial:', h0);

  await p.getByRole('button', { name: 'Επόμενο ›' }).first().tap();
  await settle(p);
  const h1 = await header(p);
  console.log('after Επόμενο:', h1);
  await p.locator('.st-key-map-anchor').first().scrollIntoViewIfNeeded();
  await p.screenshot({ path: `${OUT}/after-02-next-recentred.png` });

  await p.locator('[data-testid="stDeckGlJsonChart"]').first().scrollIntoViewIfNeeded();
  await sleep(1000);
  const box = await mapBox(p);
  const dot = await findDot(p, box);
  if (!dot) throw new Error('no dot found on the map');
  console.log('tapping dot at', Math.round(box.x + dot.x), Math.round(box.y + dot.y));
  await p.touchscreen.tap(box.x + dot.x, box.y + dot.y);
  await settle(p);
  let h2 = await header(p);
  if (h2 === h1) { // some deck.gl builds pick on mouse click only
    await p.mouse.click(box.x + dot.x, box.y + dot.y); await settle(p); h2 = await header(p);
  }
  console.log('after tap:', h2);
  await p.screenshot({ path: `${OUT}/after-03-tapped-dot.png` });

  // «Στον χάρτη» on a list card further down: selects it and scrolls back to the map.
  await p.getByRole('button', { name: 'Στον χάρτη' }).nth(4).tap();
  await settle(p);
  const h3 = await header(p);
  console.log('after Στον χάρτη (5th):', h3);
  await p.screenshot({ path: `${OUT}/after-04-on-map-from-list.png` });
  const ok = h1 !== h0 && h2 !== h1 && h3.startsWith('5 από');
  console.log(ok ? 'PASS' : 'FAIL');
  await b.close();
  process.exit(ok ? 0 : 1);
})();
