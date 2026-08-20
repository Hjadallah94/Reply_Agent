# Reply Agent — System Architecture

**Document 2 of 5 — Technical Design**

Layers, LangGraph node design, RAG and memory, data model, and tech stack for the Reply Agent.

- Prepared for: Hasan Jadallah
- Project: Meta Agent — Reply Agent (MVP use case)
- Date: August 2026
- Companion to: 01 — Product Vision & PRD

---

## 1. Architecture at a Glance

The system is organized into nine layers. The middle layer — the LangGraph orchestration graph — is the agent's "brain"; everything else exists to feed it clean context or to carry out its decisions.

| # | Layer | Responsibility |
|---|---|---|
| 1 | Channel & Ingestion | Receive webhooks from WhatsApp Cloud API, Instagram Messaging API, Messenger Platform; normalize into one internal message format; queue for processing. |
| 2 | Orchestration (LangGraph) | The agent's reasoning pipeline: classify, retrieve, generate, self-check, decide to send or escalate. |
| 3 | Knowledge / RAG | Per-tenant vector store + structured lookups over each seller's catalog, policies, and FAQs. |
| 4 | Memory | Short-term: conversation state within a thread. Long-term: customer profile (past orders, preferences) and owner-correction history. |
| 5 | Guardrail & Safety | Confidence checks, hallucination checks, PII handling, brand-voice and risk-category rules — runs inside the graph but is architecturally distinct. |
| 6 | Escalation / Human-in-the-loop | Drafts, notifies, and hands off to the business owner; resumes the graph once the owner responds or a timeout passes. |
| 7 | Integration | Order-status lookups and catalog sync with the seller's storefront (Salla/Zid/Shopify) or a simple spreadsheet. |
| 8 | Observability | Tracing, logging, conversation analytics, quality evaluation. |
| 9 | Multi-tenancy & Admin | Business onboarding, channel connection (Meta embedded signup), knowledge base management, billing. |

> **How to read this document**
> - Section 2 walks the nine layers in more depth.
> - Section 3 is the core deliverable: the actual LangGraph node-by-node design, as a graph and as a table.
> - Section 4 defines the shared state object that flows through the graph.
> - Section 5 is the data model (what gets stored, where).
> - Section 6 is the recommended tech stack.
> - Section 7 covers security/tenant isolation.
> - Section 8 walks one example conversation through the whole pipeline end to end.

## 2. Layer-by-Layer Detail

### 2.1 Channel & Ingestion Layer

Each channel has its own webhook contract, but they converge on one internal schema immediately so nothing downstream needs to know which app the message came from.

- WhatsApp Cloud API webhook → verifies signature → maps to internal message (text, media, contact, timestamp, WABA/phone number ID).
- Instagram Messaging API webhook (via the connected Facebook Page) → same normalization.
- Messenger Platform webhook → same normalization.
- A message queue (e.g. a durable queue/task runner) sits between ingestion and the graph, so a burst of messages, a slow LLM call, or a transient Meta API error never drops a customer message.
- Deduplication and idempotency keys (Meta will retry undelivered webhooks) prevent double-replies.

### 2.2 Knowledge / RAG Layer

Each business is a tenant with its own isolated knowledge base, built from whatever the seller provides at onboarding and keeps updated:

- Product catalog: name, description, price, variants (size/color), stock status.
- Store policies: delivery areas & timing, payment methods (COD, CliQ, bank transfer), return/exchange policy.
- FAQ pairs: anything the seller has answered before and wants standardized.
- Brand voice sample: a few example messages in the seller's own tone, used as few-shot grounding rather than embedded for retrieval.

Retrieval is **hybrid**: a vector similarity search (semantic — handles paraphrased questions and dialect variation) combined with a structured lookup against the catalog table (exact — for price/stock, where precision matters more than recall). The generation node is instructed to only state facts it can point to in the retrieved context; anything else must be hedged or escalated (Section 3, node 6).

### 2.3 Memory Layer

