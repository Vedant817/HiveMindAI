# HiveMindAI Hackathon Pitch Guide

## One-Line Pitch

HiveMindAI turns meetings and business goals into coordinated agent execution, with shared memory,
validation, human approval, workplace updates, and executive reporting.

## Problem

Teams lose time translating discussions into tickets, repeating old decisions, chasing status
updates, and manually checking whether AI-generated work is safe to ship.

## Solution

HiveMindAI is an enterprise agent swarm:

1. Meeting Agent extracts action items and creates Jira-ready tickets.
2. PM Agent breaks the goal into a dependency DAG.
3. Executor and Validator agents complete and check each task.
4. Debate Agent compares multiple technical options.
5. Confidence Gate escalates risky work to a human.
6. Knowledge Agent preserves decisions and fixes.
7. Summary Agent creates a manager-ready project report.

## Demo Flow

1. Start the app:

   ```powershell
   .\run-local-free.ps1 -Install -OpenRouterApiKey YOUR_OPENROUTER_KEY
   ```

   If no OpenRouter key is available, run `.\run-local-free.ps1 -Install`; the demo uses local
   deterministic fallbacks.

2. Open:

   ```text
   http://127.0.0.1:8000/
   ```

3. Click `Run live demo`.

4. Point out the visible results:

   - Health, task, ticket, and agent metrics update immediately.
   - The architecture map shows how work moves through the swarm.
   - The DAG shows the PM Agent's execution plan.
   - Jira-ready tickets are extracted from the meeting transcript.
   - The timeline shows agent messages, status, confidence, and generated artifacts.
   - Meeting tickets are queued and executed by the swarm; risky items pause for approval.
   - The debate panel shows how the swarm validates design choices.
   - The executive summary turns raw execution into manager-readable status.

## What Judges Should Remember

This is not a single chatbot. It is a self-managing work system that plans, executes, validates,
remembers, communicates, and knows when to ask a human.

## Production Switch

Local demo mode is for the pitch. Free model mode uses OpenRouter:

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=qwen/qwen3-coder:free
```

Production mode is enabled by switching `LLM_PROVIDER=azure`, filling Azure/Jira/Slack/Teams keys,
and checking:

```powershell
$env:SWARM_STRICT_INTEGRATIONS="true"
python main.py --check-config
```

For a shared demo, set `HIVEMIND_API_KEY` and `APP_SECRET` so write endpoints are protected and
approval links are signed.

When `production_ready` is true, the same UI runs against real Azure OpenAI, Redis, Service Bus,
Cosmos DB, AI Search, Jira, Slack, Teams, and email. Use `python main.py --verify-config --live-checks`
to run safe live checks against configured providers before presenting.
