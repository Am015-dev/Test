# Final QA — round 3, merged `main` (5b96a27) on a 390×844 phone, 2026-10-31

Evidence: the app run from `main` against the published DB (`data` branch, 24.331 rows, data up
to 30/10; status line «XE.gr, Green-Acres · 30/10 · 11.150 ενεργές · 1.501 ελεγμένες»), with
no `GITHUB_TOKEN` and no `ANTHROPIC_API_KEY` in the app's environment. Chromium, touch, 390×844;
desktop 1280×800 for the home and areas pages only. Re-run: `NODE_PATH=$(npm root -g) node
docs/qa/shots.js docs/qa/final` (app on :8501; flow (e) also needs the stubbed instance on :8502,
see «Method notes»). Every file below is in `docs/qa/final/` (`.png` full page, `.txt` page
text, `overflow.json` per shot).

## Gate

| check | result |
|---|---|
| `python -m pytest -q` (GAUNTLET unset) | **742 passed, 2 skipped** (5 min 45 s) |
| `ruff check src/ tests/ scripts/` | all checks passed |
| `black --check src/ tests/ scripts/` | 159 files unchanged |
| `LIVE_DB=data/listings.db pytest -q tests/test_copy.py tests/test_search_honours_filters.py` | **18 passed** (1 min 11 s) |

## Definition of done

| # | line | verdict | proof |
|---|---|---|---|
| 1a | Every main-nav page renders on 390 px without horizontal scroll | **PASS** | `overflow.json`: `scrollWidth` = 390 on all 26 shots. One clipped element: a slider (`Τιμή έως`, right edge 479 px) on «Χάρτης» inside the collapsed «Φίλτρα» panel (`b1-map-card-under-map.png`); not visible, not scrollable (defect 12) |
| 1b | Answer above the fold | **PARTIAL** | Guide step 1–4 and result sentence: yes (`a1`–`a5`). Areas: decision box yes (`c1`). Search: the count and the hidden-reasons line are above the fold, the first card is not (starts below y≈844; `f0-search-default.png`). Map: map yes, but the selected card starts at y≈1.150, below the fold (`b1`); 4 grey lines above the map (defect 9) |
| 1c | No English, raw keys or decoration | **FAIL** | No English except the brand «Green-Acres» and the OS-level «Skip to main content» in the DOM. No `None`/`N/A`. But symbols on every card: `✓ ✗ ↗ ☆ ‹ ›` (guide result: 10 `✓`, 10 `✗`, 10 `↗` per 10 cards, `a5-guide-result.txt`), and «n=» ×16 on each areas page (`c1-areas-decision.txt`) |
| 2 | No under-construction, render-only or unchecked flat shown as verified | **PASS** (caveat) | Guide cards: «Ελέγχθηκε η περιγραφή (31/10/2026) — δεν αναφέρει κατασκευή σε εξέλιξη» and, for 2025/26 builds, «Έλεγξε: Έτος κατασκευής φέτος: βεβαιώσου ότι έχει παραδοθεί και έχει άδεια» (`a5`). Map/search/listing: orange «Δεν έχει ελεγχθεί ακόμα» badge (`b1`, `d1`). Caveat: no card says anything about photos, so render-only flats cannot be flagged (`image_url` exists for ~160 rows) |
| 3 | Every number on a card has its basis within one tap | **PASS** | Guide cards: «Από πού βγαίνουν» expander; listing page: formulas for rent, gross and net yield, comps range (`d1-listing-page.txt`); areas rows carry their basis in the label |
| 4 | Filters honoured; count says what was hidden and why | **PASS** | `f1-search-filtered.txt`: «276 αγγελίες · Κρύβονται 10.874: 38 όχι κατοικία · 327 με στοιχεία που δεν στέκουν · 3.667 εκτός τιμής · … · 2.228 κάτω από 2ο όροφο · 3.107 κτίριο πριν το 2015 · 265 χωρίς όροφο/έτος» after year ≥ 2015, floor ≥ 2, price ≤ 300.000 |
| 5 | Gate green; phone screenshots of every page in `docs/qa/final/` | **PASS** | Gate table above; guide, areas, search, map, favourites, compare, listing page, sidebar, filtered search all present. «Αποθηκευμένες αναζητήσεις» is not a pill and was not shot |

### Round-3 spec lines checked on top

