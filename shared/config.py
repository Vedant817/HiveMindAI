from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

ROOT_DIR = Path(__file__).resolve().parents[1]


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    return float(value)


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def is_real_value(value: str | None) -> bool:
    """Return False for empty values and obvious sample placeholders."""
    if value is None:
        return False
    normalized = value.strip().lower()
    if not normalized:
        return False
    placeholder_fragments = (
        "<",
        ">",
        "your_",
        "your-",
        "your.",
        "yourorg",
        "your@email",
        "example.com",
        "...",
        "todo",
        "changeme",
        "replace_me",
        "placeholder",
    )
    return not any(fragment in normalized for fragment in placeholder_fragments)


def strict_integrations() -> bool:
    return env_bool("SWARM_STRICT_INTEGRATIONS", False)


def local_fallbacks_enabled() -> bool:
    return env_bool("SWARM_ENABLE_LOCAL_FALLBACKS", True)


def require_or_fallback(integration: str, message: str) -> None:
    from shared.errors import IntegrationNotConfigured

    if strict_integrations() or not local_fallbacks_enabled():
        raise IntegrationNotConfigured(f"{integration} is not configured: {message}")


PRODUCTION_ENV_GROUPS: dict[str, tuple[str, ...]] = {
    "OpenRouter": (
        "OPENROUTER_API_KEY",
        "OPENROUTER_MODEL",
    ),
    "Azure OpenAI": (
        "AZURE_OPENAI_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_OPENAI_API_VERSION",
    ),
    "Azure OpenAI Whisper": (
        "AZURE_OPENAI_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_VERSION",
        "AZURE_OPENAI_WHISPER_DEPLOYMENT",
    ),
    "Redis": ("REDIS_URL",),
    "Azure Service Bus": ("AZURE_SERVICE_BUS_CONNECTION_STRING",),
    "Cosmos DB": ("COSMOS_ENDPOINT", "COSMOS_KEY", "COSMOS_DATABASE"),
    "Azure AI Search": ("SEARCH_ENDPOINT", "SEARCH_KEY", "SEARCH_INDEX"),
    "Azure Blob Storage": ("AZURE_STORAGE_CONNECTION_STRING",),
    "Jira": ("JIRA_DOMAIN", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"),
    "Teams": ("TEAMS_WEBHOOK_URL", "APP_BASE_URL"),
    "Slack": ("SLACK_WEBHOOK_URL",),
    "Azure Communication Services": (
        "AZURE_COMMUNICATION_CONNECTION_STRING",
        "SENDER_EMAIL",
        "STAKEHOLDER_EMAIL",
    ),
}


FREE_ENV_GROUPS: dict[str, tuple[str, ...]] = {
    "OpenRouter": (
        "OPENROUTER_API_KEY",
        "OPENROUTER_MODEL",
    ),
    "MongoDB Atlas": ("MONGODB_URI",),
    "Upstash Redis": ("REDIS_URL",),
}


def app_stack() -> str:
    configured = os.getenv("APP_STACK", "free").strip().lower()
    if configured in {"free", "azure", "local"}:
        return configured
    return "free"


def llm_provider() -> str:
    configured = os.getenv("LLM_PROVIDER", "auto").strip().lower()
    if configured in {"azure", "openrouter", "none", "auto"}:
        return configured
    return "auto"


def active_llm_provider() -> str:
    provider = llm_provider()
    if provider != "auto":
        return provider
    if is_real_value(os.getenv("OPENROUTER_API_KEY")) and is_real_value(os.getenv("OPENROUTER_MODEL")):
        return "openrouter"
    if all(
        is_real_value(os.getenv(name))
        for name in (
            "AZURE_OPENAI_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_DEPLOYMENT",
            "AZURE_OPENAI_API_VERSION",
        )
    ):
        return "azure"
    return "none"


def llm_configured() -> bool:
    provider = active_llm_provider()
    if provider == "openrouter":
        return all(is_real_value(os.getenv(name)) for name in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL"))
    if provider == "azure":
        return all(
            is_real_value(os.getenv(name))
            for name in (
                "AZURE_OPENAI_KEY",
                "AZURE_OPENAI_ENDPOINT",
                "AZURE_OPENAI_DEPLOYMENT",
                "AZURE_OPENAI_API_VERSION",
            )
        )
    return False


def config_report(groups: Iterable[str] | None = None) -> dict:
    stack = app_stack()
    env_groups = FREE_ENV_GROUPS if stack in {"free", "local"} and groups is None else PRODUCTION_ENV_GROUPS
    selected = set(groups or env_groups)
    provider = active_llm_provider()
    if groups is None:
        if stack in {"free", "local"}:
            selected.discard("Azure OpenAI")
            selected.discard("Azure OpenAI Whisper")
        elif provider == "openrouter":
            selected.discard("Azure OpenAI")
            selected.discard("Azure OpenAI Whisper")
        elif provider == "azure":
            selected.discard("OpenRouter")
        elif provider == "none":
            selected.discard("OpenRouter")
    integrations = {}
    missing_total: list[str] = []
    for name, variables in env_groups.items():
        if name not in selected:
            continue
        missing = [var for var in variables if not is_real_value(os.getenv(var))]
        for variable in missing:
            if variable not in missing_total:
                missing_total.append(variable)
        integrations[name] = {
            "configured": not missing,
            "missing": missing,
        }
    return {
        "app_stack": stack,
        "stack_label": {
            "free": "Free cloud stack",
            "local": "Local fallback stack",
            "azure": "Azure production stack",
        }[stack],
        "llm_provider": provider,
        "llm_configured": llm_configured(),
        "strict_integrations": strict_integrations(),
        "local_fallbacks_enabled": local_fallbacks_enabled(),
        "local_test_ready": local_fallbacks_enabled(),
        "free_model_ready": provider == "openrouter" and llm_configured(),
        "free_stack_ready": stack in {"free", "local"} and not missing_total,
        "production_ready": not missing_total,
        "missing": missing_total,
        "integrations": integrations,
    }


def demo_defaults() -> dict:
    path = Path(os.getenv("DEMO_DEFAULTS_FILE", ROOT_DIR / "config" / "demo_defaults.json"))
    defaults = json.loads(path.read_text(encoding="utf-8"))
    return {
        "goal": os.getenv("DEMO_DEFAULT_GOAL") or os.getenv("SWARM_DEFAULT_GOAL") or defaults["goal"],
        "transcript": os.getenv("DEMO_DEFAULT_TRANSCRIPT") or defaults["transcript"],
        "question": os.getenv("DEMO_DEFAULT_DEBATE_QUESTION") or defaults["question"],
        "story": defaults["story"],
        "human_gate_threshold": confidence_threshold(),
    }


def confidence_threshold() -> float:
    return env_float("CONFIDENCE_THRESHOLD", 0.90)


def meeting_confidence(needs_review: bool) -> float:
    env_name = "MEETING_REVIEW_CONFIDENCE" if needs_review else "MEETING_CONFIDENCE"
    return env_float(env_name, 0.88 if needs_review else 0.94)


def executor_confidence_floor() -> float:
    return env_float("EXECUTOR_CONFIDENCE_FLOOR", 0.65)


def executor_confidence_cap() -> float:
    return env_float("EXECUTOR_CONFIDENCE_CAP", 0.98)


def planner_default_confidence() -> float:
    return env_float("PLANNER_DEFAULT_CONFIDENCE", 0.95)
