// C11 card photo: 390×844 shots of the guide result and the search list, plus the checks that
// matter for a thumbnail — no horizontal scroll (scrollWidth 390), no layout shift while the
// photos load (CLS from the browser's layout-shift entries once the page has rendered, and every
// .hg-thumb box the same size before and after its image loads). The page-swap CLS right after
// a tap is reported separately: it is Streamlit replacing the page, with or without photos.
//   NODE_PATH=$(npm root -g) node docs/qa/photo/shots.js <label> [baseUrl]
// Output: docs/qa/photo/<label>-*.png and docs/qa/photo/<label>.json.
const { chromium } = require('playwright');
const fs = require('fs');

const LABEL = process.argv[2] || 'after';
const BASE = process.argv[3] || 'http://127.0.0.1:8501';
const OUT = 'docs/qa/photo';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const report = {};

async function settle(page) {
  await page.waitForLoadState('networkidle').catch(() => {});
  await sleep(1500);
  for (let i = 0; i < 80; i++) {
    if (!(await page.locator('[data-testid="stStatusWidget"]').count())) break;
    await sleep(500);
  }
  await sleep(800);
}
const tap = async (page, name) => {
  await page.locator('[data-testid="stMain"]').getByText(name, { exact: true }).first().click();
  await settle(page);
};

async function boxes(page) {
  return page.evaluate(() => [...document.querySelectorAll('.hg-thumb')].map((e) => {
    const r = e.getBoundingClientRect();
    return [Math.round(r.width), Math.round(r.height)];
  }));
}

async function measure(page, name) {
  await settle(page);
  // Shifts until now belong to Streamlit swapping the page after the tap (flaky, also on the
  // build without photos); from here on, a shift could only come from photos loading.
  const clsSwap = await page.evaluate(() => { const v = window.__cls; window.__cls = 0; return v; });
  const early = await boxes(page);
  // Scroll the whole list so every lazy photo loads, then come back.
  await page.evaluate(async () => {
    const main = document.querySelector('[data-testid="stMain"]') || document.scrollingElement;
    for (let y = 0; y < 20000; y += 500) { main.scrollTo(0, y); window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 120)); }
    main.scrollTo(0, 0); window.scrollTo(0, 0);
  });
  await sleep(2500);
  const late = await boxes(page);
  const m = await page.evaluate(() => {
    const imgs = [...document.querySelectorAll('.hg-thumb img')];
    return {
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
      cards: document.querySelectorAll('.hg-card').length,
      thumbs: document.querySelectorAll('.hg-thumb').length,
      photos: imgs.length,
      photosLoaded: imgs.filter((i) => i.complete && i.naturalWidth > 0).length,
      noPhoto: document.querySelectorAll('.hg-thumb-empty').length,
      clsWhilePhotosLoad: Number((window.__cls || 0).toFixed(4)),
    };
  });
  m.clsPageSwap = Number(clsSwap.toFixed(4));
  m.boxSizes = [...new Set(late.map((b) => b.join('×')))];
  m.boxesStable = JSON.stringify(early) === JSON.stringify(late);
  report[name] = m;
  await page.screenshot({ path: `${OUT}/${LABEL}-${name}.png` });
  // …and the cards themselves: the first card with a photo (else the first card) at the top.
  await page.evaluate(() => {
    const cards = [...document.querySelectorAll('.hg-card')];
    const c = cards.find((x) => x.querySelector('.hg-thumb img')) || cards[0];
    if (c) c.scrollIntoView({ block: 'start' });
  });
  await sleep(1500);
  await page.screenshot({ path: `${OUT}/${LABEL}-${name}-cards.png` });
  console.log(name, JSON.stringify(m));
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, hasTouch: true, isMobile: true,
  });
  await ctx.addInitScript(() => {
    window.__cls = 0;
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) if (!e.hadRecentInput) window.__cls += e.value;
    }).observe({ type: 'layout-shift', buffered: true });
  });
  const page = await ctx.newPage();

  // The guide result (the owner's answers).
  await page.goto(BASE, { waitUntil: 'domcontentloaded' }); await settle(page);
  await tap(page, 'Να αγοράσω');
  await tap(page, '300 χιλ. €');
  await tap(page, 'Απόδοση ενοικίου');
  await tap(page, 'Κοντά σε μετρό/ΗΣΑΠ');
  await page.getByText('Νεόδμητο (έως 10 ετών)', { exact: true }).first().click(); await settle(page);
  await page.evaluate(() => { window.__cls = 0; });
  await tap(page, 'Η πρότασή μου');
  await measure(page, 'guide-result');

  // Search.
  await page.evaluate(() => { window.__cls = 0; });
  await page.locator('[data-testid="stMain"]').getByRole('radio', { name: 'Αναζήτηση', exact: true }).first().click();
  await measure(page, 'search');

  // A search whose first results carry photos (Golden Home lists Μαρούσι with photos).
  await page.evaluate(() => { window.__cls = 0; });
  const box = page.locator('[data-testid="stMain"] input[type="text"]').first();
  await box.fill('διαμέρισμα στο Μαρούσι'); await box.press('Enter'); await settle(page);
  await measure(page, 'search-marousi');

  // The listing page (full-width photo) from the first card that has a photo, else the first.
  const nth = await page.evaluate(() => Math.max(0, [...document.querySelectorAll('.hg-card')]
    .findIndex((c) => c.querySelector('.hg-thumb img'))));
  const details = page.getByRole('button', { name: 'Λεπτομέρειες', exact: true }).nth(nth);
  if (await details.count()) {
    await page.evaluate(() => { window.__cls = 0; });
    await details.click();
    await measure(page, 'listing');
  }

  fs.writeFileSync(`${OUT}/${LABEL}.json`, JSON.stringify(report, null, 2) + '\n');
  await browser.close();
})();