| Type | Scope | Storage | Example |
|---|---|---|---|
| Short-term (working) memory | Single conversation thread | LangGraph checkpointer (per-thread state, keyed by channel + customer ID) | Last N turns, current classified intent, pending tool results. |
| Long-term customer memory | One customer, across all their conversations with one business | Postgres customer-profile table | Past orders mentioned, stated size/preferences, whether they've been escalated before. |
| Long-term business memory | One business, across all customers | Postgres + vector store | Knowledge base content, owner-correction history feeding few-shot examples (Doc 1, Section 7). |

### 2.4 Guardrail & Safety Layer

- Groundedness check: does every factual claim in the drafted reply trace back to retrieved context or confirmed tool output?
- Risk-category rules: hard-coded categories that always escalate regardless of model confidence — refunds/complaints, price negotiation beyond a configurable discount limit, anything mentioning a competitor, legal threats, and messages the classifier flags as angry/urgent sentiment.
- PII handling: customer phone numbers/addresses are stored per-tenant, never used to train shared models, and excluded from cross-tenant analytics.

### 2.5 Escalation / Human-in-the-Loop Layer

This is a product feature, not just an error path (Doc 1, Section 7). When the graph decides to escalate, it still produces a drafted reply and a one-line reason ("customer is asking for a 20% discount — outside auto-approve limit"), then notifies the owner through their preferred channel (push notification in the dashboard app, or a WhatsApp message to the owner's own number, configurable). The owner can approve, edit, or write their own reply from their phone; the thread is marked "owner is handling" so the agent doesn't reply again until the owner responds or a timeout re-engages it.

### 2.6 Integration Layer

- Storefront connectors (Phase 3+, Doc 3): Salla and Zid (popular MENA storefront platforms) and Shopify, for live order-status and stock lookups via their APIs.
- Spreadsheet fallback: many sellers track orders in a Google Sheet or Excel file — support a simple, low-friction sync for V1 so integration is never a blocker to onboarding.

### 2.7 Observability Layer

- Structured tracing of every graph run (which nodes fired, which model was used, latency, cost) — via LangGraph's built-in tracing/LangSmith or an equivalent.
- Conversation-level analytics surfaced to the seller: messages handled, auto-resolution rate, escalations, response time.
- A running evaluation set of real (anonymized) Jordanian DM conversations to regression-test quality as prompts/models change.

### 2.8 Multi-tenancy & Admin Layer

- Business onboarding wizard: connect WhatsApp/Instagram/Facebook via Meta's embedded signup flow, upload/paste catalog, set brand voice and escalation preferences.
- Per-tenant data isolation at the database level (Section 7).
- Billing/subscription management tied to the pricing tiers in Doc 5.

## 3. LangGraph Node-by-Node Design

The core reasoning pipeline is a LangGraph StateGraph. Below is the node sequence for handling one inbound customer message; conditional edges route around nodes when they aren't needed (e.g. a clear FAQ skips the tool-calling loop entirely).

### 3.1 Graph flow (textual diagram)

```
ingest_message → load_context → classify_intent
   ↳ [risk-flagged?] ──yes──→ escalate_to_owner → update_memory → end
   ↳ no → retrieve_knowledge → generate_response → self_check
        ↳ [needs a tool / more data?] ──yes──→ (loop back to retrieve_knowledge)
        ↳ [low confidence / fails self-check?] ──yes──→ escalate_to_owner → update_memory → end
        ↳ [passes] ──→ send_reply → update_memory → end
```

### 3.2 Node reference table

| Node | Purpose | Model / tool used | Key output |
|---|---|---|---|
| ingest_message | Normalize the inbound message and attach metadata (channel, customer ID, timestamp, message type). | None (deterministic code) | Normalized message object |
| load_context | Pull recent conversation history and the customer's long-term profile from memory. | Database read | Conversation state populated |
| classify_intent | Categorize the message (price/availability question, order status, complaint, price negotiation, spam/irrelevant, other) and score urgency/sentiment. | Claude Haiku (small, fast, cheap call) | Intent label + confidence + sentiment score |
| risk gate (conditional edge) | Route straight to escalation for hard-coded risk categories (refund, legal, competitor mention, strongly negative sentiment) regardless of downstream confidence. | Rule engine on classifier output | Route decision |
| retrieve_knowledge | Hybrid RAG: vector search over the tenant's knowledge base + structured catalog/order lookups (tool calls). | Embedding model + vector search; tool calls for live order/stock data | Retrieved context bundle with source references |
| generate_response | Draft a reply grounded in retrieved context, in the business's brand voice and the customer's language/dialect. | Claude Haiku by default; routes to Claude Sonnet for longer/more ambiguous threads or when classify_intent confidence is mid-range | Draft reply text + cited sources |
| self_check | Verify every factual claim in the draft is supported by retrieved context; check tone; flag if a tool call is still needed. | Claude Haiku, structured/JSON output | Pass/fail + reason, or a request to loop back for more data |
| confidence router (conditional edge) | Decide: send automatically, loop back for more retrieval, or escalate. | Rule engine on self_check output | Route decision |
| send_reply | Dispatch the approved reply via the correct channel API, respecting each platform's messaging-window rules (Doc 5, Section 3). | Channel API call | Delivery confirmation |
| escalate_to_owner | Package the thread summary + drafted reply + reason, notify the owner, mark the thread as owner-handled, and pause auto-replies until the owner acts or a timeout elapses. | Notification service | Escalation record |
| update_memory | Persist the turn, update the customer profile, update analytics counters. | Database write | Updated state, closes the run |

### 3.3 Model routing logic

A cheap/fast model handles the large majority of turns; a stronger model is reserved for the minority that need it. This keeps quality high where it matters and cost low everywhere else (full cost math in Doc 5, Section 3).

- Claude Haiku (4.5): classification, retrieval-grounded drafting for clear-cut FAQ/price/availability questions, self-check — the default path for an estimated 80–90% of turns.
- Claude Sonnet (5): escalated to when classify_intent confidence is mid-range, the conversation is long/ambiguous, or self_check requests a retry — an estimated 10–20% of turns.
- Prompt caching: the system prompt, brand-voice profile, and static policy text are cached per business so repeated turns in the same conversation don't re-bill that context at full price (Doc 5, Section 3).

## 4. Shared Graph State

A single typed state object flows through every node. Simplified shape:

```
tenant_id, channel, customer_id, thread_id
message: { text, media_refs, received_at }
conversation_history: [ recent turns ]
customer_profile: { past_orders, preferences, prior_escalations }
intent: { label, confidence, sentiment }
retrieved_context: [ { source, snippet, score } ]
draft_reply: { text, cited_sources, model_used }
self_check: { passed, reason }
route: 'send' | 'escalate' | 'retry'
escalation: { reason, drafted_reply, notified_at, resolved_by }
```

*This state is checkpointed after every node so a crash or restart resumes mid-conversation rather than losing context — LangGraph's checkpointer handles this natively.*

## 5. Data Model

| Table | Key fields | Notes |
|---|---|---|
| businesses (tenants) | id, name, channels_connected, plan_tier, brand_voice_config, escalation_rules | One row per paying customer. |
| knowledge_documents | id, business_id, type (product/policy/faq), content, embedding_vector, updated_at | Source of truth for RAG retrieval; re-embedded on update. |
| conversations | id, business_id, channel, customer_id, status (auto/owner-handled/closed) | One per customer thread. |
| messages | id, conversation_id, direction, text, intent_label, model_used, created_at | Full audit log of every inbound/outbound message. |
| customers | id, business_id, channel_handle, profile_data, order_history_ref | Long-term memory per customer, scoped to one business. |
| escalations | id, conversation_id, reason, drafted_reply, resolved_by, resolution_time | Feeds both the owner-facing UI and the correction/learning loop. |
| subscriptions | business_id, tier, message_usage_current_period, billing_status | Drives the pricing/overage logic in Doc 5. |

## 6. Recommended Tech Stack

| Component | Recommendation | Why |
|---|---|---|
| Orchestration | LangGraph (Python) | Explicit graph control over routing/escalation logic — a plain prompt chain can't express "escalate here, retry there" as cleanly, and LangGraph's checkpointer gives durable conversation state for free. |
| LLM provider | Anthropic Claude (Haiku 4.5 + Sonnet 5, routed per Section 3.3) | Strong Arabic/dialect handling, competitive pricing, prompt caching support that materially reduces cost for repeated-context conversations (Doc 5). |
| Embeddings / vector search | pgvector extension on the same managed Postgres instance | At this scale (a few hundred to few thousand knowledge chunks per tenant) a dedicated vector database like Pinecone adds cost and operational surface without a performance need; pgvector keeps everything in one database. |
| Primary database | Managed Postgres (e.g. Supabase or Neon) | Relational data (tenants, conversations, billing) plus vector search in one place; generous free/low tiers suit early-stage cost control. |
| Queue / task runner | Redis-backed queue (e.g. Celery or a lightweight equivalent) | Buffers webhook bursts and retries without dropping messages. |
| Hosting | Container-based hosting (e.g. Fly.io, Render, or AWS Fargate) | Simple deploys, scales down to near-zero cost at low usage, scales up without a rewrite. |
| Observability | LangGraph/LangSmith tracing or an equivalent OpenTelemetry setup | Node-level tracing is essential for debugging escalation logic and tracking per-conversation cost. |
| Owner-facing app | Web dashboard (responsive) + WhatsApp notifications for escalations | Owners live in WhatsApp already; meet them there for the approval flow rather than requiring an app switch. |

## 7. Security & Tenant Isolation

- Row-level isolation: every table keyed by business_id, enforced at the database/query layer (e.g. Postgres row-level security) so one tenant's data can never leak into another's retrieval or generation.
- Secrets (Meta access tokens, API keys) stored per-tenant in a secrets manager, never in application code or logs.
- Customer PII (phone numbers, addresses) encrypted at rest; excluded from any shared/aggregate model training or cross-tenant analytics.
- Compliance with Meta's WhatsApp Business Platform and Messenger Platform policies (message-window rules, opt-in requirements, prohibited content categories) enforced in the send_reply node before dispatch.
- Jordan's Personal Data Protection Law (and any applicable regional data-residency expectations) reviewed as part of the legal checklist in Doc 3.

## 8. Example Walkthrough

A customer messages a fashion seller on Instagram: "3ndkom ha l fustan be size M? w kam el se3er?" ("Do you have this dress in size M? And what's the price?")

1. `ingest_message` normalizes the DM, attaching channel=instagram and the customer's IG-scoped ID.
2. `load_context` finds this is an existing customer with one prior order.
3. `classify_intent` labels it product_availability_price, confidence high, sentiment neutral.
4. Risk gate passes through (not a risk category).
5. `retrieve_knowledge` finds the product in the catalog: size M, in stock, 24 JOD.
6. `generate_response` (Haiku) drafts a reply in the same Jordanian/English mix: "أهلين! أيوه متوفر مقاس M 🙂 السعر 24 دينار، بدنا نرسله عالعنوان المعتاد؟"
7. `self_check` confirms the price and stock claim both trace to the retrieved catalog entry — passes.
8. Confidence router sends automatically.
9. `send_reply` dispatches via the Instagram Messaging API.
10. `update_memory` logs the turn and updates the customer's profile.

Total elapsed time: a few seconds, no owner involvement. Compare to a customer asking for a 30% discount "just this once" — that hits the risk gate on price negotiation and routes straight to `escalate_to_owner` with a drafted, policy-compliant counter-offer for the owner to approve or edit.

---

*Next document: 03 — Development & Deployment Roadmap.*
