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
- Open: W13 RE/MAX probe (`ws/sources-remax`); final phone QA (W14, `ws/final-qa`,
  `docs/qa/final/REPORT.md`). Carry-overs for the next pass: guide result sentence should
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
