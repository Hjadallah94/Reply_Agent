# Reply Agent — Pricing & Unit Economics

**Document 5 of 5 — Business Model**

Tiers, the full cost model behind each JOD price, margins, break-even, and sensitivity.

- Prepared for: Hasan Jadallah
- Project: Meta Agent — Reply Agent (MVP use case)
- Date: August 2026
- Companion to: 01 — Product Vision, 02 — System Architecture, 04 — Go-to-Market
- All conversions in this document use the fixed JOD/USD peg: 1 USD = 0.709 JOD, i.e. 1 JOD ≈ $1.41.

---

## 1. Pricing Philosophy

Most regional competitors in the research (Doc 1, Section 6) hide their price behind "contact for quote" or set it for Gulf-level enterprise budgets. Reply Agent's pricing is built on the opposite bet: publish a real, low-friction JOD price, and make sure the underlying unit economics (Section 3) support that price profitably rather than treating it as a loss-leader. That's only possible because, for this specific use case, the two cost lines that dominate most competitors' pricing — human support labor and heavy enterprise infrastructure — barely apply here (Section 3 shows why).

## 2. Pricing Tiers

| | Starter | Growth | Pro |
|---|---|---|---|
| Price | 10 JOD/mo (≈ $14.10) | 25 JOD/mo (≈ $35.25) | 45 JOD/mo (≈ $63.45) |
| Message cap | 400 customer messages/mo | 1,500 customer messages/mo | 5,000 customer messages/mo |
| Channels | WhatsApp only | + Messenger | + Instagram (all three) |
| Core reply agent (RAG, escalation) | Included | Included | Included |
| Owner dashboard & analytics | Basic (conversation log only) | Full analytics (Doc 1, Section 5 metrics) | Full analytics + team seats |
| Order-status integration | Spreadsheet only | Spreadsheet + storefront (Salla/Zid/Shopify) | Spreadsheet + storefront |
| Proactive utility messages (restock/abandoned-cart) | — | — | Included (Meta per-message fee pass-through, Section 3) |
| Overage (beyond cap) | 0.015 JOD/message (≈ $0.021) | 0.015 JOD/message | 0.012 JOD/message |
| Support | Self-serve + email | Priority email | Priority + onboarding help |

*These caps and prices are a starting hypothesis to pressure-test in the paid pilot (Doc 3, Phase 5) — not a final commitment. Section 7 explains exactly why 10 JOD was chosen as the entry price so you can adjust it deliberately if pilot data says otherwise.*

## 3. What You're Actually Paying For — the Cost Model

Three cost lines make up almost all of the variable cost per customer: the LLM provider, Meta's messaging fees, and payment processing. A fourth, infrastructure, is mostly fixed rather than per-customer. Each is broken down below.

### 3.1 LLM provider cost (Claude)

Per Doc 2, Section 3.3, each customer message triggers up to four model calls in the LangGraph pipeline: intent classification, response generation (Haiku for ~85% of turns, Sonnet for the harder ~15%), and a self-check. Using Anthropic's standard published per-token pricing (Sonnet 5's introductory $2/$10 rate expired August 31, 2026; the figures below use its standard $3/$15 rate, so this is the number to build against going forward):

| Model | Input | Output |
|---|---|---|
| Claude Haiku 4.5 | $1.00 / million tokens | $5.00 / million tokens |
| Claude Sonnet 5 | $3.00 / million tokens | $15.00 / million tokens |

**Revised against real production data (2026-09-06/07).** The table below was originally built on assumed token counts before this product had any real traffic. Two live-traffic studies since then — 8 conversations on 2026-09-06, plus a 12-message conversation on 2026-09-07, both cost-logged per API call via `billing/cost_tracking.py`'s `ApiCallLog` table — measured every single-turn message at **$0.0045–$0.0052**, 40–55% above the original $0.00325 estimate. The gap is almost entirely `self_check`: its real prompt (conversation history, retrieved context, the delivery estimate when present, and the draft itself) runs roughly 6x heavier than assumed, not the LLM's per-token price, which is unchanged. `generate_response`'s original estimate held up reasonably well by comparison.

