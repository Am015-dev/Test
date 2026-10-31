# OPS_LOG — Holargos Property Scout

Agent-maintained log. One entry per autonomous ops cycle or notable event.
**Newest entries at the top.**

**Read recent health state (postgres MCP):**
```sql
SELECT checked_at, status, issues, metrics
FROM health_report
ORDER BY checked_at DESC
LIMIT 5;
```

---

## 2026-10-31 (evening) — Round 4 "buy or rent, professional finish" merged; round 5 design finish started
- Merged to `main` (squash, CI green on each head): #85 photo check (`scripts/check_photos.py`,
  vision classification photo/render/plan/site/stock into `photo_kind`/`photo_checked_at`, a
  15-min weekly step that runs only with the repository secret `ANTHROPIC_API_KEY`; actions pinned
  by commit), #86 stations (75-station Greek table from Wikidata, real walking distance only for
  exact points, «(από το όνομα της γειτονιάς)» otherwise; `near_rail` among active rows 1,009 →
  2,540; `scripts/recompute_metro.py` runs weekly before the rescore), #87 rentals as listing rows
  (`listing_type`, `furnished`, `available_from`; separate retirement passes; `scoring.score`
  excludes rentals; weekly rent comps from stored rentals with `samples`/`updated_at`;
  `queries.load_rent_listings`; collect cap 140 → 160 min, job 220 → 250), #88 compact five-line
  cards everywhere, eight-row compare with the two cards under it, one header line and one type
  scale (guide result 7,184 → 4,554 px tall at 390), #89 rent guide («Τι ψάχνεις;» step 0, five
  rent steps, value-vs-comparables ranking, renter rules for the assistant, starred rentals on
  «Αγαπημένα», honest empty state until the first weekly run with rentals).
- Schema additions this round (owner-requested in chat, no Telegram escalation): `listing_type`,
  `furnished`, `available_from`, `photo_kind`, `photo_checked_at`; index `ix_listing_type_status`.
  Forward migration is idempotent; verified twice on a copy of the published DB.
- Pending owner decision: add the repository Actions secret `ANTHROPIC_API_KEY` (a separate key
  with a spend cap) or the photo step stays skipped. Streamlit secrets do not reach Actions.
- Known leftovers: admin-only pages (`?admin=1`) still print raw metre distances and a hard-coded
  «(Γραμμή 3)»; `scripts/daily.py` step 2 (Oracle cron, unused by the Streamlit deployment) still
  writes one-off scraped comps; `test_ui_gauntlet::test_no_developer_text_without_keys` failed
  once in a full run for W16 and passed on rerun (order or timing dependent, not reproduced).
- Round 5 opened on the owner's words «fix the app to look pretty without flaws»: vendored
  `.claude/skills/impeccable/` (pbakaus/impeccable 4.8.0 text references, Apache 2.0; no binary)
  and `.claude/skills/apple-hig-designer/` (MIT); contract C6 in `docs/COORDINATION.md` with a
  measured definition of done. W21 phase-1 baseline on e3f490d: heuristics 22/40, audit 10/20,
  448 of 481 controls under 44 px at 390, 242 contrast failures (231 decorative separators),
  15 font sizes, 172 of 495 controls without a focus ring, scrollWidth 390 everywhere
  (`docs/qa/design/AUDIT.md`, `measure.js`). Phase 2 (polish) started 19:21 UTC on b296a14.
- Weekly four-source refresh run 41224248305 (dispatched 17:22) still in progress at 19:20.

---

## 2026-10-31 — Round 3 "one guided flow, everything connected" merged
- Merged to `main` (squash, CI green on each head): #73 map+list as one selection
  (`ui/maplist.py`), #74 «Οδηγός» five-screen guide as the home page with goal weights, loan
  instalment and 10-at-a-time results (`ui/guide.py`, `picks.py`), #75 investor insights
  (trend series, liquidity, supply per rent listing, Metro Line 4, regulatory flags, six
  per-flat checks), #76 portal survey + Golden Home collector + `SOURCES` toggle + store every
  portal's copy, #77 days on market from the earliest evidence with «η αγγελία ανανεώθηκε»,
  #78 grounded assistant brief and «Ρώτα με» panel (`ui/assistant.py`), #72 accounts
  (Google or name+PIN, per-profile favourites/verdicts/searches, sources in the status line),
  #79 copy pass with `tests/test_copy.py` guard.
- Production toggles: `daily.yml` collect step now runs `SOURCES=xe,greenacres,goldenhome`
  (Golden Home smoke on the runner: Χολαργός 36 stored, 38 cross-portal twins). The assistant
  and free-text search need `ANTHROPIC_API_KEY` in the Streamlit secrets; the brief is hidden
  without it. Google sign-in needs the `[auth]` block from `docs/ACCOUNTS.md`; PIN profiles
  work with the existing gist token.
- Gate note: `GAUNTLET=0` is truthy and runs the 23-minute every-widget sweep; gate with the
  variable unset. One main-CI red (test_guide faked `scout.metro_line4` in `sys.modules`,
  ineffective once the real module exists) fixed in f223c9f.
- Data facts worth remembering: only 397 of 11,504 fresh listings carry an XE posting date and
  65 of those were re-posted after our first sighting; liquidity and supply-per-rent are
  «άγνωστο» everywhere until weekly scrapes accumulate (first regular scrape 30/10) and
  `rent_comp.samples` is recorded.
- Later the same evening: #80 RE/MAX collector merged and enabled (`SOURCES=xe,greenacres,goldenhome,remax`,
  collect cap 110→140 min, job 175→200); #81 final QA report (`docs/qa/final/REPORT.md`); #82 six
  investor checks on the listing page + budget-band sentence + word buttons; #83 areas page without
  «n=» and with one unknown row; #84 guide now feeds `assistant.facts_for` so the brief and «Ρώτα με»
  render (they never did before). Four-source weekly refresh dispatched 17:22 UTC.
- Owner-facing review (phone walk-through, `docs/qa/review/`): rents are asking rents and partly from
  July; station proximity is by neighbourhood name (9 of 1,424 candidates have a measured distance);
  photo counts exist for 130 of 1,019 new builds under 300k; result cards too long for elders.
  Next: short cards by default, real station distance, weekly rents, photo check, tenant mode. Carry-overs for the next pass: guide result sentence should
  state the +12 % budget band when the top pick is above the budget; «Σύγκριση» info text
  still says «Βρες μου σπίτι»; ~1 % of listings carry Latin XE place names (collector/enrich
  fix); a UI test writes `strategy.yaml` when run outside the `env` fixture.
- Escalated: no (schema additions `description`/`photo_count` were reported to the owner in
  chat earlier today; no objection).

---

## 2026-06-26 — Autonomy infrastructure bootstrapped
- Phase A: CI workflow added (`.github/workflows/ci.yml`), `health_report` table
  created (durable health state for cross-session reads), `scripts/uptime.py` added.
- Phase C: Skills `autonomous-ops`, `self-deploy-safely`, `weekly-review` created.
- Phase E: This OPS_LOG initialized; guardrail allow-list added to CLAUDE.md.
- CI: pending first run (no push to main yet)
- Escalated: no
