# Coordination brief — "fix the AI sloppiness" programme (2026-10-31)

One coordinator session plans, reviews and merges. Several worker sessions each own a
disjoint set of files and ship one draft PR. Read this whole file before touching code.

## Who the user is and what "AI sloppy" means to them

The owner is Greek, uses the app **on a phone**, and wants to buy ONE flat in NE Athens as a
buy-to-let investment (budget ≈ 300k, prefers new, next to a metro/ΗΣΑΠ station). They have
read the real XE listing pages behind our recommendations and found: flats still under
construction, photos that are 3D renders or architect's drawings, bare-wall shells, agency
logos instead of photos. Their words: "extremely AI sloppy", "confusing", "useless on a
phone", "I see no insights", "filters are very low — I told you building age and floor and I
still see the same shit".

"AI sloppy" = any of:

- a number without its basis (a yield with no rent figure, a score with no parts);
- a claim the data cannot support ("ευκαιρία", "fair value", "checked") presented as fact;
- generic filler sentences; marketing adjectives; emoji decoration; three words for the
  same thing on different pages (ενοίκιο / μίσθωμα / rent);
- a filter the user set that the results visibly ignore;
- a page that needs a laptop (wide tables, 4-column metric rows, sidebars with 15 widgets);
- English or mixed-language UI, `1,234.5`-style numbers (Greek is `1.234,5`), raw field
  names, tracebacks, "N/A".

Trust beats cleverness. If we don't know, the UI says we don't know, in one short line.

## Product facts you need

- Live app: https://xescout.streamlit.app/ (Streamlit 1.66, deploys from `main`, hot-reloads
  via the stale-module guard in `src/scout/ui/app.py`).
- Data: SQLite on the orphan `data` branch, refreshed weekly by `.github/workflows/daily.yml`
  (XE.gr only; XE blocks this sandbox but the GitHub runner can reach it). Get it with
  `mkdir -p data && curl -sSfL -o data/listings.db https://raw.githubusercontent.com/Am015-dev/Test/data/listings.db`
  and run anything with `DATABASE_URL="sqlite:////ABS/PATH/data/listings.db"`.
- Listings have NO exact coordinates; station proximity is inferred from the XE sub-area
  name (`picks.STATIONS`). Rents are XE asking rents (`rent_comp` table), not contracts.
- `is_unfinished` is set from the listing's own page (`xe.unfinished_on_detail`); a page
  counts as checked only if `detail_checked_at >= xe.UNFINISHED_CHECK_SINCE`
  (`queries.py` → `d["page_checked"]`). ~2,300 new-build pages are being re-read in weekly
  runs, station neighbourhoods first — so for a while many listings are legitimately
  "not checked yet". The UI must say that, not pretend.
- Comparables: `market_intel.Intel.comps(d)` = same area (Athens quarter), same kind
  (flat/house), age band, size band, floor band. >35 % under comps median = `too_cheap`
  warning, never a bonus.
- Pages (`app.py: NAV`): «Βρες μου σπίτι» (`ui/find.py`, `picks.py`), «Πού να αγοράσω»
  (`ui/areas.py`, `area_insights.py`), «Αναζήτηση» / «Αγαπημένα» / «Αποθηκευμένες
  αναζητήσεις» / «Αγγελία» (`ui/buyer.py`), «Χάρτης» / «Σύγκριση» (`app.py`). Old analyst
  pages live behind `?admin=1` (`ADMIN_NAV`) and are out of scope.
- User state (favourites, approve/drop verdicts, saved searches) persists in a private GitHub
  Gist via `shortlist.py`; without `GITHUB_TOKEN` it is session-only and the UI says so.

## Rules for every worker

1. **Own only your files.** The ownership table is in your brief. If you truly need a change
   elsewhere, make the smallest possible one and call it out at the top of your PR body.
   Never edit `app.py` unless it is in your list.
2. **Gate before every push** (CI runs the same):
   `python -m pytest -q && ruff check src/ tests/ scripts/ && black --check src/ tests/ scripts/`
   plus `python -m pytest -q tests/test_ui_gauntlet.py` with GAUNTLET unset (renders every page; `GAUNTLET=0` is a non-empty string and would start the 25-minute widget sweep — run that only once, at the end).
3. **Look at your page on a phone before claiming done.** Run the app against the live DB
   (`streamlit run src/scout/ui/app.py --server.headless true --server.port 8501`) and
   screenshot it with Playwright at viewport 390×844 (Chromium is pre-installed:
   `require('playwright')` works; `NODE_PATH=$(npm root -g) node x.js`). Save the before/after
   screenshots under `docs/qa/<workstream>/` and reference them in the PR.
