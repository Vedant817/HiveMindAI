from __future__ import annotations

from dataclasses import dataclass
import asyncio
import json
import os

from shared.config import require_or_fallback
from shared.llm_client import LLMClient


@dataclass(slots=True)
class DebatePersona:
    name: str
    bias: str
    weight: tuple[int, int, int]


DEFAULT_PERSONAS = [
    DebatePersona("PerformanceAgent", "Optimize for speed and scalability.", (10, 5, 6)),
    DebatePersona("CostAgent", "Optimize for the lowest sustainable cloud cost.", (6, 10, 7)),
    DebatePersona("SimplicityAgent", "Optimize for maintainability and the smallest viable design.", (7, 8, 10)),
]


class DebateOrchestrator:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()
        self.personas = _load_personas()

    async def run_debate(self, question: str) -> dict:
        if self.llm.configured:
            proposals = await asyncio.gather(*[self._llm_proposal(persona, question) for persona in self.personas])
            winner = await self._llm_validate(question, proposals)
            return {"question": question, "proposals": proposals, "winner": winner}
        require_or_fallback("LLM provider", "set OpenRouter or Azure OpenAI variables for live debate agents")
        proposals = [self._proposal(persona, question) for persona in self.personas]
        winner = self._validate(proposals)
        return {"question": question, "proposals": proposals, "winner": winner}

    async def _llm_proposal(self, persona: DebatePersona, question: str) -> dict:
        system = f"You are {persona.name}. {persona.bias} Return JSON: {{\"agent\":\"{persona.name}\",\"proposal\":\"...\"}}"
        row = await self.llm.chat_json(system, question)
        if row is None:
            return self._proposal(persona, question)
        row.setdefault("agent", persona.name)
        return row

    async def _llm_validate(self, question: str, proposals: list[dict]) -> dict:
        system = """You are a neutral technical validator. Score proposals on scalability, cost,
and maintainability from 0-10, then pick a winner. Return only JSON:
{"winner":"AgentName","total_score":0,"rationale":"...","scores":[{"agent":"...","scalability":0,"cost":0,"maintainability":0}]}"""
        row = await self.llm.chat_json(system, f"Question: {question}\nProposals: {proposals}")
        return row if row is not None else self._validate(proposals)

    def _proposal(self, persona: DebatePersona, question: str) -> dict:
        scores = self._score_for_question(persona, question)
        leading = max(scores, key=scores.get)
        return {
            "agent": persona.name,
            "proposal": (
                f"{persona.bias} For '{question}', prioritize {leading} because the question signals "
                f"{self._signals(question) or 'balanced delivery constraints'}."
            ),
            "scores": scores,
        }

    def _score_for_question(self, persona: DebatePersona, question: str) -> dict:
        q = question.lower()
        scores = {
            "scalability": persona.weight[0],
            "cost": persona.weight[1],
            "maintainability": persona.weight[2],
        }
        boosts = {
            "scalability": ("scale", "throughput", "latency", "realtime", "pub/sub", "redis", "status"),
            "cost": ("cost", "free", "budget", "cheap", "serverless"),
            "maintainability": ("simple", "maintain", "operat", "durable", "service bus", "audit", "enterprise"),
        }
        for dimension, words in boosts.items():
            scores[dimension] += sum(2 for word in words if word in q)
        return {key: min(10, value) for key, value in scores.items()}

    def _signals(self, question: str) -> str:
        q = question.lower()
        found = []
        if any(word in q for word in ("redis", "pub/sub", "latency", "realtime")):
            found.append("low-latency status fan-out")
        if any(word in q for word in ("service bus", "durable", "audit", "enterprise")):
            found.append("durable enterprise messaging")
        if any(word in q for word in ("cost", "free", "budget")):
            found.append("cost sensitivity")
        return ", ".join(found)

    def _validate(self, proposals: list[dict]) -> dict:
        scored = []
        for proposal in proposals:
            scores = proposal["scores"]
            total = scores["scalability"] + scores["cost"] + scores["maintainability"]
            scored.append({"agent": proposal["agent"], **scores, "total": total})
        scored.sort(key=lambda row: row["total"], reverse=True)
        return {
            "winner": scored[0]["agent"],
            "total_score": scored[0]["total"],
            "rationale": "Highest balanced score across scalability, cost, and maintainability.",
            "scores": scored,
        }


def _load_personas() -> list[DebatePersona]:
    raw = os.getenv("DEBATE_PERSONAS_JSON")
    if not raw:
        return DEFAULT_PERSONAS
    try:
        rows = json.loads(raw)
        personas: list[DebatePersona] = []
        for row in rows:
            weights = list(row.get("weight", [7, 7, 7]))[:3]
            while len(weights) < 3:
                weights.append(7)
            personas.append(
                DebatePersona(
                    name=str(row["name"]),
                    bias=str(row["bias"]),
                    weight=(int(weights[0]), int(weights[1]), int(weights[2])),
                )
            )
        return personas or DEFAULT_PERSONAS
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        return DEFAULT_PERSONAS
