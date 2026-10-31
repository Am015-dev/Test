# QA baseline — the app as the owner sees it on a phone (2026-10-31)

Evidence: live DB (`data` branch, 24.331 listings, data up to 30/10) served by the app from
`main`, no `GITHUB_TOKEN` (favourites session-only). Chromium, 390×844 touch + 1280×800.
Screenshots: `docs/qa/baseline/<nn>-<page>-<viewport>.png` (full page), page text
`<same>.txt`, overflow metrics `overflow.json`. Re-run: `NODE_PATH=$(npm root -g) node docs/qa/shots.js
[outDir] [baseUrl]` (app must be running on :8501). Paths below are relative to `docs/qa/baseline/`.

## Headline numbers

| measure | result |
|---|---|
| English strings visible | 4 in copy: «renders» (find), «top 20» (map), «Property Scout» (sidebar title, every page), «Choose an option» (Streamlit placeholder, not seen in text dump; not verified visually). Raw Streamlit leak: «5 options available.» in the page text after a selectbox pick (09-search-filtered-phone.txt) |
| Non-Greek number formats (`1,234.5`) | 0 found in all 12 phone text dumps |
| Raw keys / None / N/A | 0 in text. (Material icon names `keyboard_double_arrow_right` appear in the DOM text only; they render as icons) |
| Decoration emoji / symbols | 🔄 on every page (refresh button), ✓ ✗ ☆ ↗ ▲ ▼ ≈ on cards; 57 symbol glyphs on one filtered search screen |
| Pages with horizontal overflow at 390 px | **2**: «Πού να αγοράσω» (table right edge 403 px), «Χάρτης» (inputs 497 px, data grid 665 px). The document itself never scrolls sideways (`scrollWidth` = 390), so content is clipped, not scrollable |
| Cards presenting an unchecked flat as normal | «Βρες μου σπίτι» top 3: 2 of 3 unchecked but shown as «Γιατί αυτό» cards with the same layout. «Αναζήτηση» (filtered view 2015+/2ο+): 1.145 results, **179 checked, 966 (84 %) look identical** and the page never mentions checking. Dataset: 675 of 24.331 (2,8 %) pages checked |
| Answer below the fold at 390 px | «Αναζήτηση» (first result at y≈1.400), «Χάρτης» (map at y≈815 after 6 controls; first listing only in the table at y≈1.480), «Βρες μου σπίτι» (only the price is above 844; rent/yield at y≈880) |

## Defects, ranked

S1 = trust/misleading · S2 = unusable on phone · S3 = confusing/inconsistent · S4 = cosmetic.