| line | verdict | proof |
|---|---|---|
| Guide: 5 steps, one question each, progress line, chips reopen a step, «Δείξε άλλες 10» | **PASS** | `a1`–`a4` (Βήμα n από 5), `a5` (10 cards), `a6` (20 cards), `a7` (tap on «300 χιλ.» returns to step 1) |
| Map: tap on a point selects the card under the map | **PASS** | `b-map-selection.json`: header «1 από 8.070» → Επόμενο «2 από 8.070» → tap on canvas «1894 από 8.070»; `b3-map-after-tap-point.png` |
| Areas: new rows (Τάση €/τ.μ., Ρευστότητα, Προσφορά ανά αγγελία ενοικίασης, Γραμμή 4) | **PASS** (present) | `c2-areas-first-card-open.png`; Γραμμή 4 on Γαλάτσι: «Άλσος Βεΐκου, Γαλάτσι, Ελικώνος (ορίζοντας 2032)». Two of the four rows are «άγνωστη» for every area (defect 4) |
| Listing page: the six investor checks | **FAIL** | `d1-listing-page.txt` has none of the six lines; `area_insights.investor_checks` has no caller in `src/` (defect 1) |
| Days on market from the earliest evidence | **PASS** | `d1`: «109 μέρες στην αγορά (από τότε που τη βλέπουμε)» for a flat first seen 14/07; guide: «233 μέρες στην αγορά (από την ημερομηνία αγγελίας)»; re-posted ad: «η αγγελία ανανεώθηκε 05/09» |
| Status line shows the real sources | **PASS** | «XE.gr, Green-Acres · 30/10 · …» on every page; Golden Home does not appear because the published DB predates it (no rows) |
| Sign-in with name + PIN | **FAIL without a token** | `e0-sidebar-no-token-real-config.png`: sidebar shows only «Χωρίς σύνδεση: οι επιλογές σου μένουν μόνο σε αυτή την καρτέλα.»; no form, so the «session-only» sign-in does not exist (defect 6). With the gist stubbed in memory sign-in works: `e3`, `e4` «Συνδεδεμένος ως Δοκιμή QA» + «Αποσύνδεση» |
| «Ρώτα με» / «Σημείωμα επενδυτή» | **NOT VERIFIED** | No `ANTHROPIC_API_KEY` in this environment: the panel is hidden as specified and the brief was not captured (`a5-guide-result.txt` has no «Σημείωμα»). Needs a run with a key |
| Guide result sentence states the budget band when the top pick is above budget | **FAIL** | Defect 2 |
| «Σύγκριση» info text says «Βρες μου σπίτι» | **FAIL (code)** | Defect 7 |

## Defects (numbered, most severe first)

