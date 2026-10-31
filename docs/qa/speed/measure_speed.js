// C13 speed measurements: time from a tap to the rerun's last DOM change. Usage:
//   NODE_PATH=$(npm root -g) node docs/qa/speed/measure_speed.js <label> [baseUrl] [only] [runs]
//   NODE_PATH=$(npm root -g) node docs/qa/speed/measure_speed.js <label> [baseUrl] cold-a|cold-b
// BLOCK_BASEMAP=1 aborts the Carto basemap requests (diagnostic: app time without the internet).
// Needs the app running (docs/qa/speed/serve.sh) on the published DB with no ANTHROPIC_API_KEY /
// GITHUB_TOKEN. Writes docs/qa/speed/<label>.json (every sample + the median per tap).
//
// How a tap is timed: a MutationObserver on the whole document records the time of every DOM
// change; a capture listener records the tap's pointerdown (or the key press that submits a
// form). The tap's time = last mutation − tap, once the DOM has been quiet for 500 ms and
// Streamlit's running indicator is gone. Each tap runs `runs` times (default 3), each in a fresh
// browser context (a new Streamlit session) brought to the state just before the tap by
// unmeasured steps; the median is reported.
//
// Cold modes (run right after a server (re)start, see run_all.sh): «cold-a»/«cold-b» time the
// first page load (navigation start → last mutation) and then the guide result for answers A/B
// in that first session — process caches are empty.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const LABEL = process.argv[2] || 'before';
const BASE = process.argv[3] || 'http://127.0.0.1:8501';
const ONLY = process.argv[4] && !process.argv[4].startsWith('cold') ? process.argv[4].split(',') : null;
const COLD = process.argv[4] && process.argv[4].startsWith('cold') ? process.argv[4] : null;
const RUNS = Number(process.argv[5] || 3);
const OUT = path.join('docs', 'qa', 'speed', `${LABEL}.json`);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const QUIET = 500;

// Installed in every document before Streamlit's own scripts run.
const OBSERVER = () => {
  window.__last = performance.now();
  window.__t0 = null;
  window.__armed = false;
  new MutationObserver(() => { window.__last = performance.now(); }).observe(document, {
    subtree: true, childList: true, attributes: true, characterData: true,
  });
  const mark = (e) => { if (window.__armed && window.__t0 === null) window.__t0 = e.timeStamp; };
  window.addEventListener('pointerdown', mark, true);
  window.addEventListener('keydown', mark, true);
};

async function running(page) {
  return page.locator('[data-testid="stStatusWidget"]').count();
}
// Wait until the DOM has been quiet for QUIET ms and nothing is running; return the last change.
async function quiet(page, timeout = 90000) {
  const end = Date.now() + timeout;
  await sleep(150);
  while (Date.now() < end) {
    const idle = await page.evaluate(() => performance.now() - window.__last);
    if (idle >= QUIET && !(await running(page))) return page.evaluate(() => window.__last);
    await sleep(100);
  }
  throw new Error('page never went quiet');
}
async function settle(page) { await quiet(page); }

// Arm, run the tap, wait for quiet; ms from the tap's input event to the last DOM change.
async function timed(page, act) {
  await settle(page);
  await page.evaluate(() => { window.__t0 = null; window.__armed = true; });
  await act();
  const last = await quiet(page);
  const t0 = await page.evaluate(() => window.__t0);
  await page.evaluate(() => { window.__armed = false; });
  if (t0 === null) throw new Error('tap not seen');
  return Math.round(last - t0);
}

const main = (p) => p.locator('[data-testid="stMain"]');
const btn = (p, name) => main(p).getByRole('button', { name, exact: true }).first();
async function click(p, loc) { await loc.scrollIntoViewIfNeeded(); await loc.click(); }
async function tap(p, name) { await click(p, btn(p, name)); await settle(p); }
const pill = (p, label) => main(p).getByRole('radio', { name: label, exact: true }).first();

