# Assessment A: design review (Holargos Property Scout, Round 5 / C6)

Reviewer: Assessment A (screenshots and source only; no measured evidence read).
Mode: Operate. Primary viewport 390×844 (touch, isMobile), secondary 1280×900.
App: http://127.0.0.1:8501 against the real DB (11.150 active listings, 1.501 checked, data dated 30/10).

**Run notes**
- No `ANTHROPIC_API_KEY`, so «Ρώτα με» and the «Σημείωμα επενδυτή» brief did not render. Their states are **not assessed**.
- No `GITHUB_TOKEN`, so favourites and verdicts last only for the session. The sidebar says «Χωρίς σύνδεση: οι επιλογές σου μένουν μόνο σε αυτή την καρτέλα.»
- The harness `docs/qa/shots.js` is out of date on two labels, so I took those states myself:
  - Flow a failed at «Η πρότασή μου →». The button is now «Η πρότασή μου». I captured the result with `/tmp/assessA_js/guide.js` (x1–x3).
  - Flow b logged «NO «Επόμενο ›»». The button is now «Επόμενο». So b2 is the same state as b1, and only the map tap (b3) changed the selection.
- The harness overflow probe flagged an `INPUT` at right=479 on every map shot. I report this only as a pointer and leave the measuring to B.

**Screenshots looked at** (all in `/tmp/assessA/`):
- Guide steps: a1-guide-step1-budget, a2-guide-step2-goal, a3-guide-step3-where, a4-guide-step4-kind.
- Guide result: x1-guide-result-fold, x2-guide-result-full (+ crops x2crop-card2, x2crop-end), x3-guide-card-basis-open.
- Map: b1-map-card-under-map (+ b1crop-top, b1crop-mid), b2-map-after-next, b3-map-after-tap-point.
- Areas: c1-areas-decision (+ c1crop-top, c1crop-2), c2-areas-first-card-open.
- Search and listing: d0-search (+ d0crop-top), d1-listing-page (+ d1crop-top, d1crop-2, d1crop-3), f0-search-default, f1-search-filtered (+ f1crop-top).
- Desktop: g1-guide-desktop, g2-areas-desktop.
- Other pages: h0-first-load, h1-favourites, h2-compare.

---

## 1. Design-specificity verdict

**Partly authored, but category-interchangeable on the surface.**

The *content* is clearly built for this buyer and this market:
- Card lines name their basis: «Ενοίκιο (εκτίμηση) ~1.070 €/μήνα · Μικτή απόδοση 3,8 %», «Παρόμοια (8): 14 % κάτω».
- The status line says whether the listing page was read.
- Stations come with «(από το όνομα της γειτονιάς)».
- The price-position bar on the listing page puts the flat inside the comparables' p25–p75 band.
- The areas page names Line 4 stations and their 2032 horizon.

None of this would fit an unrelated product unchanged. The honesty language is the product's real character.

The *visual language* is generic "calm SaaS on Streamlit":
- slate ink, one teal, white cards with a soft shadow and a hairline border;
- pill buttons and a teal progress bar;
- Streamlit's default blue `st.info` boxes.

Swap the copy and the same chrome could sell a CRM. The theme's own docstring aims at "Linear / Stripe / Notion-level restraint", which is a category reference, not a product voice.

Missed chances for product character:
- **The price-position bar** (`.hg-pos-*`) is the one authored visual. It appears only on the listing page, not on the cards where buying decisions are made.
- **The trust ladder** (Υπό κατασκευή → Δεν έχει ελεγχθεί ακόμα → Ελέγχθηκε η περιγραφή) is the product's core idea. It is drawn as three ad-hoc tinted blocks, not as one recognisable status system.
- **Greek typography** gets no specific care beyond avoiding uppercase.

Coherence is weakened by visible drift:
- Four CSS sources: `theme.py`, `buyer.CARD_CSS`, `guide.CSS` and an inline `<style>` in `maplist._css`.
- Three card vocabularies: the legacy `ph-*` grid, the `hg-*` card, and the guide's `pick-*` card that reuses `.hg-card` for its extra lines.

## 2. Nielsen heuristics