4. Greek UI, Greek numbers (`1.234 €`, `4,7 %`), one term per concept (glossary below).
   Python ≥ 3.11, `from __future__ import annotations`, line length 100.
5. **No mock or seed data; no invented numbers.** Every figure on screen must trace to a
   field or a computation you can name in one sentence — and the UI should name it too.
6. Tests: add or extend tests for behaviour you change; never weaken or skip a test to pass.
7. Branch `ws/<workstream>`; commit messages plain (no model names); open ONE **draft PR**
   to `main` with the GitHub MCP tools (`mcp__github__create_pull_request`, draft=true).
   **Do not merge.** The coordinator merges.
8. When done, send the coordinator a ≤10-line summary with
   `mcp__claude-code-remote__send_message` to session
   `session_01RR7mnY233P7UW5W8MvrPrX`: PR URL, what changed, what you verified (screenshots,
   test counts), anything you could not do. Also finish your session's final message with
   the same summary.
9. If blocked for more than ~15 minutes on something outside your files, message the
   coordinator instead of working around it in someone else's files.

## Glossary (use exactly these)

| concept | term |
|---|---|
| asking price | Τιμή |
| €/m² | €/τ.μ. |
| monthly rent estimate | Ενοίκιο (εκτίμηση) ~X €/μήνα |
| gross yield | Μικτή απόδοση |
| net yield | Καθαρή απόδοση |
| comparables | Παρόμοια (N) |
| under construction / off-plan | Υπό κατασκευή |
| listing page read with the check | Ελέγχθηκε η περιγραφή |
| not yet read | Δεν έχει ελεγχθεί ακόμα |
| station | Σταθμός (ΗΣΑΠ/Μετρό + line) |
| favourites | Αγαπημένα |
| days on market | X μέρες στην αγορά |

## Definition of done for the programme (coordinator checks)

- Every main-nav page renders on a 390 px phone without horizontal scroll, with the answer
  above the fold and no English, raw keys or decoration.
- No recommendation anywhere shows an under-construction, render-only or unchecked flat as
  if it were verified. Unchecked = labelled unchecked.
- Every number on a card has its basis within one tap.
- Filters set by the user are honoured and the result count says what was hidden and why.
- Gate green; Playwright phone screenshots of every page in `docs/qa/final/`.

---

# Round 3 — "one guided flow, everything connected" (2026-10-31, 16:00)

Round 1–2 fixed honesty and filters. The owner's verdict after using it: still "AI sloppy" —
only 3–4 results, a map that shows a dot while the list is somewhere else, pages that feel like
separate items, no guidance, nothing an investor would actually look at, and no memory of who
they are. Round 3 builds the product around ONE flow. Read everything above first; it still
holds (phone-first, Greek, glossary, gate, screenshots, draft PR, message the coordinator).

## Product spec (binding)

### 1. «Οδηγός» — the home page is a short guided game, not a form
One question per screen, big tappable choices, a progress line «Βήμα 2 από 5», a back
chip, no typing except the budget. A child or a grandparent must be able to finish it.
1. «Πόσα θες να βάλεις;» chips 150 / 200 / 250 / 300 / 400 / 500 χιλ. € + «άλλο ποσό»; toggle
   «με δάνειο» (changes the net calculation: 70 % loan, 4 % rate, 25 years — show the monthly
   instalment next to the rent so the answer is "δεν βγαίνει / βγαίνει με X €").
2. «Τι σε νοιάζει πιο πολύ;» → Απόδοση ενοικίου · Σιγουριά & εύκολη ενοικίαση · Ανατίμηση
   (μετρό, ανάπτυξη περιοχής). Sets the ranking weights (document them in the method box).
3. «Πού;» → Κοντά σε μετρό/ΗΣΑΠ · Συγκεκριμένες περιοχές (chips of the covered areas) ·
   Όπου βγαίνει ο καλύτερος αριθμός.
4. «Τι σπίτι;» → Νεόδμητο (≤10) · έως 20 ετών · Οτιδήποτε, and υπνοδωμάτια chips.
5. «Η πρότασή μου»: one sentence with the recommended area(s) and why (numbers), then the
   ranked list — **10 at a time with «Δείξε άλλες 10»**, never a hard cap of 3 — each card with
   the status/photo facts from round 1–2, then the assistant's brief (see 3). The answers are
   shown as chips at the top («300 χιλ. · απόδοση · κοντά σε μετρό · νεόδμητο») and each chip
   reopens its question. Answers persist in the profile (see 4).
