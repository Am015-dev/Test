# Business model — from free screener to a profitable data business

## The honest starting point
The current app (scrape portals → score → dashboard) is worth ~€4 because it re-presents
**free** public data (XE, Green-Acres) plus an "undervaluation" score built on **asking
prices** and a noisy model. Customers won't pay for a prettier view of a free portal.

## The pivot: sell what free portals HIDE, and let it compound
Stop competing on "undervalued" (unreliable). Sell **negotiation & motivated-seller
intelligence** — a signal that is *factual, not predicted*, and that free portals
deliberately do not surface:

- **Days on market** (how long a flat has sat) — tracked daily.
- **Price-cut history** — how many times, how much, how recently the price dropped.
- **Relistings** — pulled and re-posted (a classic distress/reset signal).
- **Stale + overpriced** — sitting *above* the area median = a seller who will deal.

None of this exists in a single portal snapshot. It only exists if you **record the
market every day**. That daily time-series is the moat: a competitor starting today is
months behind, and it can't be scraped in one shot. Value **compounds with time**.

## Who actually pays (ranked by willingness-to-pay)
1. **Real-estate agents (B2B — the real revenue).** Agents pay for *seller leads*. "These
   12 owners in your patch have sat 90+ days and cut price twice → call them to win the
   listing" is money in their pocket. Sold as per-lead or a territory subscription.
2. **Active investors / small developers (B2C prosumer).** Pay a subscription for daily
   alerts: new listings first, price drops, and the motivated-seller shortlist in their
   areas/budget — so they negotiate from strength.
3. **Later: data/API licensing** of the cleaned, geocoded, time-series dataset to
   proptech/valuers/banks.

## Product tiers (built into the app)
- **Free:** browse current listings + basic filters (the commodity — a funnel, not the product).
- **Investor €19/mo:** daily email/Telegram alerts (new + price-drop + motivated-seller),
  full negotiation scores, watchlist, net-yield underwriting.
- **Pro / Agent €99/mo per territory:** the motivated-seller lead list for chosen
  municipalities, exportable (CSV), refreshed daily, with contact-readiness ranking.

## Unit economics (illustrative, must be validated with real sales)
- Cost: one small VM (~€0/mo on Oracle Always-Free) + scraping. Marginal cost per user ≈ €0.
- 50 investor subs (€19) + 15 agent territories (€99) ≈ **€2,435/mo** at near-zero COGS.
- Break-even is a handful of agents. The scarce input is **distribution**, not compute.

## The moat
1. **Time-series data** that compounds daily and can't be back-filled.
2. **Cross-portal dedup** (XE + Green-Acres + more) → one clean record per property.
3. Switching cost once an agent relies on the daily lead flow.

## What is CODE (I can build) vs GO-TO-MARKET (you must drive)
- **Code (this repo):** the negotiation-intelligence engine, daily tracking, alerts,
  tiered access, agent lead export, and the funnel UI. Delivered here.
- **Not code (yours):** signing the first agents, pricing validation, payments/billing
  (Stripe), a company/invoicing, GDPR/ToS for scraping & contacting owners, and running
  the tracker daily for months so the moat actually accrues.

Profitability = this product **+** those go-to-market steps. The code makes it sellable;
it doesn't make the sale. That part is honest and unavoidable.