| # | sev | page | what the owner sees | what it should be | owning file |
|---|---|---|---|---|---|
| 1 | blocks | Αγγελία (from «Λεπτομέρειες») | Price, rent, yield, comps, price history. None of the six checks the brief promises (τιμή vs παρόμοια · απόδοση · ρευστότητα περιοχής · ζήτηση ενοικίου · νομικά/κανονιστικά · έξοδος). The function exists (`area_insights.investor_checks`) but nothing calls it | The labelled six-line list on the listing page, with «άγνωστο» where history is missing | `src/scout/ui/buyer.py` (page_listing) |
| 2 | ugly | Οδηγός result | After 300 χιλ.: «Πρόταση: Νέα Ιωνία — 6 από τις 20 αγγελίες της λίστας …» then «20 αγγελίες 264.000 €–336.000 €, …». Card 1 costs 335.000 € and sits in Άγιος Δημήτριος, not in the recommended area; nothing says the range is ±12 % around the answer or that card 1 is above 300.000 € | One clause: «Εύρος 12 % γύρω από 300.000 € (264.000–336.000 €); η 1η είναι 35.000 € πάνω». And the area named in the sentence should be the area of card 1, or say why not | `src/scout/ui/guide.py` (`_results`, sentence builder) |
| 3 | ugly | Οδηγός result, Χάρτης, Αναζήτηση, Αγαπημένα | Symbols on every card: «✓ Εγκρίνω», «✗ Δεν μου κάνει», «Στο XE.gr ↗», «☆ Αγαπημένο», «‹ Προηγούμενο», «Επόμενο ›»; 30 glyphs per 10 guide cards | Plain words («Εγκρίνω», «Δεν μου κάνει», «Άνοιγμα στο XE.gr», «Αγαπημένο»); the copy test passes only because it does not scan button labels | `src/scout/ui/guide.py:648,667,675`, `buyer.py:436,477,1364`, `maplist.py:145`, `tests/test_copy.py` |
| 4 | ugly | Πού να αγοράσω | «n=» in 16 places: «νεόδμητα 58 % ακριβότερα από τα παλιά (n=50/243)», «Τάση €/τ.μ.: -1,1 % από τον Ιούλιο (… n=174/313)», «Για ανατίμηση: Χολαργός, +2,9 % … (n=84/148)». «Ρευστότητα: άγνωστη — χρειάζεται ιστορικό σαρώσεων, πρώτη τακτική 30/10» on all 9 cards; «Προσφορά ανά αγγελία ενοικίασης: άγνωστη» on all 9 | «σε 50 νεόδμητα και 243 παλιά»; one clause for unknowns: «Ρευστότητα: δεν ξέρουμε ακόμα». If the row is unknown on every area, drop it from the card and say it once in the method box | `src/scout/area_insights.py:501–611`, `ui/areas.py` |
| 5 | ugly | Πού να αγοράσω | «Οι 3 πρώτες: 1. Γαλάτσι — Μικτή απόδοση 4,3 % (12η από 16)», no station, rent «δείγμα ενοικίων μη καταγεγραμμένο», yet «Εμπιστοσύνη: Μέτρια»; the top box says «Για απόδοση: Νέο Ψυχικό». Intro counts «14 περιοχές» but the rank says «από 16». Same trust problem as baseline #6 | Rank 1 must be explainable from the parts; confidence «Χαμηλή» when the rent sample is unknown; one area count | `area_insights.py` (ranking, confidence), `ui/areas.py` |
| 6 | ugly | Sidebar (no token) | Only «Χωρίς σύνδεση: οι επιλογές σου μένουν μόνο σε αυτή την καρτέλα.»; no name/PIN form. If the deployed secrets lack `GITHUB_TOKEN`, the owner cannot sign in at all | Show the form with the line that choices stay in this tab, or state why sign-in is unavailable | `src/scout/ui/account.py` (`login_ui`) |
| 7 | nit | Σύγκριση (empty state) | Code: «Διάλεξε δύο αγγελίες — ή άνοιξε «Βρες μου σπίτι» για να δεις τις καλύτερες.» while the nav pill reads «Οδηγός». Not on screen in my run (compare was prefilled); appears with fewer than 2 listings | «… ή άνοιξε τον «Οδηγό» …» | `src/scout/ui/app.py:2330` |
| 8 | nit | Αναζήτηση / Αγγελία | Default sort is «Τιμή σε σχέση με παρόμοια», so the cheapest-vs-comps flat comes first. First default result: 140.000 €, 2.000 €/τ.μ., «Παρόμοια (8): 35 % κάτω», «Δεν έχει ελεγχθεί ακόμα», shown as the top card with no «ύποπτα φθηνό» line. The listing page repeats «109 μέρες στην αγορά (από τότε που τη βλέπουμε)» twice | A 35 % gap is the `too_cheap` threshold: say so; print the days once | `src/scout/ui/buyer.py`, `market_intel.py` |
| 9 | nit | Χάρτης | 4 grey lines above the map («Μόνο 23 αγγελίες έχουν ακριβή θέση· … 1.674 υπό κατασκευή δεν εμφανίζονται · 7.505 δεν έχουν ελεγχθεί ακόμα (δεν ξέρουμε αν είναι έτοιμες). Εμφανίζονται οι πρώτες 1.500 …»); map ends at y≈1.000 and the selected card starts at y≈1.150 | Map first, one line of facts, card above the fold | `src/scout/ui/maplist.py`, `app.py` (page_map) |
| 10 | nit | Σύγκριση | «Έτος 2025 (1 ετών)» (wrong plural, also in baseline #17); «Παρόμοια −24% €/τ.μ.» without the space the rest of the app uses («24 % κάτω») | «1 έτους»/«1 έτος»; one format | `src/scout/ui/app.py:2256` |
| 11 | nit | Οδηγός result | Coverage line is last on the page: «Πηγές: Green-Acres, XE.gr · 11.150 αγγελίες ενεργές …» (alphabetical, XE not first; the status line on top lists XE first). Golden Home is absent (published DB has no rows from it) | Same order everywhere; coverage line under the sentence | `src/scout/ui/guide.py` |
| 12 | nit | Χάρτης | Hidden range slider `Τιμή έως` reaches x = 479 inside the collapsed filter panel; the page does not scroll | Keep inside the viewport | `src/scout/ui/maplist.py` / `app.py` |

## What I could not check

- The assistant (`«Ρώτα με»`, `«Σημείωμα επενδυτή»`): no API key here. The fixed text and
  grounding checks are covered by `tests/test_advisor.py`, not by a screenshot.
- Real gist storage: the throwaway profile was written to an in-memory stand-in, never to a
  real gist.
- Photos: cards carry no photo fact, so «render-only» flats cannot be told apart.

## Method notes

- `docs/qa/shots.js` now drives the pills (`role=radio`, text «Οδηγός», «Περιοχές», «Αναζήτηση»,
  «Χάρτης», «Αγαπημένα», «Σύγκριση»; the pill for «Πού να αγοράσω» is «Περιοχές») and writes
  flows a–h; flow (b) taps the deck.gl canvas like `docs/qa/maplist/tap.js` and records the
  card header before and after in `b-map-selection.json`.
- Flow (e) sign-in needs storage. Without a token the form is hidden (defect 6), so a second
  instance on :8502 runs `docs/qa/final/qa_app.py` — the unmodified app with only
  `shortlist._gh` replaced by an in-memory dict and a dummy token string. `e0` is the real
  no-token sidebar; `e1`–`e4` come from the stand-in. PIN `4821` is a throwaway.
- Secrets: the sandbox has a real `GITHUB_TOKEN`; the app was started with it unset. No key or
  token appears in any file here.
