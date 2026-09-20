"""Cliente mínimo para proveedores de LLM con API compatible con OpenAI (chat completions, streaming).

DeepSeek, OpenAI, OpenRouter y Ollama comparten este formato. La clave la paga el usuario (BYOK) y
se guarda fuera de la base (`radar.settings.write_secret`).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx

from radar.settings import get_setting, read_secret

# Verifica modelos y precios vigentes en la documentación de cada proveedor antes de fijarlos.
PROVIDERS: dict[str, dict[str, Any]] = {
    "deepseek": {"base_url": "https://api.deepseek.com", "model": "deepseek-flash",
                 "models": ["deepseek-flash", "deepseek-v4-pro"],
                 "model_names": {"deepseek-flash": "DeepSeek V4.1 Flash", "deepseek-v4-pro": "DeepSeek V4 Pro"},
                 "reasoning_efforts": ["none", "low", "high", "max"]},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "models": ["gpt-4o-mini"]},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "deepseek/deepseek-chat", "models": []},
    "ollama": {"base_url": "http://127.0.0.1:11434/v1", "model": "qwen2.5:7b", "models": []},
    "custom": {"base_url": "", "model": "", "models": []},
}
NO_KEY_PROVIDERS = {"ollama"}
REASONING_EFFORTS = ("none", "low", "high", "max")


class ProviderError(RuntimeError):
    """Fallo del proveedor mostrable al usuario (sin secretos)."""


@dataclass(frozen=True, slots=True)
class LLMConfig:
    provider: str
    base_url: str
    model: str
    api_key: str | None
    reasoning_effort: str | None = None

    @property
    def ready(self) -> bool:
        return bool(self.base_url and self.model and (self.api_key or self.provider in NO_KEY_PROVIDERS))


def load_config() -> LLMConfig:
    provider = get_setting("llm_provider") or "deepseek"
    preset = PROVIDERS.get(provider, PROVIDERS["custom"])
    return LLMConfig(
        provider=provider,
        base_url=(get_setting("llm_base_url") or preset["base_url"]).rstrip("/"),
        model=get_setting("llm_model") or preset["model"],
        api_key=read_secret(f"llm_key_{provider}"),
        reasoning_effort=(get_setting("llm_reasoning_effort") if get_setting("llm_reasoning_effort") in REASONING_EFFORTS else None),
    )


def stream_chat(
    config: LLMConfig,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    client: httpx.Client | None = None,
) -> Iterator[dict[str, Any]]:
    """Emite {"text": str} por fragmento, luego {"tool_calls": [...]} y {"usage": {...}}."""
    body: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if tools:
        body["tools"] = tools
    if config.provider == "deepseek" and config.reasoning_effort:
        body["reasoning_effort"] = config.reasoning_effort
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    owns = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0))
    calls: dict[int, dict[str, Any]] = {}
    try:
        with client.stream(
            "POST", f"{config.base_url}/chat/completions", json=body, headers=headers
        ) as response:
            if response.status_code >= 400:
                detail = response.read().decode("utf-8", "replace")[:300]
                if response.status_code in (401, 403):
                    raise ProviderError("El proveedor rechazó la clave de API.")
                if response.status_code == 402:
                    raise ProviderError("Saldo insuficiente en el proveedor.")
                if response.status_code == 429:
                    raise ProviderError("Límite de uso del proveedor alcanzado; reintenta luego.")
                raise ProviderError(f"Error {response.status_code} del proveedor: {detail}")
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                chunk = json.loads(payload)
                if chunk.get("usage"):
                    yield {"usage": chunk["usage"]}
                for choice in chunk.get("choices", []):
                    delta = choice.get("delta") or {}
                    if delta.get("reasoning_content"):
                        yield {"reasoning": delta["reasoning_content"]}
                    if delta.get("content"):
                        yield {"text": delta["content"]}
                    for part in delta.get("tool_calls") or []:
                        slot = calls.setdefault(
                            part.get("index", 0), {"id": None, "name": "", "arguments": ""}
                        )
                        slot["id"] = part.get("id") or slot["id"]
                        fn = part.get("function") or {}
                        slot["name"] += fn.get("name") or ""
                        slot["arguments"] += fn.get("arguments") or ""
    except httpx.HTTPError as exc:
        raise ProviderError(f"No se pudo contactar al proveedor: {type(exc).__name__}") from exc
    finally:
        if owns:
            client.close()
    if calls:
        yield {
            "tool_calls": [
                {"id": c["id"] or f"call_{i}", "name": c["name"], "arguments": c["arguments"] or "{}"}
                for i, c in sorted(calls.items())
            ]
        }
