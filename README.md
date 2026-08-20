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

Phase 0 (foundations) and the start of Phase 1 (single-channel WhatsApp MVP) are built — see
`03_Development_Deployment_Roadmap.md`, Section 1, for the full phase plan.

Pricing, message-volume assumptions, and some architectural choices (e.g. LLM provider routing) are stated as best-available hypotheses based on external research current as of August 2026 — they're meant to be validated against real usage during the pilot (Doc 3, Phase 5), not treated as final.

## Running the code

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker.

```bash
uv sync                                # install dependencies
cp .env.example .env                   # fill in ANTHROPIC_API_KEY, VOYAGE_API_KEY, Meta creds
docker compose up -d postgres redis    # Postgres+pgvector on :5433, Redis on :6380
uv run alembic upgrade head            # create the schema
uv run python scripts/seed_business.py # seed the demo business + example knowledge base
uv run pytest tests/                   # unit + integration tests (no external API calls)
```

To run the full pipeline locally:

```bash
uv run uvicorn reply_agent.api.app:app --reload   # webhook receiver
uv run rq worker inbound_messages                 # graph worker (needs ANTHROPIC_API_KEY, VOYAGE_API_KEY)
```

To run the Jordanian Arabic/English evaluation set (`eval/conversations/`) against the real
pipeline — costs real Anthropic + Voyage API calls, set `WHATSAPP_DRY_RUN=true` first so it
doesn't try to send real WhatsApp messages:

```bash
uv run python eval/run_eval.py
```

See `src/reply_agent/` for the LangGraph pipeline (Doc 2, Section 3) and `src/reply_agent/db/models.py`
for the data model (Doc 2, Section 5).