async function freshPage(browser) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, hasTouch: true, isMobile: true });
  await ctx.addInitScript(OBSERVER);
  // Diagnostic only (BLOCK_BASEMAP=1): drop the Carto basemap requests to see how much of a map
  // tap is the basemap download (internet) rather than the app.
  if (process.env.BLOCK_BASEMAP) await ctx.route(/cartocdn\.com/, (r) => r.abort());
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.locator('[data-testid="stMain"]').first().waitFor({ timeout: 120000 });
  await settle(page);
  return [ctx, page];
}

// ---- the owner's answers -----------------------------------------------------------------
const ANSWERS = {
  A: { other: 160000, where: 'Κοντά σε μετρό/ΗΣΑΠ', age: null /* default: Νεόδμητο */ },
  B: { budget: '250 χιλ. €', where: 'Όπου βγαίνει ο καλύτερος αριθμός', age: 'Οτιδήποτε' },
};
async function toStep4(p, a) {
  await tap(p, 'Να αγοράσω');
  if (a.other) {
    await click(p, main(p).getByText('Άλλο ποσό', { exact: true }).first()); await settle(p);
    const box = main(p).getByRole('spinbutton').first();
    await box.fill(String(a.other)); await box.press('Tab'); await settle(p);
    await tap(p, 'Συνέχεια');
  } else await tap(p, a.budget);
  await tap(p, 'Απόδοση ενοικίου');
  await tap(p, a.where);
  if (a.age) { await click(p, main(p).getByText(a.age, { exact: true }).first()); await settle(p); }
}
async function toResult(p, a) { await toStep4(p, a); await tap(p, 'Η πρότασή μου'); }
async function shownCount(p) { // «Βλέπεις N από M.»
  return main(p).getByText(/^Βλέπεις \d+ από \d+/).first().innerText().catch(() => '(no count)');
}

// ---- the taps ------------------------------------------------------------------------------
// prep: unmeasured steps from a fresh session; act: the measured tap; check: proof it worked.
const TAPS = [
  { id: 'step0-step1', name: 'Οδηγός: βήμα 0 → βήμα 1 («Να αγοράσω»)',
    act: (p) => click(p, btn(p, 'Να αγοράσω')),
    check: (p) => main(p).getByText('Πόσα θες να βάλεις;').count() },
  { id: 'budget-chip', name: 'Οδηγός: κουμπί ποσού («250 χιλ. €»)',
    prep: (p) => tap(p, 'Να αγοράσω'),
    act: (p) => click(p, btn(p, '250 χιλ. €')),
    check: (p) => main(p).getByText('Τι σε νοιάζει πιο πολύ;').count() },
  { id: 'result-a', name: '«Η πρότασή μου»: 160 χιλ. · απόδοση · μετρό · νεόδμητο',
    prep: (p) => toStep4(p, ANSWERS.A),
    act: (p) => click(p, btn(p, 'Η πρότασή μου')),
    check: shownCount },
  { id: 'result-b', name: '«Η πρότασή μου»: 250 χιλ. · απόδοση · όπου βγαίνει · οποιαδήποτε ηλικία',
    prep: (p) => toStep4(p, ANSWERS.B),
    act: (p) => click(p, btn(p, 'Η πρότασή μου')),
    check: shownCount },
  { id: 'more-10', name: '«Δείξε άλλες 10» (απαντήσεις B)',
    prep: (p) => toResult(p, ANSWERS.B),
    act: (p) => click(p, main(p).getByRole('button', { name: /^Δείξε άλλες/ }).first()),
    check: shownCount },
  { id: 'details', name: '«Λεπτομέρειες» (1η κάρτα, απαντήσεις B)',
    prep: (p) => toResult(p, ANSWERS.B),
    act: (p) => click(p, btn(p, 'Λεπτομέρειες')),
    check: (p) => btn(p, 'Πίσω').count() },
  { id: 'guide-map', name: 'Οδηγός: διακόπτης «Χάρτης» (απαντήσεις B)',
    prep: (p) => toResult(p, ANSWERS.B),
    act: (p) => click(p, main(p).locator('.st-key-guide_map label').first()),
    check: (p) => main(p).locator('[data-testid="stDeckGlJsonChart"]').count() },
  { id: 'search-typed', name: 'Αναζήτηση: το παράδειγμα του πλαισίου, «Αναζήτηση»',
    prep: async (p) => {
      await click(p, pill(p, 'Αναζήτηση')); await settle(p);
      await main(p).locator('input[type="text"]').first().fill('δυάρι στον Χολαργό έως 180.000 €, από 60 τ.μ., με ανελκυστήρα');
    },
    act: (p) => click(p, btn(p, 'Αναζήτηση')),
    check: (p) => main(p).locator('.hg-count').first().innerText() },
  { id: 'search-example', name: 'Αναζήτηση: κουμπί παραδείγματος «Δυάρι στον Χολαργό»',
    prep: async (p) => { await click(p, pill(p, 'Αναζήτηση')); await settle(p); },
    act: (p) => click(p, btn(p, 'Δυάρι στον Χολαργό')),
    check: (p) => main(p).locator('.hg-count').first().innerText() },
  ...['Περιοχές', 'Αναζήτηση', 'Χάρτης', 'Αγαπημένα', 'Σύγκριση'].map((label) => ({
    id: `pill-${label}`, name: `Μπάρα: «${label}» (από τον Οδηγό)`,
    act: (p) => click(p, pill(p, label)),
    check: async (p) => (await pill(p, label).getAttribute('aria-checked')) || '?',
  })),
  { id: 'pill-Οδηγός', name: 'Μπάρα: «Οδηγός» (από την Αναζήτηση)',
    prep: async (p) => { await click(p, pill(p, 'Αναζήτηση')); await settle(p); },
    act: (p) => click(p, pill(p, 'Οδηγός')),
    check: (p) => btn(p, 'Να αγοράσω').count() },
];

