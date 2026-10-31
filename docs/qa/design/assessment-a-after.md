# Assessment A (after polish): Holargos Property Scout, Operate surface

**Method.** This is a design review only, done blind: I did not read AUDIT.md, assessment-a.md, POLISH.md, any measure files or anything under `docs/qa/design/` except the `after/*.png` screenshots. Sources:
- Method: `critique.md` (Assessment A, Cognitive Load, Heuristics, Personas) and `craft-floor.md`.
- Product facts: `docs/COORDINATION.md` (top sections and «Round 5 — C6»).
- Code: `src/scout/ui/*.py`, with `theme.py` read for tokens and selectors.
- Screenshots: all 22 screens in `docs/qa/design/after/` at 390 and 1280, cropped with PIL into `/tmp/assessA2/`.
- Live app: http://127.0.0.1:8503 with Playwright at 390×844. I took the map page at the top, read the text of the Areas page from the DOM, checked text size and colour on the home page, checked the focus ring, and measured the sidebar toggle.

Limits:
- «Ρώτα με» does not render because there is no API key, so it is not assessed.
- Favourites last only for the session, so the Αγαπημένα and Σύγκριση flows were judged from screenshots.

---

## 1. Design-specificity verdict

**Verdict: this no longer reads as AI-generated slop, but it still reads as a well-tuned Streamlit template.**

**What is specific to this product:**
- The copy is careful, plain Greek and follows the glossary.
- Honesty markers are everywhere: «Δεν έχει ελεγχθεί ακόμα», «(από το όνομα της γειτονιάς)», «Ζητούμενες τιμές, όχι τιμές πώλησης».
- Every number has its basis one tap away in «Από πού βγαίνουν».
- The guided 5-step flow ends in a result that repeats your answers back as chips.
- The relax-one-filter box («Με έναν όρο λιγότερο…», r5) is a genuinely good, product-specific idea.
- The palette is restrained and consistent: slate ink, one teal accent, semantic badge tints.

**What is generic:** the composition. It is a vertical stack of same-size bordered rectangles of text with Streamlit widgets in them. Nothing in the visual language says "a flat in Athens". Remove the words and it could be a job board, a car finder or a CRM.

**Generic tells that remain, and where they show:**

