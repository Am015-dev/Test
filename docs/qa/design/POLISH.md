# Design finish — round 5, C6 (after)

Method: the same `measure.js` (Assessment B) on the merged head before polish
(`before-merged/`, main `b296a14` + this branch's docs) and on this branch (`after/`), same
database, same viewports (390×844 touch, 1280×900), same flows, run side by side. The rent
result screens (r1–r6) run on a QA instance with the 36-row test fixture
(`docs/qa/design/rent_app.py`, never deployed): **the published DB has no rental rows yet**, so
on the real data the rent flow stops at its «coming» note (r0, measured on the real DB).
No `ANTHROPIC_API_KEY` (the «Ρώτα με» panel and the brief do not render; not assessed) and no
`GITHUB_TOKEN` (favourites are session-only and the page says so). The heuristic scores after
were given by a fresh, isolated reviewer from the after screenshots, source and the live app
([`assessment-a-after.md`](assessment-a-after.md), re-checked after its first findings were
fixed: [`assessment-a-after-recheck.md`](assessment-a-after-recheck.md)); it never saw the
before scores, AUDIT.md or the measurements.

## Does it still look AI-generated? The design-specificity verdict first

**Before (AUDIT.md, A):** *content authored, chrome generic.* Every number named its basis, but
the frame was Streamlit-on-a-SaaS-template. The tells, all visible in `before-merged/`:

| # | Generic tell (before) | What replaced it (after) | Shots |
|---|---|---|---|
| 1 | Streamlit's pale-blue `st.info` box for every note and empty state | the product's own note: hairline box on the white surface, ink text; warning / error / success tinted only with the three status tokens | `h1-favourites`, `r0-rent-empty-realdb` |
| 2 | Default bordered containers: identical padding, a hairline **and** a soft shadow (the "ghost card"), radius 12 here, 14 there, 18 on the hero, with a decorative gradient | one card: 14 px radius, hairline on the canvas, no shadow; the hero's gradient removed | every result screen |
| 3 | The same card shape repeated with no rhythm | the first pick leads (accent hairline, the price at the large-title size); the rest step down to the title size | `a5-guide-result`, `r5-rent-result-fixture` |
| 4 | Equal-weight buttons everywhere; on the guide card the solid «Εγκρίνω» was the loudest thing | one primary per card («Εγκρίνω»), «Λεπτομέρειες» / «Αγαπημένο» secondary, «Δεν μου κάνει» tertiary (text weight, same 44 px height) | `a5-guide-result` |
| 5 | Pill nav with Streamlit's default outlines; the chosen page shown as teal text on a teal tint with an underline (3,9:1) | unchosen pills quiet (hairline, ink); the chosen one a solid accent fill with white text (5,5:1) | top of every screen |
| 6 | No identity: «Σκάουτ ακινήτων» in body ink at the size of a label, the data line competing with it | the wordmark set in the accent at the headline role, 750 weight, slight negative tracking; the data line a quiet footnote under it; nothing else in the header | top of every screen |
| 7 | The step bar «Βήμα 5 από 5» and a full progress bar still on the answer screen | the result has a header row: a small «Πίσω» and «Η πρότασή μου»; no bar | `a5-guide-result` |
| 8 | Status as Streamlit colour markup (`:green[]`, `:orange[]`, 3,2–3,6:1) and a green block that also said «Φωτογραφίες: δεν ελέγχθηκαν» | one semantic token set (ok / warn / bad / neutral, ink ≥ 6,3:1 on its tint); the photo clause its own neutral chip | `d1-listing`, `a5-guide-result` |
| 9 | 13-row bullet walls on «Πού να αγοράσω» with a code-font glyph sparkline | the facts as a grouped list: label muted above, value in ink, inset hairlines, no bullets; the sparkline in the accent, not in a code box | `c1-areas` |
| 10 | Compare as a boxed markdown grid | a grouped list: no outer box, inset separators, muted label column, values in ink | `h2-compare` |
| 11 | 15 font sizes, 15 radii, 32 off-scale spacings: values picked per rule | seven type roles, a 4-pt spacing scale, one radius family — all as `--hg-*` tokens | measurements below |
| 12 | Browser defaults: no focus ring, blue selection, default scrollbars, proportional digits | accent focus ring on every control, themed selection / caret / scrollbars, tabular numerals everywhere | keyboard walk below |

**After (verdict):** the frame now carries the product's own logic rather than Streamlit's: the
trust ladder is the coloured element on a card (and the only one), the price is the one loud
number, the first pick leads, notes read as notes, and the header names the product. It is
still recognisably Streamlit in places this contract cannot reach (the select menus, the
slider, the map's attribution and zoom controls, the sidebar drawer); those are listed under
«Not reachable» rather than hidden. Palette unchanged: slate ink, one teal, off-white canvas.

## Measurements, before → after (measure.js, same script, both runs)

`before-merged` = main `b296a14` (round 4 complete) before any C6 change; `after` = this branch.
The original pre-round-4 audit numbers are in AUDIT.md (`measure-before.*`); they are not
comparable row by row because round 4 changed the screens.

### 390 px

| measure | before (merged head) | after |
|---|---|---|
| screens measured | 22 | 22 |
| max scrollWidth | 390 | 390 |
| elements wider than the viewport | 0 | 0 |
| targets < 44 px / all | 484 / 534 | 0 / 535 |
| text under AA, words | 10 | 0 |
| text under AA, decorative «·» (aria-hidden) | 242 | 254 |
| text < 11 px | 0 | 0 |
| distinct font sizes | 11 (11.4, 12.8, 13.12, 14, 14.4, 15, 15.2, 16, 16.8, 20.8, 21.6) | 6 (13, 15, 16, 17, 20.8, 28) |
| distinct radii / shadows | 13 / 3 | 9 / 2 |
| margin/padding values, off the 4-pt scale | 37, 25 off | 21, 6 off |
| Tab stops without a visible ring / stops | 36 / 494 | 0 / 455 |

### 1280 px

| measure | before (merged head) | after |
|---|---|---|
| screens measured | 22 | 22 |
| max scrollWidth | 1280 | 1280 |
| elements wider than the viewport | 0 | 0 |
| targets < 44 px / all | 510 / 559 | 4 / 560 |
| text under AA, words | 10 | 0 |
| text under AA, decorative «·» (aria-hidden) | 242 | 254 |
| text < 11 px | 0 | 0 |
| distinct font sizes | 12 (11.4, 12, 12.8, 13.12, 14, 14.4, 15, 15.2, 16, 16.8, 20.8, 21.6) | 7 (12, 13, 15, 16, 17, 20.8, 28) |
| distinct radii / shadows | 14 / 3 | 8 / 2 |
| margin/padding values, off the 4-pt scale | 38, 26 off | 22, 5 off |
| Tab stops without a visible ring / stops | 36 / 497 | 0 / 458 |

### Per screen at 390 px (before → after)

| screen | scrollWidth | < 44 px | contrast fails, words | font sizes | no ring |
|---|---|---|---|---|---|
| a4-guide-kind | 390 → 390 | 13 → 0 | 0 → 0 | 4 → 6 | 1 → 0 |
| a5-guide-result | 390 → 390 | 62 → 0 | 0 → 0 | 9 → 6 | 1 → 0 |
| c1-areas | 390 → 390 | 15 → 0 | 1 → 0 | 6 → 6 | 3 → 0 |
| r4-rent-kind-fixture | 390 → 390 | 9 → 0 | 1 → 0 | 4 → 6 | 1 → 0 |
| r5-rent-result-fixture | 390 → 390 | 42 → 0 | 0 → 0 | 9 → 6 | 1 → 0 |
| a0-guide-mode | 390 → 390 | 6 → 0 | 0 → 0 | 4 → 5 | 1 → 0 |
| a1-guide-budget | 390 → 390 | 7 → 0 | 0 → 0 | 4 → 6 | 1 → 0 |
| a2-guide-goal | 390 → 390 | 6 → 0 | 0 → 0 | 4 → 6 | 1 → 0 |
| a3-guide-where | 390 → 390 | 6 → 0 | 0 → 0 | 4 → 6 | 1 → 0 |
| a6-guide-card-expander | 390 → 390 | 62 → 0 | 0 → 0 | 9 → 6 | 1 → 0 |
| d0-search | 390 → 390 | 51 → 0 | 1 → 0 | 8 → 5 | 3 → 0 |
| d1-listing | 390 → 390 | 34 → 0 | 4 → 0 | 8 → 6 | 8 → 0 |
| b1-map | 390 → 390 | 67 → 0 | 1 → 0 | 9 → 5 | 2 → 0 |
| h1-favourites | 390 → 390 | 6 → 0 | 1 → 0 | 4 → 4 | 1 → 0 |
| h2-compare | 390 → 390 | 16 → 0 | 1 → 0 | 9 → 5 | 3 → 0 |
| s1-saved-searches | 390 → 390 | 6 → 0 | 0 → 0 | 4 → 4 | 1 → 0 |
| e0-sidebar | 390 → 390 | 8 → 0 | 0 → 0 | 4 → 4 | 1 → 0 |
| r0-rent-empty-realdb | 390 → 390 | 6 → 0 | 0 → 0 | 4 → 5 | 1 → 0 |
| r1-rent-budget-fixture | 390 → 390 | 8 → 0 | 0 → 0 | 4 → 6 | 1 → 0 |
| r2-rent-beds-fixture | 390 → 390 | 6 → 0 | 0 → 0 | 4 → 6 | 1 → 0 |
| r3-rent-where-fixture | 390 → 390 | 6 → 0 | 0 → 0 | 4 → 6 | 1 → 0 |
| r6-rent-card-expander-fixture | 390 → 390 | 42 → 0 | 0 → 0 | 9 → 6 | 1 → 0 |

Reading the table:

- **Targets.** Every control family is ≥ 44 px at 390 px (`--hg-target`). The four left at
  1280 px are the map's attribution links «OpenStreetMap» / «CARTO» (15 px, inline text drawn by
  the map library, WCAG 2.5.8 inline exception) on Περιοχές and Χάρτης. A multiselect chip's
  remove «×» is sized to 24 px, the WCAG 2.5.8 AA minimum, not 44: a 44 px chip would make every
  chosen option a button-sized block.
- **Contrast.** No word fails. The «·» separators (254 nodes) are decorative, now `aria-hidden`
  and lifted from 2,43:1 to 3,29:1 (`--hg-sep`); they are counted on their own row so the table
  reads honestly. They stay under 4,5:1 on purpose: at 4,5:1 the dots compete with the numbers
  they separate.
- **Type.** The phone uses 6 sizes, all type roles (13 footnote · 15 subhead · 16 body ·
  17 headline · 20,8 title · 28 large title); the desktop adds 12 (caption: the map attribution).
  Every `font-size` in `theme.py` is a role token (asserted in `tests/test_theme.py`).
- **Spacing and shape.** Every margin, padding and gap in `theme.py` is on the 4-pt scale and
  every radius is a token (asserted). The six off-scale values and the 4 / 8 / 12 / 9999 px radii
  still measured on the page are Streamlit's own widget internals (react-aria select, toggle
  track, checkbox), not ours.
