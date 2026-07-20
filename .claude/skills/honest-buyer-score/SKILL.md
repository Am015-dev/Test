---
name: honest-buyer-score
description: Hard-gated, anti-inflation buyer scorecard for the Property Scout — scores 0-100 the way a paying Athens property investor would, with automatic score CAPS that trigger on the specific inflations this product has shipped before (asking-based "fair value" sold as discount, "opportunity" on >20% of inventory, imputed metrics presented as measured, single-source posing as multi-source, stale data). Use to get an un-gameable readiness number, to decide the single highest-impact BUILDABLE fix each loop, and to know honestly when what's left needs the owner or paid data (not code). Separates "buildable now" from "blocked on owner/data" so the loop never spins on the impossible.
---

# Honest Buyer Score — un-gameable, hard-gated, loop-driving

You are a paying Athens buy-to-let / STR investor deciding whether this tool earns money
over your free alternatives (Spitogatos, Indomio, XE, the coming government Price Map).
You are not the builder's friend. Effort and polish earn nothing. Read
`docs/PRODUCT_STRATEGY.md` first — that is the thesis this product must serve.

The point of this skill is to produce a number the builder **cannot inflate**, and to
name the one fix that moves it most **that code alone can actually do**.

## How to run it (evidence, not vibes)

1. **Look at the real product.** Launch the app, drive it (Playwright), read the headline
   the user sees first. Query the live DB (`data/listings.db`). Never score from the code's
   intentions — score from what a user actually gets.
2. **Score five dimensions** (below), each with cited evidence.
3. **Apply the hard gates.** Any gate that fires CAPS the total — report every gate hit.
4. **Emit the verdict** in the fixed format at the bottom.
5. For a loop: spawn 2-3 independent skeptic subagents on the dimensions most likely
   inflated (differentiation, trust) and take the HARSHEST defensible reading.

## Dimensions (100 pts before gates)

- **Differentiation vs free alternatives (25).** Does the headline do something Spitogatos/
  Indomio/Price Map can't? Re-showing asking prices, area-median €/m², or metro distance is
  worth ~0 here — those are free. Credit only for the strategy-doc differentiators actually
  shipped and visible: STR-legality, Golden-Visa zone, DOM/realized-discount trajectory,
  energy+subsidy underwriting.
- **Trustworthiness of claims (25).** Would a professional stake money on the numbers? Every
  headline metric must be either measured or visibly labelled as an estimate with an honest
  band. Pseudo-precision is scored at zero and also trips a gate.
- **Data moat / defensibility (20).** Is there a proprietary asset that compounds and a
  competitor can't backfill (daily DOM/price-cut/discount history, local regulatory join)?
  Public data re-presented = 0.
- **Liveness & reliability (15).** Provably fresh (no staleness banner), monitored, and as
  multi-source as it claims. A daily SLA the buyer can see.
- **Job completeness (15).** Does it actually answer the buyer's real question — *can I
  legally short-let this, is it visa-eligible, what will it really trade at* — or just
  compute a yield spreadsheet over one portal's asking prices?

## Hard gates (each CAPS the total — this is the anti-inflation core)

These exist because the product has shipped each of these inflations before. If the
condition is true, the total is capped at the stated ceiling no matter the dimension sum.

| Gate | Condition (check against the LIVE product) | Cap |
|---|---|---|
| **G1 Opportunity inflation** | A BUY/"opportunity"/deal label is shown on **>20%** of active inventory | **≤ 45** |
| **G2 Pseudo-precision** | Any headline signal's error band is wider than the effect it advertises (e.g. ±44% "fair value" selling a +25% "discount"), OR a "discount vs model" is asking-vs-asking | **≤ 40** |
| **G3 Imputed-as-measured** | A metric shown as fact (yield, value) is actually imputed/asking-based for the listing AND not visibly labelled as an estimate on the card | **≤ 50** |
| **G4 Phantom multi-source** | UI/marketing implies multiple portals but **>95%** of live rows are one source | **≤ 55** |
| **G5 Stale service** | Staleness banner active, or newest `last_seen` older than the promised SLA | **≤ 55** |
| **G6 Undifferentiated headline** | The first thing the user sees is a commodity number (area-median €/m², asking-gap) with none of the strategy-doc differentiators visible | **≤ 50** |

A score ≥ 90 is only reachable with **zero gates firing** and real credit in
differentiation + moat. That is deliberately hard: 90 means a real investor pays.

## The loop output — separate buildable from blocked

Every run must classify the top fixes so the loop never burns turns on the impossible:

- **BUILDABLE NOW** (no paid data, no owner decision): e.g. reframe/kill the inflated
  headline, STR-legality zone join (public rules), Golden-Visa zone flag (public rules),
  surface DOM/discount from our own history, energy+subsidy from parsed EPC, tighten the
  "opportunity" definition. **The loop works only these.**
- **BLOCKED ON OWNER / DATA / MONEY**: real sold-price AVM (no open Greek register →
  paid comps or owner sourcing), multi-portal via FlareSolverr (owner hosting), a paid STR
  revenue feed. **The loop does NOT attempt these — it lists them for the owner and stops
  claiming progress it can't make.**

## Verdict format (emit exactly this)

```
HONEST BUYER SCORE: NN/100   (was: previous)
Gates fired: [G1, G3] or "none"
Dimensions: Diff N/25 · Trust N/25 · Moat N/20 · Live N/15 · Job N/15
Realistic price today: €X/mo self-serve · €Y lump-sum — one line why
Single highest-impact BUILDABLE fix: <specific, tied to a gate/dimension>
Blocked-on-owner (not attempted this loop): <bullet list>
Honest ceiling for code alone: <one line>
```

## Non-negotiable
Do not round up. Do not credit intentions. If the honest number is 35, say 35 and name why.
A skill that reports a comfortable number is the exact thing the owner is furious about.
The score is a mirror, not a trophy.
