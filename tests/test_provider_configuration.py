"""Offline credential loading, reload and truthful status regressions."""

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core import environment
from cogs.ai_engine import AIEngineCog
from services.ai_engine.engine import AIEngine
from services.ai_engine.models import AIProvider, AIRequest, ProviderReply
from services.ai_engine.providers import CompatibleProvider, ProviderManager
from services.ai_engine.tools import ToolContext


class EnvironmentFixture:
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.env_path = Path(temporary.name) / ".env"
        for context in (
            patch.object(environment, "ENV_PATH", self.env_path),
            patch.object(environment, "_file_values", {}),
            patch.dict(os.environ, {
                "GROQ_API_KEY": "", "GROQ_MODEL": "", "GROQ_CHAT_MODEL": "",
                "GROQ_VISION_MODEL": "", "AI_EXTERNAL_ENABLED": "true",
                "AI_LOCAL_ENABLED": "false", "PYTHON_DOTENV_DISABLED": "false",
                "AI_GATEWAY_API_KEY": "", "GOOGLE_API_KEY": "", "TAVILY_API_KEY": "",
                "AI_SQLITE_PATH": str(Path(temporary.name) / "brain.sqlite3"),
            }),
        ):
            context.start()
            self.addCleanup(context.stop)

    def write_env(self, content):
        self.env_path.write_text(content, encoding="utf-8-sig")


class EnvironmentTests(EnvironmentFixture, unittest.TestCase):
    def test_blank_process_key_uses_bom_and_quoted_project_key(self):
        self.write_env('GROQ_API_KEY="offline-file-key"\n')
        environment.load_environment()
        self.assertEqual(os.environ["GROQ_API_KEY"], "offline-file-key")
        self.assertEqual(environment.environment_source("GROQ_API_KEY"), "project .env")

    def test_platform_key_takes_precedence_even_on_reload(self):
        self.write_env("GROQ_API_KEY=offline-file-key\n")
        os.environ["GROQ_API_KEY"] = "offline-platform-key"
        environment.load_environment(refresh=True)
        self.assertEqual(os.environ["GROQ_API_KEY"], "offline-platform-key")
        self.assertEqual(environment.environment_source("GROQ_API_KEY"), "process environment")

    def test_reload_rotates_and_removes_file_owned_credentials(self):
        self.write_env("GROQ_API_KEY=offline-first-key\n")
        environment.load_environment()
        self.write_env("GROQ_API_KEY=offline-second-key\n")
        environment.load_environment(refresh=True, names=environment.PROVIDER_ENV_NAMES)
        self.assertEqual(os.environ["GROQ_API_KEY"], "offline-second-key")
        self.env_path.unlink()
        environment.load_environment(refresh=True, names=environment.PROVIDER_ENV_NAMES)
        self.assertNotIn("GROQ_API_KEY", os.environ)

    def test_runtime_platform_override_survives_file_rotation_and_removal(self):
        self.write_env("GROQ_API_KEY=offline-first-key\n")
        environment.load_environment()
        os.environ["GROQ_API_KEY"] = "offline-platform-key"
        self.write_env("GROQ_API_KEY=offline-second-key\n")
        environment.load_environment(refresh=True)
        self.env_path.unlink()
        environment.load_environment(refresh=True)
        self.assertEqual(os.environ["GROQ_API_KEY"], "offline-platform-key")

    def test_explicit_empty_chat_model_is_preserved(self):
        self.write_env("GROQ_CHAT_MODEL=file-model\n")
        environment.load_environment()
        self.assertEqual(os.environ["GROQ_CHAT_MODEL"], "")

    def test_provider_reload_does_not_change_discord_credentials_or_policy(self):
        os.environ.pop("DISCORD_TOKEN", None)
        os.environ.pop("AI_EXTERNAL_ENABLED", None)
        self.write_env("DISCORD_TOKEN=offline-first-token\nAI_EXTERNAL_ENABLED=false\n")
        environment.load_environment()
        self.write_env("DISCORD_TOKEN=offline-second-token\nAI_EXTERNAL_ENABLED=true\n")
        environment.load_environment(refresh=True, names=environment.PROVIDER_ENV_NAMES)
        self.assertEqual(os.environ["DISCORD_TOKEN"], "offline-first-token")
        self.assertEqual(os.environ["AI_EXTERNAL_ENABLED"], "false")

    def test_unrelated_working_directory_is_not_a_configuration_source(self):
        self.write_env("GROQ_API_KEY=offline-project-key\n")
        unrelated = self.env_path.parent / "unrelated"
        unrelated.mkdir()
        (unrelated / ".env").write_text("GROQ_API_KEY=offline-untrusted-key\n")
        previous = Path.cwd()
        try:
            os.chdir(unrelated)
            environment.load_environment()
        finally:
            os.chdir(previous)
        self.assertEqual(os.environ["GROQ_API_KEY"], "offline-project-key")

    def test_dotenv_disabled_does_not_load_or_refresh_file(self):
        self.write_env("GROQ_API_KEY=offline-file-key\n")
        os.environ["PYTHON_DOTENV_DISABLED"] = "true"
        environment.load_environment(refresh=True)
        self.assertEqual(os.environ["GROQ_API_KEY"], "")


