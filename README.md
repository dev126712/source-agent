# sourcing-agent

AI agent backend that finds local products worth reselling on Amazon. Takes a
product (typed, scanned, or from a bulk CSV), researches it via a LangGraph
agent, and returns a buy/avoid verdict with profit math and an auditable
evidence trail.

## Stack

- FastAPI + async SQLAlchemy 2.0 + PostgreSQL (`asyncpg`)
- LangGraph for the agent (`StateGraph`)
- Celery + Redis for the bulk research queue
- `uv` for packaging
- Provider-agnostic LLM factory (Anthropic / OpenAI / Groq / Ollama) via `DEPLOYMENT_ENV`

## Architecture

Three input channels (photo/barcode, text, CSV) normalize into one canonical
`ProductCandidate`. Three sourcing modes (retail arbitrage, wholesale, artisan)
are handled by a single graph with a conditional route in the middle:

```
identify_product -> fetch_amazon_data -> [route_by_mode]
                                             |-> retail_arb_research  --\
                                             |-> wholesale_research   ---> compute_profit -> score_and_report -> END
                                             |-> artisan_research    --/
```

Everything before the route is shared; everything after converges back to
shared scoring. The LLM is used only where judgment is needed (identification,
research, final synthesis). Amazon data pulls and profit math are deterministic
by design — a wrong margin that looks authoritative is worse than none.

## Layout

    app/
      core/        config, enums, logging
      db/          async engine + session
      models/      SQLAlchemy: candidate, report, run
      schemas/     Pydantic input contracts
      adapters/    input adapters (CSV implemented)
      agent/       LangGraph state, graph, nodes/
      providers/   llm_factory, amazon data provider
      services/    fee ruleset
      api/routes/  FastAPI endpoints
      workers/     Celery tasks (scheduler TODO)

## Running

    uv sync
    uv run uvicorn app.main:app --reload

Endpoints:
- `GET  /health`
- `POST /api/v1/candidates/evaluate` — single candidate, synchronous
- `POST /api/v1/candidates/csv/validate` — CSV phase 1 (validate + preview)
- `POST /api/v1/discovery/run` — on-demand location discovery (returns fresh candidates)
- `POST /api/v1/discovery/schedule` — premium-gated recurring discovery (stub)

## Location discovery mode

A prospecting loop that starts from a *location* instead of a known product:

    seed -> expand_categories -> discover_stores -> fetch_products
         -> filter_seen (TTL memory) -> ProductCandidates -> evaluation graph

Key behaviours:
- Loose seed ("outdoor gear") or none; `expand_categories` widens it into
  concrete categories. `exploration` (0..1) controls how far it wanders — low
  stays near the seed, high draws widely from the category pool.
- `seen_products` table gives a per-user "never repeat" guarantee with a TTL
  escape valve (default 90 days) so a province is never permanently exhausted.
- Real retailer data sits behind a `RetailerAdapter` (the PostBridge
  PlatformAdapter pattern). Most retailer product/inventory APIs are gated
  behind partner approval, so launch with the mock + one approved adapter and
  add others behind the same interface. Province-scoped, same-country, compared
  against the home Amazon marketplace.
- On-demand for everyone; scheduled/background discovery is premium-gated and
  runs the same `run_discovery` code path via Celery beat (TODO).

## Provider config

`resolved_llm_provider` defaults to Groq in dev and Anthropic in prod; override
with `LLM_PROVIDER`. Amazon data defaults to a deterministic mock so the graph
runs without credentials — set `AMAZON_PROVIDER=keepa` and `KEEPA_API_KEY` for
real data.

## Status / TODO

- [x] Canonical schema, enums, DB models with dedup + SKIP-LOCKED indexes
- [x] LangGraph graph with conditional routing + abort path (runs end-to-end)
- [x] CSV adapter: header mapping, delimiter sniffing, dedup, per-row rejects
- [x] Deterministic profit math + rules-based verdict
- [ ] Real `web_search`/`web_fetch` tool bindings in research nodes
- [ ] LLM synthesis in `score_and_report` (deterministic fallback in place)
- [ ] Keepa / SP-API provider implementations
- [ ] Celery scheduler with `FOR UPDATE SKIP LOCKED` claiming
- [ ] Alembic migrations
- [ ] Photo/barcode input adapters
