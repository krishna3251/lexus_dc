"""Request orchestration regressions without live providers or Discord mutations."""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from services.ai_engine.brain import ResponseStyle
from services.ai_engine.engine import AIEngine
from services.ai_engine.models import AIIntent, AIProvider, AIRequest, ProviderReply, ToolCall
from services.ai_engine.orchestrator import ContextBudgetExceeded, RequestOrchestrator, serialize_observation
from services.ai_engine.providers import CompatibleProvider, ProviderManager
from services.ai_engine.router import RequestRouter
from services.ai_engine.tools import ToolContext, ToolRegistry, ToolSpec


def final(text="Result checked."):
    return ProviderReply(AIProvider.GROQ, "openai/gpt-oss-120b",
                         {"role": "assistant", "content": text}, text)


def inspect(call_id):
    call = ToolCall(call_id, "inspect", {})
    return ProviderReply(AIProvider.GROQ, "test", {
        "role": "assistant", "content": None,
        "tool_calls": [{"id": call_id, "type": "function",
                        "function": {"name": "inspect", "arguments": "{}"}}],
    }, tool_calls=[call])


class PlanningTests(unittest.TestCase):
    def test_freshness_keeps_server_questions_on_discord_and_explicit_search_on_web(self):
        for prompt in ("today server report", "how many channels do we currently have?", "our server activity today"):
            self.assertEqual(RequestRouter.route(prompt).intent, AIIntent.SERVER_QUERY)
        self.assertEqual(RequestRouter.route("search latest Discord server pricing").intent, AIIntent.SEARCH)
        self.assertEqual(RequestRouter.route("latest Hyderabad news").intent, AIIntent.SEARCH)

    def test_reasoning_budget_tracks_task_complexity(self):
        orchestrator = RequestOrchestrator()
        levels = []
        for prompt in ("hello", "debug this Python function", "review architecture and optimize this workflow"):
            request = AIRequest(1, None, 2, prompt)
            plan = orchestrator.plan(request, RequestRouter.route(prompt), ResponseStyle.choose(prompt))
            levels.append(plan.reasoning_effort)
            self.assertLessEqual(plan.completion_tokens, 4096)
        self.assertEqual(levels, ["low", "medium", "high"])

    def test_truncated_tool_observations_retain_valid_json_and_failure_status(self):
        for success in (True, False):
            raw = serialize_observation({"success": success, "result": '"\\🔥' * 600, "error": "timeout " * 200}, 280)
            self.assertLessEqual(len(raw), 280)
            parsed = json.loads(raw)
            self.assertEqual(parsed["success"], success)
            self.assertTrue(parsed["truncated"])

    def test_context_compaction_preserves_request_and_complete_tool_protocol(self):
        messages = [
            {"role": "system", "content": "policy"},
            {"role": "user", "content": "old question " * 150},
            {"role": "assistant", "content": "old answer " * 150},
            {"role": "user", "content": "current request"},
            inspect("call-1").assistant_message,
            {"role": "tool", "tool_call_id": "call-1", "name": "inspect",
             "content": json.dumps({"success": True, "result": "data " * 1000})},
        ]
        orchestrator = RequestOrchestrator()
        orchestrator.fit_messages(messages, [], 1600)
        self.assertEqual([m["role"] for m in messages], ["system", "user", "assistant", "tool"])
        self.assertEqual(messages[1]["content"], "current request")
        self.assertTrue(json.loads(messages[-1]["content"])["success"])
        self.assertLessEqual(len(json.dumps({"messages": messages, "tools": []}, ensure_ascii=False)), 1600)
        with self.assertRaises(ContextBudgetExceeded):
            orchestrator.fit_messages([{"role": "user", "content": "required " * 200}], [], 500)


class OrchestrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"AI_SQLITE_PATH": self.temp.name + "/brain.db",
                                          "GROQ_API_KEY": "", "AI_GATEWAY_API_KEY": "", "AI_LOCAL_ENABLED": "false"})
        self.env.start()
        self.provider = SimpleNamespace(available=True, complete=AsyncMock(), close=AsyncMock())
        self.registry = ToolRegistry()
        self.handler = AsyncMock(return_value={"members": 7})
        self.registry.register(ToolSpec("inspect", "Inspect server", {"type": "object", "properties": {}}, self.handler))
        self.registry.register(ToolSpec("danger", "Mutate server", {"type": "object", "properties": {}}, AsyncMock(), mutating=True))
        self.engine = AIEngine(provider_manager=self.provider, tool_registry=self.registry)
        self.context = ToolContext(SimpleNamespace(is_ready=lambda: True), None,
                                   SimpleNamespace(id=2), SimpleNamespace(id=1))

    async def asyncTearDown(self):
        await self.engine.close()
        self.env.stop()
        self.temp.cleanup()

    async def test_duplicate_reads_reuse_evidence_and_conclude(self):
        self.provider.complete.side_effect = [inspect("a"), inspect("b"), final()]
        result = await self.engine.ask(AIRequest(1, None, 2, "inspect this server"), self.context)
        self.assertTrue(result.success)
        self.handler.assert_awaited_once()
        calls = self.provider.complete.await_args_list
        self.assertEqual([s["function"]["name"] for s in calls[0].kwargs["tools"]], ["inspect"])
        self.assertEqual(calls[2].kwargs["tools"], [])
        outputs = [json.loads(m["content"]) for m in calls[2].kwargs["messages"] if m["role"] == "tool"]
        self.assertTrue(all(output["success"] for output in outputs))
        self.assertEqual(self.engine.orchestrator.metrics()["reused_reads"], 1)

    async def test_large_observations_are_compacted_during_the_tool_loop(self):
        self.handler.return_value = {"members": 7, "details": "large result " * 2000}
        self.provider.complete.side_effect = [inspect("a"), inspect("b"), final()]
        result = await self.engine.ask(AIRequest(1, None, 2, "inspect this server"), self.context)
        self.assertTrue(result.success)
        self.assertGreater(self.engine.orchestrator.context_compactions, 0)
        for message in self.provider.complete.await_args.kwargs["messages"]:
            if message["role"] == "tool":
                self.assertTrue(json.loads(message["content"])["success"])

    async def test_failed_read_can_retry_once_before_concluding(self):
        self.handler.side_effect = [RuntimeError("transient test failure"), {"members": 7}]
        self.provider.complete.side_effect = [inspect("a"), inspect("b"), final()]
        result = await self.engine.ask(AIRequest(1, None, 2, "inspect this server"), self.context)
        self.assertTrue(result.success)
        self.assertEqual(self.handler.await_count, 2)

    async def test_budget_reserves_a_final_answer_and_prevents_last_step_execution(self):
        self.provider.complete.side_effect = [inspect("a"), inspect("b")]
        result = await self.engine.ask(AIRequest(1, None, 2, "inspect this server", max_iterations=2), self.context)
        self.assertEqual(result.error, "max_iterations")
        self.handler.assert_awaited_once()
        self.assertEqual(self.provider.complete.await_args_list[-1].kwargs["tools"], [])

    async def test_native_reasoning_reaches_supported_groq_model_only(self):
        for model in ("openai/gpt-oss-120b", "custom-model"):
            provider = CompatibleProvider(AIProvider.GROQ, "test-placeholder", "https://example.com", model)
            create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content="Answer", tool_calls=[]), finish_reason="stop")], usage=None))
            provider.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)), close=AsyncMock())
            await provider.complete([], [], 2000, reasoning_effort="high")
            if model.startswith("openai/gpt-oss"):
                self.assertEqual(create.await_args.kwargs["reasoning_effort"], "high")
                self.assertFalse(create.await_args.kwargs["extra_body"]["include_reasoning"])
            else:
                self.assertNotIn("reasoning_effort", create.await_args.kwargs)
            await provider.close()

    async def test_complex_request_uses_primary_reasoning_budget_through_normal_entry(self):
        manager = ProviderManager()
        primary = CompatibleProvider(AIProvider.GROQ, "test-placeholder", "https://example.com", "openai/gpt-oss-120b")
        economy = CompatibleProvider(AIProvider.GROQ, "test-placeholder", "https://example.com", "openai/gpt-oss-20b")
        primary.complete = AsyncMock(return_value=final())
        economy.complete = AsyncMock(return_value=final())
        manager.providers = [primary]
        manager.chat_provider = economy
        self.engine.providers = manager
        result = await self.engine.ask(AIRequest(1, None, 2, "review architecture and optimize this workflow"), self.context)
        self.assertTrue(result.success)
        economy.complete.assert_not_awaited()
        self.assertEqual(primary.complete.await_args.kwargs["reasoning_effort"], "high")
        self.assertGreater(primary.complete.await_args.kwargs["max_output_tokens"], 700)
        self.assertEqual(manager.calls, 1)
