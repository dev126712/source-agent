# CLAUDE.md

Context bridge for Claude Code sessions on this repo. Read this first.

## What this is

An AI-agent backend that finds local products worth reselling on Amazon. Two
directions of work:

- **Evaluation** — start from a *known* product (typed / scanned / CSV), research
  it, return a buy/avoid verdict with profit math and an auditable evidence trail.
- **Discovery** — start from a *location*, discover stores → products → filter
  against per-user "seen" memory → hand fresh candidates to the evaluation graph.

Everything funnels through one canonical `ProductCandidateIn` so all input paths
share the same downstream pipeline.

## Stack & conventions (match these — they are deliberate)

- Python 3.12, FastAPI, async SQLAlchemy 2.0 (`Mapped[...]` / `mapped_column`), Postgres (`asyncpg`).
- `uv` for packaging. In Dockerfiles `uv` replaces pip. Use `uv sync` / `uv run`.
- LangGraph for the agent (`StateGraph`).
- Celery + Redis for async/bulk work (not yet wired — see TODOs).
- Provider-agnostic LLM via `app/providers/llm_factory.py::get_llm()`. Provider is
  chosen by `DEPLOYMENT_ENV` (Groq in dev, Anthropic in prod) unless `LLM_PROVIDER`
  overrides. Never import a specific LLM SDK outside `llm_factory.py`.
- `bcrypt` used directly (not passlib) when auth lands. JWT in httponly cookies
  (ApplyOps pattern) — auth is currently stubbed, see `discovery.py`.
- `HealthCheckFilter` suppresses `/health` access-log noise (`app/core/logging.py`).
- Prefer prose-free, deterministic code where numbers matter (see the LLM boundary rule).

## Architecture map

```
input adapters ─┐
 (photo/barcode │
  text / csv /  ├─► ProductCandidateIn ─► LangGraph evaluation ─► SourcingReport
  discovery)    │      (canonical)          (app/agent/graph.py)
────────────────┘

discovery loop (app/services/discovery.py):
  seed ─► expand_categories ─► discover_stores ─► fetch_products
       ─► filter_seen (TTL) ─► ProductCandidateIn[] ─► (feed evaluation graph)
```

### Evaluation graph (`app/agent/graph.py`)
Linear shared section, one conditional fan-out by sourcing mode, converge back:

```
identify_product → fetch_amazon_data → [route_by_mode]
                       ├→ retail_arb_research ─┐
                       ├→ wholesale_research  ─┼→ compute_profit → score_and_report → END
                       └→ artisan_research    ─┘
```
`route_by_mode` also has an abort shortcut straight to `score_and_report` when a
candidate can't be identified. State is `app/agent/state.py::SourcingState`
(TypedDict); `findings` and `sources` use `Annotated[list, add]` so research nodes
*accumulate* rather than overwrite.

## Non-obvious rules (violating these breaks the design)

1. **LLM boundary.** The LLM touches only identification, mode-specific research,
   and final synthesis. `fetch_amazon_data`, the fee ruleset, and `compute_profit`
   are deterministic Python. A wrong margin that looks authoritative is worse than
   no margin. Do not let an LLM compute money.
2. **Adapter pattern everywhere external.** Retailers (`app/adapters/retailers.py`),
   Amazon data (`app/providers/amazon.py`), LLMs (`llm_factory.py`) all sit behind
   an interface with a mock impl. Add new providers by adding an adapter, never by
   branching in call sites. This mirrors PostBridge's `PlatformAdapter`.
3. **Lazy DB engine.** `app/db/session.py` builds the engine via `get_engine()`
   (lru_cached), NOT at import time. Keep it that way — it's what lets models and
   services import/test without a live DB driver. Don't add module-level
   `create_async_engine`.
4. **Canonical candidate is input-only.** `ProductCandidateIn` holds identity +
   source context. Researched data (BSR, profit, verdict) lives in `SourcingReport`,
   linked by `candidate_id`. Don't add researched fields to the candidate.
5. **`Decimal` for all money.** Never float. Prices, fees, margins.
6. **Reports must stay auditable.** `score_and_report` should cite the specific
   `findings`/`sources` in state. Keep the evidence trail intact end to end.

## Product decisions already made (don't relitigate without reason)

- Sourcing modes: retail arbitrage, wholesale, artisan — one graph, conditional route.
- Input channels: photo, barcode, text, csv, discovery.
- CSV is two-phase: sync validate/preview, then async enqueue (Phase 2 not built).
  Never drop a row silently — rejects carry a reason.
- Discovery seed is *loose*: user gives a vibe or nothing; `expand_categories`
  fills the rest. `exploration` (0..1) controls wander (low = near seed via
  adjacency, high = wide pool draw). Looseness lives in `seed_expansion.py`.
