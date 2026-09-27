"""OpenAI-compatible adapters for Gemini and Groq with failover."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from openai import AsyncOpenAI

from .models import AIProvider, ProviderReply, ToolCall

logger = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    """Raised when a provider cannot complete a request."""


class CompatibleProvider:
    def __init__(
        self,
        provider: AIProvider,
        api_key: str,
        base_url: str,
        model: str,
    ) -> None:
        self.provider = provider
        self.model = model
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=25.0,
            max_retries=0,
        )

    async def close(self) -> None:
        await self.client.close()

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_output_tokens: int,
        web_search: bool = False,
    ) -> ProviderReply:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.35,
        }

        if self.provider is AIProvider.GROQ:
            kwargs["max_completion_tokens"] = max(
                64, min(max_output_tokens, 4096)
            )
            kwargs["parallel_tool_calls"] = False
            kwargs["reasoning_effort"] = "low"

            if web_search:
                kwargs["tools"] = [{"type": "browser_search"}]
                kwargs["tool_choice"] = "required"
            elif tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
        else:
            kwargs["max_tokens"] = max(64, min(max_output_tokens, 4096))
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

        try:
            response = await self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise ProviderError(
                f"{self.provider.value} request failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        if not response.choices:
            raise ProviderError(f"{self.provider.value} returned no choices")

        message = response.choices[0].message
        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": message.content,
        }

        parsed_calls: list[ToolCall] = []
        raw_tool_calls = getattr(message, "tool_calls", None) or []

        for raw in raw_tool_calls:
            try:
                parsed_args = json.loads(raw.function.arguments or "{}")
                if not isinstance(parsed_args, dict):
                    raise ValueError("tool arguments must decode to an object")

                parsed_calls.append(
                    ToolCall(
                        call_id=raw.id,
                        name=raw.function.name,
                        arguments=parsed_args,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Ignoring malformed tool call from %s: %s",
                    self.provider.value,
                    exc,
                )

        if parsed_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(
                            call.arguments,
                            separators=(",", ":"),
                        ),
                    },
                }
                for call in parsed_calls
            ]

        return ProviderReply(
            provider=self.provider,
            model=self.model,
            assistant_message=assistant_message,
            text=(message.content or "").strip(),
            tool_calls=parsed_calls,
            finish_reason=getattr(response.choices[0], "finish_reason", None),
        )


class ProviderManager:
    """Provider chain with transient-failure cooldowns and search routing."""

    GEMINI_MODEL = "gemini-3.8-flash"
    GEMINI_BASE_URL = (
        "https://generativelanguage.googleapis.com/v1beta/openai/"
    )

    GROQ_MODEL = "openai/gpt-oss-120b"
    GROQ_BASE_URL = "https://api.groq.com/openai/v1"

    PROVIDER_COOLDOWN_SECONDS = 300.0

    def __init__(self) -> None:
        self.providers: list[CompatibleProvider] = []
        self._cooldown_until: dict[AIProvider, float] = {}
        try:
            self.provider_cooldown_seconds = max(
                60.0,
                float(os.getenv("AI_PROVIDER_COOLDOWN_SECONDS", "300"))
            )
        except (TypeError, ValueError):
            self.provider_cooldown_seconds = 300.0

        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        gemini_model = os.getenv("GEMINI_MODEL", self.GEMINI_MODEL).strip()
        if gemini_key:
            self.providers.append(
                CompatibleProvider(
                    AIProvider.GEMINI,
                    gemini_key,
                    self.GEMINI_BASE_URL,
                    gemini_model or self.GEMINI_MODEL,
                )
            )

        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        groq_model = os.getenv("GROQ_MODEL", self.GROQ_MODEL).strip()
        if groq_key:
            self.providers.append(
                CompatibleProvider(
                    AIProvider.GROQ,
                    groq_key,
                    self.GROQ_BASE_URL,
                    groq_model or self.GROQ_MODEL,
                )
            )

    @property
    def available(self) -> bool:
        return bool(self.providers)

    @property
    def names(self) -> list[str]:
        return [f"{item.provider.value}:{item.model}" for item in self.providers]

    def health(self) -> dict[str, Any]:
        now = time.monotonic()
        return {
            item.provider.value: {
                "model": item.model,
                "cooldown_seconds": max(
                    0.0,
                    self._cooldown_until.get(item.provider, 0.0) - now,
                ),
            }
            for item in self.providers
        }

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_output_tokens: int,
        web_search: bool = False,
    ) -> ProviderReply:
        if not self.providers:
            raise ProviderError(
                "No AI provider configured. Set GEMINI_API_KEY or GROQ_API_KEY."
            )

        now = time.monotonic()

        if web_search:
            groq_providers = [
                item for item in self.providers
                if item.provider is AIProvider.GROQ
            ]
            if not groq_providers:
                raise ProviderError(
                    "Web search requires GROQ_API_KEY because Lexus uses "
                    "Groq's built-in browser search."
                )

            ordered = [
                item for item in groq_providers
                if self._cooldown_until.get(item.provider, 0.0) <= now
            ]
            if not ordered:
                remaining = max(
                    0.0,
                    self._cooldown_until.get(
                        AIProvider.GROQ,
                        0.0,
                    ) - now,
                )
                raise ProviderError(
                    f"Groq browser search is temporarily cooling down for "
                    f"{remaining:.0f}s."
                )
        else:
            ordered = [
                item for item in self.providers
                if self._cooldown_until.get(item.provider, 0.0) <= now
            ]

            if not ordered:
                ordered = [
                    min(
                        self.providers,
                        key=lambda item: self._cooldown_until.get(
                            item.provider,
                            0.0,
                        ),
                    )
                ]

        errors: list[str] = []

        for provider in ordered:
            try:
                reply = await provider.complete(
                    messages=messages,
                    tools=tools,
                    max_output_tokens=max_output_tokens,
                    web_search=(
                        web_search and provider.provider is AIProvider.GROQ
                    ),
                )
                self._cooldown_until.pop(provider.provider, None)
                return reply
            except ProviderError as exc:
                errors.append(str(exc))
                logger.error("%s", exc)

                if self._is_transient_failure(exc):
                    until = (
                        time.monotonic()
                        + self.provider_cooldown_seconds
                    )
                    self._cooldown_until[provider.provider] = until
                    logger.warning(
                        "AI provider %s cooling down for %.0fs",
                        provider.provider.value,
                        self.provider_cooldown_seconds,
                    )

        raise ProviderError(
            "All AI providers failed: " + " | ".join(errors)
        )

    @staticmethod
    def _is_transient_failure(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        if status == 429 or (
            isinstance(status, int) and 500 <= status <= 504
        ):
            return True

        text = str(exc).casefold()
        return any(
            marker in text
            for marker in (
                "429",
                "rate limit",
                "500",
                "502",
                "503",
                "504",
                "timeout",
                "timed out",
                "service unavailable",
                "temporarily unavailable",
                "high demand",
                "unavailable",
            )
        )

    async def close(self) -> None:
        for provider in self.providers:
            try:
                await provider.close()
            except Exception as exc:
                logger.warning(
                    "Failed closing %s provider: %s",
                    provider.provider.value,
                    exc,
                )
