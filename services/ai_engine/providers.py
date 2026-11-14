"""Groq adapters with bounded retries and optional local inference."""

from __future__ import annotations

import json
import asyncio
import logging
import os
import time
import math
from collections import Counter
from typing import Any

from openai import AsyncOpenAI
import aiohttp
from urllib.parse import urlsplit

from .config import BrainConfig

from .models import AIProvider, ProviderReply, ToolCall

logger = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    """Raised when a provider cannot complete a request."""

    def __init__(self, message: str, *, status_code=None, retry_after=None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


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
        self._api_key = api_key
        self._base_url = base_url
        self.client = None
        self.timeout = 45.0

    def _client(self):
        if self.client is None:
            self.client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url,
                                      timeout=self.timeout, max_retries=0)
        return self.client

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()
            self.client = None

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
            response = await self._client().chat.completions.create(**kwargs)
        except Exception as exc:
            headers = getattr(getattr(exc, "response", None), "headers", {})
            try:
                delay = float(headers.get("retry-after", ""))
                retry_after = delay if math.isfinite(delay) and delay >= 0 else None
            except (TypeError, ValueError):
                retry_after = None
            raise ProviderError(
                f"{self.provider.value} request failed: "
                f"{type(exc).__name__} status={getattr(exc, 'status_code', 'unknown')}",
                status_code=getattr(exc, "status_code", None), retry_after=retry_after,
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
                    type(exc).__name__,
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
            input_tokens=getattr(getattr(response, "usage", None), "prompt_tokens", None),
            output_tokens=getattr(getattr(response, "usage", None), "completion_tokens", None),
            cached_input_tokens=getattr(getattr(getattr(response, "usage", None), "prompt_tokens_details", None), "cached_tokens", None),
        )


class LocalModelProvider:
    """Text-only loopback OpenAI-compatible runtime; no proxy or redirects."""
    provider = AIProvider.LOCAL

    def __init__(self, base_url: str, model: str, timeout: float):
        self.base_url, self.model, self.timeout = base_url.rstrip('/'), model, timeout
        self.session: aiohttp.ClientSession | None = None

    async def complete(self, messages, tools, max_output_tokens, web_search=False):
        if tools or web_search:
            raise ProviderError("Local backend is text-only")
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        try:
            async with self.session.post(self.base_url + '/chat/completions',
                                         json={"model": self.model, "messages": messages,
                                               "max_tokens": min(max(64, max_output_tokens), 4096),
                                               "temperature": .35}, allow_redirects=False) as response:
                if response.status != 200:
                    raise ProviderError(f"Local inference status={response.status}")
                body = bytearray()
                async for chunk in response.content.iter_chunked(8192):
                    body.extend(chunk)
                    if len(body) > 131072:
                        raise ProviderError("Local inference response exceeded size limit")
                data = json.loads(body)
                message = data['choices'][0]['message']
                text = message.get('content')
                if not isinstance(text, str) or not text.strip() or message.get('tool_calls'):
                    raise ProviderError("Local inference returned unusable text")
                return ProviderReply(AIProvider.LOCAL, self.model,
                                     {"role": "assistant", "content": text[:12000]}, text[:12000])
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"Local inference failed: {type(exc).__name__}") from exc

    async def close(self):
        if self.session is not None:
            await self.session.close()
            self.session = None