| # | Heuristic | Score | Key issue (screen, element) |
|---|---|---|---|
| 1 | Visibility of system status | 3 | Good: «Βήμα N από 5» plus a progress bar, a data line on every page («XE.gr, Green-Acres · 30/10 · 11.150 ενεργές · 1.501 ελεγμένες»), «Βλέπεις 10 από 18.», and the map's «Εμφανίζονται οι πρώτες 1.500 …». Weak: the result page still shows «Βήμα 5 από 5» and «Πίσω» as if it were a question step. Tapping a map dot gives no visible confirmation beyond the header changing to «3157 από 8.070». |
| 2 | Match between system and real world | 2 | Greek throughout, but the investor shorthand assumes an analyst: «Παρόμοια (8): 35 % κάτω», «μεσαίο 50 % των παρομοίων», «διάμεσος», «Ρευστότητα και ζήτηση ενοικίου». Compare options carry raw ids («· #10685»). The map basemap says «ATHENS» in English. |
| 3 | User control and freedom | 2 | The guide has «Πίσω», answer chips that reopen a question, and «Επαναφορά» for dropped flats. The listing page («Αγγελία») has no way back to where you came from; you must use the top pills and lose your place in the list. «Δεν μου κάνει» removes a card, and the undo hides in a collapsed «Απέρριψες N» expander at the very bottom. |
| 4 | Consistency and standards | 1 | Three action vocabularies for one decision: guide «Εγκρίνω / Δεν μου κάνει», search and map «Αγαπημένο», list «Στον χάρτη». Page titles use three heading levels: «Οδηγός» / «Πού να αγοράσω» are `##`, «Χάρτης» / «Σύγκριση» are `st.subheader`, «Αγαπημένα» is larger again, and «Αγγελία» has none. Counter copy differs: «Βλέπεις 10 από 18.» vs «Εμφανίζονται 10 από 8.070.». Percent formatting differs: «−24% €/τ.μ.» in Σύγκριση vs «14 % κάτω» on cards. Two selected-nav styles on desktop: solid teal in the sidebar, pale teal plus underline in the pills. |
| 5 | Error prevention | 2 | Strong: budget presets, the disabled «Συνέχεια» until an area is chosen, and «Δείξε όλες, χωρίς όροφο/έτος (+5.752)» naming the cost of a filter. Weak: in the search filters «Τιμή έως (€)» shows raw «300000» with no thousands separator, and the «Τύπος» multiselect truncates its chip to «δια…». After a tap on a touch device, the button under the finger on the next step keeps a grey hover tint (a3: «Κοντά σε μετρό/ΗΣΑΠ»), which looks pre-selected. |
| 6 | Recognition rather than recall | 3 | The answer chips on the result («300 χιλ. · απόδοση · κοντά σε μετρό · νεόδμητο») and the filter summary in the expander label («Φίλτρα · τιμή έως 300.000 € · από 2ο όροφο …») are textbook. Σύγκριση makes you find flats again by typing «Γράψε περιοχή, τ.μ. ή τιμή» into a select, instead of picking from cards you just saw. |
| 7 | Flexibility and efficiency of use | 2 | Two paths exist: the guide for novices, free-text search with examples for experts. But the guide result has no sort and no compare-from-card. The map caps at 1.500 points. Favourites have no «compare these two» shortcut. Nothing is batchable. |
| 8 | Aesthetic and minimalist design | 2 | The cards are honest but dense: seven text lines, a status block, an expander, then 5 full-width buttons in the guide. Area cards are 13-bullet walls plus a glyph sparkline plus «Προσοχή». The map page prints «Μόνο 23 … ακριβή θέση» twice. There is a ~70 px dead band between the data line and the page title. |
| 9 | Help users recognize, diagnose, recover from errors | 2 | The relax box («Χαλάρωσε έναν όρο — σε παρένθεση πόσες αγγελίες προστίθενται») is excellent. Elsewhere the recovery is a sentence, not a control: Αγαπημένα says «Πάτα «Αγαπημένο» σε μια αγγελία.» with no button to go there, and «Ο χάρτης δεν φορτώθηκε.» offers no retry. |
| 10 | Help and documentation | 3 | «Από πού βγαίνουν» on every card, «Πώς υπολογίζω», «Πώς βαθμολογούμε» and the calculator's formula caption make the method genuinely inspectable. Many explanations live in `help=` tooltips (the (?) icons), which are hover-only and effectively invisible on a phone. |
| | **Total** | **22 / 40** | **Acceptable (20–27)**: significant improvements needed before the user is happy. |

## 3. Cognitive load

**Checklist result: 4 failures out of 8, which counts as high cognitive load.**

| Item | Pass / Fail | Evidence |
|---|---|---|
| Single focus | **Fail** | The result page stacks, before the first card: chips, the recommendation paragraph, a count paragraph, the relax box when few results, the brief and the map toggle. Each card then carries 5 actions. |
| Chunking (≤4 per group) | **Fail** | Area card: 13 fact rows in one bullet list. Listing card: 7–8 lines. The hidden-count line on Αναζήτηση lists 7 reasons in one run: «Κρύβονται 8.893: 38 όχι κατοικία · 327 … · 623 χωρίς όροφο/έτος». |
| Grouping | Pass | Cards, expanders and the filter box group related facts. |
| Visual hierarchy | Partial (counted as pass) | Price is clearly the lead on cards. But the guide's answer is a paragraph, not a headline, and the solid-teal «Εγκρίνω» is the loudest thing on every card. |
| One thing at a time | Pass | The guide is one question per screen. |
| Minimal choices (≤4) | **Fail** | See the decision points below. |
| Working memory | **Fail** | Σύγκριση makes the user re-identify two flats by neighbourhood, size and price, or by «#id», remembered from other pages. The listing page has no back path, so the user must remember their position in a list of 18 or 8.070. |
| Progressive disclosure | Pass | «Άλλο ποσό», «Από πού βγαίνουν», «Τι λέει η αγγελία», «Όλες οι περιοχές (14)» and «Φίλτρα» are all collapsed. |

**Decision points with more than 4 visible options:**
- Top navigation pills: 6. On desktop there is also the sidebar radio with 7 more options, a duplicate set.
- Guide step 1: 6 budget buttons, «Άλλο ποσό» and the «Με δάνειο» toggle (8).
- Guide result card: 5 buttons (Άνοιγμα στο XE.gr, Λεπτομέρειες, Εγκρίνω, Δεν μου κάνει, Στον χάρτη), plus 2 disclosures (Από πού βγαίνουν, Τι λέει η αγγελία).
- «Όλες με τη σειρά» card on Χάρτης: 4 buttons, at the limit.
- Αναζήτηση filter box: about 12 controls (Περιοχή, Τιμή έως, Από τ.μ., Από όροφο, Κτίριο από, a checkbox, Υπνοδωμάτια, Τύπος, Να έχει, and three checkboxes).
- Listing page calculator: 6 number steppers (Ενοίκιο, Κοινόχρηστα, ΕΝΦΙΑ, Μήνες κενό, Φόρος, Συντήρηση) in one run.

## 4. Emotional journey

**Opening, the guide steps: good.** The guide opens calm and confident: one large question, six big budget buttons, a visible «Βήμα 1 από 5». The older buyer feels led, not tested.

**First valley, step 4.** «Ηλικία κτιρίου» wraps «Οτιδήποτε» onto its own line, and «Όσα να 'ναι» is chatty next to the formal rest. This is minor, but it is the first moment the UI looks unfinished.

**The peak should be the answer, and it is flat.** After four taps the reward is:
- the same title block and a full progress bar;
- a paragraph of dense numbers: «Πρόταση: Νέα Ιωνία — 6 από τις 18 αγγελίες της λίστας, διάμεση μικτή απόδοση τους 3,7 % · ενοίκιο περιοχής 10,1 €/τ.μ. …».

No flat is visible above the fold at 844 px (x1). The emotional payoff is deferred by one scroll and delivered as arithmetic.

**Reassurance at the high-stakes moment is mixed.**
- The status block is the right idea. But it is tinted **green** while saying «Φωτογραφίες: δεν ελέγχθηκαν», which is exactly the thing this owner was burned by (renders, shells, logos). Green over a partial check reads as "verified" at a glance.
- On the listing page, «Τιμή έναντι παρομοίων: **καλό**» appears in green for a flat that is −34,9 % under comparables. That is a hair under the product's own 35 % «too cheap» warning. The verdict colour reassures where the copy should make the user cautious. This is a data/threshold matter outside C6, but the green tone is a design choice.

**Valley on «Πού να αγοράσω».** The decision box names Νέο Ψυχικό for yield, then «Οι 3 πρώτες» opens with Γαλάτσι, «12η από 16» in yield. With no stated basis for the order, the user's trust drops right where the product asks for it.

**The end is weak.** Each list ends on:
- a grey «Βλέπεις 10 από 18.»;
- a collapsed «Πώς υπολογίζω»;
- a faint source line.

The listing page, the deepest point, ends on «Άνοιγμα στο XE.gr / Αγαπημένο» after ~3.300 px of scroll. There is no closing summary («what to do next with this flat») and no return path. By the peak-end rule, the remembered experience is "long and dense".

## 5. Strengths

1. **Every number names its basis within one tap.** The «Από πού βγαίνουν» disclosure spells out the arithmetic: «Μικτή απόδοση = 12 × ενοίκιο ÷ τιμή = 12 × 1.070 € ÷ 335.000 € = 3,8 %, πριν από έξοδα και φόρους.» The listing page's calculator shows its formula beneath. This is the anti-"AI sloppy" core and it works.
2. **The guide's one-question-per-screen structure with answer chips.** Big two-up budget buttons, a clear «Βήμα N από 5», and chips on the result that reopen any answer. This is the right model for an older phone user, and it is also the clearest information architecture in the app.
3. **Filters that confess their cost.** The Αναζήτηση count line («2.257 αγγελίες … Κρύβονται 8.893: …»), the one-tap «Δείξε όλες, χωρίς όροφο/έτος (+5.752)», and the guide's relax buttons with "+N" counts directly answer the owner's "a filter the results ignore" complaint.

## 6. Issues (P0–P3)

No P0: every primary task can be completed.

### [P1-1] Guide result: the answer is not above the fold
- **Screen:** Οδηγός, step 5 (x1). At 390×844 the viewport holds the nav pills, the data line, a ~70 px gap, «Οδηγός», «Πίσω / Βήμα 5 από 5», the progress bar, «Η πρότασή μου», 4 chips and two paragraphs. Zero flats are visible.
- **Source:**
  - `app.main()`: `st.pills("Σελίδα"…)` and `st.caption(_data_status…)`.
  - `guide.page()`: `st.markdown("## Οδηγός")`, then `_progress(step)`, which is `.st-key-guide-progress` plus a bare `st.progress` (`[data-testid="stProgress"]`).
  - `guide._results()`: `st.markdown("### Η πρότασή μου")`, `st.pills(key="guide_chips")`, then the recommendation and count paragraphs.
  - `theme.py`: `@media (max-width:640px) [data-testid="stMainBlockContainer"] { padding: 3.1rem 1rem 2rem }`, plus the h2 margins.
- **Why it matters:** The whole guide promises "answer"; Operate mode demands that the result be visible. An older user may think the tap did nothing.
- **Fix:**
  1. Class hook: move `st.progress` inside the `guide-progress` container and key it per step (e.g. `key=f"guide-progress-{step}"`). Then in `theme.py`, hide `.st-key-guide-progress-5` on the result: progress and «Πίσω» have no meaning there, and the chips already do «back».
  2. In `theme.py`, tighten the phone top padding and the gap between `stCaption` and the first heading. The dead band is ~70 px.
  3. Copy (wording defect): make the recommendation a short headline sentence with the area and one number, e.g. «Πρόταση: Νέα Ιωνία · μικτή απόδοση 3,7 %». Move the remaining clauses into the count line or the basis.

### [P1-2] Card actions: too many, wrong weight, inconsistent vocabulary
- **Screen:** The guide card (x3, x2crop-card2) has 5 stretched buttons, with «Εγκρίνω» in solid teal as the loudest element on the card. The search/map card has «Άνοιγμα στο XE.gr / Λεπτομέρειες / Αγαπημένο». The map list card has «Στον χάρτη / Λεπτομέρειες / Αγαπημένο» plus Άνοιγμα.
- **Source:**
  - `guide._card()`: `st.link_button(f"Άνοιγμα στο {src}")`, `st.button("Λεπτομέρειες")`, `"Εγκρίνω"` with `type="primary"`, `"Δεν μου κάνει"`, `"Στον χάρτη"`, all inside `.st-key-pick-*`.
  - `buyer.result_card()`: `.st-key-act-*`, where `theme.py` repaints primary as amber.
- **Why it matters:** The verdict action outranks the information. Users meet two mental models («Εγκρίνω» vs «Αγαπημένο») for "I like this one", and it is unclear whether an approved flat appears in «Αγαπημένα» (it does not). Five 48 px buttons also double each card's height.
- **Fix:**
  - In `theme.py` for `[class*="st-key-pick-"]`: render the approve/reject pair as one segmented row, with secondary weight and the amber "on" state reused from `.st-key-act-*` primary.
  - Make «Άνοιγμα στο XE.gr» and «Στον χάρτη» quiet text-link style (no border, accent colour, still 44 px tall) on one row.
  - Leave «Λεπτομέρειες» as the single bordered action.
  - Flag the «Εγκρίνω» vs «Αγαπημένο» naming for the coordinator. It is a glossary decision (glossary has «Αγαπημένα» only), not a C6 CSS fix.

### [P1-3] The status block's tone contradicts its content, and it sprawls
- **Screen:** Every card. A green block reads «Ελέγχθηκε η περιγραφή (31/10/2026) — δεν αναφέρει κατασκευή σε εξέλιξη · Φωτογραφίες: δεν ελέγχθηκαν» and wraps to 3 lines. An orange block reads «Δεν έχει ελεγχθεί ακόμα · Φωτογραφίες: δεν ελέγχθηκαν».
- **Source:** `buyer.card_html()` builds the `hg-l3` line as `<span class="hg-st hg-st-{tone}">` from `picks.status_line(d)`. Styles are in `buyer.CARD_CSS`: `.hg-st`, `.hg-st-ok`, `.hg-st-unk`, `.hg-st-bad`, `.hg-st-photo`.
- **Why it matters:** The owner's core complaint is renders and unbuilt shells. A green block that includes "photos not checked" signals verified at a glance. The three-line tinted slab is also the heaviest shape on the card.
- **Fix:**
  - Class hook / markup chunking only, same words. Split into two spans: `hg-st-ok` «Ελέγχθηκε η περιγραφή» and a neutral `hg-st-photo` / `hg-b-muted` «Φωτογραφίες: δεν ελέγχθηκαν». Move the parenthetical date and «δεν αναφέρει κατασκευή…» into the basis, where `status_basis()` already says it.
  - In `theme.py`, define the three status tones once as tokens (`--hg-ok-bg/fg`, `--hg-warn-*`, `--hg-bad-*`) and point `.hg-st-*`, `.hg-b-*` and `.hg-advice-*` at them.

### [P1-4] «Πού να αγοράσω»: ranked list contradicts the decision box; area cards are walls
- **Screen:** c1. The decision box says «Για απόδοση: Νέο Ψυχικό…», then «Οι 3 πρώτες» starts with «1. Γαλάτσι — Μικτή απόδοση 4,3 % (12η από 16…)». Each card is a 13-row bullet list with a glyph sparkline and «Προσοχή».
- **Source:**
  - `areas.page_areas()`: `st.markdown("### Οι 3 πρώτες")`.
  - `areas._card()`: `st.container(border=True)` (no key), `st.markdown("\n".join(f"- **{k}:** {v}" …))`, and `render_series()`, which prints `` `▃▇` `` in inline code.
- **Why it matters:** The user cannot tell what «πρώτες» ranks by, which reads as a contradiction and costs trust. Thirteen bullets on a phone are unscannable.
- **Fix:**
  - Copy: «Οι 3 πρώτες» becomes «Οι 3 πρώτες στη συνολική βαθμολογία». This is a wording defect: the basis is unnamed.
  - Class hook: `st.container(border=True, key=f"area-card-{key}")`.
  - In `theme.py`, style `.st-key-area-card-* ul` as a grouped list: no bullets, label left muted, value right ink, inset hairline separators, `tabular-nums`.
  - Drop the code-font sparkline styling: it is a decorative glyph chart. Keep `series_text`.

### [P1-5] Listing page («Αγγελία»): no title, no way back, actions at the bottom
- **Screen:** d1. The page opens on a selectbox labelled «Αγγελία». «Άνοιγμα στο XE.gr» and «Αγαπημένο» come only after ~3.300 px: calculator, costs, comparables, six checks, price history. There is no «back to results».
- **Source:** `buyer.page_listing()`: `st.selectbox("Αγγελία", …)`, the sections, and the trailing action buttons.
- **Why it matters:** This is the deepest page and the one most often opened. A phone user is stranded at its bottom with no context of where they came from, which hurts user control and the peak-end experience.
- **Fix:**
  - Class hook: wrap the trailing actions in `st.container(key="listing-actions")`. In `theme.py`, make it `position: sticky; bottom: 0` with a surface background and a top hairline.
  - Add a page-title hook (see P2-7) so «Αγγελία» reads as a page, not a form field. The label can stay for accessibility, with a visible title above.
  - Add a «Πίσω» button that restores the previous `page`. This is a small control, and «Πίσω» is already guide vocabulary.

### [P2-6] Banned side-stripe borders
- **Screen:** AI advice and bad-note callouts on search/listing.
- **Source:** `theme.py`: `.hg-note-bad { border-left: 4px solid #DC2626 }` and `.hg-advice { border-left: 4px solid }` (with the `-good/-warn/-bad` variants).
- **Why it matters:** These are craft-floor bans, and they read as template alerts.
- **Fix:** Use a full 1 px border in the tone's border token on the tinted background (the pattern `.ph-rec-*` already uses). Remove the `border-left`.

### [P2-7] Page titles: four different treatments
- **Screen:**
  - «Οδηγός» and «Πού να αγοράσω» are `st.markdown("## …")`.
  - «Χάρτης» and «Σύγκριση» are `st.subheader` (h3).
  - «Αγαπημένα» renders larger again (h1).
  - «Αγγελία» has no title.
- **Source:** the respective page functions in `guide.py`, `areas.py`, `app.py` (`page_map`, `page_compare`) and `buyer.py` (`page_watchlist`, `page_listing`).
- **Why it matters:** The page title is the user's "where am I" anchor, and on a phone the nav pills alone do not show it strongly.
- **Fix:** Class hook: emit each page title as `<h1 class="hg-page-title">` (one call per page). In `theme.py`, give `.hg-page-title` the large-title role (1.75 rem, 700, −0.02 em, line-height 1.3), with more space above than below. Demote the in-page `###` to the title role (1.3 rem).

### [P2-8] Touch "sticky hover" looks like a pre-selected answer
- **Screen:** a3. Right after tapping «Απόδοση ενοικίου», the button that now sits under the finger, «Κοντά σε μετρό/ΗΣΑΠ», shows a grey-teal tint and a border. It looks already chosen.
- **Source:** `theme.py`: `.stButton > button:hover { border-color: var(--hg-accent); color: var(--hg-accent) }` and `[data-testid="stExpander"] summary:hover`.
- **Why it matters:** In a one-question-per-screen flow, a phantom selection on the next question is a real error trap.
- **Fix:** Wrap every `:hover` rule in `@media (hover: hover) and (pointer: fine)`. Give touch an `:active` pressed state instead (tint or `scale(.98)`).

### [P2-9] Guide step chrome misaligned; step-4 segmented control wraps badly
- **Screen:** a1–a4.
  - «Βήμα N από 5» is centred in a 2/3 column, so it jumps between step 1 (no «Πίσω») and the later steps, and floats away from «Πίσω».
  - On step 4, «Οτιδήποτε» wraps alone onto a second row under «Νεόδμητο (έως 10 ετών) | Έως 20 ετών».
  - «Όσα να 'ναι» is colloquial.
- **Source:**
  - `guide._progress()`: `st.columns([1, 2])` in `.st-key-guide-progress`.
  - `guide._step4()`: `st.segmented_control` (`[data-testid="stButtonGroup"]`), which is not inside a keyed container.
- **Fix:**
  - In `theme.py`, `.st-key-guide-progress`: put the step text on the right and keep it in a fixed position whether or not «Πίσω» is present.
  - Class hook: wrap step 4 in `st.container(key="guide-kind")`. In `theme.py`, lay its button groups out as an equal-width grid (age as 3 rows full-width, or 1+2), with each option ≥ 44 px.
  - Copy: «Όσα να 'ναι» becomes «Οποιαδήποτε», matching «Οτιδήποτε».

### [P2-10] The basis link is the smallest thing on the card, and net yield is cut off from gross
- **Screen:** x3. «▸ Από πού βγαίνουν» is small teal text with a native disclosure triangle. Below it, outside the `.hg-card` block, come «Καθαρή απόδοση ~2,6 %» and «Πρώτη προσφορά ~315.000 €». Net yield is thus separated from «Μικτή απόδοση 3,8 %» by the comparables line, the days line and the expander.
- **Source:** `buyer.CARD_CSS`: `.hg-card details`, `.hg-card summary`. `guide._card()`: the `lines` block rendered after `buyer.card_html()`.
- **Why it matters:** The basis link is the programme's definition of done ("every number has its basis within one tap"), yet it is the hardest target to hit. Two yields far apart invite misreading.
- **Fix:**
  - In `theme.py`, make `.hg-card summary` a full-width row of at least 44 px, with a custom chevron (no glyph marker) and a hairline above.
  - In the guide card, render the net-yield line directly under `hg-l4`. This is a layout order change only, with the same text.

### [P2-11] Empty states: off-palette blue boxes and no next-step control
- **Screen:**
  - h1 «Αγαπημένα»: a blue `st.info` box says «Δεν έχεις αγαπημένα ακόμα. Πάτα «Αγαπημένο» σε μια αγγελία.» There is no button.
  - Σύγκριση's «Διάλεξε δύο αγγελίες…» does include a button. Areas and map use the same blue.
- **Source:** `buyer.page_watchlist()` (`st.info`), `theme.py` `[data-testid="stAlert"]` (only radius and border are themed).
- **Fix:**
  - In `theme.py`, re-tint `[data-testid="stAlert"]` informational to a neutral surface with ink text and the accent border. Keep warning and error on the semantic tokens.
  - In `page_watchlist`, add `st.button("Οδηγός")` to the empty state, mirroring `page_compare`'s `cmp_to_find`.

### [P2-12] Desktop: two navigations, two selected styles
- **Screen:** g1, g2. The sidebar radio shows «Οδηγός» as a solid-teal, content-width pill. The top pills show the same page as pale teal with an underline. The sidebar also lists «Αποθηκευμένες αναζητήσεις», which the pills omit.
- **Source:** `app.main()`: `st.radio(key="page")` in `st.sidebar` and `st.pills(key="nav_pill")`. `theme.py`: `[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked)` and `.st-key-nav_pill button[aria-checked="true"]`.
- **Fix:**
  - Pick one selected style (solid accent fill plus weight) and apply it to both.
  - Make the sidebar labels truly full-width (`label { width:100% }` evidently is not winning over Streamlit's own flex).
  - At ≥ 641 px, consider hiding `.st-key-nav_pill` when the sidebar is open, so one nav shows at a time.

### [P3-13] Map page: repeated caption and English basemap label
- **Screen:** b1. «Μόνο 23 αγγελίες έχουν ακριβή θέση· …» appears under the count (`app.page_map`) and again under the legend as «Μόνο 23 από 8.070 έχουν ακριβή θέση…» (`maplist.render`). The CARTO basemap labels «ATHENS».
- **Fix:** Copy: drop the `page_map` instance, since maplist owns it next to the legend. Note the Latin basemap labels as a follow-up; tiles are outside C6.

### [P3-14] Compare table: formatting and identity drift
- **Screen:** h2.
  - «−24% €/τ.μ. · 17 παρόμοια, υψηλή» lacks the Greek space before % and the «κάτω/πάνω» wording the cards use.
  - The select options end in «· #10685».
  - The «Α · Αθήνα (Κυψέλη) · 75 τ.μ. · 180.000 €» lines restate the selects.
  - The table is fully boxed, and the label column header is empty.
- **Source:** `app._compare_rows()` (`f"{cmp['pct']:+.0%}"`), `app.page_compare()` (`_name`), and `theme.py` `[data-testid="stMarkdownContainer"] th/td`.
- **Fix:**
  - Copy: use the cards' «Παρόμοια (17): 24 % κάτω» form.
  - Replace `#id` with something human in the label, or hide it.
  - In `theme.py`, give the compare table the grouped-list treatment: no outer box, inset separators, `tabular-nums` on the value columns, and a muted label column, which the CSS already half-does at `td:first-child`.

### [P3-15] Top-of-page rhythm and the tooltip-only help on phones
- **Screen:** every page.
  - A ~70 px gap separates the faint data line from the title (a1, h1).
  - The (?) `help=` icons («Μόνο ΒΑ Αθήνα», «Σειρά», «Τιμή έως», «Αξιοπιστία σύγκρισης») are hover tooltips and do nothing for a thumb.
- **Fix:**
  - In `theme.py`, tighten the margin after `stCaption` at the top of the main block, and keep more space above section headings than below.
  - The tooltip content is a design-content decision. For the two that carry meaning («Αξιοπιστία σύγκρισης», «Μόνο ΒΑ Αθήνα»), surface the text as a caption. This is a copy move, not new content.

## 7. Persona red flags

**Older Greek buyer on a 390 px phone (the owner's profile)**
- Lands on step 1 with a faint grey line above the title: «XE.gr, Green-Acres · 30/10 · 11.150 ενεργές · 1.501 ελεγμένες». Low-contrast-looking, jargon («ελεγμένες» of what?), and the first text on screen.
- After answering, sees no flat on the result screen (x1). It must scroll past two paragraphs of numbers.
- On every guide card, five full-width buttons. «Εγκρίνω» is the loudest, and what it does («Εγκρίνω» → «· το ενέκρινες») is unclear: does it buy, save or notify?
- The green status block says «Ελέγχθηκε η περιγραφή …» and they will stop reading before «Φωτογραφίες: δεν ελέγχθηκαν».
- «Από πού βγαίνουν» is a small teal line, hard to hit and easy to miss.
- On the listing page they scroll ~3.300 px of calculators to reach «Άνοιγμα στο XE.gr», with no «Πίσω».
- (?) tooltips never open on touch.

**Confused first-timer**
- Three ways in («Οδηγός», «Περιοχές», «Αναζήτηση») with no hint which to start with. Only the home default decides.
- On «Πού να αγοράσω» the decision box recommends Νέο Ψυχικό, Ζωγράφου, Χολαργός and Αμπελόκηποι. Then «Οι 3 πρώτες» is Γαλάτσι, Χαλάνδρι, Νέα Φιλαδέλφεια: which is the answer?
- Jargon reached without a definition on screen: «Παρόμοια (8): 35 % κάτω», «μεσαίο 50 % των παρομοίων», «διάμεσος», «Ρευστότητα και ζήτηση ενοικίου: άγνωστες ακόμα (χρειάζεται ιστορικό εβδομαδιαίων σαρώσεων από 30/10)».
- «Στην αγορά: 1 μέρες» on Χαλάνδρι is a grammar slip that undermines trust.
- Αγαπημένα empty state tells them to press «Αγαπημένο», but the guide cards they just used have no «Αγαπημένο», only «Εγκρίνω».
- Σύγκριση opens pre-filled with two flats they never chose, identified by «#10685».

**Power user (investor who wants speed)**
- The guide result has no sort and no filter beyond reopening chips. «Δείξε άλλες 8» pages 10 at a time.
- The map draws only «τις πρώτες 1.500» of 8.070 until filtered, and its filter is hidden in a collapsed «Φίλτρα».
- There is no compare-from-card: to compare two guide picks you go to Σύγκριση and type into two selects.
- The free-text search («π.χ. δυάρι στον Χολαργό έως 180.000 €, από 60 τ.μ., …») is the efficient path. But its filter box exposes ~12 controls with raw «300000» numerals and a truncated «δια…» chip.
- Without a token, verdicts and favourites vanish with the tab. This is stated, but there is no export or share.
- On desktop, the duplicated sidebar plus pill nav wastes 300 px of width, while guide buttons stretch to 400 px each (g1).

## 8. Minor observations

- The results header reads «Βήμα 5 από 5» with a full bar, but the guide docstring calls step 5 "the answer", not a step.
- `.ph-*` legacy card CSS (gradients `.ph-photo-*`, `.ph-grade-*`, `.ph-rec-*`) is still shipped in `theme.py` for admin-only pages. It is dead weight in the buyer surface's stylesheet and a source of drift: three radii (9 / 12 / 14 / 16 px) and several badge tints.
- `.st-key-hero` uses a decorative vertical gradient (`#FFFFFF → #F2FBF9`) and an 18 px radius, against 12–16 px everywhere else.
- Card radius differs: `.hg-card` containers 14 px, `stVerticalBlockBorderWrapper` 12 px, `.ph-card` 16 px, hero 18 px.
- Elevation is doubled: bordered containers, expanders and metrics all have a 1 px border **and** `--hg-shadow`, which is the "ghost card" pattern the craft floor warns about.
- No `:focus-visible` ring, `::selection` colour, `caret-color`, scrollbar theme or `font-variant-numeric: tabular-nums` is declared anywhere in `theme.py`. These are browser surfaces left at defaults.
- `.st-key-nav_pill` selected state uses `text-decoration: underline` on a pill, a link idiom on a button.
- The listing page's six checks use Streamlit colour markup (`:green[**καλό**]`, `:orange[**μέτριο**]`, `:gray[**άγνωστο**]`) rather than the badge tokens. This is a third status vocabulary.
- «Σκάουτ ακινήτων» (sidebar brand) appears nowhere on the phone, where the sidebar is collapsed. The product has no visible name on mobile.
- Rounding drift between surfaces: «~510 €/μήνα» on the card vs «12 × 509 €/μήνα» in the six checks; «35 % κάτω» vs «(−34,9 %)».

## Questions to consider

1. If the product's promise is "verified, not AI sloppy", why is the trust state (Υπό κατασκευή / Δεν έχει ελεγχθεί / Ελέγχθηκε) drawn as one more tinted text slab, instead of being *the* visual signature of every card? It could be the first thing the eye lands on, before the price.
2. Does the guide's answer need to be a list of 18 at all? What if step 5 showed *one* flat (the best checked one) as a full-width answer, with «Δες τις άλλες 17» below? That is the peak the journey currently lacks.
3. «Εγκρίνω», «Αγαπημένο», «Δεν μου κάνει», «Στον χάρτη»: is there one gesture (a single star or a "shortlist" toggle) that would make Αγαπημένα and Σύγκριση the natural end of the guide, rather than separate pages the user must rediscover?