«Βρες μου σπίτι» becomes this flow (keep `picks.find`/`relaxations` as the engine); the old
page is retired, not duplicated.

### 2. Everything connected — one selection, one list, one map
`st.session_state["selected_id"]` is the single selection. A card's «Στον χάρτη» button opens
the map centred on it with the point highlighted; tapping a point on the map
(`st.pydeck_chart(..., on_select="rerun", selection_mode="single-object")`) selects that
listing and its card renders DIRECTLY UNDER the map (not in a table somewhere below). The map
is a toggle inside the results, not a separate destination; the «Χάρτης» page shows the same
ranked list under the map. Compare takes its two flats from favourites or from the current
list with one tap («Σύγκρινε με το προηγούμενο»). No page may show a table the user has to
scroll to in order to understand a dot.

### 3. The assistant — smart, grounded, never Captain Obvious
A «Ρώτα με» box on the results and listing pages (hidden when no API key). It receives, as
JSON, the facts we already computed for the current shortlist/listing (price, €/m², comps
median and n, rent estimate and its basis, gross/net yield, days on market and basis, status,
photo count, station, area insight numbers, regulatory flags) and answers in Greek, ≤120
words, with numbers taken ONLY from that JSON; if the data does not say, it says «δεν το
ξέρω από τα δεδομένα». Suggested questions as chips: «Γιατί αυτό και όχι το φθηνότερο;», «Τι
να προσέξω στη διαπραγμάτευση;», «Τι ρίσκο έχει αυτή η περιοχή;», «Πόσο θα νοικιάσει;».
Also one automatic 4–5 line «Σημείωμα επενδυτή» per shortlist: the trade-off between the top
3 in numbers (yield vs. new-build premium vs. liquidity), the one thing to verify on each, and
the opening offer. Model id for the API: `claude-sonnet-5-5` (env `ANTHROPIC_MODEL` to
override). Temperature low. Cache per (question, facts hash). Never pass the key to the UI.

### 4. Accounts & memory
`st.login()` with Streamlit's OIDC when `[auth]` secrets exist (Google); otherwise a simple
profile: «Όνομα» + 4-digit PIN, PIN stored as a salted hash in the gist document under
`profiles[name]`. A profile holds: wizard answers, favourites, approve/drop verdicts, saved
searches, last page. The sidebar shows «Συνδεδεμένος ως …» and «Αποσύνδεση». Without a
profile the app still works (session only) and says so in one neutral line.

### 5. Investor insights — what a buyer actually checks, per area and per flat
Per area (feeds the Οδηγός recommendation and «Πού να αγοράσω»): median €/m² TREND from our
own history (median by month of `first_seen` over the last 6–12 months, with n), liquidity
(median days on market; share of listings gone within 30/60 days using `status`/`last_seen`),
supply (sale listings per rent listing), new-build premium, share under construction,
stations today AND **Metro Line 4 stations under construction** (static table with area,
station name, planned opening; e.g. Γαλάτσι, Κυψέλη, Εξάρχεια, Ζωγράφου, Γουδή, Ιλίσια,
Ευαγγελισμός — verify the list from a reliable public source and cite it in the module
docstring), short-term-rental restrictions (`regulatory.py`). Per flat: the same six checks as
a labelled list: τιμή vs παρόμοια · απόδοση · ρευστότητα περιοχής · ζήτηση ενοικίου ·
νομικά/κανονιστικά · έξοδος (μεταπώληση: τάση €/τ.μ.).

### 6. More sources — availability like noikaki.gr
Survey, from a GitHub runner (the sandbox is blocked), which Greek portals serve
server-rendered listing pages to plain `requests`: spiti24.gr, plot.gr, tospitimou.gr,
remax.gr, era.gr, xrysi-eukairia.gr, golden-home, greek portals' RSS/JSON endpoints; note
which need JS/WAF (Spitogatos, Indomio → FlareSolverr path exists). Implement the top 1–2 with
`.claude/skills/add-portal`, fixtures, polite pacing, and a `source` label on every card.
Cross-portal duplicates are grouped with the existing twins logic (same area, m², floor,
year, price ±10 %) and shown as «και σε N ακόμα πηγές». Honest coverage line on the Οδηγός
result: «Πηγές: XE.gr, … · N αγγελίες ενεργές».

