# Reply Agent — Development & Deployment Roadmap

**Document 3 of 5 — Execution Plan**

Phased build plan, Meta app review process, testing, deployment, and legal/compliance checklist.

- Prepared for: Hasan Jadallah
- Project: Meta Agent — Reply Agent (MVP use case)
- Date: August 2026
- Companion to: 01 — Product Vision, 02 — System Architecture

---

## 1. Phased Build Plan

Six phases, sequenced so every phase produces something usable — no "big bang" launch. Durations assume a small team (1–2 builders, possibly you plus one engineer) working part-time-to-full-time; treat them as planning inputs, not commitments.

### Phase 0 — Foundations (1–2 weeks)

- Register the Meta Developer app; start Meta Business verification (this has the longest external lead time of anything in this plan — start it first).
- Stand up hosting, database (Postgres + pgvector), and repo/CI skeleton per the stack in Doc 2, Section 6.
- Draft the product's own Privacy Policy and Terms of Service (required for Meta app review — see Section 2).
- Build the evaluation set: 40–60 real or realistic Jordanian DM conversations (Arabic/English mixed) covering FAQs, price questions, order status, complaints, and edge cases — this becomes the quality bar for every phase after.

### Phase 1 — Single-channel MVP (3–5 weeks)

- Build the LangGraph pipeline end to end (Doc 2, Section 3) for one channel first — WhatsApp is recommended, since it's the primary ordering channel for most sellers and has the clearest free-messaging rules (Doc 5, Section 3).
- Manual knowledge-base entry (no upload UI yet) — enough to run the pipeline against a real seller's catalog.
- Escalation via a simple notification (e.g., a WhatsApp message to the owner) — the dashboard UI can come later.
- Run the evaluation set from Phase 0 against the pipeline; do not proceed until auto-resolution and escalation-precision targets from Doc 1, Section 5 are within reach on the eval set.

### Phase 2 — Multi-channel + real RAG (3–4 weeks)

- Add Instagram Messaging and Messenger channels, reusing the same graph (this validates the "one brain, three channels" architecture bet from Doc 1).
- Replace manual knowledge entry with a proper ingestion pipeline: spreadsheet/doc upload → chunk → embed → store.
- Add the spreadsheet-based order-status integration (Doc 2, Section 2.6).

### Phase 3 — Escalation UX + analytics (2–3 weeks)

- Build the owner-facing web dashboard: connect channels, manage knowledge base, view/approve escalations, basic analytics (Doc 1, Section 5 metrics).
- Implement the draft-and-approve escalation flow properly (one-tap approve/edit/send), not just a raw alert.
- Implement the owner-correction feedback loop (Doc 1, Section 7) so corrections on escalated drafts improve future replies.

### Phase 4 — Billing & self-serve onboarding (2 weeks)

- Implement the pricing tiers and usage metering from Doc 5.
- Build the self-serve signup + Meta embedded signup flow so a new seller can go from "never heard of this" to "connected and live" in under 15 minutes (Doc 1, Section 3.1).
- Payment collection suited to Jordan (see Section 5 of this document).

### Phase 5 — Pilot, harden, launch (3–4 weeks, overlaps with Doc 4's launch plan)