const median = (xs) => { const s = [...xs].sort((a, b) => a - b); return s[Math.floor(s.length / 2)]; };
function save(results) {
  const prev = fs.existsSync(OUT) ? JSON.parse(fs.readFileSync(OUT, 'utf8')) : {};
  fs.writeFileSync(OUT, JSON.stringify({ ...prev, ...results }, null, 1));
}

async function cold(browser) {
  const a = COLD === 'cold-a' ? ANSWERS.A : ANSWERS.B;
  const t = Date.now();
  const [ctx, page] = await freshPage(browser); // navigation start = 0 on the page's clock
  const load = Math.round(await page.evaluate(() => window.__last));
  await toStep4(page, a);
  const result = await timed(page, () => click(page, btn(page, 'Η πρότασή μου')));
  const out = JSON.parse(fs.existsSync(OUT) ? fs.readFileSync(OUT, 'utf8') : '{}');
  const key = COLD === 'cold-a' ? 'cold-result-a' : 'cold-result-b';
  for (const [k, v] of [['cold-load', load], [key, result]]) {
    out[k] = out[k] || { name: k, samples: [] };
    out[k].samples.push(v); out[k].median = median(out[k].samples);
  }
  out['cold-load'].name = 'Πρώτο άνοιγμα μετά από επανεκκίνηση (navigation → τελευταία αλλαγή)';
  out[key].name = `«Η πρότασή μου» ${COLD === 'cold-a' ? 'A' : 'B'}, πρώτη μετά από επανεκκίνηση`;
  fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
  console.log(COLD, 'load', load, 'ms; result', result, 'ms; wall', Date.now() - t, 'ms');
  await ctx.close();
}

(async () => {
  const browser = await chromium.launch();
  if (COLD) { await cold(browser); await browser.close(); return; }
  const results = {};
  for (const t of TAPS) {
    if (ONLY && !ONLY.includes(t.id)) continue;
    const samples = []; let check = '';
    for (let i = 0; i < RUNS; i++) {
      const [ctx, page] = await freshPage(browser);
      try {
        if (t.prep) await t.prep(page);
        samples.push(await timed(page, () => t.act(page)));
        check = String(await t.check(page));
      } catch (e) { console.log(t.id, 'run', i, 'FAILED', e.message.split('\n')[0]); }
      await ctx.close();
    }
    results[t.id] = { name: t.name, samples, median: samples.length ? median(samples) : null, check };
    console.log(t.id.padEnd(16), String(results[t.id].median).padStart(6), 'ms', JSON.stringify(samples), check);
    save(results);
  }
  await browser.close();
})();