class ProviderManager:
    """Provider chain with transient-failure cooldowns and search routing."""

    GROQ_MODEL = "openai/gpt-oss-120b"
    GROQ_BASE_URL = "https://api.groq.com/openai/v1"

    PROVIDER_COOLDOWN_SECONDS = 300.0

    def __init__(self, config: BrainConfig | None = None) -> None:
        self.config = config or BrainConfig.from_env()
        self.providers: list[CompatibleProvider] = []
        self.local: LocalModelProvider | None = None
        self._local_capacity = asyncio.Semaphore(1)
        self.calls = 0
        self.local_calls = 0
        self.failures = 0
        self.duration_ms = 0.0
        self._budget_started = time.monotonic()
        self._budget_calls = 0
        self._usage: dict[tuple[str, str], Counter] = {}
        self.chat_provider: CompatibleProvider | None = None
        if self.config.local_enabled and self.config.local_model:
            url = urlsplit(self.config.local_url)
            # Only explicit loopback backends are treated as private local inference.
            if (url.scheme not in {"http", "https"} or url.hostname not in
                    {"localhost", "127.0.0.1", "::1"} or url.username or url.password
                    or url.query or url.fragment):
                raise ValueError("AI_LOCAL_URL must be a loopback inference endpoint")
            self.local = LocalModelProvider(self.config.local_url, self.config.local_model,
                                            self.config.local_timeout)
        self._cooldown_until: dict[AIProvider, float] = {}
        try:
            self.provider_cooldown_seconds = max(
                60.0,
                float(os.getenv("AI_PROVIDER_COOLDOWN_SECONDS", "300"))
            )
        except (TypeError, ValueError):
            self.provider_cooldown_seconds = 300.0

        # Groq is the only hosted generation provider.
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        groq_model = os.getenv("GROQ_MODEL", self.GROQ_MODEL).strip()
        if groq_key and self.config.external_enabled:
            self.providers.append(
                CompatibleProvider(
                    AIProvider.GROQ,
                    groq_key,
                    self.GROQ_BASE_URL,
                    groq_model or self.GROQ_MODEL,
                )
            )
            chat_model = os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-20b").strip()
            if chat_model and chat_model != self.providers[0].model:
                self.chat_provider = CompatibleProvider(
                    AIProvider.GROQ, groq_key, self.GROQ_BASE_URL, chat_model,
                )

    @property
    def available(self) -> bool:
        return bool(self.providers or self.local)

    @property
    def names(self) -> list[str]:
        return [f"{item.provider.value}:{item.model}" for item in
                ([self.local] if self.local else []) + self.providers]

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
            for item in ([self.local] if self.local else []) + self.providers
        }

    def metrics(self) -> dict[str, Any]:
        return {"external_calls": self.calls, "local_calls": self.local_calls,
                "failures": self.failures, "last_completion_ms": round(self.duration_ms, 2),
                "hourly_calls_used": self._budget_calls,
                "hourly_call_limit": self.config.external_call_limit,
                "first_token_ms": None,
                "chat_model": self.chat_provider.model if self.chat_provider else None,
                "token_usage": [{"provider": provider, "model": model, **dict(counts)}
                                for (provider, model), counts in self._usage.items()]}

    def record_usage(self, provider: str, model: str, usage: Any) -> None:
        """Aggregate provider-reported usage only; retain no prompts or user IDs."""
        key = (provider, model)
        if key not in self._usage:
            if len(self._usage) >= 32:
                return
            self._usage[key] = Counter()
        counts = self._usage[key]
        counts["responses"] += 1
        def value(name):
            return usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        reported = False
        for target, source in (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens")):
            amount = value(source)
            if isinstance(amount, int) and not isinstance(amount, bool) and amount >= 0:
                counts[target] += amount
                reported = True
        details = value("prompt_tokens_details")
        cached = details.get("cached_tokens") if isinstance(details, dict) else getattr(details, "cached_tokens", None)
        if isinstance(cached, int) and not isinstance(cached, bool) and cached >= 0:
            counts["cached_input_tokens"] += cached
        counts["responses_with_usage" if reported else "responses_without_usage"] += 1

    def reserve_external(self) -> None:
        """Reserve one external attempt, including legacy feature requests."""
        if not self.config.external_enabled:
            raise ProviderError("External inference disabled")
        self._charge()

    def inherit_accounting(self, previous: ProviderManager) -> None:
        """Credential reload must not reset the process call budget or usage."""
        for name in ("calls", "local_calls", "failures", "_budget_started", "_budget_calls", "_usage"):
            setattr(self, name, getattr(previous, name))

    def _charge(self):
        now = time.monotonic()
        if now - self._budget_started >= 3600:
            self._budget_calls = 0
            self._budget_started = now
        if self._budget_calls >= self.config.external_call_limit:
            raise ProviderError("External provider call budget exhausted")
        self._budget_calls += 1
        self.calls += 1

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_output_tokens: int,
        web_search: bool = False,
        allow_external: bool = True,
        prefer_local: bool = True,
        prefer_economy: bool = False,
    ) -> ProviderReply:
        allow_external = allow_external and self.config.external_enabled
        # Local models are deliberately text-only until their tool support is tested.
        if (self.local and not tools and not web_search
                and (prefer_local or not allow_external or not self.providers)
                and (not allow_external or sum(len(str(m.get('content') or '')) for m in messages) < 16000)):
            try:
                self.local_calls += 1
                started = time.monotonic()
                async def run_local():
                    async with self._local_capacity:
                        return await self.local.complete(messages, [], max_output_tokens)
                reply = await asyncio.wait_for(run_local(), timeout=self.config.local_timeout)
                if reply.text.strip() and not reply.tool_calls:
                    self.duration_ms = (time.monotonic() - started) * 1000
                    return reply
            except (ProviderError, asyncio.TimeoutError):
                self.failures += 1
        if not allow_external:
            raise ProviderError("External inference disabled; no suitable local response available")
        if not self.providers:
            raise ProviderError(
                "No AI provider configured. Set GROQ_API_KEY."
            )

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

            ordered = groq_providers
        else:
            ordered = [item for item in self.providers if item.provider is AIProvider.GROQ]
            if prefer_economy and not tools and self.chat_provider is not None:
                ordered = [self.chat_provider, *ordered]

        errors: list[str] = []

        for provider in ordered:
            for attempt in range(self.config.provider_retries + 1):
                try:
                    self.reserve_external()
                    started = time.monotonic()
                    reply = await provider.complete(
                        messages=messages,
                        tools=tools,
                        max_output_tokens=max_output_tokens,
                        web_search=(web_search and provider.provider is AIProvider.GROQ),
                    )
                    self.duration_ms = (time.monotonic() - started) * 1000
                    self._cooldown_until.pop(provider.provider, None)
                    self.record_usage(reply.provider.value, reply.model, {
                        "prompt_tokens": reply.input_tokens,
                        "completion_tokens": reply.output_tokens,
                        "prompt_tokens_details": {"cached_tokens": reply.cached_input_tokens},
                    })
                    return reply
                except ProviderError as exc:
                    self.failures += 1
                    errors.append(str(exc))
                    logger.warning("Provider failure | provider=%s type=%s", provider.provider.value, type(exc).__name__)
                    if self._is_transient_failure(exc) and attempt < self.config.provider_retries:
                        delay = getattr(exc, "retry_after", None)
                        if delay is not None and delay > 60:
                            break
                        await asyncio.sleep(delay if delay is not None else 0.25 * 2 ** attempt)
                        continue
                    break
            if errors and self._is_transient_failure(ProviderError(errors[-1])):
                self._cooldown_until[provider.provider] = time.monotonic() + self.provider_cooldown_seconds

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
        for provider in ([self.local] if self.local else []) + self.providers + ([self.chat_provider] if self.chat_provider else []):
            try:
                await provider.close()
            except Exception as exc:
                logger.warning(
                    "Failed closing %s provider: %s",
                    provider.provider.value,
                    type(exc).__name__,
                )
