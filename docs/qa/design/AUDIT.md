# Design audit — round 5, C6 (before)

Method: dual-agent. Assessment A (design review from screenshots and source) ran as an isolated
sub-agent and finished before any measurement was read; its full report is
[`assessment-a.md`](assessment-a.md). Assessment B is [`measure.js`](measure.js) (Playwright,
computed styles on the running app; raw output [`measure-before.json`](measure-before.json),
table [`measure-before.md`](measure-before.md)). The impeccable `detect` binary is not vendored;
measure.js is its replacement per `.claude/skills/impeccable/SKILL.md`. Head measured:
`e3f490d` (main before round-4 PRs #87 #88 #89). App: Streamlit 1.66 on 127.0.0.1:8501 against
the published DB (`data` branch, 11.150 active listings, data dated 30/10), no
`ANTHROPIC_API_KEY` (so «Ρώτα με» and the «Σημείωμα επενδυτή» brief do not render and were not
assessed) and no `GITHUB_TOKEN` (favourites and verdicts are session-only; the sidebar says so).
Viewports 390×844 (touch, isMobile) and 1280×900. **The rent flow (Οδηγός → «Να νοικιάσω», r1–r5)
is pending: it exists only after PR #89 merges; it is measured in phase 2.**

Screens (both widths, `before/<id>-<width>.png`): a1 budget, a2 goal, a3 where, a4 kind,
a5 result, a6 result with a card's «Από πού βγαίνουν» open, c1 Περιοχές, d0 Αναζήτηση,
d1 listing page (Αγγελία), b1 Χάρτης, h1 Αγαπημένα (empty), h2 Σύγκριση, s1 Αποθηκευμένες
αναζητήσεις, e0 sidebar. Phone shots are capped at 4.200 px tall, desktop at 3.000 px.

## Measured evidence (B), phone 390 px

| measure | value | DoD target |
|---|---|---|
| `scrollWidth` | **390 on all 14 phone screens** (1280 on all desktop) | 390 |
| interactive targets < 44 px tall | **448 of 481** (93 %) | 0 |
| text nodes under WCAG AA | **242**, of which **231** are the decorative «·» separator (`span.hg-sep`, 2,43:1) and **11** are words | 0 |
| text < 11 px | 0 | 0 |
| distinct font sizes (all screens) | **15**: 12, 12.8, 13.12, 14, 14.4, 15, 15.2, 16, 16.8, 20, 21.6, 22.4, 24, 28, 36 px | ≤ 8 |
| distinct border radii | 15 (9 px ×223, 9999 px, 8, 6, 14, 999, 12, 4, 50 %, 10, 7, 2 …) | one family per role |
| distinct box-shadows | 4 | 1–2 |
| margin/padding values | 44 distinct, 32 off the 4-pt scale (2.5, 4.8, 13.6, 17.6, 18.4, 49.6 …) | 4-pt scale in theme.py |
| controls with no `:focus-visible` change | **172 of 495** checked (all nav pills, 36 buttons, 18 inputs, 10 selects, 9 link buttons) | 0 |

Where the small targets are (phone, count × height): segmented controls / pills
`[data-testid=stButtonGroup] button` 84 × 40 px and 15 × 32 px; `stBaseButton-secondary` 72 × 40
and 57 × 36 px; the card disclosure `.hg-card summary` 43 × **18,4 px**; link buttons
`stBaseLinkButton-secondary` 46 × 36–40 px; primary buttons 20 × 40 px; number inputs 35,6 px and
their ± steppers 38 px; selectbox 38 px; expander summaries 38 px; checkbox labels 22,4 px;
tooltip (?) icons 16 px; map zoom buttons 28,8 px; multiselect 28 px.

The 11 word-level contrast failures: the **selected nav pill** (teal `#0F766E` on its tint
`rgb(201,223,224)`, 3,93:1) on every page except the guide; on the listing page the six-check
verdicts «μέτριο» (`:orange`, 3,24:1) and «άγνωστο» (`:gray`, 3,62:1); on the map two slider
value labels read as teal-on-teal (1:1) — a **false positive**: the background resolver picks the
slider track under the floating label; verify visually in phase 2.

Not measured: hover/pressed states (A judged them), the assistant panel (no key), the sign-in
sidebar flow (needs the stubbed second instance). Known limit: a closed native `<details>` keeps
its body in the layout tree in Chromium, so a5 already counts the basis text that a6 opens;
the two rows are therefore identical.

## Heuristic scores (A, confirmed by B)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | «Βήμα N από 5» + bar, data line, counts are good; the result still shows «Βήμα 5 από 5» and «Πίσω» as if it were a question |
| 2 | Match system / real world | 2 | analyst shorthand («Παρόμοια (8): 35 % κάτω», «μεσαίο 50 % των παρομοίων», «διάμεσος»); compare options end in «#10685»; basemap says «ATHENS» |
| 3 | User control and freedom | 2 | listing page has no way back; undo of «Δεν μου κάνει» hides in a collapsed expander at the bottom |
| 4 | Consistency and standards | 1 | «Εγκρίνω» vs «Αγαπημένο» for one intent; four page-title treatments; «−24%» vs «24 % κάτω»; two selected-nav styles; 15 font sizes, 15 radii (B) |
| 5 | Error prevention | 2 | filters confess their cost; but raw «300000», truncated «δια…» chip, and touch sticky-hover makes the next step's button look pre-selected |
| 6 | Recognition rather than recall | 3 | answer chips and the filter summary in the expander label are textbook; Σύγκριση makes you re-find flats by typing |
| 7 | Flexibility and efficiency | 2 | free-text search is a real fast path; no sort on the result, no compare-from-card |
| 8 | Aesthetic and minimalist design | 2 | honest but dense cards with five stacked buttons; 13-bullet area cards; repeated map caption; ~70 px dead band under the data line |
| 9 | Error recovery | 2 | relax buttons with «+N» are excellent; empty states are a sentence, not a control |
| 10 | Help and documentation | 3 | «Από πού βγαίνουν», «Πώς υπολογίζω» are inspectable; `help=` tooltips are hover-only on a phone |
| | **Total** | **22 / 40** | **Acceptable** — significant work needed |

## Audit dimensions (B-led)

| # | Dimension | Score | Key finding |
|---|---|---|---|
| 1 | Accessibility | 2 | 172/495 controls show no focus ring; selected pill 3,93:1; six-check verdict colours 3,2–3,6:1; tooltips need hover |
| 2 | Performance | 3 | one injected sheet per page, no animation cost; four separate CSS sources re-sent each rerun; result DOM ~400 text nodes |
| 3 | Theming | 2 | `--hg-*` tokens exist but `#DC2626`, `:green[]`/`:orange[]` markup and the blue `st.info` sit outside them; no status tokens; dark mode absent (out of scope, follow-up) |
| 4 | Responsive design | 1 | no horizontal scroll anywhere (good) but 93 % of touch targets are under 44 px, the card disclosure is 18 px, `:hover` sticks on touch |
| 5 | Implementation integrity | 2 | 15 font sizes, 15 radii, 32 off-scale spacings; ghost-card elevation (border + shadow); banned side-stripe borders; three card vocabularies (`ph-*`, `hg-*`, `pick-*`) |
| | **Total** | **10 / 20** | **Acceptable** |

Design-specificity verdict (A): the *content* is authored for this buyer (every number names
its basis, the trust ladder, «(από το όνομα της γειτονιάς)», the price-position bar); the
*chrome* is category-generic calm SaaS on Streamlit. The polish should make the trust ladder
and the basis rows the visual signature instead of adding decoration.

## Issues

Fix scope per C6: `ui/theme.py` and `.streamlit/config.toml`; elsewhere class names / keys only;
copy only for the wording defects named here. Items marked **(coord)** need a decision or a file
outside C6 and are reported, not silently skipped.

### P0
None: every primary task completes on a phone.

### P1
1. **Touch targets under 44 px, systemic (B).** `theme.py`: `.stButton > button`,
   `[data-testid=stBaseButton-secondary|primary]`, `[data-testid=stBaseLinkButton-secondary]`,
   `[data-testid=stButtonGroup] button`, `[data-testid=stExpander] summary`,
   `.hg-card summary` (`buyer.CARD_CSS`), `[data-testid=stNumberInputField]` and steppers,
   `[data-baseweb=select] > div`, `[data-testid=stCheckbox] label`, `[data-testid=stRadioOption]`.
   Fix: one `--hg-target: 44px` token; `min-height` on every control at ≤ 640 px (and desktop for
   consistency); the card disclosure becomes a full-width 44 px row; 8 px gap between adjacent
   targets. Streamlit-owned (map zoom 28,8 px, tooltip 16 px, element toolbar 24 px): enlarge via
   `min-height`/padding where the hook allows, list the rest as exceptions.
2. **No visible keyboard focus on 172 controls (B).** `theme.py`: add one
   `:focus-visible { outline: 2px solid var(--hg-accent); outline-offset: 2px }` for `button`,
   `a`, `summary`, `[role=radio]`, inputs and the BaseWeb select wrapper (`:focus-within`).
3. **Selected nav pill fails contrast, 3,93:1 (B).** `theme.py`
   `.st-key-nav_pill button[aria-checked="true"]` (teal on teal tint, underline): solid accent
   fill with white text (5,5:1) and no underline; reuse the same selected style for the desktop
   sidebar radio (A P2-12).
4. **Guide result: no flat above the fold (A P1-1).** `guide.page()` / `_progress()`
   (`.st-key-guide-progress`), `theme.py` phone padding
   `@media (max-width:640px) [data-testid=stMainBlockContainer] { padding: 3.1rem … }`. Fix: key
   the progress block per step (class hook) and hide it on the result; reduce the top band
   (~70 px dead space under `stCaption`). Shorter recommendation sentence is a copy change —
   **(coord)**, it touches guide copy that #89 also edits.
5. **Card actions: five full-width buttons, the loudest is «Εγκρίνω» (A P1-2).** `guide._card()`
   in `.st-key-pick-*`. Fix in `theme.py`: verdict pair as one quiet two-up row, link-style
   «Άνοιγμα στο XE.gr» / «Στον χάρτη», one bordered «Λεπτομέρειες». The «Εγκρίνω» vs «Αγαπημένο»
   vocabulary is a glossary decision **(coord)**; PR #88 already reduces card buttons to two.
6. **Status block is green while it says photos were not checked (A P1-3).**
   `buyer.card_html()` `.hg-st.hg-st-ok` + «Φωτογραφίες: δεν ελέγχθηκαν». Fix: status tokens
   (`--hg-ok-*`, `--hg-warn-*`, `--hg-bad-*`, ≥ 4,5:1 on their tints) in `theme.py`; class hook
   to give the photo clause its own neutral span (same words). #88 rewrites `card_html`, so the
   hook lands after the merge.
7. **Πού να αγοράσω: «Οι 3 πρώτες» contradicts the decision box; 13-row bullet walls
   (A P1-4).** `areas.page_areas()` heading, `areas._card()` `st.container(border=True)`.
   Fix: wording defect — «Οι 3 πρώτες» names its basis («στη συνολική βαθμολογία»); key the card
   (`area-card-*`) and render its facts as a grouped list in `theme.py`.
8. **Listing page: no title, no way back, actions after ~3.300 px (A P1-5).**
   `buyer.page_listing()`. Fix in C6: page-title class, sticky action bar via
   `st.container(key="listing-actions")` + `position: sticky`. A «Πίσω» button changes
   navigation logic **(coord)**.

### P2
9. **Separator «·» at 2,43:1 (B, 231 nodes).** `span.hg-sep` uses `--hg-faint` `#94A3B8` on the
   canvas. Decorative, but it is the most frequent glyph on every card: move to `--hg-muted`
   (4,51:1 on the canvas, 4,76:1 on a white card) so the whole line reads as one grey.
10. **Six checks colour words below AA (B):** «μέτριο» 3,24:1, «άγνωστο» 3,62:1 — Streamlit
    `:orange[]` / `:gray[]` markup in `buyer.page_listing` (A minor: a third status vocabulary).
    Fix: map to the status tokens via a class hook; until then the theme cannot reach
    Streamlit's colour markup without `!important`.
11. **Type scale drift: 15 font sizes (B).** Fix: the seven type roles as tokens (large title
    1.75, title 1.3, headline 1.0625/600, body 1.0, subhead .9375, footnote .8125, caption .75 rem)
    and every `hg-*` / heading / caption rule pointing at them.
12. **Radius and elevation drift (B + A):** 15 radii; bordered containers, expanders and metrics
    carry a hairline **and** `--hg-shadow` (ghost card); hero 18 px with a gradient. Fix: cards
    14 px, controls 10 px, pills 999 px; elevation = hairline only on the canvas, the soft shadow
    reserved for the one raised card.
13. **Banned side-stripe borders.** `theme.py` `.hg-note-bad { border-left: 4px }`, `.hg-advice*`.
    Fix: 1 px full border in the tone token on the tint.
14. **Four page-title treatments (A P2-7).** `##`, `st.subheader`, h1, none. Fix: one
    `.hg-page-title` role (class hook per page) at 1.75 rem.
15. **Touch sticky hover looks like a pre-selected answer (A P2-8).** `theme.py`
    `.stButton > button:hover`. Fix: wrap hover rules in `@media (hover: hover)`, give touch an
    `:active` pressed state.
16. **Guide step chrome (A P2-9):** «Βήμα N από 5» drifts; step 4 wraps «Οτιδήποτε» alone; «Όσα
    να 'ναι» is colloquial (wording defect → «Οποιαδήποτε»).
17. **Empty states: blue `st.info`, no next-step control (A P2-11).** Re-tint `stAlert` info to the
    neutral surface; an «Οδηγός» button in the empty Αγαπημένα is a logic change **(coord)**.
18. **Spacing off the 4-pt scale (B):** 32 values. Fix: `--hg-space-*` tokens, every margin and
    padding in `theme.py` on 4 8 12 16 20 24 32 40.

### P3
19. Browser surfaces at defaults: no `::selection`, `caret-color`, scrollbar theme,
    `text-underline-offset`, `tabular-nums` (A minor, B confirms no `font-variant-numeric`).
20. Map: «Μόνο 23 … ακριβή θέση» printed twice (A P3-13) — copy, `app.page_map`.
21. Compare: «−24% €/τ.μ.» vs the cards' «24 % κάτω», «#10685» in options (A P3-14) — #88 owns
    the compare page; re-check after merge.
22. `help=` tooltips are hover-only on a phone (A P3-15) — content decision **(coord)**.
23. Harness drift: `docs/qa/shots.js` still clicks «Η πρότασή μου →» and «Επόμενο ›» (both
    renamed); flows a and b stop early. Update with the after-run.

## Systemic patterns

- **Controls inherit Streamlit's 36–40 px heights.** The theme styles colour and radius but never
  height, so every widget family misses 44 px by 4–8 px; one token fixes ~400 targets.
- **No interaction-state layer:** no focus ring, hover not gated to fine pointers, no pressed state.
- **Values chosen per rule, not from a scale:** 15 font sizes, 15 radii, 32 off-scale spacings —
  four CSS sources (`theme.py`, `buyer.CARD_CSS`, `guide.CSS`, `maplist._css`) each pick their own.
- **Status colour is spoken three ways** (`.hg-st-*` tints, `:green[]` markup, blue `st.info`);
  there is no semantic token set.

## What works

- **Zero horizontal scroll** on every screen at 390 px, including the map and the listing page.
- **No text under 11 px** anywhere; body text is ink on off-white well above 4,5:1.
- **Every number has its basis within one tap** («Από πού βγαίνουν» spells out
  «12 × 1.070 € ÷ 335.000 € = 3,8 %»), and filters confess what they hide with «+N» counts.
- **The guide's one-question-per-screen structure** with answer chips that reopen a question is
  the clearest IA in the app and the right model for the older phone user.
