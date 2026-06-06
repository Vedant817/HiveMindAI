from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re
from typing import Any

from shared.config import ROOT_DIR, env_str


def workspace_root() -> Path:
    root = Path(env_str("WORKSPACE_DIR", str(ROOT_DIR / "workspace")))
    if not root.is_absolute():
        root = ROOT_DIR / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_segment(value: str, fallback: str = "item") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip(".-")
    return cleaned[:80] or fallback


def write_task_artifacts(task: dict[str, Any], output: dict[str, Any]) -> list[str]:
    """Write deterministic local artifacts for a task and return repo-relative paths."""
    dag_id = safe_segment(str(task.get("dag_id") or task.get("metadata", {}).get("dag_id") or "local"), "local")
    task_id = safe_segment(str(task.get("task_id") or task.get("title") or "task"), "task")
    artifact_dir = workspace_root() / dag_id / task_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "task": task,
        "output": output,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    result_json = artifact_dir / "task_result.json"
    result_json.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    result_md = artifact_dir / "task_report.md"
    result_md.write_text(_task_report_markdown(task, output), encoding="utf-8")

    paths = [result_json, result_md]
    if _looks_like_dashboard(task):
        dashboard = artifact_dir / "dashboard.html"
        dashboard.write_text(_dashboard_html(task, output), encoding="utf-8")
        paths.append(dashboard)
    if _looks_like_api(task):
        contract = artifact_dir / "api_contract.json"
        contract.write_text(json.dumps(_api_contract(task), indent=2), encoding="utf-8")
        paths.append(contract)

    return [str(path.relative_to(ROOT_DIR)) if path.is_relative_to(ROOT_DIR) else str(path) for path in paths]


def artifact_exists(path_or_url: str) -> bool:
    if re.match(r"^https?://", path_or_url, flags=re.I):
        return True
    path = Path(path_or_url)
    if not path.is_absolute():
        path = ROOT_DIR / path
    resolved = path.resolve()
    allowed_roots = (ROOT_DIR.resolve(), workspace_root().resolve())
    if not any(_is_relative_to(resolved, root) for root in allowed_roots):
        return False
    return path.exists() and path.is_file() and path.stat().st_size > 0


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _task_report_markdown(task: dict[str, Any], output: dict[str, Any]) -> str:
    title = task.get("title", "Untitled task")
    description = task.get("description", "")
    summary = output.get("summary") or output.get("title") or "Completed task"
    details = output.get("details") or description
    return (
        f"# {title}\n\n"
        f"## Acceptance Criteria\n\n{description}\n\n"
        f"## Result Summary\n\n{summary}\n\n"
        f"## Implementation Details\n\n{details}\n"
    )


def _looks_like_dashboard(task: dict[str, Any]) -> bool:
    text = f"{task.get('title', '')} {task.get('description', '')}".lower()
    return any(word in text for word in ("dashboard", "reporting ui", "manager view"))


def _looks_like_api(task: dict[str, Any]) -> bool:
    text = f"{task.get('title', '')} {task.get('description', '')}".lower()
    return any(word in text for word in ("api", "endpoint", "webhook"))


def _dashboard_html(task: dict[str, Any], output: dict[str, Any]) -> str:
    title = str(task.get("title", "HiveMindAI Dashboard"))
    summary = str(output.get("summary", "Task output"))
    details = str(output.get("details", task.get("description", "")))
    return f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{_html_escape(title)}</title>
    <style>
      body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #202124; }}
      main {{ max-width: 920px; margin: auto; }}
      section {{ border: 1px solid #d6d9d2; border-radius: 12px; padding: 1rem; margin-top: 1rem; }}
    </style>
  </head>
  <body>
    <main>
      <h1>{_html_escape(title)}</h1>
      <section><h2>Summary</h2><p>{_html_escape(summary)}</p></section>
      <section><h2>Details</h2><p>{_html_escape(details)}</p></section>
    </main>
  </body>
</html>
"""


def _api_contract(task: dict[str, Any]) -> dict[str, Any]:
    title = str(task.get("title", "task api"))
    slug = safe_segment(title.lower(), "task")
    return {
        "openapi": "3.0.3",
        "info": {"title": title, "version": "1.0.0"},
        "paths": {
            f"/{slug}": {
                "post": {
                    "summary": title,
                    "responses": {"200": {"description": "Accepted task result"}},
                }
            }
        },
    }


def _html_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