- Run a paid or free pilot with 10–20 real sellers (Doc 4, Section 4).
- Fix issues surfaced by real traffic; re-run the evaluation set; tighten guardrails based on real escalations.
- Load-test the queue/webhook path for burst traffic (e.g. a seller's post going viral).
- Public launch.

> **Total estimated timeline**
> Roughly 14–20 weeks from a standing start to public launch, dominated less by engineering effort than by Meta's app review and business verification lead times (Section 2) — start those immediately and build in parallel.

### Phase 6 — V2: Operational Automation (post-launch expansion, timeline TBD pending Phase 5 pilot learnings)

Not part of the original six-phase plan — added after early customer conversations validated demand for real operational reasoning (delivery logistics), not just informational Q&A (Doc 1, Section 9; Doc 2, Section 9). Sequenced to prove the riskiest, cheapest-to-validate piece first, before investing in the bigger, more open-ended UI redesign.

1. **Foundation** — extend the Order/Business schema (Doc 2, Section 9.3), integrate the Google Maps Distance Matrix API, get real current pricing for it into Doc 5.
2. **Delivery-estimation reasoning** — build the `estimate_delivery` node, prove it against two real test scenarios (an after-cutoff order correctly deferred to next-day; a same-day order with a real 3-4 hour transit estimate) live, against real data, the same way every other feature in this project has been proven, not just unit tests.
3. **Approval workflow** — reuse the existing WhatsApp owner-notification channel first (cheapest, already built, no new infrastructure) rather than jumping straight to a native/PWA app. Prove the approve/reject mechanic works end-to-end before investing in a nicer notification surface.
4. **Adaptive autonomy** — start logging every approval outcome from day one of Phase 6.3, even before any auto-approval logic exists, so there's real historical data to build the heuristic in Doc 2, Section 9.4 against once there's enough of it.
5. **Product/catalog management + promotions** — dashboard CRUD for products and time-bound promotional content, replacing the spreadsheet-upload-only flow.
6. **UI modernization + bilingual redesign** — the biggest, most open-ended piece of this phase: a genuinely polished, Arabic/English (RTL-aware) owner-facing interface, including real push notifications (Doc 2, Section 9.6). Scoped as its own initiative so it doesn't gate the operational-reasoning capability above, which delivers real value on the existing dashboard first.

This phase is explicitly sequenced after Phase 5's pilot, not before — real pilot feedback should inform which of these pieces actually matter most to real sellers before committing further build time.

## 2. Meta App Review & Business Verification

This is the step most likely to be the critical path, so it's called out separately. Requirements evolve, so re-verify against Meta's current developer documentation before Phase 0, but the shape of the process is stable:

1. Create a Meta Business Portfolio and complete Business Verification (legal business documents, may take days to a couple of weeks).
2. Create a Meta Developer app; add the WhatsApp Business Platform, Instagram (via a connected Facebook Page), and Messenger products.
3. Set up WhatsApp Cloud API access (Meta-hosted, no BSP required — see Doc 5, Section 3 for why this is the recommended path over a third-party BSP).
4. Request the specific permissions needed: `whatsapp_business_messaging`, `instagram_manage_messages` / `pages_messaging`, and related. Each requires an App Review submission with a screen-recorded demo of the exact use case ("an AI agent that replies to customer messages on behalf of a connected business").
5. Because this product is a platform where each of your customers connects their own WhatsApp/Instagram/Facebook account, implement Meta's embedded signup flow (Tech Provider / Solution Partner pattern) so sellers can connect their own accounts without you holding their raw credentials.
6. Budget for at least one review rejection-and-resubmission cycle — common for first-time submissions, factored into the Phase 0–1 timeline above.

A note on positioning: Meta's review process will ask what the app does. "An AI agent replies automatically" is a legitimate, disclosed use case, but plan to clearly label AI-generated replies to end customers as an AI assistant — this satisfies both Meta's policies and general good practice, and is already a V1 design principle in Doc 1.

## 3. Testing & QA Strategy

| Layer | What's tested | How |
|---|---|---|
| Node-level unit tests | Each LangGraph node in isolation (classification accuracy, retrieval relevance, self-check logic). | Automated tests against the Phase 0 evaluation set, run on every change. |
| End-to-end conversation tests | Full graph runs against realistic multi-turn conversations, including the risk-category escalation paths. | Scripted conversation replays; assert on final route (send/escalate) and reply quality. |
| Bilingual quality review | Arabic (Jordanian/Levantine) and code-switched replies specifically — the area most likely to underperform if only tested in English. | Native-speaker manual review each phase, not just automated metrics. |
| Guardrail red-teaming | Attempts to get the agent to invent a price/stock/delivery promise, or to be talked out of escalating a risk-category message. | Manual adversarial testing before pilot launch (Phase 5). |
| Load / reliability | Webhook burst handling, queue backpressure, Meta API rate limits, checkpoint recovery after a crash. | Synthetic load tests before public launch. |
| Pilot feedback loop | Real seller and real customer reactions. | Direct interviews with pilot sellers plus escalation/correction data (Doc 2, Section 2.8). |

## 4. Deployment & Infrastructure Plan

- Environments: separate staging and production, with the evaluation set run against staging before every production deploy.
- CI/CD: automated tests gate merges; deploys to production are a deliberate, reviewed step (not every commit) at this stage of the business.
- Monitoring: uptime/error alerting on the webhook ingestion path (a silent failure there directly means a seller's customer gets no reply — the core failure mode to guard against), plus cost-tracking dashboards (LLM spend and Meta message spend per tenant, tying back to Doc 5's margin model).
- Backups: automated Postgres backups (conversation history and knowledge bases are business-critical data for your customers).
- Secrets management: Meta access tokens and API keys in a managed secrets store, rotated per Meta's token-refresh requirements.

## 5. Legal & Compliance Checklist

- Privacy Policy and Terms of Service covering: what data is collected from sellers and their customers, how it's used, retention, and the fact that replies are AI-generated.
- Review Jordan's Personal Data Protection Law obligations for handling customer PII (phone numbers, addresses, order data) collected on behalf of your business customers.
- Meta Platform Terms and WhatsApp Business Messaging Policy / Messenger Platform Policy compliance — opt-in requirements, messaging-window rules (Doc 5, Section 3), prohibited content categories.
- Payment processor / payment gateway terms for whichever collection method is used (Section 6).
- A clear disclosure in each conversation that the customer is talking to an AI assistant, satisfying both platform policy and customer-trust goals from Doc 1.

## 6. Team & Skills Needed

| Role | Needed for | Can this be you (Hasan) initially? |
|---|---|---|
| Backend/AI engineer (LangGraph, Python, RAG) | Core pipeline, Phases 1–3 | If you have or are building this skill set, yes for the MVP; otherwise the first hire or contractor to bring in. |
| Frontend engineer | Owner dashboard, Phase 3 | Could be combined with the backend role for V1's fairly simple UI, or a short contract engagement. |
| Native Arabic (Levantine) speaker for QA | Bilingual quality review, Section 3 | Essential and worth budgeting for even if everything else is solo/contracted — this is the product's core differentiator (Doc 1, Section 7) and the easiest thing to get subtly wrong. |
| Business/ops (you) | Meta verification, pilot recruiting, pricing, legal docs, GTM (Doc 4) | Yes — this track runs in parallel with engineering from Phase 0. |

Payment collection note: card processing in Jordan for a SaaS subscription typically routes through a local/regional gateway (e.g. a bank's payment gateway, or a regional processor) or through CliQ-style bank transfers for early pilot customers if a full recurring-billing integration isn't ready by Phase 4 — factor the gateway's own fee into the margin model (Doc 5, Section 3).

---

*Next document: 04 — Go-to-Market & Marketing Plan.*
