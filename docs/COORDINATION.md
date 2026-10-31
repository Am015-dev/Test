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
