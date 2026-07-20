# Product Strategy — why anyone would pay

_Anchored to sourced market research (2026-07-20). This file is the north star for every
build decision. If a feature doesn't serve the thesis below, it's commodity — cut it or
keep it as silent table-stakes, never as the headline._

## The buyer & the job
Cross-border / semi-professional buy-to-let & short-term-rental (STR) investor in Athens —
including Golden Visa applicants and the advisors who serve them — deploying €150k–€800k
into a market whose rules just changed, who often doesn't read Greek.

**The job they hire us for:** "Tell me which specific listing I can *legally* short-let,
what it will actually rent for, how far below asking it will really trade, and whether it
qualifies for my Golden Visa / subsidy — before I wire money."

## Why they pay (and can't get it free)
Portals (Spitogatos/Indomio/XE) show asking prices + area medians for free, and the
government "Price Map" will soon give *sold* prices free. None of them join listing-level
data to the things that now decide the investment:
- **STR legality** — new Airbnb (AMA) registrations frozen in central Athens districts 1–3
  through 2026, expanding to 5 more hotspots; AMA is **non-transferable** (dies on sale),
  fines €5k–€20k under Law 5170/2025.
- **Golden Visa zone** — €800k floor in Athens / €400k elsewhere since Sept 2024.
- **Energy class** — EU EPBD binds May 2026; >50% of Greek homes predate 1980; up to 80%
  renovation subsidy for 30-yr-old homes.

Each turns a listing's headline yield into a **legal/eligibility question no portal answers
and the buyer can't get wrong cheaply.** That join is the product.

## The moat (the asset that compounds)
Scrape listings **daily** and keep what portals deliberately hide: per-property
days-on-market, every price cut, relisting cycles, realized **discount-from-ask**. A
proprietary longitudinal time-series a competitor starting today cannot backfill. The
Price Map gives *sold* prices but never the *trajectory* (how long, how many cuts, how far
below ask) — and that trajectory is the "which seller is motivated / what will it really
trade at" signal investors pay Reonomy & PropertyData for. **We already store price history
daily — this asset is live and growing. Protect and surface it.**

## Build priority (WTP × defensibility)
1. **STR-legality + grandfathered-AMA scarcity layer** — per listing: can it be legally
   short-let today? value the premium on stock that already holds a grandfathered license.
   Highest WTP × highest defensibility (local regulation is the moat). → ~€25–49/mo.
2. **Longitudinal DOM + realized discount-from-ask** — surface the accumulating history as
   a "motivated seller / true trade price" signal. The compounding moat.
3. **Golden Visa eligibility targeting** — €400k vs €800k zone per listing; visa-qualifying
   filter. Advisory-grade → €99+/mo pro tier.
4. **Energy-class renovation underwriting tied to subsidy** — EPC class, cost to jump ≥3
   classes, net of Exoikonomo/2026 subsidy. Rising into 2026.
5. **Property-level STR revenue nowcast** — ADR/occupancy/revenue from local comps, but only
   as the *input* to (1), never standalone (that's AirDNA's $15 commodity).

## STOP doing (commodity — table-stakes at most, never the headline)
- Re-presenting asking prices / area medians / metro proximity (portals do it free).
- Static "fair-value gap vs **asking**" (Price Map makes it worthless; gap-vs-realized-
  discount does not).
- Generic net-yield / 5-yr / transfer-tax calculators as a headline.
- Standalone Airbnb revenue estimates decoupled from Greek STR-legality.

## Positioning (one line)
"The only tool that tells a cross-border investor which Athens listing they can **legally
short-let**, what it will **really trade for**, and whether it **qualifies for their
visa/subsidy** — priced ~€29/mo self-serve, ~€99/mo pro, with daily-scraped DOM/discount
history as the asset that can't be copied."

## Honest ceiling
Code alone reaches a credible **subscription product**, not a €1M asset. €1M = recurring
revenue (~€200–300k ARR at 3–5× multiples) or a proven data moat with customers. This doc
gets the product to "a real investor would pay €29–99/mo"; the rest is revenue + time
accumulating the moat — the part only the owner + market can close.

---
_Sources captured in the 2026-07-20 market-gap research (RentalScaleUp, GreekCityTimes,
GlobalCitizenSolutions, AirDNA, PropertyData, Reonomy comps, Law 5170/2025 coverage)._
