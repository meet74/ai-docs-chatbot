"""One small LLM client: Anthropic, any OpenAI-compatible API, or a deterministic mock."""
import json
import re
from typing import Protocol

import httpx

from .config import Settings
from .prompt import LLMRequest, build_messages
from .text import tokenize

REFUSAL_TEXT = "I don't know the answer to that from our documents."
MOCK_MIN_COVERAGE = 0.5


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    name: str

    async def complete(self, req: LLMRequest, correction: str | None = None) -> str: ...


class MockLLM:
    """Composes an answer from the best-matching sentences, or refuses on weak retrieval.

    It never invents anything: every word of the answer is copied from a passage.
    """
    name = "mock"

    async def complete(self, req: LLMRequest, correction: str | None = None) -> str:
        good = [p for p in req.passages if p.coverage >= MOCK_MIN_COVERAGE]
        if not good:
            return json.dumps({"answer": REFUSAL_TEXT, "citations": [],
                               "confidence": 0.1, "needs_human": True})
        good.sort(key=lambda p: (-p.coverage, p.rank))
        used = good[:2]
        q = set(tokenize(req.question))
        picked: list[tuple[int, int, str]] = []  # (passage order, unit order, text)
        scored = []
        for pi, p in enumerate(used):
            for ui, unit in enumerate(_units(p.chunk.text)):
                overlap = len(q & set(tokenize(unit)))
                if overlap:
                    scored.append((-overlap, pi, ui, unit))
        scored.sort()
        for _, pi, ui, unit in scored[:3]:
            picked.append((pi, ui, unit))
        if not picked:
            picked = [(0, 0, _units(used[0].chunk.text)[0])]
        picked.sort()
        parts = []
        for _, _, u in picked:
            u = re.sub(r"^[-*]\s+", "", u).strip()
            u = u.rstrip(":").rstrip()
            parts.append(u if u[-1] in ".!?" else u + ".")
        used_idx = sorted({pi for pi, _, _ in picked})
        citations = [{"doc": used[i].chunk.doc, "section": used[i].chunk.section} for i in used_idx]
        confidence = round(min(0.95, 0.35 + 0.65 * used[0].coverage), 2)
        return json.dumps({"answer": " ".join(parts), "citations": citations,
                           "confidence": confidence, "needs_human": False})


def _units(text: str) -> list[str]:
    units = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        units.extend(s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", line) if s)
    return units


class HTTPLLM:
    def __init__(self, provider: str, base_url: str, model: str, api_key: str,
                 http: httpx.AsyncClient | None = None, timeout: float = 30.0):
        self.name = f"{provider}:{model}"
        self.provider, self.base_url, self.model = provider, base_url.rstrip("/"), model
        self.api_key, self._http, self.timeout = api_key, http, timeout

    async def complete(self, req: LLMRequest, correction: str | None = None) -> str:
        system, messages = build_messages(req, correction)
        client = self._http or httpx.AsyncClient(timeout=self.timeout)
        try:
            if self.provider == "anthropic":
                r = await client.post(
                    f"{self.base_url}/v1/messages",
                    headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                    json={"model": self.model, "max_tokens": 700, "temperature": 0,
                          "system": system, "messages": messages})
                r.raise_for_status()
                return "".join(b.get("text", "") for b in r.json()["content"])
            r = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "temperature": 0,
                      "response_format": {"type": "json_object"},
                      "messages": [{"role": "system", "content": system}, *messages]})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise LLMError(f"LLM request failed: {type(e).__name__}") from e
        finally:
            if self._http is None:
                await client.aclose()


def make_llm(settings: Settings, http: httpx.AsyncClient | None = None) -> LLMClient:
    provider, base_url, model, key = settings.resolved_llm()
    if provider == "mock":
        return MockLLM()
    if not key:
        raise ValueError(f"LLM_PROVIDER={provider} needs an API key")
    return HTTPLLM(provider, base_url, model, key, http=http, timeout=settings.llm_timeout)