- "Never repeat a product" = per-user `seen_products` table WITH a TTL escape
  valve (default 90d, `DEFAULT_TTL_DAYS`). Filter excludes seen-and-unexpired only,
  so a location is never permanently exhausted. Upsert refreshes TTL on recurrence.
- Cross-region scope: **province only, same country, no currency conversion.**
  Comparison always against the home Amazon marketplace. Region field is kept
  general so state/country is a later config change, not a rewrite.
- Scheduled discovery is **premium-gated** (`/discovery/schedule` → 402 for free).
  On-demand is open. Both must run the SAME `run_discovery` code path.
- Amazon data: gated APIs (SP-API / Keepa). Retailer inventory APIs are also
  partner-gated and explicitly not for competitor price analysis — so launch is
  mock + one approved adapter, others roll out behind `RetailerAdapter`.

## Layout

```
app/
  core/        config (env-driven provider switch), enums, logging
  db/          lazy async engine + session
  models/      SQLAlchemy: candidate, report, discovery (SeenProduct, DiscoveryRun)
  schemas/     Pydantic input contracts (ProductCandidateIn + validator)
  adapters/    csv_adapter, retailers (RetailerAdapter + MockRetailer)
  agent/       state, graph, nodes/{shared,research,scoring}
  providers/   llm_factory, amazon (AmazonDataProvider + Mock/Keepa)
  services/    fees, seen_memory, seed_expansion, discovery (orchestrator)
  api/routes/  candidates, discovery
  workers/     (empty — Celery tasks go here)
tests/         (empty — no tests written yet)
```

## Running / checking

```bash
uv sync
uv run uvicorn app.main:app --reload
# Offline sanity without a DB (engine is lazy): import the app, hit pure services.
PYTHONPATH=. python -c "from app.main import app; print('ok')"
```
Amazon + retailer providers default to deterministic mocks, so the whole system
runs with zero external credentials. Set `AMAZON_PROVIDER=keepa` + `KEEPA_API_KEY`
for real Amazon data; register real retailer adapters in `retailers.py::_REGISTRY`.

## Open work (TODO markers live in code; grep `TODO`)

High-leverage, roughly in order:

1. **Real research loop** — `app/agent/nodes/research.py::wholesale_research` is the
   heaviest. Bind `web_search` + `web_fetch`, run a ReAct loop up to
   `settings.max_research_iterations`, append each supplier as a `Finding`.
   `retail_arb_research` / `artisan_research` are lighter but same shape.
2. **LLM synthesis** — `scoring.py::score_and_report` currently uses a deterministic
   fallback. Wire `get_llm()` to produce reasoning that cites findings/sources.
   Keep the rules-based verdict as the floor.
3. **Discovery → evaluation auto-chain** — `/discovery/run` returns candidates but
   does NOT yet evaluate them. Chain each `ProductCandidateIn` through
   `get_compiled_graph().ainvoke(...)`, ideally via Celery for volume.
4. **Celery** — nothing in `app/workers/` yet. Needed for: CSV Phase 2 enqueue
   (bulk insert candidates as `pending`, claim in chunks with
   `FOR UPDATE SKIP LOCKED` — serviceflow-marketing pattern), and premium scheduled
   discovery (beat → persisted schedule row → `run_discovery(triggered_by="scheduled")`).
5. **Amazon provider** — `providers/amazon.py::KeepaProvider.lookup` is `NotImplementedError`.
6. **Real RetailerAdapter** — implement one approved retailer; register in `_REGISTRY`.
7. **Fee ruleset** — `services/fees.py` values are illustrative placeholders. Verify
   against Amazon's published referral/FBA schedules before production. Wire real
   size/weight tiers (currently `_default`).
8. **Alembic** — no migrations yet. Models exist; generate the initial revision.
9. **Auth** — `discovery.py::current_user_id` / `current_tier` are hardcoded stubs.
   Replace with JWT (httponly cookie), and back `current_tier` with a real
   subscription lookup.
10. **Tests** — `tests/` is empty. Priorities: `seed_expansion` looseness,
    `seen_memory.filter_unseen`, the graph's abort path, CSV rejects/dedup.

## Gotchas

- The graph is compiled without a checkpointer. Add a Postgres checkpointer in
  `graph.py::get_compiled_graph` so failed research runs resume mid-graph and CSV
  batch progress is trackable.
- `DiscoveryRun.categories` / `exploration` are stored as strings — tighten types
  when you add the persistence path (the run row isn't actually written yet).
- Discovery currently persists `seen_products` (via `record_seen`) but does NOT yet
  write a `DiscoveryRun` row — add that when wiring the real DB session in the route.