## Ownership (round 3) — disjoint files, as before
| Worker | Owns |
|---|---|
| W8 guide | `src/scout/ui/guide.py` (new), `src/scout/picks.py`, `src/scout/ui/find.py` (retire into guide), `tests/test_picks.py`, `tests/test_guide.py` |
| W9 map-list | `src/scout/ui/components.py`, `src/scout/ui/maplist.py` (new: map + list + selection), `tests/test_map_page.py`; exposes `maplist.render(listings_ranked, key)` for W8/W10 to call |
| W10 accounts+shell | `src/scout/ui/app.py`, `src/scout/ui/account.py` (new), `src/scout/shortlist.py`, `src/scout/ui/buyer.py` (favourites/verdict storage calls only), `tests/test_shell.py`, `tests/test_shortlist.py` |
| W11 assistant | `src/scout/advisor.py`, `src/scout/ui/assistant.py` (new), `tests/test_advisor.py`; exposes `assistant.panel(facts: dict, key)` and `assistant.brief(facts) -> str` |
| W12 insights | `src/scout/area_insights.py`, `src/scout/ui/areas.py`, `src/scout/regulatory.py`, `src/scout/metro_line4.py` (new), `tests/test_area_insights.py`, `tests/test_where_to_buy.py` |
| W13 sources | `src/scout/collectors/*` except `xe.py` internals (new collector files), `src/scout/pipeline.py`, `.github/workflows/*`, `scripts/*`, `tests/fixtures/*`, `tests/test_<portal>.py` |

Integration contract: W8's guide page calls `maplist.render(...)` (W9) and
`assistant.panel(...)`/`assistant.brief(...)` (W11) when those modules exist — import inside a
`try`, degrade gracefully when absent, so PRs can merge in any order. W10 wires NAV: the first
entry is `guide.TITLE`; `account.current_user()` returns the profile name or None and
`account.storage()` the per-user store the others read/write favourites and answers through.
Until W10 lands, others use `shortlist.*` as today.

---

# Round 4 — "buy or rent, professional finish" (2026-10-31, 18:00)

Round 3 shipped the guided flow, the connected map, the grounded assistant, accounts and
four portals. The owner then used it and asked for: **renting as an option**, the review's
suggestions (short cards by default, real station distance, weekly rents with their date, a
photo check, a phone-friendly compare) and a **professional finish**. Everything above still
holds: phone-first at 390 px, Greek only, one glossary, no decoration, every number with its
basis within one tap, «άγνωστο» instead of a guess, draft PR + gate green (`pytest` with
`GAUNTLET` unset, `ruff`, `black`) + screenshots, message the coordinator, touch only your files.

Schema additions in this round are authorised by the owner's request (renting + photo check):
`listing.listing_type`, `listing.photo_kind`, `listing.photo_checked_at`, `listing.furnished`,
`listing.available_from`. Add them with `db._ensure_columns` (idempotent forward migration,
see `.claude/skills/db-schema-change`), never by hand.

## Contracts (binding; whoever owns the file implements, everyone else codes against them)

### C1 — rental listings are first-class rows (W16, `models.py`, `db.py`, `pipeline.py`, `collectors/xe.py`, `rent_comps.py`, `ui/queries.py`, `scoring.py`)
- `Listing.listing_type: Literal["sale","rent"] = "sale"`; column `listing_type TEXT NOT NULL DEFAULT 'sale'`, indexed with `status`.
- The XE collector yields FULL rental cards (same fields as sale cards: price = monthly rent,
  area_m2, floor, year_built, bedrooms, neighborhood, url, source_id, image_url, listed_date,
  is_private_seller, plus `furnished: bool|None`, `available_from: date|None` when the card
  says so). Golden Home / RE/MAX rentals are optional this round.
- The pipeline stores rentals in the same `listing` table with `listing_type="rent"`, same
  dedup/history/retire rules, **per area** like sales. Rentals are never scored, never in sale
  market stats, never in comps of sale flats; `scoring.score` returns `excluded` with reason
  `rent` for them, or the pipeline skips scoring for them (choose one, document it).
- Rent comps (`rent_comp`) are recomputed every run from the stored rentals of the last 60
  days (not from a one-off scrape), with `samples` and `updated_at` filled, so the UI can print
  «ενοίκια έως ΗΗ/ΜΜ, N αγγελίες» next to every yield.
- `queries.load_listings(..., kind="sale")` keeps today's behaviour (sale only). New
  `queries.load_rent_listings()` returns rental dicts with the same keys as sale dicts plus
  `rent_per_m2`, `furnished`, `available_from`, `days_on_market`/`dom_basis`/`relisted_on`,
  `is_fresh`, `page_checked` (False until a rental page is ever read).
- `daily.yml`: no new step; the collect step scrapes rentals for the same 15 areas. Budget:
  about one extra minute per area.