| Pipeline step | Model | Approx. tokens (in / out) | Cost per message |
|---|---|---|---|
| classify_intent | Haiku | ~700 / 20 (was assumed at 200) | ≈ $0.0008 |
| self_check | Haiku | ~1,500 / 20 (was assumed at 250) | ≈ $0.0016 |
| generate_response | Haiku — real data so far | 1,500 / 100 | ≈ $0.0028 |
| **Total, Haiku-path (real, observed)** | — | — | **$0.0045–$0.0052 per customer message** |

Both live studies stayed entirely on the Haiku path — neither has yet produced a single message genuinely ambiguous/complex enough to route to Sonnet, so **the 85%/15% Haiku/Sonnet split above is still a planning assumption, not something real data has validated either way.** Section 4 below uses **$0.0052** (the upper end of the real observed range) as the per-message figure, consistent with this document's own worst-case convention (Section 4's intro). Prompt caching (Doc 2, Section 3.3) still applies on top of this at 10% of normal input price on a cache hit — not yet isolated in the real numbers above, so actual costs may run a little below $0.0052 once caching's effect is measured directly.

### 3.2 Meta channel cost (WhatsApp, Instagram, Messenger)

This is the single most important — and most misunderstood — cost line, and it's the reason this business model works at a 10 JOD entry price:

- **Instagram Messaging and Facebook Messenger: $0 per message.** Meta does not charge for messages sent or received through these APIs — the cost is entirely the friction of app review (Doc 3, Section 2), not a per-message fee.
- **WhatsApp "service" messages (replies to a customer within the 24-hour window they opened): $0 per message.** Meta made service conversations free for all businesses in November 2024, and the July 2025 shift to per-message billing only applies to business-initiated Marketing, Utility, and Authentication template messages sent outside that window.
- **This product is architected to stay almost entirely inside the free lane:** Doc 1, Section 4.2 explicitly excludes outbound marketing/broadcast messages from V1, and the agent only ever replies to a customer who messaged first. The only paid WhatsApp messages in this model are the optional Pro-tier proactive utility messages (restock/abandoned-cart), which are priced with the Meta fee passed through, not absorbed.
- **Recommended integration path: Meta's own WhatsApp Cloud API directly, not a third-party BSP** (Business Solution Provider) like Twilio or 360dialog. Those typically add $40–55/month in platform fees or a per-message markup on top of Meta's own rates — money that would otherwise erode margin at this price point. Building directly on the Cloud API (Doc 2, Section 6) means Reply Agent itself is the "platform layer" a seller would otherwise pay a BSP for.

> **Budgeted Meta cost per customer, per month**
> - Starter: ≈ $0.30 buffer (occasional utility templates, e.g. re-opening a stale thread) — most months this will be closer to $0.
> - Growth: ≈ $0.50 buffer.
> - Pro: ≈ $1.00, since this tier includes intentional proactive utility messages as a paid feature.

### 3.3 Payment processing

Card/subscription payment gateways typically charge 2.5–3.5% of the transaction; this model uses 3% as a planning assumption, to be confirmed against the specific gateway chosen in Doc 3, Phase 4.

### 3.4 Infrastructure — mostly fixed, not per-customer

Hosting, the Postgres+pgvector database, the queue, and observability tooling (Doc 2, Section 6) are a shared, largely fixed monthly cost that gets cheaper per customer as the customer base grows — the normal SaaS pattern. At pilot scale this is estimated at roughly $200/month total, growing gradually (not linearly) with usage. A small marginal per-tenant allocation (storage, compute) is included in the tables below for completeness.

### 3.5 Google Maps / distance-estimation cost (built and live — not yet in Section 4)