- **Focus.** A real Tab walk now finds a visible accent ring on every stop (0 of 455 / 458
  without). Before, 36 stops had none, among them every nav pill.
- **Width.** `scrollWidth` = 390 / 1280 on every screen, before and after; nothing is wider than
  the viewport.
- **Method changes, applied to both runs:** focus is checked by a real Tab walk (not by
  programmatic focus), content of closed `<details>` and screen-reader-only inputs are not
  counted as visible (`checkVisibility()`), and a `label[for]` whose control is visible is
  counted through its control. These removed false positives on both sides (the map slider's
  hidden range inputs, links inside a collapsed expander).

## Scores

| # | Heuristic | AUDIT.md (before) | after | note (after) |
|---|---|---|---|---|
| 1 | Visibility of system status | 3 | 3 | step line and bar gone from the result; the rent «coming» note (r0) still shows «Βήμα 1 από 5» |
| 2 | Match system / real world | 2 | 3 | «1 μέρα», glossary terms; analyst jargon on Περιοχές and the listing page remains |
| 3 | User control and freedom | 2 | 3 | «Πίσω» on the listing page and the result; favourites session-only, listings not linkable |
| 4 | Consistency and standards | 1 | 2 | one type scale, one radius family, one status vocabulary, same card buttons; two navigations with different names on desktop remain |
| 5 | Error prevention | 2 | 2 | chips no longer clip; the search's default order still opens on unchecked flats 33–35 % under comparables (ranking, not C6) |
| 6 | Recognition rather than recall | 3 | 3 | saved searches only in the sidebar; compare options carry «#id» |
| 7 | Flexibility and efficiency | 2 | 3 | keyboard path complete (a ring on every Tab stop) |
| 8 | Aesthetic and minimalist design | 2 | 2 | calmer chrome, a leading first pick; card density and the long listing page remain |
| 9 | Error recovery | 2 | 3 | empty favourites lead to «Οδηγός»; the rent «coming» note has no way to the buy flow |
| 10 | Help and documentation | 3 | 3 | unchanged; `help=` tooltips still hover-only |
| | **Total** | **22 / 40** | **27 / 40** | +5: the DoD asks +6; the points left are outside C6 (see «Remaining») |

