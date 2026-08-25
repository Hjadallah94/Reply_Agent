# Reply Agent — Planning Docs

Pre-build planning set for the Reply Agent: an autonomous LangGraph agent that replies to Instagram, WhatsApp, and Facebook messages for solo/small online sellers in Jordan. This is the first product under the broader "Meta Agent" project.

Each document exists in two formats:
- `md/` — plain Markdown, meant to be read by Claude Code / used as project context when you start building.
- `docx/` — the same content as formatted Word documents, meant for reading/reviewing/sharing outside the editor.

## Documents

1. **01_Product_Vision_PRD** — the problem, target customer, MVP scope, competitive landscape, differentiation, and key risks.
2. **02_System_Architecture** — the 9 architecture layers, the LangGraph node-by-node design, shared state schema, data model, and recommended tech stack.
3. **03_Development_Deployment_Roadmap** — the 6-phase build plan, Meta app review process, testing strategy, deployment plan, and legal/compliance checklist.
4. **04_GoToMarket_Marketing** — positioning, acquisition channels for the Jordan market, launch sequencing, and retention.
5. **05_Pricing_Unit_Economics** — the pricing tiers and the full cost model behind them (LLM cost, Meta fees, payment processing, infra), margins, and break-even.

## Status

Phase 0 (foundations), Phase 1 (single-channel WhatsApp MVP), and Phase 2 (real catalog
ingestion, Instagram + Messenger channels, spreadsheet order-status sync) are built. Phase 3
(owner dashboard: escalation resolution, history export) is done. Phase 4 (billing &
self-serve onboarding) has usage metering built, and WhatsApp Embedded Signup built but not
yet live-tested (see below) — see `03_Development_Deployment_Roadmap.md`, Section 1, for the
full phase plan.

Pricing, message-volume assumptions, and some architectural choices (e.g. LLM provider routing) are stated as best-available hypotheses based on external research current as of August 2026 — they're meant to be validated against real usage during the pilot (Doc 3, Phase 5), not treated as final.

## Running the code

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker.

```bash
uv sync                                # install dependencies
cp .env.example .env                   # fill in ANTHROPIC_API_KEY, VOYAGE_API_KEY, Meta creds
docker compose up -d postgres redis    # Postgres+pgvector on :5433, Redis on :6380
uv run alembic upgrade head              # create the application schema
uv run python scripts/setup_checkpointer.py  # create the LangGraph checkpointer's own tables
uv run python scripts/seed_business.py   # seed the demo business + example knowledge base
uv run pytest tests/                     # unit + integration tests (no external API calls)
```

To run the full pipeline locally:

```bash
uv run uvicorn reply_agent.api.app:app --reload   # webhook receiver
uv run python scripts/run_worker.py               # graph worker (needs ANTHROPIC_API_KEY, VOYAGE_API_KEY)
```

Use `scripts/run_worker.py`, not the bare `rq worker inbound_messages` CLI — the CLI reads
`REDIS_URL` from the OS environment rather than `.env` (so it silently connects to the wrong
Redis), and its default fork-based worker crashes immediately on Windows (`os.fork()` doesn't
exist there). The script fixes both: it uses our own settings for the Redis connection and
picks a non-forking worker class on Windows.

```bash
```

To run the Jordanian Arabic/English evaluation set (`eval/conversations/`) against the real
pipeline — costs real Anthropic + Voyage API calls, set `META_DRY_RUN=true` first so it
doesn't try to send real WhatsApp messages:

```bash
uv run python eval/run_eval.py
```

See `src/reply_agent/` for the LangGraph pipeline (Doc 2, Section 3) and `src/reply_agent/db/models.py`
for the data model (Doc 2, Section 5).

### Real catalog ingestion (Doc 3 Phase 2)

Replaces the hand-typed YAML knowledge base with a real upload: a single `.xlsx` workbook with
up to three sheets — `Products` (name, price_jod required; description, stock_status, variants
optional), `Policies` (topic, content), `FAQs` (question, answer). A product's `variants` cell
uses `label:status; label:status`, e.g. `size S:in_stock; size L:out_of_stock`.

```bash
uv run python scripts/ingest_catalog.py --file catalog.xlsx --business "Rose Abaya House"
```

