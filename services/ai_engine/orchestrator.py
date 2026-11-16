"""Request planning, capability selection, and bounded working context."""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import replace

from .brain import needs_stronger_model
from .models import AIIntent
from .permissions import AIPermissionGuard
from .planner import Planner


class ContextBudgetExceeded(ValueError):
    pass


def serialize_observation(result, limit):
    """Truncation remains valid JSON and retains the authoritative success flag."""
    raw = json.dumps(result, ensure_ascii=False, default=str)
    if len(raw) <= limit:
        return raw
    summary = {"success": result.get("success") is True, "truncated": True}
    key = "result_excerpt" if summary["success"] else "error"
    value = raw if summary["success"] else str(result.get("error", raw))
    low, high = 0, len(value)
    while low < high:
        middle = (low + high + 1) // 2
        summary[key] = value[:middle]
        if len(json.dumps(summary, ensure_ascii=False)) <= limit:
            low = middle
        else:
            high = middle - 1
    summary[key] = value[:low]
    return json.dumps(summary, ensure_ascii=False)


class RequestOrchestrator:
    """Application policy chooses resources; the configured model reasons."""
    def __init__(self):
        self.planner = Planner()
        self.reasoning_modes = Counter()
        self.reused_reads = 0
        self.context_compactions = 0

    def plan(self, request, route, style):
        plan = self.planner.build(route)
        complex_task = needs_stronger_model(request.prompt) or bool(re.search(
            r"\b(architecture|orchestrat\w*|root cause|trade.?offs|think carefully|think deeply|"
            r"reason carefully|optimi[sz]\w*)\b", request.prompt, re.I))
        if complex_task:
            effort = "high"
        elif style.name in {"technical", "helpful", "serious"} or route.intent in {
            AIIntent.SEARCH, AIIntent.SERVER_QUERY, AIIntent.SECURITY_QUERY, AIIntent.ACTION_REQUEST,
        }:
            effort = "medium"
        else:
            effort = "low"
        visible_tokens = min(max(64, request.max_output_tokens), style.output_tokens)
        reserve = {"low": 0, "medium": 512, "high": 1536}[effort]
        self.reasoning_modes[effort] += 1
        return replace(plan, reasoning_effort=effort,
                       completion_tokens=min(4096, visible_tokens + reserve))

    @staticmethod
    def instruction(plan):
        if plan.reasoning_effort == "low":
            return "Answer directly using the available context."
        return (
            "Resolve the request against the supplied evidence before answering. "
            "Identify the goal and constraints, inspect missing live facts with available tools, "
            "evaluate the observations, and check that the answer addresses the request. "
            "If an inspection fails or a result is truncated, state the limitation or request a narrower inspection. "
            "Never turn a missing observation or failed tool into a claim of success. "
            "Return the answer and a concise explanation of the relevant evidence and assumptions. "
            "Keep private deliberation out of the response."
        )

    @staticmethod
    def schemas(registry, context, plan):
        if not plan.allow_tools:
            return []
        allowed = {name for name in registry.names()
                   if AIPermissionGuard.check(registry.get(name), context, plan.allow_mutations).allowed}
        return [schema for schema in registry.schemas() if schema["function"]["name"] in allowed]

    def fit_messages(self, messages, schemas, limit):
        """Keep the current request and complete tool exchanges; compact observations."""
        def size():
            return len(json.dumps({"messages": messages, "tools": schemas}, ensure_ascii=False, default=str))

        current = max(i for i, message in enumerate(messages) if message["role"] == "user")
        while size() > limit and current > 1:
            remove = 2 if current > 2 and messages[1]["role"] == "user" and messages[2]["role"] == "assistant" else 1
            del messages[1:1 + remove]
            current -= remove
            self.context_compactions += 1
        observations = sorted((message for message in messages if message["role"] == "tool"),
                              key=lambda message: len(message["content"]), reverse=True)
        for message in observations:
            excess = size() - limit
            if excess <= 0:
                return
            target = max(180, len(message["content"]) - excess - 100)
            if target < len(message["content"]):
                message["content"] = serialize_observation(json.loads(message["content"]), target)
                self.context_compactions += 1
        if size() > limit:
            raise ContextBudgetExceeded("Required request context exceeds the configured budget")

    def metrics(self):
        return {"reasoning_modes": dict(self.reasoning_modes),
                "reused_reads": self.reused_reads,
                "context_compactions": self.context_compactions}
