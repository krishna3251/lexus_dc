"""Local orchestration primitives, not a substitute for language-model reasoning."""
from __future__ import annotations

import ast
import asyncio
import math
import operator
import re
import time
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import dataclass

from services.cache import TTLCache
from .config import BrainConfig

Scope = tuple[int, int | None, int | None]


class BrainBusy(RuntimeError):
    pass


class RequestCapacity:
    """No wait queue: active locks cannot expire/evict while held."""
    def __init__(self, config: BrainConfig):
        self.config = config
        self.scopes: set[Scope] = set()
        self.guilds: Counter = Counter()
        self.users: Counter = Counter()
        self.tasks: set[asyncio.Task] = set()
        self.by_scope: dict[Scope, asyncio.Task] = {}
        self.rates = TTLCache[int, list[float]](5000, 60)
        self.closed = False

    @asynccontextmanager
    async def acquire(self, scope: Scope):
        user, guild, _ = scope
        # DM users have separate capacity buckets.
        bucket = (guild, None if guild is not None else user)
        now = time.monotonic()
        recent = [stamp for stamp in self.rates.get(user, []) if now - stamp < 60]
        if (self.closed or scope in self.scopes or self.users[user] >= 1
                or len(recent) >= 12
                or len(self.scopes) >= self.config.max_concurrent
                or self.guilds[bucket] >= self.config.per_guild):
            raise BrainBusy("request capacity reached")
        self.rates.set(user, recent + [now])
        task = asyncio.current_task()
        self.scopes.add(scope)
        self.guilds[bucket] += 1
        self.users[user] += 1
        self.tasks.add(task)
        self.by_scope[scope] = task
        try:
            yield
        finally:
            self.scopes.discard(scope)
            self.tasks.discard(task)
            self.by_scope.pop(scope, None)
            self.guilds[bucket] -= 1
            self.users[user] -= 1
            if not self.guilds[bucket]:
                del self.guilds[bucket]
            if not self.users[user]:
                del self.users[user]

    async def close(self):
        self.closed = True
        pending = self.tasks - {asyncio.current_task()}
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    async def cancel_user(self, user: int, guild: int | None):
        pending = [task for scope, task in self.by_scope.items()
                   if scope[:2] == (user, guild) and task != asyncio.current_task()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


class ConversationState:
    """Only addressed conversations; bounded RAM history with absolute TTL."""
    def __init__(self, config: BrainConfig):
        self.config = config
        self._sessions: TTLCache[Scope, list[dict[str, str]]] = TTLCache(
            config.session_count, config.session_ttl)

    def recent(self, scope: Scope) -> list[dict[str, str]]:
        return list(self._sessions.get(scope) or [])

    def append(self, scope: Scope, prompt: str, response: str):
        history = self.recent(scope) + [
            {"role": "user", "content": prompt[:4000]},
            {"role": "assistant", "content": response[:4000]},
        ]
        history = bounded_turns(history, self.config.context_chars // 2)
        self._sessions.set(scope, history[-12:])

    def clear(self, user_id: int, guild_id: int | None):
        # Explicit deletion also covers other channels in the same user/guild scope.
        for scope in self._sessions.keys():
            if scope[:2] == (user_id, guild_id):
                self._sessions.delete(scope)

    def close(self):
        self._sessions.clear()


def bounded_turns(turns: list[dict[str, str]], max_chars: int) -> list[dict[str, str]]:
    result = []
    remaining = max_chars
    for turn in reversed(turns):
        content = str(turn.get("content", ""))
        if turn.get("role") not in {"user", "assistant"} or not content:
            continue
        if len(content) > remaining:
            break
        result.append({"role": turn["role"], "content": content})
        remaining -= len(content)
    return list(reversed(result))


@dataclass(slots=True, frozen=True)
class StyleDecision:
    name: str
    instruction: str
    output_tokens: int


class ResponseStyle:
    """Conservative cues guide a model; they do not generate canned chat replies."""
    STYLES = {
        "casual": "Be natural and brief; match the user's language and avoid repeated greetings.",
        "friendly": "Be warm and direct, without flattery or excessive emojis.",
        "playful": "A little humor fits; avoid forced slang or teasing sensitive topics.",
        "sarcastic": "Use only mild invited sarcasm; never insult a vulnerable person.",
        "serious": "Be calm and clear; no jokes, sarcasm, or exaggerated emotional claims.",
        "technical": "Be precise; explain assumptions and give usable steps or code when needed.",
        "helpful": "Answer first; include practical detail and acknowledge uncertainty.",
        "concise": "Use the shortest useful answer; omit introductions and follow-up offers.",
    }

    @classmethod
    def choose(cls, prompt: str, preference: str | None = None) -> StyleDecision:
        text = prompt.casefold()
        if re.search(r"\b(grief|suicide|depressed|died|emergency|serious|pareshan)\b", text):
            style = "serious"
        elif preference in cls.STYLES:
            style = preference
        elif re.search(r"\b(code|python|javascript|debug|traceback|sql|asyncio)\b", text):
            style = "technical"
        elif re.search(r"\b(brief|short|concise)\b", text):
            style = "concise"
        elif re.search(r"\b(explain|compare|steps|why|how)\b", text):
            style = "helpful"
        else:
            style = "casual"
        tokens = 650 if style in {"technical", "helpful", "serious"} else 220
        return StyleDecision(style, cls.STYLES[style], tokens)

    @staticmethod
    def clean(text: str, max_chars: int = 12000) -> str:
        # No semantic rewriting: preserve code, citations and action outcomes.
        text = re.sub(r"\AAs an AI (?:assistant|language model)[,:]?\s*", "", text.strip(), flags=re.I)
        return text[:max_chars].strip()


class Calculator:
    """Small AST interpreter with structural and numeric caps; never eval()."""
    OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
           ast.Mod: operator.mod, ast.Pow: operator.pow}

    @classmethod
    def calculate(cls, expression: str) -> str:
        if len(expression) > 180:
            raise ValueError("expression too long")
        tree = ast.parse(expression, mode="eval")
        if len(list(ast.walk(tree))) > 50:
            raise ValueError("expression too complex")

        def visit(node):
            if isinstance(node, ast.Expression):
                return visit(node.body)
            if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
                result = node.value
            elif isinstance(node, ast.UnaryOp) and type(node.op) in {ast.UAdd, ast.USub}:
                result = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
            elif isinstance(node, ast.BinOp) and type(node.op) in cls.OPS:
                left, right = visit(node.left), visit(node.right)
                if isinstance(node.op, ast.Pow) and abs(right) > 12:
                    raise ValueError("exponent too large")
                result = cls.OPS[type(node.op)](left, right)
            else:
                raise ValueError("only arithmetic is supported")
            if not isinstance(result, (int, float)) or not math.isfinite(result) or abs(result) > 1e15:
                raise ValueError("result outside supported range")
            return result
        return f"{visit(tree):g}"


class LocalSkills:
    def __init__(self):
        self.cache = TTLCache[str, str](256, 300)
        self.hits = 0
        self.misses = 0

    def respond(self, prompt: str, context) -> str | None:
        text = prompt.strip().casefold().rstrip("?")
        calc = re.fullmatch(r"(?:calculate|calc)\s+(.+)", text)
        expression = calc.group(1) if calc else text if re.fullmatch(r"[\d\s.+*/%()\-]+", text) else None
        if expression is not None:
            cached = self.cache.get(expression)
            if cached is not None:
                self.hits += 1
                return cached
            self.misses += 1
            try:
                result = Calculator.calculate(expression)
            except (ValueError, SyntaxError, ArithmeticError, TypeError):
                return "That calculation is invalid or exceeds the supported limits."
            self.cache.set(expression, result)
            return result
        # Exact unambiguous requests only. General questions still need a model.
        if text in {"server info", "server information", "member count", "server member count"} and context.guild:
            guild = context.guild
            return f"{guild.name}: {guild.member_count if guild.member_count is not None else 'unknown'} members."
        if text in {"my id", "user id"}:
            return str(context.user.id)
        if text in {"bot commands", "command list", "what commands can i use"}:
            names = sorted(command.qualified_name for command in getattr(context.bot, "commands", []) if not command.hidden)
            return "Commands: " + ", ".join(names)[:1600] if names else None
        return None


def needs_stronger_model(prompt: str) -> bool:
    """A cheap capability hint, not an LLM-based routing call or quality guarantee."""
    return len(prompt) > 1800 or bool(re.search(
        r"\b(deep analysis|prove|rigorous|complex reasoning|comprehensive|multi.step|architecture review)\b",
        prompt, re.I))
