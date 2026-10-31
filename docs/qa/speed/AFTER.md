# C13 — speed: AFTER (side by side with BEFORE)

**BEFORE:** `main` at 7caf9c1 (after #92, no C13 change), clean worktree.
**AFTER:** `ws/speed` merged with `main` at 286b008 (#98 card photos included).
Same machine, same published DB, same protocol (`BEFORE.md`): fresh session per run, 3 runs,
median; cold rows = 3 server restarts per answer set. ✗ = over 1,5 s (cold guide result: 2 s).

| Tap | before | after | αλλαγή | samples (ms) |
|---|---|---|---|---|
| Πρώτο άνοιγμα μετά από επανεκκίνηση (navigation → τελευταία αλλαγή) | 7,31 s | 7,60 s | +4 % | 7372,7312,7181,7366,7228,7085 / 7599,7457,7512,7589,7663,7948 |
| «Η πρότασή μου» A, πρώτη μετά από επανεκκίνηση | 1,62 s ✓ | 1,45 s ✓ | -11 % | 1522,1618,1689 / 1470,1446,1358 |
| «Η πρότασή μου» B, πρώτη μετά από επανεκκίνηση | 1,51 s ✓ | 1,30 s ✓ | -14 % | 1469,1599,1507 / 1300,1356,1298 |
| Οδηγός: βήμα 0 → βήμα 1 («Να αγοράσω») | 0,49 s ✓ | 0,46 s ✓ | -6 % | 418,486,490 / 456,479,437 |
| Οδηγός: κουμπί ποσού («250 χιλ. €») | 0,33 s ✓ | 0,32 s ✓ | -4 % | 378,334,320 / 356,299,319 |
| «Η πρότασή μου»: 160 χιλ. · απόδοση · μετρό · νεόδμητο | 1,61 s ✗ | 0,87 s ✓ | -46 % | 1662,1611,1514 / 957,803,866 |
| «Η πρότασή μου»: 250 χιλ. · απόδοση · όπου βγαίνει · οποιαδήποτε ηλικία | 1,52 s ✗ | 0,54 s ✓ | -64 % | 1517,1638,1495 / 569,540,517 |
| «Δείξε άλλες 10» (απαντήσεις B) | 1,48 s ✓ | 0,55 s ✓ | -63 % | 1436,1514,1478 / 508,554,556 |
| «Λεπτομέρειες» (1η κάρτα, απαντήσεις B) | 0,79 s ✓ | 0,58 s ✓ | -26 % | 2217,793,755 / 1869,564,584 |
| Οδηγός: διακόπτης «Χάρτης» (απαντήσεις B) | 2,67 s ✗ | 1,69 s ✗ | -37 % | 2704,2563,2671 / 1720,1621,1686 |
| Αναζήτηση: το παράδειγμα του πλαισίου, «Αναζήτηση» | 1,17 s ✓ | 0,93 s ✓ | -20 % | 1142,1201,1170 / 930,993,934 |
| Αναζήτηση: κουμπί παραδείγματος «Δυάρι στον Χολαργό» | 0,89 s ✓ | 0,68 s ✓ | -23 % | 894,829,908 / 684,684,661 |
| Μπάρα: «Περιοχές» (από τον Οδηγό) | 1,65 s ✗ | 1,42 s ✓ | -13 % | 1795,1248,1645 / 1998,1400,1423 |
| Μπάρα: «Αναζήτηση» (από τον Οδηγό) | 1,31 s ✓ | 1,03 s ✓ | -22 % | 1312,1312,1226 / 1044,1004,1026 |
| Μπάρα: «Χάρτης» (από τον Οδηγό) | 3,52 s ✗ | 1,88 s ✗ | -47 % | 3565,3517,3334 / 2973,1877,1835 |
| Μπάρα: «Αγαπημένα» (από τον Οδηγό) | 0,39 s ✓ | 0,41 s ✓ | +5 % | 391,354,385 / 405,419,383 |
| Μπάρα: «Σύγκριση» (από τον Οδηγό) | 1,63 s ✗ | 1,01 s ✓ | -38 % | 1679,1475,1632 / 1371,1006,1002 |
| Μπάρα: «Οδηγός» (από την Αναζήτηση) | 0,40 s ✓ | 0,40 s ✓ | -1 % | 376,399,408 / 397,385,408 |

**Results unchanged:** `tests/test_speed_identity.py` drives the real app on this DB and compares
with a golden captured on the pre-cache code of the same `main` (286b008): the first ten picks
for both of the owner's answer sets, the first ten hits of six searches, the map's ranked list,
the compare page's default pair, the HTML of every card shown, and a hash of the buyer score of
all 25.921 listings — identical. The map at 390 px: 0,00 % of pixels differ
(`map-before.png`, `map-after.png`).

## The three map taps: server done ≤ 0,75 s, the rest is deck.gl in the browser

`map_split.js` (3 fresh sessions each, medians): **server** = tap → the rerun's last websocket
frame; **total** = tap → last DOM change.

| Tap | server | browser (rest) | total |
|---|---|---|---|
| Μπάρα «Χάρτης» | 0,70 s | 1,07 s | 1,77 s |
| Μπάρα «Περιοχές» | 0,48 s | 0,99 s | 1,47 s |
| Οδηγός: «Χάρτης» | 0,66 s | 0,97 s | 1,63 s |

After the last frame the browser loads deck.gl's chunk (first map of a session), builds the
mapbox canvas and lays it out (its last resize lands ~0,9–1,1 s after the server is done). The
basemap is not the cause: with the Carto requests blocked (`BLOCK_BASEMAP=1`) the guide's map
is 1,66 s and the map pill 1,89 s.

## What changed

* `market_intel.kind()` memoised by title (the largest single cost on every page).
* `market_intel.share()`: one comparables index per data version, handed read-only to every
  `market_intel.build(listings)` on the app's list (guide, search, map, compare, favourites,
  listing page); `_SHARED` keeps only the current version so an old list is freed.
* `app.get_listings`: one shared list per data version — `cache_resource` keyed by (data file
  path, mtime, row count), `max_entries=1`.
* `ui/derived.py` (new): per-data-version, read-only values keyed by that list — the map's
  scored rows (the 9.124 visible ones only, not 25.921 copies), their buyer views and default
  order (a rerun filters the ordered list); the compare pool and its scores; the status line;
  the guide's area facts, coverage line and `picks.find`'s per-listing memo (`find` itself and
  `picks.buyer_score` untouched).
* `components.results_map`: the same pydeck spec as compact JSON (no indent, Greek as UTF-8,
  without the unused `title` column) — 1.500 points 1,5 MB → 0,59 MB; a test proves the parsed
  spec is equal.

## Not done / still slow

* Cold page load after a restart is ~7,5 s (was ~7,3 s): `load_listings` materialises 26.758
  rows (~7 s) and now also builds the shared index once. Not a tap; out of C13's list.
* The first «Λεπτομέρειες» after a restart is ~1,9 s: `areas._ranked` (cache_data in
  `ui/areas.py`, not mine) is filled once per process; later ones ~0,58 s.
* The searches return 0 hits on this DB (no Χολαργός listing matches the examples).

Files: `after.json` / `after.log` (raw), `map_split.json`, `measure_speed.js`, `run_all.sh`,
`serve.sh`, `profile_app.py` + `top.py` (cProfile per rerun), `report.py` (these tables).