| # | Tell | Where |
|---|---|---|
| 1 | **No imagery at all on a property product.** No thumbnail on any card, none on the listing page. Every card is a text slab. This is the single strongest "assembled, not designed" signal. | a5, a6, d0, b1, d1, h2, r5, r6 (both widths) |
| 2 | **Two navigations at once on desktop**, and they use different names: pills say «Περιοχές», the sidebar says «Πού να αγοράσω». «Αποθηκευμένες αναζητήσεις» appears only in the sidebar. This is the classic Streamlit `st.navigation` plus custom-nav tell. | a5-1280, b1-1280, e0-390/1280 |
| 3 | **Streamlit's sidebar toggle «»»** sits at top left of every phone screen. It is 28×28 px (measured live), under the 44 px floor, and floats over content when scrolled. | every -390 shot; a6-390 and b1-390 show the overlap |
| 4 | **Stock Streamlit widgets left mostly unstyled.** `st.toggle` («Με δάνειο», «Χάρτης», «Μόνο ΒΑ Αθήνα», «Επιπλωμένο»). `st.number_input` with −/+ steppers (six in a column on the listing page). An `st.selectbox` at the top of the listing page whose label is cut off («…Νέα Ιωνία (Σαφράμπολ»). `st.expander` with a «›» caret for «Άλλο ποσό» and «Φίλτρα». | a1, r1, r4, a5, c1, d1, d0, b1 |
| 5 | **Identical card stack** for the main view, nine per screen. Each card has 4–5 equal-weight controls. Craft-floor: "same-size cards as the page structure". | a5, d0, b1, r5 |
| 6 | **Text wordmark only.** «Σκάουτ ακινήτων» in teal bold, 17 px, with a 13 px grey data line under it. There is no mark and no product voice in the header. | every screen |
| 7 | **Decorative mini bar sparkline** («▁▇», three data points, no axis, no label) inside the Areas cards. Craft-floor: "sparklines standing in for content". | c1-390 (Galatsi, Chalandri cards) |
| 8 | **Default map chrome**: light-grey base tiles, stock +/− zoom, coloured dot clusters at area centroids, and no legend in the first screen. | b1 (live top of page) |
| 9 | **Plain `st.table`** for comparison, with the same two cards repeated as full cards underneath. | h2 |
| 10 | **Three different "selected" looks**: solid teal (nav and primary actions), pale grey-blue fill (the chosen answer on guide steps, a2, a3, r2, r3), and teal tint with teal border (segmented chips, a4, r4). | a2–a4, r2–r4 |

---

## 2. Nielsen's heuristics (0–4)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | **3** | Good: «Βήμα N από 5» with a progress bar, a data-freshness line, result counts that say what was hidden and why, and the «Χωρίς σύνδεση» note. Gap: on r0 a dead rent flow still shows «Βήμα 1 από 5» and a progress bar, which suggests progress where none is possible. |
| 2 | Match with the real world | **3** | The guide speaks plain Greek and numbers use Greek format (verified live: «5,5 %»). Analyst terms still leak, though: «Ρευστότητα», «Εμπιστοσύνη: Μέτρια (δείγμα ενοικίου άγνωστο)», «Παρόμοια (8): 14 % κάτω», «ΠΕΑ», «ΒΑ Αθήνα». There is also a grammar slip, «1 μέρες» (c1, `areas.py:457`). |
| 3 | User control and freedom | **3** | «Πίσω» on every step, answer chips that reopen a step, and «Αναίρεση»/«Επαναφορά» for verdicts. But favourites vanish on reload (only a caption warns about it), and you cannot link or share a listing (no query params except `admin`). |
| 4 | Consistency and standards | **2** | Two navs with different names. Page titles come in two sizes (Οδηγός/Αγαπημένα/Αγγελία at 28 px; Χάρτης/Σύγκριση at about 21 px). Card button labels are 13 px on Search and Map (`st-key-act-*`) but 17 px on guide cards. «Δεν μου κάνει» is a text button in the buy flow and an outlined button in rent. There are three selected-state looks, and three different action sets on what is the same card. |
| 5 | Error prevention | **2** | The guide's presets prevent bad input. But Αναζήτηση's default sort («Τιμή σε σχέση με παρόμοια») and the Map list put 33–35 %-under-comparables, «Δεν έχει ελεγχθεί ακόμα» flats at the top. That is the exact trap the owner complained about, one point below the `too_cheap` line. Separately, a segmented chip is clipped off-screen (r4), so it can be missed. |
| 6 | Recognition rather than recall | **3** | The result repeats the user's answers as chips, the basis is inline, and labels are everywhere. Saved searches are reachable only from the hidden sidebar. The compare picker shows internal ids («… · #106»). |
| 7 | Flexibility and efficiency | **3** | There are several ways in: guide, free-text search plus filters, map, areas, compare. But the guide result cannot be sorted, compare is limited to two flats, saved searches are off without a token, the 8,070-row map list pages 10 at a time, and there are no shareable URLs. |
| 8 | Aesthetic and minimalist design | **2** | Calm palette and a good type scale. But cards are dense: about 6 lines plus 5 controls, a «Ελέγχθηκε η περιγραφή» badge repeated on all 18 cards, «(από το όνομα της γειτονιάς)» repeated on every card, and the solid-teal «Εγκρίνω» nine times per screen. The Areas cards carry 12+ rows, many of which just say «άγνωστο». The listing page runs 3,186 px with a six-field calculator before the verdict. |
| 9 | Recognize and recover from errors | **3** | Empty states name the next step (h1, s1, r0), and «Μόνο 6. Με έναν όρο λιγότερο…» offers one-tap relaxations, which is excellent. But the r0 empty state has no route out except «Πίσω», when it could offer «Να αγοράσω». |
| 10 | Help and documentation | **3** | Every card has «Από πού βγαίνουν», there are «?» tooltips, and the method captions are honest. The home screen has no one-line "what this does" before «Τι ψάχνεις;». «Ρώτα με» was not testable (no key). |
| | **Total** | **27/40** | **Acceptable (top of the 20–27 band)** |

---

## 3. Cognitive-load checklist

| Item | Result | Note |
|---|---|---|
| Single focus | ✗ | Guide steps pass. The guide result does not: a summary paragraph, 5 answer chips, a map toggle, the cards and 5 controls per card all compete above and around the first card (a5). |
| Chunking (≤4 per group) | ✗ | Each Areas card has 12–14 label/value rows (c1). The listing page has 6 number fields in one block (d1). |
| Grouping | ✓ | Cards, hairline separators, and «Από πού βγαίνουν» kept inside the card. |
| Visual hierarchy | ✓ (partial) | Price leads every card. On the result, the five-sentence «Πρόταση:» paragraph has no hierarchy. |
| One thing at a time | ✓ | The guide is one question per screen. |
| Minimal choices (≤4) | ✗ | Budget step: 6 presets, «Άλλο ποσό» and a loan toggle (8 options). Nav: 6 pills, plus 7 sidebar items. Each guide card: 4 buttons plus an expander. Kind step: 3 ages plus 4 bedroom choices plus a CTA. |
| Working memory | ✓ | The answers are echoed on the result. |
| Progressive disclosure | ✓ (partial) | The card basis is behind an expander, which is good. The listing page shows everything at once (costs, calculator, six checks, history). |

**3 hard failures, so cognitive load is moderate.** Decision points with more than 4 visible options: the budget step (a1/r1), the nav (every screen), each card's action row (a5/r5/b1), and the kind step (a4).

**Emotional journey.**
- **Start is cold.** a0 shows «Τι ψάχνεις;» with two buttons on an otherwise empty phone screen and no promise of what the app does.
- **The middle is brisk and pleasant**: four one-tap questions with progress.
- **The peak** is «Πρόταση: Νέα Ιωνία». It is immediately undercut by card #1 being 35.000 € over the stated budget, though the copy explains why.
- **The end is flat.** The list just stops; there is no "what next" (visit, compare, save).
- **Rent on the real DB is a valley.** The user picks «Να νοικιάσω» and lands in a progress-barred dead end (r0).

---

## 4. Strengths

1. **The trust language is designed, not bolted on.** Semantic badges use one token set with readable tints (`theme.py` `.hg-st-*`, `--hg-ok/warn/bad-*`). «Από πού βγαίνουν» on every card, with the arithmetic written out («12 × 1.070 € ÷ 335.000 € = 3,8 %»), answers the owner's main complaint about numbers with no basis.
2. **The guide is a real phone-first flow.**
   - One question per screen and full-width 44 px+ choices.
   - Back, step counter and progress bar.
   - Answer chips on the result that reopen a step.
   - The «Με έναν όρο λιγότερο (+N)» relaxations, which turn an empty or thin result into one tap.
3. **The token discipline is visible.** One accent, a type scale of 13/15/17/21/28 px, a 4-pt spacing scale, a 14 px card radius, a hairline-only elevation, and a themed `:focus-visible` (measured: 2 px solid #0F766E). No horizontal scroll at 390 (`scrollWidth` 390 measured live on the home page). Greek number formatting is correct throughout.

---

## 5. Remaining issues

**P1-1. The segmented chips touch each other and overflow off-screen at 390.**
- **Where:** r4-390 («Έως 20 ετών» is clipped at the right edge); a4-390 («Νεόδμητο» / «Έως 20 ετών» touch with no gap; «Οποιαδήποτε 1 2 3+» touch with no gap).
- **Code:** `theme.py:888` gives every `[data-testid="stButtonGroup"] button` a pill radius, including `st.segmented_control` (`guide.py:600`, `rent_guide.py:560`). That widget is natively a joined bar with no gap and no wrap. Only `.st-key-nav_pill` gets `flex-wrap: wrap; gap: 8px` (`theme.py:661`).
- **Fix:** Pick one of two:
  - Keep segmented controls as a true joined bar: radius only on the first and last child, full width, `flex: 1` per segment.
  - Or give `[data-testid="stMain"] [data-testid="stButtonGroup"]` `flex-wrap: wrap; gap: 8px` globally.
  - Re-shoot a4/r4 and confirm no element passes x = 374.

**P1-2. Duplicate navigation with different names and contents.**
- **Where:** e0, every -1280 screen; `app.py:2361` and `app.py:2384` («Περιοχές» → «Πού να αγοράσω»).
- **Problem:**
  - The sidebar (`st.navigation`, `[data-testid="stSidebarNav"]`) and the pill nav (`.st-key-nav_pill`) both show. At 1280 they sit side by side.
  - The listing page's footnote sends users to «Πού να αγοράσω», a name that does not exist in the visible pills.
  - «Αποθηκευμένες αναζητήσεις» can be found only through the 28 px «»» toggle.
- **Fix:**
  - Use one label («Περιοχές») everywhere, including copy that refers to the page.
  - Hide the sidebar nav list (keep the sidebar for the sign-in note and «Ανανέωση»), or hide the pills at ≥ 1024 px.
  - Add «Αποθηκευμένες» to the Αναζήτηση page as a link, or as a 7th pill under «Αγαπημένα».
  - Raise `[data-testid="stExpandSidebarButton"]` to 44×44.

**P1-3. The default sort promotes the riskiest flats on Αναζήτηση and the Map list.**
- **Where:** d0 and b1. The first ~20 cards are all «Παρόμοια: 33–35 % κάτω» and «Δεν έχει ελεγχθεί ακόμα». Sort selectbox «Τιμή σε σχέση με παρόμοια», `buyer.py`.
- **Why it matters:** Visually this leads with exactly the "too good to be true, unchecked" flats the owner called sloppy. A 34 % discount on an unchecked new-build reads as a deal.
- **Fix (design-level, no ranking change):**
  - Default the sort to the guide's ranking or to «Ελέγχθηκε πρώτα».
  - Or add a strip above the list: «Οι πρώτες είναι 30 %+ κάτω από τα παρόμοια και δεν έχουν ελεγχθεί — συχνά υπό κατασκευή».
  - Render the «Παρόμοια: N % κάτω» row in the warn tone when it is ≥ 30 % and the page is unchecked (`.hg-st-unk`).

**P2-1. Card actions are inconsistent and too many.**
- **Where:**
  - Guide card (a5): «Λεπτομέρειες», «Αγαπημένο», «Εγκρίνω» (primary) and «Δεν μου κάνει».
  - Rent card (r5): the same four buttons, but «Δεν μου κάνει» is outlined, because `rent_guide.py:651` keys are `{k}-no-*`, which `theme.py:897` `[class*="st-key-pick-no-"]` does not match.
  - Search card (d0): 2 buttons at 13 px (`theme.py:615`, `[class*="st-key-act-"] button p { font-size: var(--hg-fs-footnote) }`).
  - Map card (b1): 4 buttons at 13 px.
- **Problem:** «Εγκρίνω» and «Αγαπημένο» overlap in meaning (s1 says approval puts the flat in favourites).
- **Fix:**
  - Merge to one keep action («Κράτα» = approve + favourite) and one dismiss action («Δεν μου κάνει», tertiary).
  - Make the card body itself open «Λεπτομέρειες».
  - Use one action row component and one 15 px label size everywhere.
  - Match the rent key to `pick-no-`.

**P2-2. The listing page buries what matters.**
- **Where:** d1, 3,186 px tall.
- **Problem:**
  - The top control is a truncated selectbox.
  - «Άνοιγμα στο XE.gr» and «Αγαπημένο» sit only at the very bottom.
  - Six stepper inputs (net-yield calculator) come before the «Έξι έλεγχοι επενδυτή» verdict.
- **Fix:**
  - Header order: price row, status badges, then a sticky two-button row («Άνοιγμα στο XE.gr» | «Αγαπημένο») right under the summary card.
  - Move the calculator into a «Καθαρή απόδοση — άλλαξε τις παραδοχές» expander placed after the six checks.
  - Drop the selectbox, or make it a «Πίσω στη λίστα» link.

**P2-3. Areas cards are walls of text.**
- **Where:** c1. `areas.py` `_card` has 12–14 rows per area, and several just say «άγνωστες ακόμα» or «δείγμα ενοικίου μη καταγεγραμμένο».
- **Fix:**
  - Collapse unknown rows into one footnote («Άγνωστα ακόμα: ρευστότητα, δείγμα ενοικίου»).
  - Show 4 headline rows (Μικτή απόδοση, Τιμή, Νεόδμητα/παλιά, Σταθμός) and put the rest behind «Όλα τα στοιχεία».
  - Remove the unlabeled «▁▇» bars or give them month labels.
  - Fix «1 μέρες» → «1 μέρα» at `areas.py:457` (singular/plural helper).

**P2-4. Page titles come in two sizes, and Αναζήτηση has none.**
- **Where:** Χάρτης and Σύγκριση use `###` (about 21 px; b1, h2). Οδηγός, Αγαπημένα, Αγγελία, Πού να αγοράσω and Αποθηκευμένες use `##` (28 px). Αναζήτηση has only the hero card heading «Διαμέρισμα για επένδυση».
- **Fix:** Make every page title one `--hg-fs-large` heading, through a shared `page_title()` helper in `components.py`.

**P2-5. The rent flow dead-ends on the real DB.**
- **Where:** r0, `rent_guide.py`.
- **Problem:** «Βήμα 1 από 5» and a 20 % progress bar sit above a «δεν έχουμε ακόμα αγγελίες ενοικίασης» note, and the only exit is «Πίσω».
- **Fix:** When there are no rental rows, skip the step chrome. Show the note plus a primary «Δες διαμερίσματα για αγορά» and a secondary «Πίσω».

**P2-6. The guide's "selected answer" state is weak and unlike every other selected state.**
- **Where:** a2, a3, r2, r3. The chosen choice is a pale grey-blue fill; elsewhere selected means solid teal or a teal tint.
- **Code:** `guide.py:520` `_choice` passes `type="primary"`, but it renders grey.
- **Fix:** Selected choice = `--hg-accent-tint` background, 2 px `--hg-accent` border and a check glyph or SVG, matching the segmented chips.

**P3-1. Repetition inside cards.**
- «Ελέγχθηκε η περιγραφή» appears on all 18 of 18 result cards, after the summary already says «Ελέγχθηκε η περιγραφή σε 18 από αυτές». Show the badge only when it differs from the rest of the list.
- «(από το όνομα της γειτονιάς)» appears on every card. Move it into «Από πού βγαίνουν».
- The rent expander (r6) repeats «Ιδιώτης» and «28 μέρες στην αγορά» twice, and has double parentheses: «(Γαλάτσι (Λαμπρινή))».

**P3-2. The price row wraps and leaves a separator dangling.**
- **Where:** a5-390, card 1: «335.000 € · 93 τ.μ. ·», then «3.602 €/τ.μ.» on the next line.
- **Code:** `.hg-facts span + span::before` (`theme.py:552`).
- **Fix:** Put the separator inside each span with `white-space: nowrap`, or let the €/τ.μ. drop to its own line with no leading «·».

**P3-3. The compare picker leaks internal ids.**
- **Where:** h2, «Αθήνα (Κυψέλη) · 75 τ.μ. · 180.000 € · #106». Below the table, the two full cards repeat the table.
- **Fix:** Drop `#id` and disambiguate by floor and year. Collapse the cards into «Λεπτομέρειες» links.

**P3-4. There are no photos anywhere.**
- Even without verifying the photos, a 72×72 thumbnail tagged «Φωτογραφίες: δεν ελέγχθηκαν» would make this a property product.
- This is out of C6 scope (no change to what a card says), so it is listed as a question, not a defect.

**P3-5. The 13 px muted text is a lot for an older reader.**
- **Where:** the header data line (13 px #64748B on #F7F9FC, about 4.5:1, borderline), «109 μέρες στην αγορά», method captions, map notes.
- **Fix:** Use 15 px for anything that carries a decision (days on market, hidden counts), and keep 13 px for provenance only.

---

## 6. Persona red flags

**The owner: an older Greek buyer on a 390 px phone.**
- The search and map card buttons are 13 px text («Λεπτομέρειες», «Αγαπημένο»; `st-key-act-*`), small for older eyes even though the targets are 44 px.
- The sidebar toggle is 28 px.
- On Χάρτης, the plotly map fills the width, so dragging the page scrolls the map instead (b1). There is no legend for the green/amber/red dots in the first screen.
- Hearts are lost on reload (session-only). The warning is a 13 px grey caption.
- He cannot send a flat to his wife or son: there is no shareable URL.
- He sees «Εγκρίνω» next to «Αγαπημένο» and cannot tell the difference.
- The cards have no photos, so he must open XE for every one, and on the listing page that button is at the very bottom.

**First-timer (Jordan).**
- a0 has no line saying what the app does.
- On the result, the answer chips look like the nav pills. Are they buttons? (They are, but nothing says so.)
- Jargon without inline definitions: «Μικτή απόδοση», «Παρόμοια (8): 14 % κάτω», «ΠΕΑ», «Ρευστότητα», «Εμπιστοσύνη: Μέτρια».
- Two menus that disagree: «Περιοχές» vs «Πού να αγοράσω».
- Choosing «Να νοικιάσω» leads to a dead end with a progress bar (r0).
- After «Εγκρίνω», nothing says where the flat went (the saved-searches page says approval goes to favourites, but the card does not).

**Power user (Alex).**
- The guide result has no sort and cannot show more than the 18 results in budget.
- Compare is limited to two flats.
- The map list of 8,070 pages 10 at a time.
- Saved searches are disabled without a token.
- There are no URL deep links or keyboard shortcuts.
- Αναζήτηση's free-text box and the «Φίλτρα» expander are the fast path, but its default sort puts unchecked, suspiciously cheap flats first, so he has to re-sort every visit.

---

## 7. Minor observations

- At 390, the free-text placeholder in Αναζήτηση is cut off («…από 60 τ»).
- At 390, the listing selectbox value is cut off («…(Σαφράμπολ»).
- On the guide result, the «Πίσω» button and the «Η πρότασή μου» heading are on one row; at 390 the step counter is gone, which is fine, but the result has no "start over".
- The comps band on the listing page (d1) puts the black dot outside the 50 % band with a 12 px legend under it, which is hard to read.
- The Areas card has extra top padding before «1. Γαλάτσι», unlike the other cards (c1).
- The «Προσοχή» sub-heading in the Areas cards is followed by an empty gap (c1).

## 8. Questions to consider

- If the product's promise is "one flat, checked", why does any list default to unchecked flats?
- Could the result screen be one recommended flat plus "8 more", instead of nine equal cards?
- What would a single thumbnail plus a «φωτογραφίες: render;» badge do to trust, compared with no images at all?
