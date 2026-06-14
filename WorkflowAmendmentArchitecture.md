# Workflow Amendment Architecture

This document describes the feature for handling prompt changes after a user has already started a workflow.

## Problem

A user may click **Run workflow** and then remember an extra requirement, constraint, or transcript detail while the orchestrator is already planning or executing. The system needs a safe way to accept that new context without silently corrupting the active run.

## UX Modes

HiveMindAI supports two user choices when the prompt changes during an active run:

1. **Update running workflow**
   - The edited goal/transcript is applied immediately.
   - The frontend aborts the current Server-Sent Events stream.
   - A new workflow starts with the updated prompt payload.
   - This is the current safe implementation for “update the running workflow” because it avoids mutating a partially executed DAG in place.

2. **Run after current finish**
   - The edited goal/transcript is stored as the next workflow payload.
   - The current workflow continues unchanged.
   - When the current workflow completes, the queued payload automatically starts as a new workflow.

The current implementation uses **immediate restart** for live updates and **queued follow-up run** for after-finish updates. A future live-DAG amendment controller can be added when the runtime has cancellation, task versioning, and worker coordination.

## Current Implemented Flow

```mermaid
flowchart TD
    A[User clicks Run workflow] --> B[Frontend snapshots active payload]
    B --> C[Backend starts SSE workflow stream]
    C --> D[Orchestrator plans and executes DAG]
    D --> E[Frontend renders live metrics, logs, trace]

    F[User edits goal or transcript while running] --> G{Prompt differs from active payload?}
    G -- No --> E
    G -- Yes --> H[Show prompt update panel near Run workflow button]
    H --> I{User choice}

    I -- Update running workflow --> J[Store immediateUpdatePayload]
    J --> K[Abort active SSE stream]
    K --> L[Start a new workflow with edited payload]
    L --> B

    I -- Run after current finish --> M[Store queuedPayload + autoRun=true]
    I -- Clear update --> N[Ignore current edit for this run]

    D --> O[Current workflow completes]
    O --> P{Queued follow-up exists?}
    P -- Yes --> Q[Start new workflow with queued payload]
    P -- No --> R[Stay on completed workflow]
    Q --> B
```

## Future Live-DAG Amendment Architecture

```mermaid
flowchart TD
    A[Prompt amendment submitted] --> B[Amendment Controller]
    B --> C[Sanitize and diff new context]
    C --> D[Classify amendment]

    D --> E{Amendment type}
    E -- Adds new independent work --> F[Append new DAG node]
    E -- Changes pending task --> G[Version pending task]
    E -- Changes running task --> H[Ask user: cancel/restart or queue follow-up]
    E -- Conflicts with completed work --> I[Create reconciliation task]

    F --> J[Validate DAG remains acyclic]
    G --> J
    H --> J
    I --> J

    J --> K[Persist DAG vNext]
    K --> L[Publish orchestrator trace event]
    L --> M[Workers consume updated ready tasks]
```

## Why Immediate Restart Instead of Silent In-Place Mutation?

Silently mutating a live workflow is risky because:

- A task may already be executing with the old prompt.
- A downstream task may depend on old assumptions.
- Human approval may already be pending for an earlier version.
- Artifacts and validation results need version tracking.

The current **Update running workflow** button uses an explicit restart of the active stream with the edited prompt. It feels immediate to the user while keeping the runtime deterministic.

## Data Model Additions for Future In-Place Amendments

A future implementation should add:

```text
WorkflowRun
- run_id
- active_payload
- status
- current_dag_id
- current_dag_version

PromptAmendment
- amendment_id
- run_id
- submitted_at
- new_goal
- new_transcript
- diff_summary
- classification
- selected_strategy
- status

TaskNode
- task_id
- dag_version
- supersedes_task_id
- amendment_id
- status
```

## Safety Rules

- Do not expose hidden chain-of-thought.
- Redact API keys, tokens, secrets, and passwords in trace output.
- Do not silently rewrite running tasks.
- If an amendment changes active execution, require explicit user choice.
- Persist every amendment decision for auditability.

## Files Involved in Current Implementation

```text
api/static/index.html     Prompt update panel and buttons
api/static/app.js         Payload snapshot, immediate restart, queued follow-up behavior
api/demo.py               Existing stream endpoint used by workflow runs
orchestrator/             Future location for live amendment controller
```