Or via the API (same parsing/embedding logic — this is what Phase 3's dashboard will call):

```bash
curl -X POST http://localhost:8000/businesses/{business_id}/knowledge/upload -F file=@catalog.xlsx
```

Bad individual rows are skipped and reported back, not fatal to the rest of the sheet; a
missing required column in a present sheet is a hard error for that sheet.

### Instagram + Messenger channels (Doc 3 Phase 2)

Both webhooks (`/webhooks/instagram`, `/webhooks/messenger`) normalize into the same
`NormalizedInboundEvent` shape WhatsApp already used, so `worker.py` and the LangGraph pipeline
don't know or care which app a message came from — genuinely one brain, three channels. Needs
`META_PAGE_ACCESS_TOKEN` and `META_WEBHOOK_VERIFY_TOKEN` in `.env` (both channels are accessed
via the connected Facebook Page's token, unlike WhatsApp's phone-number-scoped one). A
business's `channels_connected` JSON needs an `"instagram"`/`"messenger"` key with a `page_id`
for inbound routing to find it — not yet verified against a live payload (no Instagram/Messenger
product set up in the Meta app yet), same caveat as WhatsApp had before Phase 1's live test.

### Spreadsheet order-status sync (Doc 2 Section 2.6)

A single `.xlsx` file with an `Orders` sheet — `order_reference`, `customer_phone`, `status`
required; `customer_name`, `items_summary`, `order_date` optional. Phone numbers are normalized
(`orders/phone.py`) to match how WhatsApp sends them (handles a local `07...` format, a `+`/`00`
prefix, and Excel's habit of stripping a phone column's leading zero when it's stored as a
number). A full replace per sync — re-run whenever the seller's order sheet changes.

```bash
uv run python scripts/sync_orders.py --file orders.xlsx --business "Rose Abaya House"
# or: curl -X POST http://localhost:8000/businesses/{business_id}/orders/upload -F file=@orders.xlsx
```

Once synced, `order_status` questions are no longer an automatic capability-gap escalation —
`retrieve_knowledge` looks up the customer's order by phone number (WhatsApp only; Instagram/
Messenger customers aren't phone-identified) and, if found, grounds a normal auto-sendable
reply. No match still escalates, same as before this existed.

### Owner dashboard (Doc 3 Phase 3, first slice)

Server-rendered (Jinja2, no separate frontend build) at `/dashboard` → pick a business → see
escalations that need a reply, with the drafted reply pre-filled into an editable box. Sending
reuses the exact same channel-dispatch code (`graph/nodes/send_reply.py`) a real auto-send would
go through, then logs the outbound message and resumes the conversation to `auto`. **No auth** —
this is an internal MVP tool, not safe to expose publicly as-is.

```bash
uv run uvicorn reply_agent.api.app:app --reload
# then open http://localhost:8000/dashboard
```

Each business's dashboard also has a "Download as Excel" link
(`/businesses/{business_id}/dashboard/export`) — every message across every conversation for
that business, one row per message, sorted by customer then time: who sent it, the channel, the
text, the classified intent, whether Claude or the owner handled it, and the conversation's
status. This is the standing history export for a seller who has no CRM (Doc 1 explicitly defers
real CRM/ERP integrations to a future paid tier); it reads the same `messages` table the
dashboard and the graph itself already write to, so there's nothing new to keep in sync.

### Usage metering (Doc 5 Section 2, Doc 3 Phase 4 first slice)

Every genuinely new inbound customer message (`billing/usage.py`, wired into
`graph/nodes/load_context.py` at the same idempotent insert that already dedupes Meta's webhook
retries) increments that business's `Subscription.message_usage_current_period`, auto-creating
the subscription row on first use and rolling it over to a fresh 30-day period once the old one
lapses. Tier caps and overage rates (`billing/tiers.py`) are Doc 5 Section 2's numbers as code —
**this is a soft cap**: a business stays fully live past its cap, since Doc 5 prices overage per
message rather than cutting the product off. The business dashboard shows a usage bar against the
cap; deciding to actually *bill* for overage is the separate payment-collection piece of Phase 4,
not yet built.

### WhatsApp Embedded Signup (Doc 3 Phase 4, self-serve onboarding)

Lets a business connect its own WhatsApp number from `/onboarding/whatsapp?business_id={id}`
(linked from that business's dashboard page) instead of us doing it manually — Meta's own JS SDK
popup flow (`templates/onboarding_whatsapp.html`), with the server-side completion
(`onboarding/whatsapp_signup.py` + `api/onboarding.py`) exchanging the code, subscribing our app
to the customer's WABA webhooks, and registering their phone number for Cloud API use.

Building this required a prerequisite fix: `send_text_message` was hardcoded to one global phone
number (fine for a single demo business); it now takes the sending business's own
`phone_number_id` from `channels_connected`, while the access token stays one shared value — our
own Tech Provider System User token, which Meta grants access to each customer's WABA as they
complete this flow, rather than a separate token per business.

**Two one-time manual steps in the Meta App Dashboard, not automatable:**
1. **Business Settings → System Users** — create one (or use an existing one), generate a
   long-lived access token with `whatsapp_business_management` + `whatsapp_business_messaging`,
   set it as `WHATSAPP_ACCESS_TOKEN`.
2. **App Dashboard → Facebook Login for Business → Configurations** — create one using the
   *WhatsApp Embedded Signup* template, set its ID as `META_EMBEDDED_SIGNUP_CONFIG_ID`.

**Not yet live-tested** — it can't be until both of the above exist and App Review clears for
`whatsapp_business_management`/`whatsapp_business_messaging`. Built and verified as far as
possible without that: unit tests mock Meta's HTTP responses for the three server-side calls,
integration tests cover the callback saving `channels_connected` correctly, and the page itself
renders correctly (confirmed live) including its "not configured" state. The actual Facebook
Login popup and its postMessage payload shape have not been exercised against Meta's real
servers — re-verify against Meta's current docs before relying on it, same caveat every other
Meta integration in this project carried before its own first live test.