### C2 — the rent guide (W17, new `ui/rent_guide.py`, new `picks_rent.py`, ≤ 30 changed lines in `ui/guide.py`)
- Guide step 0 (before today's step 1): «Τι ψάχνεις;» → «Να αγοράσω» · «Να νοικιάσω», big
  buttons, remembered in `st.session_state["guide"]["mode"]` and in the profile store under
  `guide.mode`. The pill stays «Οδηγός»; the progress line counts the mode's own steps.
- Rent steps: 1 «Πόσο τον μήνα;» chips 400 / 600 / 800 / 1.000 / 1.300 / 1.600 € + «Άλλο
  ποσό»; 2 «Πόσα υπνοδωμάτια;» chips 1 / 2 / 3+ / αδιάφορο; 3 «Πού;» (same three choices as
  buying); 4 «Τι σπίτι;» → «Επιπλωμένο» toggle, «Νεόδμητο / έως 20 ετών / Οτιδήποτε»; 5 «Η
  πρότασή μου».
- `picks_rent.find(rentals, budget_month, bedrooms, near_rail, areas, max_age, furnished,
  top)` → `RentPick(listing, rent_per_m2, vs_area_pct, dom, checks, reasons, risks)` sorted by
  value (rent €/τ.μ. against the area's rental median, same neighbourhood first), then
  freshness. Band: rent ≤ budget × 1.10, say so. `relaxations(...)` with exact counts like
  the buy flow.
- Rent result card (phone): rent · τ.μ. · €/τ.μ.; floor · year · area · station text; «Παρόμοια
  ενοίκια (N): X % κάτω/πάνω»; days on market with basis; «Επιπλωμένο»/«Διαθέσιμο από»;
  buttons «Άνοιγμα στο XE.gr», «Λεπτομέρειες», «Αγαπημένο». Four checks per rental: Τιμή
  έναντι παρόμοιων · Φρεσκάδα (days, re-posted) · Ιδιώτης ή μεσιτικό · Ενεργειακή κλάση.
- Assistant: `assistant.facts_for` must accept rental dicts (W17 adds a `mode: "rent"` key
  to `answers`; W11's module is frozen, so W17 may add a thin `rent_facts()` in
  `rent_guide.py` that calls `assistant.brief/panel` with `facts["listings"]` built from
  `RentPick`s). Rules text for renters: no yield talk; what to ask the landlord (deposit,
  charges, contract length, energy certificate).

### C3 — short cards, compare, finish (W18, `ui/buyer.py` card helpers, `ui/guide.py` `_card` only, `ui/app.py` compare + header, `ui/theme.py`, `ui/components.py`)
- `buyer.card_html(d, adv, compact=True)`: five lines max — price · τ.μ. · €/τ.μ.; floor ·
  year · area · station; status badge; rent + gross yield (or rent + €/τ.μ. for rentals);
  one comparison line. Everything else behind the existing «Από πού βγαίνουν» expander.
  The guide result and the search use the compact card by default; the listing page uses
  the full one. Buttons on a card: two («Λεπτομέρειες», «Αγαπημένο»); the guide adds
  «Εγκρίνω» / «Δεν μου κάνει» as the second row only on the first ten.
- Compare page: pick two flats (favourites first), then a two-column table with at most
  eight rows (price, €/τ.μ., τ.μ., floor, year, rent, gross yield, station), each cell one
  value, then the two cards compact. Works at 390 px without horizontal scroll.
- Finish: one header line «Σκάουτ ακινήτων» with the data line under it, consistent spacing
  and font sizes across pages (theme.py), no English anywhere a user reads, consistent
  singular/plural, no empty states without a sentence and a next step. Keep the pills.

### C4 — real station distance (W19, `enrich.py`, `picks.py` `station*` helpers, `tests`)
- Today every listing has `metro_distance_m`, but 75 % are computed from the AREA CENTROID
  (`location_precision="approx"`), so «684 μ.» is fiction for them. Rule: distance is shown
  only when `location_precision == "exact"`; otherwise the station comes from the
  neighbourhood name as today, labelled «(από το όνομα της γειτονιάς)».
- `picks.station_text(d)` → «Μετρό Άγιος Δημήτριος · 450 μ.» (exact) or «ΗΣΑΠ Περισσός
  (γειτονιά)» (name) or "". `picks.near_rail(d)` → True when exact distance ≤ 800 m, else
  when the neighbourhood name carries a station, as today. Station names in Greek
  (`nearest_metro` today holds Latin names like `Holargos`: map them).
- Station table: all Line 1/2/3 stations + the suburban railway stops inside the covered
  municipalities, with coordinates, in one data file with its source and date.

### C5 — photo check (W20, new `scripts/check_photos.py`, `collectors/xe.py` image URLs, `models.py` columns `photo_kind`, `photo_checked_at`, `ui` text via `picks.status_line`)
- For new-build sale listings in the 15 weekly areas whose page was read, fetch up to three
  listing images (the JSON-LD list) and classify them with the Claude API (vision, cheapest
  model) into `photo` / `render` / `plan` / `site` / `stock`; store the majority as
  `photo_kind` with `photo_checked_at`. Deterministic pre-filters first: fewer than three
  images → no call; identical images across listings of the same agent → `stock`.
- The weekly workflow gets one step after the page check, `continue-on-error`, capped at
  15 min, that runs ONLY when `secrets.ANTHROPIC_API_KEY` is present; the owner must add
  that secret to the repository for it to run (say so in the PR).
- UI: `picks.status_line` and the card status badge gain «Φωτογραφίες: πραγματικές» /
  «σχέδια ή ψηφιακή απεικόνιση» / «εργοτάξιο» / «δεν ελέγχθηκαν»; `picks.find` sorts render /
  plan / site below real photos (after the page-checked rule, before the score).

## Ownership and order

| WS | Owner files | Depends on | Merge order |
|---|---|---|---|
| W16 rent data | models, db, pipeline, collectors/xe (rent part), rent_comps, ui/queries, scoring, tests, daily.yml (comment only) | — | 1 |
| W19 station distance | enrich, picks station helpers, data file, tests | — | 2 |
| W20 photo check | scripts/check_photos.py, models (two columns), collectors/xe (image list), picks status/sort, daily.yml (one step), tests | — | 3 |
| W18 cards/compare/finish | buyer card helpers, guide `_card`, app compare+header, theme, components, tests | — | 4 |
| W17 rent guide | ui/rent_guide.py, picks_rent.py, guide.py (≤ 30 lines), tests | C1 contract (code against fixtures until merged) | 5 |

Shared rules: fixtures for new parsers are real captured HTML; no network in tests; keep
`tests/test_copy.py` green (extend its allowlist only for portal names); screenshots at
390×844 of every new screen into `docs/qa/<ws>/`; the message to the coordinator carries the
head SHA, the gate numbers and anything outside your files.

## Round 5 — the design finish (impeccable + Apple HIG)

The owner's words: «fix the app to look pretty without flaws». Round 4 made the product
complete (buy or rent, short cards, real distances, weekly rents, photo check). Round 5 makes
it look and feel finished, measured, not asserted. Two vendored skills carry the method:
`.claude/skills/impeccable/` (critique → audit → craft floor → polish) and
`.claude/skills/apple-hig-designer/` (the type roles, 8-pt spacing, 44-pt targets, grouped
lists, semantic colour, concentric radii). The surface mode is **Operate**.

### C6 — design finish (W21, `ui/theme.py`, `.streamlit/config.toml`, class hooks only elsewhere)

**Scope.** Visual and interaction finish of every user-facing screen at 390×844 (primary) and
1280×900 (secondary): Οδηγός (buy and rent flows, every step, the result, a card's expander,
the brief and «Ρώτα με» when a key is set), Περιοχές, Αναζήτηση, Χάρτης, Αγαπημένα,
Σύγκριση, the listing page, saved searches, the sidebar. No logic, data or ranking changes.
UX copy may change only where the critique names a wording defect (labels, empty states,
errors), one glossary (`docs/COORDINATION.md` «Glossary»), Greek only.

**Method (in this order, each with a written artefact).**
1. `docs/qa/design/AUDIT.md`: the impeccable critique (assessment A from screenshots and
   source, assessment B from `docs/qa/design/measure.js`, kept apart until synthesis), the
   ten heuristic scores, the five audit dimensions, P0–P3 issues with file and selector.
   «Before» screenshots of flows a–h plus rent r1–r5 in `docs/qa/design/before/`.
2. The polish, per `craft-floor.md` and `polish.md`, with the Apple lens:
   - **Type roles** (rem, system stack): large title 1.75, title 1.3, headline 1.0625/600,
     body 1.0, subhead .9375, footnote .8125, caption .75; line-height 1.3 headings, 1.5
     body; tracking −0.01 to −0.02 em on titles only; `tabular-nums` on every number.
   - **Spacing**: one 4-pt scale (4 8 12 16 20 24 32 40); tight inside a group, generous
     between groups; more space above a heading than below it.
   - **Touch**: every button, pill, chip, select, toggle, expander summary and link ≥ 44 px
     tall at 390 px; 8 px minimum between adjacent targets.
   - **Shape and depth**: cards 12–16 px radius, elevation declared once (hairline border on
     the canvas OR a soft offset shadow, not both heavy); controls one radius family;
     concentric nesting (inner radius + padding = outer).
   - **Colour**: tokens only (`--hg-*`); semantic status colours for the three badges
     (ok / warning / bad) with ≥ 4.5:1 text contrast on their tints; one accent; links and
     focus from the accent; `:focus-visible` ring on every control; selection and caret
     colours themed.
   - **States**: hover, pressed (`scale(.98)` or tint), disabled, loading, empty and error
     on every control and list; empty states name the next step.
   - **Grouped lists** for fact rows (compare table, the six checks, the listing page facts):
     inset separators, label left muted, value right ink, no zebra.
   - Browser surfaces: scrollbars, selection, underline offset, number alignment.
3. `docs/qa/design/POLISH.md`: the same measurements after, side by side with before, every
   remaining P1 named with a reason; «after» screenshots in `docs/qa/design/after/`.

**Definition of done (the coordinator re-runs `measure.js` on the merged head).**
- `scrollWidth` = 390 on every shot; no element wider than the viewport.
- 0 interactive elements under 44 px tall at 390 px (list any exception with its reason).
- 0 text nodes under 4.5:1 contrast (3:1 for ≥ 24 px); 0 under 11 px.
- Font sizes in use ≤ 8 distinct values; margins and paddings in `theme.py` on the 4-pt scale.
- Card radius and elevation consistent across guide, search, favourites, compare, listing.
- Heuristic total up by ≥ 6 points over AUDIT.md; audit score ≥ 16/20; no P0/P1 left open.
- Gate green: `pytest -q` (GAUNTLET unset), ruff, black, `tests/test_copy.py`; new
  `tests/test_theme.py` asserts the token set, the type roles and the 44-px rule in the CSS.
- Before/after screenshots committed; the PR message carries the two score tables.

**Not in scope.** Dark mode (Streamlit's theme is light; note it as a follow-up), web fonts,
new pages, any change to what a card says.

### C7 — never a thin list, and the score on every card (W22, `picks.py`, `picks_rent.py`, guide/rent-guide result sections, `buyer` card chip)

Owner's words: «The amount of suggestions are extremely low, you should give more when user
presses more. Where is the score?»

**Never thin.** `picks.find` (and `picks_rent.find`) return the strict matches first and then
**near matches**: the same ranking applied after loosening ONE answer at a time, in this fixed
order, until at least `3 × PAGE` candidates exist or the pool is exhausted: price band 12 % →
20 % → 30 % over the budget; building age one step up (10 → 20 → any); station rule off;
chosen areas → all areas; bedrooms off. Each near match carries `relaxed: str` naming the one
loosened answer in the user's words («ποσό +18 %», «κτίριο 1998», «χωρίς όρο σταθμού»,
«Μαρούσι», «3 υπν.») and sorts after every strict match; within the near matches the
smallest loosening first. Nothing is relaxed twice on one candidate.
- The result sentence says both counts: «**4** αγγελίες ακριβώς όπως ζήτησες και **31** κοντινές
  (ένας όρος χαλαρωμένος, γραμμένος σε κάθε κάρτα).» With no strict match: «Καμία ακριβώς όπως
  ζήτησες· **31** κοντινές.»
- «Δείξε άλλες 10» keeps paging through strict then near, always ten more while any exist.
  The relaxation buttons stay as a shortcut to make a loosening permanent.
- On a near-match card, line 3 gets one chip in the neutral tone: «Έξω από: ποσό +18 %».
- The assistant facts carry `relaxed` per listing; the brief must not call a near match exact.

**The score.** One number per listing, the same definition everywhere, the buyer score 0–100
from `nl_search.advise` (already the map colour and the search advice): on every card (compact
and full) as the chip «Βαθμολογία 78» right of the price in line 1, on the compare table as the
first row, on the listing page with «Πώς βγαίνει η βαθμολογία» (the components and their
weights, in words, from `nl_search`). Rentals show the rent-value score («Βαθμολογία» from
`vs_area_pct` and freshness, 0–100, basis in the expander). The guide keeps its goal ordering;
if the top-ten order and the scores disagree by more than two places on the published DB,
say so in the PR with examples (the coordinator decides whether the guide ranks by the score).

**Definition of done.** On the published DB with the answers 160 χιλ. · απόδοση · κοντά σε
μετρό · νεόδμητο (the owner's own), the result shows at least 30 candidates in total, each near
match labelled; every card on every page shows the score; `tests/test_guide.py` covers the
near-match order, the labels and the counts; `tests/test_copy.py` stays green; screenshots of
the result at 390 px before and after in `docs/qa/more/`. No visual redesign (W21 owns the
look): add classes and chips only through `buyer.card_html`'s existing slots.

### C8 — trust-ordered lists everywhere (W23, `ui/buyer.py` sort helpers, `ui/maplist.py`, `nl_search` default order)

The design reviewer's finding (b): «Αναζήτηση» and the map list open on unchecked flats 33–35 %
under their comparables, the classic bait listing, while the guide already applies a trust
ladder. Rule: every list in the app opens in the same order as the guide: page read first,
real photos next, then the chosen sort; a flat more than 30 % under its comparables sorts after
the rest of its tier and its card says «έλεγξε γιατί» (already in `comps_text`). The user's
explicit sort («Σειρά») keeps working inside the tiers. Definition of done: first screen of
Αναζήτηση with the default example and of the map list show page-read flats first on the
published DB; a test on a seeded DB asserts the tier order and that the bait flat is not first;
copy guard green; one 390 px before/after shot of Αναζήτηση in `docs/qa/trust/`. No change to
the guide, the cards or the theme (W22 owns the card slots).

### C9 — one navigation on desktop, saved searches reachable (W24, `ui/app.py` `main()` + sidebar, `theme.py` sidebar block only)

The design reviewer's finding (a): desktop shows two navigations with different names (the
sidebar radio and the top pills) and «Αποθηκευμένες αναζητήσεις» is sidebar-only. Rule: one
navigation. The pills are the navigation on every width; the sidebar keeps only sign-in,
«Ανανέωση δεδομένων» and the saved searches entry as a link-style button; the radio is removed
(keep `session_state["page"]` as the single source of truth so cards and buttons still
navigate). «Αποθηκευμένες αναζητήσεις» becomes reachable from «Αναζήτηση» (a secondary button
under the search box, «Αποθηκευμένες») and from the sidebar. Definition of done: at 1280 px
exactly one set of page names on screen; every page still reachable by keyboard; AppTest
shell tests updated; copy guard and theme tests green; 1280 px before/after shots in
`docs/qa/shell/`. No visual redesign beyond removing the duplicate control.

### C10 — the voice pass: every sentence as a Greek professional says it to a 65-year-old (W25, strings only)

Owner's words tonight: «the AI sloppiness is very obvious». The design is fixed (C6); what
still reads as machine-made is the prose: statistics-speak («διάμεση», «δείγμα», «εκτίμηση από
ζητούμενα»), stacked clauses, hedges, labels that explain the code rather than the flat.
Rule: every user-facing sentence is rewritten as an experienced Athens estate agent would say
it across a table to a 65-year-old buyer: one idea per sentence, the number first, the reason
second, no jargon (say «τα άλλα σπίτια της γειτονιάς» not «τα παρόμοια», «πόσο νοικιάζονται τα
διπλανά» not «διάμεσο ενοίκιο περιοχής», «δεν το ξέρουμε» not «άγνωστο δείγμα»), no English, no
decoration, no apologies, no «το σύστημα». Keep every number and its basis; keep the glossary's
nouns for the five card lines (Τιμή, €/τ.μ., Ενοίκιο (εκτίμηση), Μικτή απόδοση, Παρόμοια,
Βαθμολογία) because the tests and the owner know them. Scope: string literals and f-strings in
`picks.py` (lines, risks, offer_line, status_line), `area_insights.py` (why, reasons, risks,
decision, trend, checks), `ui/areas.py`, `ui/buyer.py` (status / basis / comps sentences, empty
states, SORT_HELP), `nl_search.py` advice text, `ui/assistant.py` RULES and BRIEF_TASK (so the
brief speaks the same way), `ui/rent_guide.py` METHOD and checks, `ui/guide.py` METHOD and
recommend (after C7 lands). No logic, no layout, no new widgets. Definition of done: a table in
`docs/qa/voice/VOICE.md` with every changed sentence before → after and the screen it is on; a
blind read by an isolated sub-agent of ten random after-sentences scoring «sounds like a
person» ≥ 8/10; `tests/test_copy.py` green with its allowlist unchanged except removed words;
glossary section of this file updated where a term changed; 390 px shots of the guide result,
a listing page and an area card in `docs/qa/voice/`.
