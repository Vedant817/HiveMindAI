from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

from shared.config import active_llm_provider, env_float, is_real_value, require_or_fallback


class LLMClient:
    def __init__(self) -> None:
        self.provider = active_llm_provider()
        self.azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        self.azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.azure_api_key = os.getenv("AZURE_OPENAI_KEY")
        self.azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION")
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", "qwen/qwen3-coder:free")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.request_timeout = env_float("LLM_REQUEST_TIMEOUT_SECONDS", 20.0)

    @property
    def configured(self) -> bool:
        if self.provider == "openrouter":
            return all(is_real_value(value) for value in (self.openrouter_model, self.openrouter_api_key))
        if self.provider == "azure":
            return all(
                is_real_value(value)
                for value in (
                    self.azure_deployment,
                    self.azure_endpoint,
                    self.azure_api_key,
                    self.azure_api_version,
                )
            )
        return False

    async def chat_text(
        self,
        system: str,
        user: str,
        temperature: float = 0.1,
    ) -> str | None:
        if not self.configured:
            require_or_fallback(
                "LLM provider",
                "set OpenRouter variables or Azure OpenAI variables",
            )
            return None

        try:
            if self.provider == "openrouter":
                return await asyncio.to_thread(self._openrouter_chat, system, user, temperature)
            if self.provider == "azure":
                return await asyncio.to_thread(self._azure_chat, system, user, temperature)

            require_or_fallback("LLM provider", f"unsupported provider: {self.provider}")
            return None
        except Exception as exc:
            require_or_fallback("LLM provider", f"chat request failed: {exc}")
            return None

    async def chat_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.1,
    ) -> Any | None:
        text = await self.chat_text(system, user, temperature=temperature)
        if text is None:
            return None
        try:
            return json.loads(_strip_json_fence(text))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            require_or_fallback("LLM provider", f"response was not valid JSON: {exc}")
            return None

    async def transcribe_audio(self, path: str) -> str | None:
        deployment = os.getenv("AZURE_OPENAI_WHISPER_DEPLOYMENT")
        if self.provider != "azure":
            require_or_fallback(
                "Speech transcription",
                "audio transcription currently requires Azure OpenAI Whisper; text transcripts work locally",
            )
            return None
        if not all(is_real_value(value) for value in (self.azure_endpoint, self.azure_api_key, self.azure_api_version, deployment)):
            require_or_fallback(
                "Azure OpenAI Whisper",
                "set AZURE_OPENAI_WHISPER_DEPLOYMENT plus Azure OpenAI endpoint/key/version",
            )
            return None

        try:
            def _call() -> str:
                from openai import AzureOpenAI

                client = AzureOpenAI(
                    api_key=self.azure_api_key,
                    azure_endpoint=self.azure_endpoint,
                    api_version=self.azure_api_version,
                    timeout=self.request_timeout,
                )
                with open(path, "rb") as audio:
                    response = client.audio.transcriptions.create(model=deployment, file=audio)
                return response.text

            return await asyncio.to_thread(_call)
        except Exception as exc:
            require_or_fallback("Azure OpenAI Whisper", f"transcription request failed: {exc}")
            return None

    def _azure_chat(self, system: str, user: str, temperature: float) -> str:
        from openai import AzureOpenAI

        client = AzureOpenAI(
            api_key=self.azure_api_key,
            azure_endpoint=self.azure_endpoint,
            api_version=self.azure_api_version,
            timeout=self.request_timeout,
        )
        response = client.chat.completions.create(
            model=self.azure_deployment,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""

    def _openrouter_chat(self, system: str, user: str, temperature: float) -> str:
        from openai import OpenAI

        extra_headers = {}
        if site_url := os.getenv("OPENROUTER_SITE_URL"):
            extra_headers["HTTP-Referer"] = site_url
        if app_name := os.getenv("OPENROUTER_APP_NAME", "HiveMindAI"):
            extra_headers["X-Title"] = app_name

        client = OpenAI(
            api_key=self.openrouter_api_key,
            base_url=self.openrouter_base_url,
            default_headers=extra_headers or None,
            timeout=self.request_timeout,
        )
        response = client.chat.completions.create(
            model=self.openrouter_model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, flags=re.S)
    return match.group(1).strip() if match else stripped