| # | Sev | Page | What is seen (exact) | Screenshot | Proposed fix |
|---|---|---|---|---|---|
| 1 | S1 | Αναζήτηση, Αγγελία, area listings, Χάρτης | Result cards carry no check status at all (0 mentions of «ελέγχ»/«υπό κατασκευή»). 966 of 1.145 results are not page-checked yet look verified | 09-search-filtered-phone.png, 08-detail-phone.png | Show «Δεν έχει ελεγχθεί ακόμα» / «Ελέγχθηκε η περιγραφή» badge from `d["page_checked"]` on every card |
| 2 | S1 | Βρες μου σπίτι | Headline «Αυτές είναι οι 3 με την καλύτερη απόδοση και τιμή» while 2 of the 3 cards are unchecked (rank 1 is the only checked one; 9 of 10 top picks unchecked). After rejecting card 1 the line reads «Ελεγμένες σελίδες αγγελιών: 0 από 38» yet three flats are still presented as the best | 01-find-phone.png, 10-find-rejected-phone.png | Rank checked above unchecked and say «κανένα δεν έχει ελεγχθεί» in the headline when 0; do not call unchecked picks «καλύτερα» |
| 3 | S1 | Αγγελία (detail), cards | «Σκορ 80» with «τιμή vs παρόμοια ▲ · ηλικία ▲ · απόδοση ≈» but the comps block says «Δεν υπάρχουν αρκετά παρόμοια (ίδια περιοχή και ηλικία) για σύγκριση» – the score claims a vs-comps advantage it has no comps for. Score has no parts/numbers | 08-detail-phone.png | Drop the ▲/▼ for any part lacking data; show the numeric parts or remove the score |
| 4 | S1 | Αγγελία, search cards | Same listing: «108 μέρες στην αγορά» next to «(από 29/10/2026, ημερομηνία αγγελίας)» = 2 days. Days are counted from our `first_seen` (14/07), not the listing date | 08-detail-phone.png | Use one date: listing date if present, otherwise say «από την πρώτη φορά που το είδαμε» |
| 5 | S1 | Αναζήτηση | Implausible card shown as a top result: «Μονοκατοικία 287 τ.μ., Γλυκά Νερά, 440.000 €, 1.533 €/τ.μ., 2ος όροφος, ενοίκιο ~3.420 €/μήνα · μικτή απόδοση 9,3 %, Σκορ 75». House with a floor number, a yield 2× its neighbours. Rent is `est €/τ.μ. × τ.μ.` on 287 m² | 09-search-filtered-phone.png | Cap rent estimate by size band (or hide yield) for >150 m² / houses; flag price/area outliers |
| 6 | S1 | Πού να αγοράσω | Every area card: «δείγματα ενοικίου: —» and risk «Ο αριθμός δειγμάτων του ενοικίου δεν έχει καταγραφεί.» yet «Εμπιστοσύνη: Μέτρια» and «μικτή απόδοση 4,8 %» in bold; «Σκορ 59,6/100» with no parts | 02-areas-phone.png | If rent sample count is unknown, confidence = Χαμηλή and yield labelled «δεν επαληθεύεται»; list the score parts |
| 7 | S1 | Βρες μου σπίτι | Rank-1 card: «Προσφορά: ξεκίνα από ~315.000 €» and «φθηνότερο από τα 3 στα 4» while the model's own risks (hidden) say DSCR 0,58, «δεν βγαίνει ούτε με 100 % πληρότητα», 233 days on market. Positive «Γιατί αυτό» shown, the negative is not | 01-find-phone.png | Surface the financing/DSCR risk under «Έλεγξε» or drop the offer line |
| 8 | S2 | Σελίδα συνολικά (phone) | After choosing a page in the drawer, the drawer stays open and covers the page until the user finds «««». Captured: drawer open over every page after click (initial load is collapsed) | (visible in a run before the script closed it; the script now closes it) | Collapse the sidebar on navigation (or use top tabs / `st.navigation(position="top")`) |
| 9 | S2 | Χάρτης | 6 stacked controls (checkbox truncated «Απόκρυψη εκτός κριτηρίων, ύποπτων & ημιτε…», multiselect, 3 sliders) before the map; map = 5.000 overlapping dots in a few blobs; table clipped at 665 px wide (Περιοχή cut: «Νέα Φιλαδέλφεια Αττικής») | 04-map-phone.png | Collapse the filters into an expander; cluster markers; make the table 2 columns |
| 10 | S2 | Πού να αγοράσω | «Όλες οι περιοχές» table is 403 px wide at the bottom (clipped, sort headers off-screen) | 02-areas-phone.png | Render as stacked cards on narrow screens or limit columns to name + score + yield |
| 11 | S2 | Αναζήτηση | 6 filters + 4 example chips + NL box before the first result (first card at y≈1.400, ≈1,7 screens). Filter set is bands only: no «από έτος 2015» control (the owner asked for min year) – «Έως 10 ετών» ≈ 2016+ | 03-search-phone.png, 09-search-filtered-phone.png | Put filters in an expander and results first; add a year-from input |
| 12 | S3 | Αναζήτηση | Default results silently hide 7.291 (floor <2 or no floor, older than 10 y, no year). The notice is a grey caption, then a separate «Δείξε όλες» button and a checkbox for 13.181 older listings | 09-search-filtered-phone.png | One line with count by reason, one action |
| 13 | S3 | Αναζήτηση | Sort default «Σκορ αγοράς» orders by an unexplained 0–100 number; legend repeated on each page | 09-search-filtered-phone.png | Default sort by Τιμή or by comps gap; explain in one tap |
| 14 | S3 | All | Three words for rent: «Ενοίκιο» (card), «ζητούμενο ενοίκιο» (area), «ενοίκιο μάλλον» (find). Glossary asks «Ενοίκιο (εκτίμηση)». The Find tile reads «Ενοίκιο ~1.070 €» with no «εκτίμηση» | 01-find-phone.png | One term everywhere per glossary |
| 15 | S3 | Αγαπημένα / Αποθηκευμένες / Αγγελία | Red error banner «Τα αγαπημένα δεν φορτώθηκαν (δεν επιτρέπεται η πρόσβαση στην αποθήκευση)…» and «Δεν μπόρεσα να διαβάσω τις αναζητήσεις: δεν επιτρέπεται η πρόσβαση στην αποθήκευση» when no token is configured (this run); also on detail and area-listing pages | 08-detail-phone.png, 06-saved-phone.png | Neutral one-liner «Τα αγαπημένα κρατιούνται μόνο σε αυτή τη συνεδρία», no red |
| 16 | S3 | Σύγκριση, Αγαπημένα | Pages are empty (844 px) with an instruction; compare starts with an empty picker even though the whole app has results | 07-compare-phone.png | Preselect favourites or the current top picks |
| 17 | S3 | Αγγελία | «κατασκευή 2025 (1 έτους)» wrong plural (all cards); «Ενοίκιο ~690 €/μήνα … (εκτίμηση περιοχής)» wraps over three lines | 09-search-filtered-phone.png | «1 έτος»; one-line label |
| 18 | S3 | Βρες μου σπίτι | Intro text says «Βρίσκω τα 3 καλύτερα» then the paragraph is 6 lines of instructions; «δες τις φωτογραφίες: αν είναι μόνο renders…» delegates verification to the owner; no photo is shown (image_url set for 160 of 24.331) | 01-find-phone.png | Say «δεν έχουμε φωτογραφίες· άνοιξε το XE»; remove «renders» |
| 19 | S4 | All | Symbols as decoration: 🔄 refresh, ✓ ✗ ☆ ↗, ▲ ▼ ≈ chips | 09-search-filtered-phone.png | Text labels |
| 20 | S4 | Sidebar | «Property Scout» (English title), «Αγγελία» listed as a nav item although it needs a selected listing | 00-first-load-phone.png | Greek title; hide the item |
| 21 | S4 | Χάρτης | «Οι καλύτερες στον χάρτη (top 20)» | 04-map-phone.png | «Οι 20 καλύτερες» |
| 22 | S4 | Βρες μου σπίτι | Metric tiles wrap 2 + 1 on 390 px («Καθαρή» alone), budget field has no € grouping («300000») | 01-find-phone.png | 3 stacked rows or a 3-column grid; format with thousands |

