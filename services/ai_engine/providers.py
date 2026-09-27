"""OpenAI-compatible provider adapters for Gemini and Groq.

Both providers expose chat-completions style interfaces. Keeping the adapter
small lets the engine share one tool-calling loop without coupling the rest
of Lexus to a vendor SDK.
"""

from __future__ import annotations

import json
import logging
import os
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
    ) -> ProviderReply:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max(64, min(max_output_tokens, 4096)),
            "temperature": 0.35,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            # Groq documents this switch for its tool-calling API. Gemini's
            # OpenAI-compatibility layer is left on its documented defaults.
            if self.provider is AIProvider.GROQ:
                kwargs["parallel_tool_calls"] = False

        # Gemini documents reasoning_effort on its OpenAI compatibility layer.
        # Groq also accepts reasoning_effort on supported models, but the value
        # is kept conservative for predictable latency.
        if self.provider is AIProvider.GEMINI:
            kwargs["reasoning_effort"] = "low"

        try:
            response = await self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise ProviderError(
                f"{self.provider.value} request failed: {type(exc).__name__}: {exc}"
            ) from exc

        if not response.choices:
            raise ProviderError(f"{self.provider.value} returned no choices")

        message = response.choices[0].message
        assistant_message = {
            "role": "assistant",
            "content": message.content,
        }

        parsed_calls: list[ToolCall] = []
        raw_tool_calls = getattr(message, "tool_calls", None) or []

        for raw in raw_tool_calls:
            try:
                arguments = raw.function.arguments or "{}"
                import json

                parsed_args = json.loads(arguments)
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
                continue

        if parsed_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, separators=(",", ":")),
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
    """Builds the configured provider chain.

    Model IDs are intentionally fixed in code so deployment only needs API
    credentials in environment variables. Provider order is Gemini -> Groq.
    """

    GEMINI_MODEL = "gemini-3.8-flash"
    GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

    GROQ_MODEL = "openai/gpt-oss-120b"
    GROQ_BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(self) -> None:
        self.providers: list[CompatibleProvider] = []

        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        if gemini_key:
            self.providers.append(
                CompatibleProvider(
                    AIProvider.GEMINI,
                    gemini_key,
                    self.GEMINI_BASE_URL,
                    self.GEMINI_MODEL,
                )
            )

        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if groq_key:
            self.providers.append(
                CompatibleProvider(
                    AIProvider.GROQ,
                    groq_key,
                    self.GROQ_BASE_URL,
                    self.GROQ_MODEL,
                )
            )

    @property
    def available(self) -> bool:
        return bool(self.providers)

    @property
    def names(self) -> list[str]:
        return [f"{item.provider.value}:{item.model}" for item in self.providers]

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_output_tokens: int,
    ) -> ProviderReply:
        if not self.providers:
            raise ProviderError(
                "No AI provider configured. Set GEMINI_API_KEY or GROQ_API_KEY."
            )

        errors: list[str] = []
        for provider in self.providers:
            try:
                return await provider.complete(
                    messages,
                    tools,
                    max_output_tokens,
                )
            except ProviderError as exc:
                errors.append(str(exc))
                logger.error("%s", exc)

        raise ProviderError("All AI providers failed: " + " | ".join(errors))

    async def close(self) -> None:
        for provider in self.providers:
            try:
                await provider.close()
            except Exception:
                logger.exception("Failed closing %s provider", provider.provider.value)