| # | Audit dimension | before | after | key finding (after) |
|---|---|---|---|---|
| 1 | Accessibility | 2 | 3 | 0 word contrast fails, 0 Tab stops without a ring, 0 phone targets < 44 px; not a full screen-reader audit, and `help=` tooltips still need hover |
| 2 | Performance | 3 | 3 | one injected sheet (54 KB) per rerun, no new animation cost; the four CSS sources remain |
| 3 | Theming | 2 | 3 | `--hg-*` tokens for colour, status, type, space, shape and target; no dark mode (out of scope, follow-up) |
| 4 | Responsive design | 1 | 4 | no overflow at 390; every control family ≥ 44 px; hover gated to fine pointers, pressed state on touch |
| 5 | Implementation integrity | 2 | 3 | one type scale, one spacing scale, one radius family, elevation declared once; page modules still ship their own small `<style>` blocks (overridden, not removed: not C6 files) |
| | **Total** | **10 / 20** | **16 / 20** | |

## What changed, by file

- `src/scout/ui/theme.py` (owned): tokens in `:root` (status ok / warn / bad / neutral with
  ink ≥ 6,3:1 on each tint, `--hg-sep`, seven type roles, the 4-pt scale `--hg-s1…s10`, radii
  `--hg-r-card 14 / control 10 / chip 6 / pill`, `--hg-target 44px`); every literal font size,
  spacing and radius mapped onto them; ghost-card shadows removed (hairline only), hero gradient
  removed, side-stripe borders replaced by full 1 px tone borders; every `:hover` gated to
  `(hover: hover)`; the round-5 block: type roles, touch targets for every widget family
  (buttons, link buttons, pills, segmented controls, expander summaries, the card's
  «Από πού βγαίνουν» row with a drawn chevron, checkbox / toggle / radio labels, number and text
  inputs and steppers, react-aria selects, multiselect, tooltip icons, map and toolbar buttons),
  the focus ring, pressed / disabled states with a reduced-motion fallback, the status tones,
  grouped lists (area cards, the six checks, compare), notes for `st.info / warning / error /
  success`, the header wordmark, quiet pills, the first pick leading, sticky listing actions,
  and the browser surfaces (selection, caret, scrollbars, underline offset, tabular numerals).
  The page modules' `<style>` blocks rendered as empty 12 px gaps; they are taken out of the
  layout (the styles still apply).
