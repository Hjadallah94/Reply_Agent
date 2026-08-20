# Reply Agent — Product Vision & Requirements

**Document 1 of 5 — Product Strategy**

An autonomous LangGraph agent that replies to Instagram, WhatsApp, and Facebook messages for solo and small online sellers.

- Prepared for: Hasan Jadallah
- Project: Meta Agent — Reply Agent (MVP use case)
- Date: August 2026
- Status: Pre-build planning draft — for review before development begins

---

## 1. The Problem

Solo and small online sellers in Jordan run their entire storefront through Instagram DMs, WhatsApp chats, and Facebook Messenger. There is no checkout page — the **chat window is the business.** That means the owner is on call constantly: a customer asking "is this available in medium?" at 11pm, another asking for the price they already posted, another asking where their order is. Stepping away for even a few hours risks a lost sale, a frustrated customer, or a bad review.

This is the specific, narrow problem the first product solves: give a solo online seller their evenings and weekends back by having an agent answer the repetitive, answerable questions in their DMs — accurately, in their own voice, in Arabic and English — while knowing exactly when to stop and wake the owner up.

> **Why this use case first**
> - It is narrow enough to ship in weeks, not months.
> - It has a clear, felt pain point ("I can't leave my phone") that is easy to market around.
> - It validates the core technical bets — LangGraph orchestration, multi-channel Meta integration, RAG grounding, escalation logic — that every other idea on the research sheet (HR assistant, document reviewer, executive assistant) will also need.
> - The competitive research shows real willingness to pay for exactly this in the region (see Section 6), but almost every regional competitor is priced opaquely ("contact for quote") or built for mid-market/enterprise budgets — leaving solo sellers underserved.

## 2. Target Customer

### 2.1 Primary ICP (Ideal Customer Profile)

| Attribute | Profile |
|---|---|
| Who | A solo or small-team online seller (1–3 people) running a shop primarily through Instagram and/or WhatsApp, with Facebook as a secondary channel. |
| What they sell | Physical goods with a fairly stable catalog and price list: fashion, abaya/modest wear, cosmetics, home goods, accessories, baked goods/food, phone accessories, etc. |
| Geography | Jordan first (Amman-centric, national reach). Arabic (Jordanian/Levantine dialect) and English, often mixed within a single conversation. |
| Order flow today | Manual: customer DMs → seller answers questions → confirms order → arranges Cash-on-Delivery or CliQ transfer → books a courier (Aramex, local delivery). |
| Pain today | Owner is the only person answering messages, at all hours, answering the same 10 questions repeatedly (price, sizes/colors, delivery time, availability, order status). |
| Tech comfort | Comfortable with Instagram/WhatsApp Business apps; not technical. Will not tolerate a complex setup — expects something closer to "turn on a toggle" than "hire a developer." |
| Willingness to pay | Price-sensitive relative to Gulf peers, but already spends on boosted posts, courier fees, and sometimes basic CRM/inbox tools. A monthly SaaS fee under what one lost sale or one afternoon of lost time would cost is an easy yes. |

### 2.2 Jobs to be Done