class ProviderConfigurationTests(EnvironmentFixture, unittest.IsolatedAsyncioTestCase):
    async def make_engine(self):
        engine = AIEngine()
        self.addAsyncCleanup(engine.close)
        return engine

    def context(self, user_id=1):
        return ToolContext(SimpleNamespace(is_ready=lambda: True), None,
                           SimpleNamespace(id=2), SimpleNamespace(id=user_id))

    async def test_direct_manager_loads_file_and_reports_presence_without_secret(self):
        self.write_env("GROQ_API_KEY=offline-file-key\n")
        manager = ProviderManager()
        self.addAsyncCleanup(manager.close)
        self.assertTrue(manager.available)
        self.assertTrue(manager.configuration()["groq_key_present"])
        self.assertNotIn("offline-file-key", str(manager.configuration()) + str(manager.health()))

    async def test_reload_picks_up_file_added_after_startup_and_keeps_budget(self):
        engine = await self.make_engine()
        self.assertFalse(engine.providers.available)
        engine.providers.reserve_external()
        self.write_env("GROQ_API_KEY=offline-added-key\n")
        await engine.reload_providers()
        self.assertTrue(engine.providers.available)
        self.assertEqual(engine.providers.metrics()["hourly_calls_used"], 1)
        self.assertIs(engine.research.providers, engine.providers)

    async def test_reload_rotates_existing_file_key_and_closes_old_client(self):
        self.write_env("GROQ_API_KEY=offline-first-key\n")
        engine = await self.make_engine()
        old = engine.providers
        old.providers[0].client = SimpleNamespace(close=AsyncMock())
        close = old.providers[0].client.close
        self.write_env("GROQ_API_KEY=offline-second-key\n")
        await engine.reload_providers()
        self.assertEqual(engine.providers.providers[0]._api_key, "offline-second-key")
        close.assert_awaited_once()

    async def test_missing_provider_recovers_on_next_request_without_owner_command(self):
        engine = await self.make_engine()
        self.write_env("GROQ_API_KEY=offline-added-key\n")
        reply = ProviderReply(AIProvider.GROQ, "offline-test-model",
                              {"role": "assistant", "content": "A short story."}, "A short story.")
        with patch.object(CompatibleProvider, "complete", new=AsyncMock(return_value=reply)) as complete:
            result = await engine.ask(AIRequest(1, None, 2, "Tell me a short story"), self.context())
        self.assertTrue(result.success)
        self.assertEqual(result.text, "A short story.")
        complete.assert_awaited_once()

    async def test_missing_provider_refresh_is_bounded(self):
        engine = await self.make_engine()
        with patch.object(engine, "reload_providers", wraps=engine.reload_providers) as reload:
            for user_id in range(1, 4):
                result = await engine.ask(AIRequest(user_id, None, 2, "Tell me a story"), self.context(user_id))
                self.assertEqual(result.error, "no_provider")
            self.assertEqual(reload.await_count, 1)

    async def test_disabled_external_policy_is_not_misreported_as_missing_key(self):
        self.write_env("GROQ_API_KEY=offline-file-key\n")
        os.environ["AI_EXTERNAL_ENABLED"] = "false"
        engine = await self.make_engine()
        result = await engine.ask(AIRequest(1, None, 2, "Tell me a story"), self.context())
        self.assertEqual(result.error, "external_disabled")
        self.assertTrue(engine.providers.configuration()["groq_key_present"])
        self.assertNotIn("set GROQ_API_KEY", result.text)
        self.assertFalse(engine.providers.available)
        self.assertFalse(engine.config.external_enabled)

    async def test_status_and_reload_do_not_claim_unconfigured_ai_is_ready(self):
        cog = object.__new__(AIEngineCog)
        cog.engine = await self.make_engine()
        ctx = SimpleNamespace(send=AsyncMock())
        await AIEngineCog.ai_status.callback(cog, ctx)
        fields = {field.name: field.value for field in ctx.send.await_args.kwargs["embed"].fields}
        self.assertEqual(fields["Status"], "LOCAL SKILLS ONLY")
        self.assertIn("Groq key: missing", fields["Provider configuration"])
        ctx.send.reset_mock()
        await AIEngineCog.ai_reload.callback(cog, ctx)
        self.assertIn("No Groq key was found", ctx.send.await_args.args[0])
        self.assertNotIn("✅", ctx.send.await_args.args[0])

    async def test_request_during_reload_does_not_use_closing_provider(self):
        engine = await self.make_engine()
        engine._providers_reloading = True
        result = await engine.ask(AIRequest(1, None, 2, "Tell me a story"), self.context())
        self.assertEqual(result.error, "busy")
        self.assertFalse(engine.capacity.scopes)
