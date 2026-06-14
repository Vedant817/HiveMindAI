# HiveMindAI

HiveMindAI is a self-managing agent swarm that turns business goals and meeting transcripts into
coordinated, validated, observable execution. Instead of acting like a single chatbot, HiveMindAI
uses multiple specialist agents — Planner, PM, Executor, Validator, Meeting, Debate, Comms,
Knowledge, Reflection, and Summary — connected through a dependency-aware task DAG with validation
checkpoints, confidence-based human approval gates, organizational memory, and workplace
communication fallbacks.

The system starts with a high-level goal or meeting transcript. The Meeting Agent extracts Jira-ready
tickets; the PM/Planner Agent converts goals into a dependency-aware task DAG. Executor Agents
generate real task artefacts, Validator Agents verify them, and a confidence-based Human-in-the-Loop
gate pauses low-confidence or risky tasks for Teams-based approval. A Knowledge Agent stores
decisions and relations with graph traversal, while Reflection and Summary Agents produce improvement
notes and executive summaries.

Decision-making is augmented by a multi-persona Debate Orchestrator that scores proposals across
scalability, cost, and maintainability. The system runs a FastAPI dashboard with real-time SSE
streaming, ingestion endpoints for meeting files and transcripts, signed approval tokens via HMAC,
Azure Functions for nightly summaries, and a full local-first fallback stack requiring no paid
services. Every agent, integration, and persistence layer degrades gracefully through deterministic
local fallbacks when cloud credentials are absent.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Language** | Python 3.10–3.13 |
| **Web Framework** | FastAPI, Uvicorn |
| **LLM Providers** | OpenRouter (OpenAI SDK), Azure OpenAI, deterministic local fallbacks |
| **Orchestration** | pyautogen (AutoGen GroupChat), custom SwarmRuntime |
| **Databases** | MongoDB Atlas (pymongo), Azure Cosmos DB, local JSON fallback |
| **Caching / Queue** | Upstash Redis (redis-py), Azure Service Bus, in-memory fallback |
| **Search** | Azure AI Search, keyword-based local fallback |
| **Storage** | Azure Blob Storage, local filesystem workspace |
| **Messaging** | Microsoft Teams webhooks (adaptive cards), Slack webhooks |
| **Project Mgmt** | Jira REST API, Azure DevOps REST API |
| **Email** | Azure Communication Services Email |
| **Auth / Security** | HMAC-signed approval tokens (hmac, hashlib), API key header |
| **Validation** | Pydantic v2, custom payload bounds |
| **Serverless** | Azure Functions (nightly summary sender) |
| **Infrastructure** | Docker, docker-compose |
| **Testing / Lint** | pytest, pytest-asyncio, ruff |
| **HTTP Client** | httpx, httpcore |

The implementation is intentionally credential-safe:

- Without Azure, Jira, Slack, or Teams secrets, it runs in local fallback mode.
- With environment variables from `.env.example`, the same interfaces call the configured services.
- Set `SWARM_STRICT_INTEGRATIONS=true` to make missing production integrations fail immediately.
- Local state is written under `local_state/`; generated task artifacts are written under `workspace/`.
- Public/shared deployments can set `HIVEMIND_API_KEY` and `APP_SECRET` to protect mutating API routes and sign Teams approval links.

## Quick Start

Free/local mode with OpenRouter:

```powershell
.\run-local-free.ps1 -Install
```

To use a free OpenRouter model, pass your key:

```powershell
.\run-local-free.ps1 -Install -OpenRouterApiKey YOUR_OPENROUTER_KEY
```

With free cloud persistence and queue services:

```powershell
.\run-local-free.ps1 -Install -OpenRouterApiKey YOUR_OPENROUTER_KEY -MongoDbUri "YOUR_MONGODB_URI" -RedisUrl "YOUR_UPSTASH_REDIS_URL"
```

Recommended free model:

```text
qwen/qwen3-coder:free
```

If that endpoint is unavailable, use:

```powershell
.\run-local-free.ps1 -Model openrouter/free
```

The app still runs without an OpenRouter key by using deterministic local fallbacks.

Free cloud services for the hackathon demo:

```env
APP_STACK=free
OPENROUTER_API_KEY=your_openrouter_key
MONGODB_URI=your_mongodb_atlas_connection_string
MONGODB_DATABASE=hivemindai
REDIS_URL=your_upstash_rediss_url
```

- OpenRouter: model calls.
- MongoDB Atlas free tier: persistent task DAGs, knowledge, reflection history.
- Upstash Redis free tier: queue/cache/pub-sub style state.
- Jira, Slack, Teams, Azure services: optional; the app uses local visual fallbacks when they are not configured.

General runner:

```powershell
.\run.ps1 -Install
```

Then open:

```text
http://127.0.0.1:8000/
```

After dependencies are installed once, use:

```powershell
.\run.ps1
```

If a previous server is already running and you want a fresh start:

