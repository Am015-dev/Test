# C13 — speed: BEFORE

**Code:** `main` at 7caf9c1 (after #92, before any C13 change), run from a clean worktree.
**Data:** the published DB (`origin/data:listings.db`, 26.758 active sale rows, last seen
31/10/2026 19:38; 25.921 cards after the re-listing merge).
**Machine:** 4 vCPU Intel Xeon 2,1 GHz, 16 GB (GitHub-runner class), Chromium headless,
viewport 390×844 phone, app on `127.0.0.1` with no `ANTHROPIC_API_KEY` / `GITHUB_TOKEN`.

**How:** `docs/qa/speed/run_all.sh before` → `measure_speed.js`. A MutationObserver on the whole
document stamps every DOM change; a capture listener stamps the tap's `pointerdown`. Tap time =
last DOM change − tap, once the DOM has been quiet for 500 ms and Streamlit's running indicator
is gone. Every tap runs 3 times, each in a fresh browser context (a new Streamlit session)
brought to the state just before the tap by unmeasured steps; the table gives the median
(✗ = over 1,5 s; the cold guide result's budget is 2 s). The cold rows restart the server before
each run (3 per answer set) and time the first page load (navigation start → last DOM change)
and then the first guide result in that first session.

Owner's answers: **A** = 160 χιλ. («Άλλο ποσό») · απόδοση · κοντά σε μετρό · νεόδμητο;
**B** = 250 χιλ. · απόδοση · όπου βγαίνει ο καλύτερος αριθμός · οποιαδήποτε ηλικία.
The searches return 0 hits on this DB: no listing in Χολαργός matches either example (data,
not the timer — the page still renders its counts and the «Κρύβονται …» line).

| Tap | before | samples (ms) |
|---|---|---|
| Πρώτο άνοιγμα μετά από επανεκκίνηση (navigation → τελευταία αλλαγή) | 7,31 s | 7372,7312,7181,7366,7228,7085 |
| «Η πρότασή μου» A, πρώτη μετά από επανεκκίνηση | 1,62 s ✓ | 1522,1618,1689 |
| «Η πρότασή μου» B, πρώτη μετά από επανεκκίνηση | 1,51 s ✓ | 1469,1599,1507 |
| Οδηγός: βήμα 0 → βήμα 1 («Να αγοράσω») | 0,49 s ✓ | 418,486,490 |
| Οδηγός: κουμπί ποσού («250 χιλ. €») | 0,33 s ✓ | 378,334,320 |
| «Η πρότασή μου»: 160 χιλ. · απόδοση · μετρό · νεόδμητο | 1,61 s ✗ | 1662,1611,1514 |
| «Η πρότασή μου»: 250 χιλ. · απόδοση · όπου βγαίνει · οποιαδήποτε ηλικία | 1,52 s ✗ | 1517,1638,1495 |
| «Δείξε άλλες 10» (απαντήσεις B) | 1,48 s ✓ | 1436,1514,1478 |
| «Λεπτομέρειες» (1η κάρτα, απαντήσεις B) | 0,79 s ✓ | 2217,793,755 |
| Οδηγός: διακόπτης «Χάρτης» (απαντήσεις B) | 2,67 s ✗ | 2704,2563,2671 |
| Αναζήτηση: το παράδειγμα του πλαισίου, «Αναζήτηση» | 1,17 s ✓ | 1142,1201,1170 |
| Αναζήτηση: κουμπί παραδείγματος «Δυάρι στον Χολαργό» | 0,89 s ✓ | 894,829,908 |
| Μπάρα: «Περιοχές» (από τον Οδηγό) | 1,65 s ✗ | 1795,1248,1645 |
| Μπάρα: «Αναζήτηση» (από τον Οδηγό) | 1,31 s ✓ | 1312,1312,1226 |
| Μπάρα: «Χάρτης» (από τον Οδηγό) | 3,52 s ✗ | 3565,3517,3334 |
| Μπάρα: «Αγαπημένα» (από τον Οδηγό) | 0,39 s ✓ | 391,354,385 |
| Μπάρα: «Σύγκριση» (από τον Οδηγό) | 1,63 s ✗ | 1679,1475,1632 |
| Μπάρα: «Οδηγός» (από την Αναζήτηση) | 0,40 s ✓ | 376,399,408 |

Raw samples: `before.json`; console log: `before.log`.

## Where the time went (cProfile per rerun, `profile_app.py`; yappi through AppTest)

* `market_intel.kind()` NFD-normalised every title on every call: 73.000+ calls per guide
  rerun (`market_intel.build` and `area_insights`), the single largest cost on every page.
* `market_intel.build(listings)` rebuilt the comparables index on every rerun of the guide,
  search, map, compare, favourites and listing pages (same data, same result).
* The guide rebuilt `area_insights.rank_areas` and every `picks._build` (2.232 listings) on each
  rerun, though neither depends on the answers.
* «Χάρτης»: `buyer_scores` over all listings, 25.921 dict copies, a second index over the
  copies, `buyer_view` + `nl_search.match` for 9.124 visible listings — every rerun; then a
  1,7 MB pydeck JSON (indent=2, Greek escaped as `\uXXXX`, an unused `title` column).
* «Σύγκριση»: `buyer_scores` over 10.795 candidates every rerun.
* The status line under the title walked all listings three times on every rerun.
* The first «Λεπτομέρειες» after a restart (2,2 s) fills `areas._ranked` (cache_data); later
  ones read it.
