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
   plus `GAUNTLET=0 python -m pytest -q tests/test_ui_gauntlet.py` (renders every page).
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
