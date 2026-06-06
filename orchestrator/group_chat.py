from __future__ import annotations

import os

from agents.planner_agent import PlannerAgent
from shared.config import active_llm_provider, llm_configured, require_or_fallback


def run_swarm(task: str) -> list[dict]:
    """Run the AutoGen group chat when configured, otherwise return a local plan trace."""
    provider = active_llm_provider()
    if llm_configured():
        try:
            return _run_autogen(task, provider)
        except Exception as exc:
            require_or_fallback(f"AutoGen/{provider}", f"group chat failed: {exc}")
            return [{"role": "system", "content": f"AutoGen unavailable, local fallback used: {exc}"}] + _local_trace(task)
    require_or_fallback("LLM provider", "set OpenRouter or Azure OpenAI variables for AutoGen group chat")
    return _local_trace(task)


def _local_trace(task: str) -> list[dict]:
    dag = PlannerAgent().plan(task)
    messages = [{"role": "user", "content": task}]
    for node in dag.tasks:
        messages.append(
            {
                "role": node.assigned_to,
                "content": {
                    "title": node.title,
                    "description": node.description,
                    "depends_on": node.depends_on,
                },
            }
        )
    return messages


def _run_autogen(task: str, provider: str) -> list[dict]:
    import autogen
    from dotenv import load_dotenv

    load_dotenv()
    config = _autogen_model_config(provider)
    llm_config = {
        "config_list": [config],
        "temperature": 0.1,
    }
    planner = autogen.AssistantAgent(
        name="Planner",
        system_message="Break high-level goals into JSON subtasks.",
        llm_config=llm_config,
    )
    executor = autogen.AssistantAgent(
        name="Executor",
        system_message="Implement subtasks and include confidence.",
        llm_config=llm_config,
    )
    validator = autogen.AssistantAgent(
        name="Validator",
        system_message="Validate output and report PASS or FAIL.",
        llm_config=llm_config,
    )
    user_proxy = autogen.UserProxyAgent(
        name="UserProxy",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=10,
        code_execution_config={"work_dir": "workspace", "use_docker": False},
    )
    groupchat = autogen.GroupChat(
        agents=[user_proxy, planner, executor, validator],
        messages=[],
        max_round=15,
    )
    manager = autogen.GroupChatManager(groupchat=groupchat, llm_config=llm_config)
    user_proxy.initiate_chat(manager, message=task)
    return groupchat.messages


def _autogen_model_config(provider: str) -> dict:
    if provider == "openrouter":
        return {
            "model": os.getenv("OPENROUTER_MODEL", "qwen/qwen3-coder:free"),
            "api_key": os.getenv("OPENROUTER_API_KEY"),
            "base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        }
    if provider == "azure":
        return {
            "model": os.getenv("AZURE_OPENAI_DEPLOYMENT"),
            "api_type": "azure",
            "api_key": os.getenv("AZURE_OPENAI_KEY"),
            "base_url": os.getenv("AZURE_OPENAI_ENDPOINT"),
            "api_version": os.getenv("AZURE_OPENAI_API_VERSION"),
        }
    raise ValueError(f"Unsupported AutoGen provider: {provider}")