## Trust spot-check: `picks.find(L, I, R, 300_000, top=10)`

Loaded with the live DB (24.331 listings; 675 page-checked, 1.308 `is_unfinished`, 390 of those
are also `page_checked`). `photo_count` does not exist in the listing dict; `image_url` is None
for every pick (24.171 of 24.331 listings).

| # | Τιμή € | Περιοχή | Έτος | page_checked | is_unfinished | image_url | μέρες | ενοίκιο €/μ | μικτή |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 335.000 | Άγιος Δημήτριος Αττικής (Κέντρο) | 2025 | **True** | False | None | 233 | 1.070 | 3,8 % |
| 2 | 300.000 | Νέα Ιωνία (Περισσός) | 2025 | False | False | None | 108 | 1.170 | 4,7 % |
| 3 | 320.000 | Νέα Ιωνία (Περισσός) | 2024 | False | False | None | 108 | 1.050 | 3,9 % |
| 4 | 273.750 | Νέα Ιωνία (Κέντρο) | 2026 | False | False | None | 108 | 900 | 3,9 % |
| 5 | 270.000 | Νέα Ιωνία (Περισσός) | 2026 | False | False | None | 108 | 890 | 4,0 % |
| 6 | 280.000 | Νέα Ιωνία (Περισσός) | 2025 | False | False | None | 0 | 890 | 3,8 % |
| 7 | 300.000 | Άγιος Δημήτριος Αττικής (Κέντρο) | 2025 | False | False | None | 102 | 850 | 3,4 % |
| 8 | 320.000 | Νέα Ιωνία (Περισσός) | 2025 | False | False | None | 0 | 990 | 3,7 % |
| 9 | 276.000 | Αθήνα (Αμπελόκηποι) | 2025 | False | False | None | 0 | 800 | 3,5 % |
| 10 | 325.000 | Αθήνα (Αμπελόκηποι) | 2025 | False | False | None | 87 | 880 | 3,2 % |

Reading: 9 of 10 `is_unfinished = False` only because the page was never read (False here
means unknown). Rank 1 is page-checked but costs 335.000 € (top of the ±12 % band around 300.000 €)
and has DSCR 0,58 in its own risk list. Four listings with 108 identical days_on_market
(first_seen batch, see #4). Pick #1's `Pick.checked` = `page_checked`; for the others the card does carry the line
«δεν έχει ελεγχθεί ακόμα», so «Find» is honest in the risk list but not in the headline (#2).
Net: the top-10 are real station-area flats within the budget band; only 1 is verified and none has a photo.

## Optional: `GAUNTLET=1 pytest tests/test_ui_gauntlet.py -k every_widget`

Not completed: the run produced no output after ~10 minutes against the 24k-row DB and was
stopped (no pass/fail to report). Re-run it separately with a longer budget.