- `.streamlit/config.toml`: unchanged; its colours already match the tokens.
- Class hooks / data attributes only: `app.py` (`st.container(key="app-head")` around the
  wordmark and the data line), `areas.py` (`key="area-card-…"`; the six checks' verdict word as
  `<span class="hg-v hg-v-…">` instead of `:green[]` markup), `buyer.py` (`aria-hidden` on the
  «·» separator; `data-rank` on the card; the photo clause as its own neutral chip),
  `components.py` (the map legend's inline `font-size` → `class="hg-legend"`).
- Coordinator-approved changes (decisions message): `buyer.open_detail` remembers
  `detail_from`, the listing page gets the title «Αγγελία» and «Πίσω» (fallback: the home
  page), and its select label is collapsed because the title now says the same; the empty
  «Αγαπημένα» gets an «Οδηγός» button; the guide and rent results drop the step line and bar
  (`guide.result_head`, «Πίσω» small next to the title); the guide recommendation is three short
  lines with every number and the basis kept; «Όσα να 'ναι» → «Οποιαδήποτε» (wording defect);
  «Οι 3 πρώτες» → «Οι 3 πρώτες στη συνολική βαθμολογία» (the basis was unnamed).
- Tests: new `tests/test_theme.py` (token set, type roles, every font size a role, 4-pt
  spacing, one radius family, the 44 px rule and its hooks, focus ring and browser surfaces,
  hover only for fine pointers, craft-floor bans, status / accent / separator contrast);
  `tests/test_shell.py` (+2: «Πίσω» returns where the listing was opened, or home; the empty
  favourites' «Οδηγός»); `test_guide.py` / `test_rent_guide.py` (the result has no step line, as
  decided); `test_where_to_buy.py` and `test_card_render.py` follow the new markup, same words.
- QA: `docs/qa/design/measure.js` (rent flow, Tab walk, visibility), `rent_app.py` (QA-only
  fixture instance), `docs/qa/shots.js` (step 0 and the renamed buttons).

## Remaining, with reasons

The heuristic total rose by 5 (22 → 27), one short of the +6 in the definition of done. The
independent reviewer names what holds the last points; none is a theme change:

- **P1 (coordinator): two navigations that disagree on desktop.** The sidebar radio lists
  «Πού να αγοράσω» and «Αποθηκευμένες αναζητήσεις», the pills say «Περιοχές» and have no saved
  searches (`app.main`, `SHORT_NAV`). One name per page and one visible navigation per width is
  a shell decision (W10's `app.py`), not CSS: hiding the sidebar nav on desktop would strand
  «Αποθηκευμένες αναζητήσεις».
- **P1 (coordinator, ranking): Αναζήτηση and the Χάρτης list open on unchecked flats 33–35 %
  under comparables**, just inside the 35 % too-cheap line. C6 forbids ranking changes; a default
  of «checked first» or the guide's order is the fix.
- **P2: the rent «coming» note (r0, real DB) still shows «Βήμα 1 από 5» and a bar, and offers
  only «Πίσω»** (`rent_guide.page` draws the progress before the empty check). A one-line order
  change plus a «Να αγοράσω» button; logic, so left for your call.
- **P2: the listing page is ~3.200 px**, with the six-field calculator before the six checks;
  the actions are now sticky at the bottom, the section order is a content decision.

- **P2: the «·» separators stay at 3,29:1** (decorative, aria-hidden; see above).
- **P2: `help=` tooltips are hover-only on a phone.** Moving their text into captions is a
  content decision (AUDIT P3-22, coordinator).
- **P3: the map caption «Μόνο N … ακριβή θέση» is printed twice** (`app.page_map` and
  `maplist.render`): a copy change in two non-C6 files, left for the owner of those pages.
- **P3: compare options still end in «· #id»** (`app.page_compare`, outside C6).
- **Not reachable inside Streamlit's DOM without `!important` wars:** the select drop-down
  menu, the slider, the map's own zoom and attribution controls, the sidebar drawer's
  open / close animation, the Material Symbols icons (never overridden). They inherit the
  accent, focus ring and radius tokens where Streamlit exposes them.
- **Dark mode:** not in scope (Streamlit's theme is light). Follow-up: the tokens are the place
  to add a `prefers-color-scheme: dark` set.
- **Not assessed:** «Ρώτα με» and the investor brief (no API key in this sandbox); sign-in
  (needs the stubbed second instance).

## Screens

Before / after side by side (390 px, top of the page): `pairs/a5-guide-result-390.png`,
`pairs/a4-guide-kind-390.png`,
`pairs/r5-rent-result-fixture-390.png`, `pairs/d1-listing-390.png`, `pairs/c1-areas-390.png`,
`pairs/h2-compare-390.png`, `pairs/h1-favourites-390.png`, `pairs/r0-rent-empty-realdb-390.png`.
Full shots: `before-merged/<id>-<width>.png` and `after/<id>-<width>.png` for a0–a6, c1, d0,
d1, b1, h1, h2, s1, e0, r0 (real DB) and r1–r6 (fixture), at 390 and 1280.