```powershell
.\run.ps1 -Restart
```

For free/local mode:

```powershell
.\run-local-free.ps1 -Restart
```

Alternative manual setup:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python main.py --serve --host 127.0.0.1 --port 8000
```

Open the visual hackathon dashboard:

```text
http://127.0.0.1:8000/
```

For the presentation story, use `PitchGuide.md`.

To verify the real production path before a demo:

```powershell
$env:SWARM_STRICT_INTEGRATIONS="true"
python main.py --check-config
python main.py --verify-config --live-checks
```

Or:

```powershell
.\run.ps1 -CheckConfig
```

For free/local mode:

```powershell
.\run-local-free.ps1 -CheckConfig
```

In free/local mode, `local_test_ready: true` means the dashboard can run locally. `free_model_ready:
true` means OpenRouter is configured and the agents can call the selected free model. `free_stack_ready:
true` means the free cloud stack has OpenRouter, MongoDB Atlas, and Upstash Redis configured.

Useful endpoints:

- `GET /` — Dashboard UI
- `GET /health`
- `GET /config/check`
- `POST /demo/run` — Full pitch demo (swarm + meeting + debate + summary)
- `POST /demo/run/stream` — Same demo as server-sent events (SSE)
- `POST /swarm/run` with `{"goal": "Build payment API"}`
- `POST /ingest/transcript` with `{"transcript": "Action: build the dashboard before Friday", "execute": true}`
- `POST /ingest/meeting` — Upload a meeting file (audio, txt, md, vtt, srt)
- `POST /debate` with `{"question": "Should we use Redis or Service Bus for short-lived state?"}`
- `POST /knowledge` — Store a decision or fix
- `GET /knowledge/search?q=redis`
- `GET /knowledge/{entry_id}/related`
- `POST /approval/{id}/approve` — Resume task after human approval
- `POST /approval/{id}/reject` — Block task after human rejection
- `GET /summary` — Executive project summary
- `GET /config/verify?live=true`
- `GET /demo/defaults`

When `HIVEMIND_API_KEY` is set, mutating endpoints require the `X-Hivemind-Api-Key` header.

## Project Layout

```text
agents/          Planner, PM, Executor, Validator, Meeting, Debate, Comms, Reflection, Summary
api/             FastAPI routes and visual dashboard for ingestion, approvals, demo runs, memory
hitl/            Confidence gate and Teams approval card sender
integrations/    Jira, Slack, Azure DevOps facades with strict production checks
memory/          MongoDB Atlas / Cosmos DB facades with local JSON and keyword local fallbacks
orchestrator/    AutoGen group chat facade and local SwarmRuntime
schemas/         Task DAG and knowledge graph records
shared/          Agent message contract, Redis wrapper, Service Bus wrapper
functions/       Nightly Azure Function summary sender
infra/           Dockerfile and docker-compose local stack
tests/           Deterministic unit and runtime tests
```

## Local Docker

```powershell
Copy-Item .env.example .env
docker compose -f infra/docker-compose.yml up --build
```

## LLM Modes

Set `APP_STACK` in `.env`:

- `free`: OpenRouter + MongoDB Atlas + Upstash Redis readiness checks.
- `local`: deterministic local fallbacks for offline demos.
- `azure`: Azure production readiness checks.

Set `LLM_PROVIDER` in `.env`:

- `openrouter`: free/local testing through OpenRouter.
- `azure`: production Azure OpenAI path.
- `auto`: use OpenRouter if configured, otherwise Azure if configured, otherwise local fallback.
- `none`: always use local deterministic fallback.

Local fallback mode still produces real workspace artifacts (`task_result.json`, `task_report.md`, and
specialized dashboard/API artifacts when relevant). The validator checks these artifacts before marking
work complete.

OpenRouter variables:

```env
APP_STACK=free
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=qwen/qwen3-coder:free
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
MONGODB_URI=your_mongodb_atlas_connection_string
MONGODB_DATABASE=hivemindai
REDIS_URL=your_upstash_rediss_url
```

Azure variables are still supported:

```env
APP_STACK=azure
LLM_PROVIDER=azure
AZURE_OPENAI_KEY=your_key_here
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-02-01
```

## Submission Notes

Generated/runtime artifacts are ignored by git: `.env`, `.venv/`, `local_state/`, `workspace/`,
`screenshots/`, Python cache folders, `.antigravitycli/`, and the reference `symphony/` checkout.
The final project code lives in the app folders plus `config/`, `requirements.txt`, `run.ps1`,
`run.bat`, `run-local-free.ps1`, `run-local-free.bat`, `Readme.md`, and `PitchGuide.md`.

## Notes

The `symphony/` reference emphasizes durable orchestration, isolated workspaces, local policy, and
operator-visible status. HiveMindAI applies those ideas to the Azure/AutoGen swarm plan while keeping
the app runnable before managed infrastructure is provisioned.
