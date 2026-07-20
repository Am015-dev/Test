# Readiness Log — honest, un-inflated

Running ledger of the sell-readiness loop. Scores come from the `honest-buyer-score`
skill (hard-gated). No number here is rounded up.

## Baseline — 2026-07-20 · Buyer score 30/100
An honest, well-built screener that re-scores ONE free portal's *asking* listings with a
valuation whose ±44% band is wider than the discounts it claims, and which flagged 82% of
inventory as an "opportunity." Genuinely engineered, commercially thin. Realistic price
today: €0–5/mo (bordering free-only); €3–8k as an acqui-hire codebase — **not** €19/mo SaaS
or €100k, and nowhere near €1M.

**The 5 buyer objections (ranked):**
1. "Fair value" is trained on ASKING prices, not sold (no open Greek sold register) — ±44% band, circular, fires for only 16% of listings.
2. Core "undervalued deals" claim sits inside its own noise.
3. Single-source (99.7% XE, 0 Spitogatos/Indomio) despite multi-source framing.
4. Net yield rests on imputed rent (0.3% real rents; 234 comps for 22k listings).
5. "Opportunity" = 82% of inventory; top picks are data errors; data was stale.

## The pivot (validated by sourced market research — see PRODUCT_STRATEGY.md)
Stop leading with the asking-based AVM and the "everything is an opportunity" label. Lead
with what's real and defensible: (a) the regulatory join no portal offers — STR-legality,
Golden-Visa, energy-subsidy; (b) the longitudinal DOM/discount history that compounds daily.

## Shipped this loop
- **Staleness root cause fixed** (green-acres re-scraped all 55 areas per call → blew the
  collect timeout before storing → `last_seen` never advanced). Now scoped like XE. Data
  refreshes on the next daily run. [G5]
- **Regulatory differentiator built + surfaced** (`src/scout/regulatory.py` + UI): per
  listing, can a buyer legally short-let it (frozen Athens districts: a new AMA is
  impossible and dies on sale), Golden-Visa eligibility, energy-subsidy candidacy. Header
  now leads with these (Short-let frozen 1,989 · Energy-subsidy 9,699). No portal shows
  this; needs no history. [Differentiation, Job]
- **Killed the inflation**: header no longer calls 17,384 listings "opportunities" [G1];
  fair-value relabelled "vs asking (est.), ±44%, not a sold-price valuation" [G2]; source
  shows "XE" with real share, not phantom multi-source [G4].
- **honest-buyer-score skill** — hard-gated, un-gameable scorecard driving this loop.

## In progress
- Data-quality guards: stop whole-building-as-flat / future-year / implausible-yield
  listings from topping the ranking (the #1 credibility killer).

## Buildable next (no owner/data needed)
- Tighten the BUY bar — 2,096 "BUY" is still too loose for a credible shortlist. [G1]
- Fix imputed-rent honesty end to end — "real_rent 100%" is false (0.3% real); label
  every yield as estimated-from-area-comp. [G3]
- Begin accumulating the moat: the daily run now stores history; DOM/discount signal grows
  from here (empty today — 8 of 22k listings have >1 price point).

## BLOCKED ON OWNER / DATA / MONEY (not attempted — honest ceiling of code alone)
- **Sold-price AVM**: Greece has no open sold-price register. A trustworthy "fair value"
  needs paid comps, notary feeds, or the government Price Map when it opens — owner cost/decision.
- **Multi-portal (Spitogatos/Indomio)**: needs a hosted FlareSolverr (stable IP) — owner
  hosting decision. Until then the product is honestly single-source.
- **Real rents at scale**: more scraping helps, but investable-grade yields need a real
  rent dataset the current sources don't expose.
- **The €1M outcome**: that is recurring revenue (~€200–300k ARR) or a proven data moat with
  paying customers — go-to-market and time, not code. Code can reach "a real investor would
  pay €29–99/mo"; the rest is the owner's to close.
