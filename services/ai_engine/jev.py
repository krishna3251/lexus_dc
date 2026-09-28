"""Jev decision layer for compact, typed AI evaluations.

Jev is intentionally kept separate from the generative provider chain. It is
used for narrow application decisions where a typed boolean/choice/score is
more appropriate than another prose-generation turn.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class JevAnswer:
    """Normalized Jev answer independent of the transport shape."""

    name: str
    answer_type: str
    value: Any = None
    probability: float | None = None
    probabilities: dict[str, float] = field(default_factory=dict)
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class JevResult:
    """Bounded, provider-neutral result from a Jev evaluation."""

    success: bool
    answers: dict[str, JevAnswer] = field(default_factory=dict)
    latency_ms: float = 0.0
    cached: bool = False
    error: str | None = None


class JevDecisionService:
    """Small HTTP client for Jev through Vercel AI Gateway.

    This service is deliberately not part of ProviderManager because Jev does
    typed decisions rather than chat completions. The normal Groq -> Gemini
    generation chain stays untouched.
    """

    ENDPOINT = "https://ai-gateway.vercel.sh/v1/evaluate"
    MODEL = "typesafe-ai/jev"

    DEFAULT_TIMEOUT_SECONDS = 8.0
    DEFAULT_CACHE_TTL_SECONDS = 30.0
    DEFAULT_CACHE_SIZE = 256
    DEFAULT_MAX_STATE_CHARS = 6000
    DEFAULT_NO_TOOLS_THRESHOLD = 0.08
    FAILURE_COOLDOWN_SECONDS = 60.0

    TOOL_GATE_INTENTS = {
        "server_query",
        "security_query",
        "help",
    }

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, JevResult]] = {}
        self._cooldown_until = 0.0
        self._configure_from_env()

    def _configure_from_env(self) -> None:
        self.api_key = os.getenv("AI_GATEWAY_API_KEY", "").strip()
        self.endpoint = (
            os.getenv("JEV_API_URL", self.ENDPOINT).strip()
            or self.ENDPOINT
        )
        self.model = (
            os.getenv("JEV_MODEL", self.MODEL).strip()
            or self.MODEL
        )
        self.enabled = self._get_bool("JEV_ENABLED", True)
        self.tool_gate_enabled = self._get_bool("JEV_TOOL_GATE_ENABLED", True)
        self.timeout_seconds = self._get_float(
            "JEV_TIMEOUT_SECONDS",
            self.DEFAULT_TIMEOUT_SECONDS,
            minimum=2.0,
            maximum=15.0,
        )
        self.cache_ttl_seconds = self._get_float(
            "JEV_CACHE_TTL_SECONDS",
            self.DEFAULT_CACHE_TTL_SECONDS,
            minimum=0.0,
            maximum=300.0,
        )
        self.cache_size = self._get_int(
            "JEV_CACHE_SIZE",
            self.DEFAULT_CACHE_SIZE,
            minimum=16,
            maximum=2048,
        )
        self.max_state_chars = self._get_int(
            "JEV_MAX_STATE_CHARS",
            self.DEFAULT_MAX_STATE_CHARS,
            minimum=500,
            maximum=20000,
        )
        self.no_tools_threshold = self._get_float(
            "JEV_NO_TOOLS_THRESHOLD",
            self.DEFAULT_NO_TOOLS_THRESHOLD,
            minimum=0.01,
            maximum=0.25,
        )

    @staticmethod
    def _get_bool(key: str, default: bool) -> bool:
        value = os.getenv(key)
        if value is None:
            return default
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
            "enable",
            "enabled",
        }

    @staticmethod
    def _get_int(
        key: str,
        default: int,
        *,
        minimum: int,
        maximum: int,
    ) -> int:
        try:
            value = int(os.getenv(key, str(default)).strip())
        except (TypeError, ValueError):
            return default
        return max(minimum, min(value, maximum))

    @staticmethod
    def _get_float(
        key: str,
        default: float,
        *,
        minimum: float,
        maximum: float,
    ) -> float:
        try:
            value = float(os.getenv(key, str(default)).strip())
        except (TypeError, ValueError):
            return default
        return max(minimum, min(value, maximum))

    @property
    def available(self) -> bool:
        return bool(self.enabled and self.api_key)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def cooldown_seconds(self) -> float:
        return max(0.0, self._cooldown_until - time.monotonic())

    def health(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "configured": self.configured,
            "enabled": self.enabled,
            "tool_gate_enabled": self.tool_gate_enabled,
            "model": self.model,
            "cache_entries": len(self._cache),
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "cooldown_seconds": self.cooldown_seconds,
        }

    async def reload(self) -> None:
        """Reload the Jev environment settings without touching generation providers."""
        self._configure_from_env()
        self._cache.clear()
        self._cooldown_until = 0.0

    async def close(self) -> None:
        """Reserved for interface symmetry; the client is per-request."""
        self._cache.clear()

    def _normalize_state(self, state: Any) -> tuple[Any, str]:
        if isinstance(state, str):
            normalized = state.strip()
            if not normalized:
                raise ValueError("state must not be empty")
            serialized = normalized
            if len(serialized) > self.max_state_chars:
                raise ValueError("state_too_large")
            return normalized, serialized

        serialized = json.dumps(
            state,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        if len(serialized) > self.max_state_chars:
            raise ValueError("state_too_large")
        return state, serialized

    def _cache_key(self, state_json: str, questions: dict[str, Any]) -> str:
        material = json.dumps(
            {
                "model": self.model,
                "state": state_json,
                "questions": questions,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def _prune_cache(self, now: float) -> None:
        expired = [
            key
            for key, (expires_at, _) in self._cache.items()
            if expires_at <= now
        ]
        for key in expired:
            self._cache.pop(key, None)

        while len(self._cache) > self.cache_size:
            oldest_key = min(
                self._cache,
                key=lambda item: self._cache[item][0],
            )
            self._cache.pop(oldest_key, None)

    @staticmethod
    def _validate_questions(questions: dict[str, Any]) -> None:
        if not questions:
            raise ValueError("questions must not be empty")
        if len(questions) > 12:
            raise ValueError("too_many_questions")

        for name, question in questions.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("question names must be non-empty strings")
            if not isinstance(question, dict):
                raise ValueError(f"question {name!r} must be an object")
            question_type = question.get("type")
            if question_type not in {"boolean", "choice", "score"}:
                raise ValueError(f"unsupported Jev question type: {question_type!r}")
            instructions = str(question.get("instructions") or "").strip()
            if not instructions:
                raise ValueError(f"question {name!r} needs instructions")
            if len(instructions) > 1200:
                raise ValueError(f"question {name!r} instructions are too long")

            if question_type == "choice":
                criteria = question.get("criteria")
                if not isinstance(criteria, dict) or not criteria:
                    raise ValueError(f"choice question {name!r} needs criteria")
                if len(criteria) > 12:
                    raise ValueError(f"choice question {name!r} has too many options")

    @staticmethod
    def _as_probability(value: Any) -> float | None:
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if 0.0 <= number <= 1.0:
            return number
        return None

    @classmethod
    def _parse_answers(
        cls,
        body: dict[str, Any],
    ) -> dict[str, JevAnswer]:
        raw_answers = body.get("answers")
        if not isinstance(raw_answers, dict):
            raise ValueError("Jev response did not contain answers")

        metadata = body.get("providerMetadata") or body.get("provider_metadata") or {}
        typesafe_meta = (
            metadata.get("typesafe", {})
            if isinstance(metadata, dict)
            else {}
        )
        confidence_map = (
            typesafe_meta.get("confidence", {})
            if isinstance(typesafe_meta, dict)
            else {}
        )

        answers: dict[str, JevAnswer] = {}
        for name, raw in raw_answers.items():
            if not isinstance(raw, dict):
                continue

            answer_type = str(raw.get("type") or "").strip().casefold()
            if answer_type == "boolean":
                answer_type = "boolean"
            elif "choice" in raw or "probabilities" in raw:
                answer_type = "choice"
            elif "score" in raw:
                answer_type = "score"
            else:
                answer_type = str(raw.get("type") or "unknown")

            value = raw.get("value")
            probability = cls._as_probability(raw.get("probability"))
            if probability is None:
                probability = cls._as_probability(raw.get("noul"))

            choice = raw.get("choice")
            if choice is not None:
                value = choice

            score = raw.get("score")
            if score is not None:
                value = score

            probabilities: dict[str, float] = {}
            raw_probabilities = raw.get("probabilities")
            if isinstance(raw_probabilities, dict):
                for option, option_probability in raw_probabilities.items():
                    parsed = cls._as_probability(option_probability)
                    if parsed is not None:
                        probabilities[str(option)] = parsed

            if probability is None and value is not None and probabilities:
                selected = probabilities.get(str(value))
                probability = cls._as_probability(selected)

            raw_confidence = (
                confidence_map.get(name)
                if isinstance(confidence_map, dict)
                else None
            )
            confidence = cls._as_probability(raw_confidence)

            answers[str(name)] = JevAnswer(
                name=str(name),
                answer_type=answer_type,
                value=value,
                probability=probability,
                probabilities=probabilities,
                confidence=confidence,
            )

        if not answers:
            raise ValueError("Jev response contained no usable answers")
        return answers

    async def evaluate(
        self,
        state: Any,
        questions: dict[str, Any],
    ) -> JevResult:
        """Evaluate bounded application state with typed Jev questions."""
        started = time.perf_counter()

        if not self.available:
            return JevResult(
                success=False,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                error="jev_not_configured",
            )

        now = time.monotonic()
        self._prune_cache(now)

        if self.cooldown_seconds > 0:
            return JevResult(
                success=False,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                error="jev_cooldown",
            )

        try:
            payload_state, serialized_state = self._normalize_state(state)
            self._validate_questions(questions)
        except ValueError as exc:
            return JevResult(
                success=False,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                error=str(exc),
            )

        cache_key = self._cache_key(serialized_state, questions)
        cached = self._cache.get(cache_key)
        if cached and cached[0] > now:
            result = cached[1]
            return JevResult(
                success=result.success,
                answers=result.answers,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                cached=True,
                error=result.error,
            )

        payload = {
            "model": self.model,
            "state": payload_state,
            "questions": questions,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.endpoint,
                    json=payload,
                    headers=headers,
                ) as response:
                    body = await response.json(content_type=None)
                    if response.status >= 400:
                        message = (
                            body.get("error")
                            if isinstance(body, dict)
                            else body
                        )
                        raise RuntimeError(
                            f"HTTP {response.status}: {str(message)[:500]}"
                        )

            answers = self._parse_answers(body)
            result = JevResult(
                success=True,
                answers=answers,
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
            if self.cache_ttl_seconds > 0:
                self._cache[cache_key] = (
                    time.monotonic() + self.cache_ttl_seconds,
                    result,
                )
                self._prune_cache(time.monotonic())
            return result

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error_text = str(exc)
            if any(
                marker in error_text
                for marker in ("HTTP 429", "HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504")
            ):
                self._cooldown_until = (
                    time.monotonic() + self.FAILURE_COOLDOWN_SECONDS
                )
            logger.warning("Jev evaluation failed: %s", exc)
            return JevResult(
                success=False,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                error=f"jev_request_failed:{type(exc).__name__}",
            )

    async def should_use_discord_tools(
        self,
        prompt: str,
        intent: str,
    ) -> bool | None:
        """Use Jev as a conservative, token-saving tool-schema gate.

        A False result is returned only when Jev gives a very low probability
        that live Discord inspection is required. Any failure/uncertainty leaves
        the original deterministic planner untouched.
        """
        if not self.tool_gate_enabled:
            return None
        if intent not in self.TOOL_GATE_INTENTS:
            return None

        result = await self.evaluate(
            state={
                "intent": intent,
                "request": prompt.strip()[:2400],
            },
            questions={
                "discord_tools": {
                    "type": "boolean",
                    "instructions": (
                        "Does this request require Lexus to inspect live Discord "
                        "server state or use a Discord tool to answer it?"
                    ),
                }
            },
        )
        if not result.success:
            return None

        answer = result.answers.get("discord_tools")
        if answer is None or answer.probability is None:
            return None

        return answer.probability > self.no_tools_threshold
