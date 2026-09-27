"""Data models for the Lexus AI Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class AIProvider(str, Enum):
    GEMINI = "gemini"
    GROQ = "groq"


@dataclass(slots=True)
class AIRequest:
    user_id: int
    guild_id: Optional[int]
    channel_id: Optional[int]
    prompt: str
    system_prompt: Optional[str] = None
    max_output_tokens: int = 700
    max_iterations: int = 4


@dataclass(slots=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class ProviderReply:
    provider: AIProvider
    model: str
    assistant_message: dict[str, Any]
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None


@dataclass(slots=True)
class ToolResult:
    success: bool
    output: Any
    error: Optional[str] = None


@dataclass(slots=True)
class AIResult:
    success: bool
    text: str
    provider: Optional[AIProvider] = None
    model: Optional[str] = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    iterations: int = 0
    error: Optional[str] = None