Doc 1, Section 9 and Doc 2, Section 9's planned delivery-time estimation is now built and live (the `estimate_delivery` pipeline step, using Google's Routes API "Compute Route Matrix Pro" tier). Its per-call price is now known and confirmed from a real production call, cost-logged the same way as the LLM calls in Section 3.1: **$10.00 per 1,000 elements = $0.01 per call.** This only fires for `place_order` messages that include a delivery address (not every customer message needs one), still excluded from Section 4's per-tier tables below — what's still missing is a real, observed call-volume-per-customer rate (what fraction of a tier's monthly messages are actually order-placement messages that trigger this call), not the per-call price itself. Before folding this into Section 4:

- Gather enough live order volume to estimate that rate with real data, the same way Section 3.1's LLM figures were revised — not an assumed fraction.
- Re-run Section 4's unit economics with this added as a new line once that rate exists.

## 4. Full Unit Economics per Tier

Costs below are calculated at full message-cap utilization — the conservative, worst-case scenario for margin. Most customers won't use their full cap every month, so real margins will typically run higher than shown here.

| | Starter (10 JOD / $14.10, 400 msgs) | Growth (25 JOD / $35.25, 1,500 msgs) | Pro (45 JOD / $63.45, 5,000 msgs) |
|---|---|---|---|
| LLM cost (at $0.0052/msg, real observed) | $2.08 | $7.80 | $26.00 |
| Meta channel fees | $0.30 | $0.50 | $1.00 |
| Payment processing (3%) | $0.42 | $1.06 | $1.90 |
| Marginal infra allocation | $0.50 | $0.75 | $1.25 |
| **Total variable cost** | **$3.30** | **$10.11** | **$30.15** |
| **Contribution margin** | **$10.80** | **$25.14** | **$33.30** |
| Contribution margin % | ≈ 77% | ≈ 71% | ≈ 52% |

*(Revised 2026-09-07 against real per-message LLM cost — Section 3.1 above. Previously, before any real traffic existed, this table used an assumed $0.00325/message and showed 82%/80%/68% margins.)*

The Pro tier's margin percentage is lower for two compounding reasons: it's the only tier carrying real, intentional Meta messaging fees (the proactive utility messages), and its 5,000-message cap means the same real per-message LLM cost increase above compounds the most there — the underlying reply-agent economics are consistent across all three tiers, but Pro's margin is now visibly thinner than Starter/Growth's, worth watching once real Pro-tier usage exists.

## 5. Break-Even & Fixed Costs

Assume a $220/month fixed platform baseline (Section 3.4) and an early customer mix weighted toward the lower tiers (a reasonable assumption for a Jordan-first launch): 60% Starter, 30% Growth, 10% Pro.

| Tier | Mix | Contribution margin | Weighted contribution |
|---|---|---|---|
| Starter | 60% | $10.80 | $6.48 |
| Growth | 30% | $25.14 | $7.54 |
| Pro | 10% | $33.30 | $3.33 |
| **Blended average per customer** | — | — | **≈ $17.35** |

> **Break-even point**
> $220 fixed cost ÷ ≈ $17.35 blended contribution margin per customer ≈ **13 paying customers** to cover the fixed platform cost (12 customers' contribution, $208.20, doesn't quite cover the $220 fixed baseline; 13 does — revised from the previous ≈12-customer estimate now that Section 4's margins reflect real per-message LLM cost).
> Doc 1's own pilot target (15–25 paying customers, Section 5) would still put the business past break-even on infrastructure — everything beyond that is close to pure contribution margin, since the cost base barely grows with each additional customer.

## 6. Sensitivity — What Could Change This

| Risk / variable | Effect | Mitigation |
|---|---|---|
| Meta reintroduces paid "service" conversations on WhatsApp (it has changed pricing policy before). | Would meaningfully raise the WhatsApp cost line, especially for high-volume tiers. | Monitor Meta's developer pricing announcements as a standing operational task; keep tier pricing/caps as an adjustable lever, not hard-coded into the product. |
| Actual usage runs consistently near the message cap rather than below it. | Margins shown in Section 4 are already the worst case (100% cap utilization), so this is already priced in — but overage pricing (Section 2) is set above marginal cost specifically to protect margin if it happens anyway. | — |
| LLM prices drop further (the historical trend for both Anthropic and OpenAI). | Improves margin further; no action needed beyond periodically revisiting model routing (Doc 2, Section 3.3) to take advantage. | — |
| Payment gateway fee is higher than the 3% assumption for the chosen local provider. | Slightly compresses margin (roughly $0.15–0.30/customer/month at the assumed volumes). | Confirm actual gateway fee during vendor selection (Doc 3, Phase 4) and re-run this table before finalizing prices. |
| Willingness to pay in Jordan is lower than 10 JOD in practice. | Directly affects revenue. | Validate with the paid pilot (Doc 3, Phase 5; Doc 4, Section 3) before committing to final public pricing — treat these numbers as a hypothesis. |
| The Google Maps cost line (Section 3.5) is priced ($0.01/call, confirmed live) but not yet volume-modeled into Section 4. | Section 4's margins do not yet reflect this cost — they'll compress somewhat once real order-volume data lets it be added. | Gather real order-placement call-volume data, then re-run Section 4 with the new line before changing any tier price or cap. |

## 7. Why 10 JOD, Specifically

- **It undercuts the closest priced comparables once converted.** Teammates.ai's cheapest paid tier is $25/mo; The Whatbot (WhatsApp-only) is $29/mo. Wittify AI's entry credit tier (≈33 AED) converts to roughly $9 — the nearest real comparable — putting 10 JOD ($14.10) in a defensible, still-affordable position just above it while covering three channels instead of one.
- **It sits far below the Gulf-agency price band.** HalaFlow's cheapest tier (199 AED) converts to roughly $54/mo — nearly 4x the Starter price here — reflecting UAE purchasing power that doesn't match a Jordanian solo seller's budget (Doc 1, Section 2.1).
- **It's a psychologically easy "yes."** 10 JOD a month is roughly the cost of a single boosted Instagram post or a couple of coffees for many sellers — priced low enough to be an impulse decision rather than a budget conversation, consistent with the "self-serve, no sales call" design principle in Doc 1.
- **It is genuinely profitable, not a loss-leader.** Section 4 shows an ≈77% contribution margin on the Starter tier even at full cap usage, using real per-message LLM cost. That's only possible because, for this specific use case, the two cost lines that usually make cheap AI products unprofitable — expensive per-message platform fees and expensive frontier-model calls — are both structurally small here: Meta's core messaging is free by design (Section 3.2) and a classification/self-check pipeline lets most turns run on the cheap model (Section 3.1).
- **It's round and memorable for word-of-mouth marketing** ("10 dinars a month") — directly supporting the community/referral-driven acquisition strategy in Doc 4.

## 8. Future Pricing Evolution

- Once Jordan pricing and product-market fit are validated (Doc 1, Section 8; Doc 4, Section 3), introduce AED-denominated tiers for Gulf expansion, priced closer to — but still below — the Gulf competitor band identified in Doc 1, Section 6 (e.g. positioned under HalaFlow's 199 AED entry tier).
- Introduce usage-based overage as the primary lever for heavy users rather than constantly raising base prices, preserving the low, easy entry point that is core to the positioning.
- Reserve a custom/enterprise tier (Doc 1, Section 4.2) for sellers who outgrow Pro — deep storefront integrations, multiple team seats, dedicated support — priced case-by-case like most of the competitive set, once there's real demand for it.

---

*This closes the five-document set: 01 Product Vision & PRD, 02 System Architecture, 03 Development & Deployment Roadmap, 04 Go-to-Market & Marketing, 05 Pricing & Unit Economics.*