- When a customer messages outside working hours, I want a fast, accurate reply sent automatically, so I don't lose the sale to a competitor who answers first.
- When a customer asks something routine (price, size, color, delivery time, order status), I want it answered without me lifting a phone.
- When a customer asks something risky (a refund, a complaint, a custom deal, something the agent isn't sure about), I want to be the one who decides — but with minimal effort, ideally a one-tap approval on a drafted reply.
- I want one place to manage my product info and FAQs, not three separate chatbot settings for three separate apps.
- I want to trust that the agent will never invent a price, a stock level, or a delivery promise that isn't true.

## 3. Product Vision & Value Proposition

**Vision:** Every solo seller in the Levant runs their DMs through an agent that knows their catalog, their voice, and their customers — and only wakes them up when it truly matters.

**V1 value proposition:** "Reply Agent answers your Instagram, WhatsApp, and Facebook messages like you would — instantly, in Arabic or English — and only pings you when a human decision is actually needed."

### 3.1 Design principles

1. **Trust over cleverness.** A wrong price or an invented promise costs the seller a customer relationship. Every generated claim must be traceable to the seller's own data (RAG-grounded) or explicitly hedged.
2. **The owner is never fully out of the loop.** Escalation is a first-class feature, not a fallback — with drafted replies so the owner's effort is a tap, not a typing session.
3. **One brain, three channels.** A single knowledge base, brand voice, and escalation policy drive Instagram, WhatsApp, and Messenger — sellers manage it once.
4. **Self-serve from day one.** No sales call required to start a free trial; setup should take under 15 minutes (connect channel, paste/upload catalog, done).
5. **Transparent pricing.** Unlike most competitors in the regional research (Section 6), publish real JOD prices on the website.

## 4. Scope — MVP vs Later

### 4.1 In scope for V1 (the reply agent)

- Inbound message handling on WhatsApp (Cloud API), Instagram Messaging, and Facebook Messenger.
- Knowledge base per business: product catalog (name, price, variants, stock status), store policies (delivery, returns, payment methods), FAQs — uploaded as a spreadsheet/doc or typed in.
- RAG-grounded auto-replies for informational questions (price, availability, delivery time, policies).
- Order-status lookups when the seller connects a simple order sheet or supported storefront (Salla/Zid/Shopify — see Doc 3).
- Escalation to the owner (push notification / WhatsApp message to the owner's own number) with a drafted reply for anything outside policy, low-confidence, or emotionally charged (angry customer, refund/complaint, price negotiation).
- Bilingual Arabic (Jordanian/Levantine, code-switched with English) and English responses matching the seller's tone.
- A lightweight web dashboard: connect channels, manage knowledge base, view conversations, view escalations, basic analytics.

### 4.2 Explicitly out of scope for V1

- Outbound marketing/broadcast campaigns (this is a reply agent, not a marketing sender) — avoids most Meta per-message fees, see Doc 5.
- Payment collection / checkout automation — sellers keep their existing COD/CliQ flow for now.
- Voice calls, TikTok, or other channels beyond the three named Meta surfaces.
- Deep CRM/ERP integrations (enterprise-style) — reserved for a future "Pro"/custom tier once there is demand.
- The other three ideas on the research sheet (HR assistant, document reviewer, employee assistant) — parked, but the architecture in Doc 2 is intentionally reusable for them.

## 5. Success Metrics (V1)

| Metric | Target for first 90 days post-launch | Why it matters |
|---|---|---|
| Auto-resolution rate | ≥ 60% of inbound messages answered without escalation | Core value prop: hours given back to the owner. |
| Escalation precision | ≥ 90% of escalated threads are ones a human would agree needed escalation | Trust — false escalations annoy the owner, false auto-replies risk the business. |
| Time-to-first-response | < 30 seconds for auto-replies, < 15 min median for owner-approved escalations | Speed is the entire pitch versus a human checking their phone late. |
| Paying pilot customers | 15–25 sellers converted from free trial | Validates willingness to pay at the proposed JOD price point (Doc 5). |
| Monthly churn | < 8%/month in the first two quarters | Early SaaS health signal; watch closely given small sample. |

## 6. Competitive Landscape

Two research passes are already on file. Summarized below with implications for positioning.

### 6.1 Direct / adjacent competitors (from your research)

| Company | Offer | Price | Gap this leaves |
|---|---|---|---|
| The Whatbot | WhatsApp-only agent on Meta API | $29/mo flat | Single channel only; no Instagram/Messenger unification. |
| HalaFlow (Dubai) | WhatsApp + Instagram unified inbox, Gulf-dialect detection, booking/CRM | 199 / 599 / 1,299 AED per month (≈ $54 / $163 / $354) | Gulf-dialect tuned, not Levantine/Jordanian; priced for UAE purchasing power, not Jordan; targets service SMEs (salons, clinics) more than product sellers. |
| Aiingo (Dubai/India) | Instagram DM → WhatsApp funnel automation, lead qualification | Custom quote | No published pricing; oriented to lead-gen/clinics rather than direct product-catalog Q&A. |
| Korvax AI (Dubai) | Custom RAG chatbots, IG + WhatsApp automation | 45,000–150,000 AED setup + custom monthly | High-end bespoke build, not a self-serve product a solo seller can turn on. |
| Mint Digital Solutions (UAE) | Meta Official Partner, WhatsApp AI bots + Zoho CRM | 2,600–13,000+ AED setup, 800–2,200 AED/mo | Enterprise-grade agency pricing, far above solo-seller budgets. |
| Wittify AI (Saudi) | No-code omnichannel agent builder, credit-based | 33–208 AED/mo (credit tiers) | Closest in price band, but general-purpose builder (not e-commerce-reply specialized) and Saudi-first. |
| Teammates.ai | Named-role agents incl. "Raya" for customer support | Free / $25 / $50 / $100 per month | Global generic support agent, no Meta-channel or Arabic-dialect specialization. |
| Fin (Intercom) | Customer support agent, e-commerce variant | $0.99/resolution (50 min) + $29–139/seat Intercom plan | Priced and built for teams already on Intercom — not solo Instagram/WhatsApp sellers. |

### 6.2 Positioning takeaway

Nobody in the research set is a self-serve, transparently-priced, Levantine-Arabic-fluent, three-channel reply agent built specifically for solo product sellers. The closest analogues (HalaFlow, Wittify) are Gulf-first and priced for AED-level purchasing power. That gap is the opening: launch in Jordan with honest pricing and dialect fluency, then expand toward the Gulf pricing tiers once the product is proven (see Doc 4 and Doc 5).

## 7. Differentiation — the Product's Edge

- **Levantine/Jordanian dialect fluency, not just "Arabic."** Competitors that do dialect-matching (HalaFlow) tune for Khaliji/Egyptian/Gulf speech. Reply Agent is tuned and evaluated specifically on Jordanian/Levantine colloquial chat — including the English/Arabic code-switching sellers and customers actually use.
- **Draft-and-approve escalation, not just an alert.** When the agent isn't confident, the owner doesn't get a bare notification — they get a ready-to-send drafted reply they can approve, edit, or override in one tap from their phone. This keeps the "take a few hours off" promise true even for the messages that do need a human.
- **Hallucination guardrails tuned for commerce risk.** A dedicated self-check step (Doc 2, Section 3) refuses to let the agent state a price, stock level, or delivery date that isn't backed by the seller's own data — the single biggest trust risk for this use case.
- **One knowledge base, three channels.** Update your catalog once; Instagram, WhatsApp, and Messenger all reflect it immediately — versus juggling three separate chatbot tools.
- **A continuous, cheap learning loop.** Every owner correction on an escalated draft is captured and folds back into the knowledge base / few-shot examples — the agent gets better at this specific seller's voice without any model fine-tuning or retraining cost.
- **Transparent, Jordan-appropriate pricing.** Published JOD tiers instead of "book a demo" — removes the biggest friction competitors leave on the table in this segment.

## 8. Key Risks & Assumptions

| Risk / Assumption | Mitigation |
|---|---|
| Meta app review for WhatsApp/Instagram messaging permissions could take longer than expected or be rejected. | Start the Meta Business verification and app review process in Phase 0 (Doc 3), in parallel with build; have a manual/demo fallback for pilot customers. |
| Sellers may not trust an AI to represent their brand voice. | Default to a conservative, clearly-labeled "AI assistant" persona at launch (transparency also reduces regulatory/customer-trust risk); make brand-voice tuning easy in onboarding. |
| Arabic dialect handling is genuinely hard and may under-perform English. | Treat as a core V1 quality bar with dedicated evaluation set (Jordanian DMs) before pilot launch, not an afterthought. |
| Low message-volume sellers may not see enough value to pay monthly. | Starter tier priced low enough (Doc 5) to be a low-risk yes; free trial lets sellers feel the time saved before paying. |
| Willingness-to-pay in JOD is unproven versus the AED benchmarks in the research. | Run a paid pilot with 15–25 real sellers before committing to a final price; treat Doc 5's numbers as a starting hypothesis, not a fixed price. |

---

*Next document: 02 — System Architecture (LangGraph nodes, RAG and memory layers, data model, tech stack).*
