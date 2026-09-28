"""Discord interface for the Lexus AI Engine.

This cog exposes the unified V3 AI entry points while keeping existing cogs
coexisting with the engine.
"""

from __future__ import annotations

import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from services.ai_engine.engine import AIEngine
from services.ai_engine.models import AIRequest
from services.ai_engine.tools import ToolContext
from services.cache import TTLCache

logger = logging.getLogger(__name__)


class AIEngineCog(commands.Cog, name="AI Engine"):
    """Lexus V3 agent interface."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.engine = AIEngine()
        self.engine.register_default_tools(bot)
        self._handled_messages: TTLCache[int, bool] = TTLCache(
            max_size=10000,
            default_ttl=90.0,
        )

    async def cog_load(self) -> None:
        self.bot.ai_engine = self.engine
        await self.engine.memory.initialize()
        await self.engine.research.initialize()
        memory_health = self.engine.memory.health()
        logger.info(
            "🤖 Lexus AI Engine loaded | providers=%s | tools=%d | memory=%s",
            ", ".join(self.engine.provider_names) if self.engine.provider_names else "none",
            len(self.engine.tools.names()),
            memory_health["backend"],
        )

    async def cog_unload(self) -> None:
        if getattr(self.bot, "ai_engine", None) is self.engine:
            delattr(self.bot, "ai_engine")
        await self.engine.close()

    async def _run(
        self,
        user: discord.Member | discord.User,
        guild: discord.Guild | None,
        channel: discord.abc.GuildChannel | None,
        prompt: str,
    ) -> str:
        request = AIRequest(
            user_id=user.id,
            guild_id=guild.id if guild else None,
            channel_id=channel.id if channel else None,
            prompt=prompt,
        )
        result = await self.engine.ask(
            request,
            ToolContext(
                bot=self.bot,
                guild=guild,
                channel=channel,
                user=user,
            ),
        )

        if result.success:
            return result.text

        logger.warning(
            "AI request failed | provider=%s model=%s error=%s",
            result.provider,
            result.model,
            result.error,
        )
        if result.error and "Web search requires GROQ_API_KEY" in result.error:
            return ""
        return result.text or "The AI engine could not complete that request."

    @commands.command(name="aireload", help="Reload AI provider settings from the current process environment.")
    @commands.is_owner()
    async def ai_reload(self, ctx: commands.Context) -> None:
        await self.engine.reload_providers()
        providers = self.engine.provider_names or ["none"]
        jev_state = "enabled" if self.engine.health()["jev"]["available"] else "unavailable"
        await ctx.send(
            "✅ AI provider config reloaded. Providers: "
            + ", ".join(str(item) for item in providers)
            + f" | Jev: {jev_state}"
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Handle natural AI chat through the unified AI Engine."""
        if message.author.bot:
            return

        try:
            ctx = await self.bot.get_context(message)
            if ctx.valid:
                return
        except Exception:
            logger.exception("AI natural-chat context lookup failed")
            return

        prompt = await self._extract_natural_prompt(message)
        if not prompt:
            return

        db_claim = await self.engine.memory.claim_message(message.id)
        if db_claim is False:
            logger.warning(
                "Ignoring duplicate AI message across processes | message=%s",
                message.id,
            )
            return

        if self._handled_messages.contains(message.id):
            logger.warning(
                "Ignoring duplicate AI natural-chat event | message=%s",
                message.id,
            )
            return
        self._handled_messages.set(message.id, True)

        channel = (
            message.channel
            if isinstance(message.channel, discord.abc.GuildChannel)
            else None
        )

        try:
            async with message.channel.typing():
                response = await self._run(
                    message.author,
                    message.guild,
                    channel,
                    prompt,
                )
            await self._send_message_chunks(message.channel, response)
        except Exception:
            logger.exception(
                "AI natural chat failed | user=%s guild=%s channel=%s",
                message.author.id,
                getattr(message.guild, "id", None),
                message.channel.id,
            )
            await message.channel.send(
                "Arre yaar, abhi AI side pe thoda scene hai 😭. Ek baar phir try karo."
            )

    async def _extract_natural_prompt(self, message: discord.Message) -> str | None:
        """Extract a prompt from the configured prefix or bot mention."""
        content = message.content.strip()
        if not content:
            return None

        if self.bot.user and self.bot.user in message.mentions:
            pattern = rf"<@!?{self.bot.user.id}>\s*"
            prompt = re.sub(pattern, "", content, count=1).strip()
            return prompt or None

        try:
            prefixes = await self.bot.get_prefix(message)
        except Exception:
            prefixes = ["lx "]

        if isinstance(prefixes, str):
            prefixes = [prefixes]

        prefixes = list(prefixes) + ["lx ", "lex "]

        for prefix in dict.fromkeys(prefixes):
            if prefix and content.startswith(prefix):
                prompt = content[len(prefix):].strip()
                return prompt or None

        return None

    async def _send_message_chunks(
        self,
        channel: discord.abc.Messageable,
        response: str,
    ) -> None:
        """Send an AI response without exceeding Discord message limits."""
        if not response or not response.strip():
            return
        chunks = [
            response[i : i + 1900]
            for i in range(0, len(response), 1900)
        ]
        for chunk in chunks:
            await channel.send(chunk)

    @commands.command(
        name="ask",
        help="Ask Lexus AI Engine a question or request an allowed bot action.",
    )
    async def ask_prefix(self, ctx: commands.Context, *, prompt: str) -> None:
        async with ctx.typing():
            response = await self._run(
                ctx.author,
                ctx.guild,
                ctx.channel if isinstance(ctx.channel, discord.abc.GuildChannel) else None,
                prompt,
            )
        await self._send_chunked(ctx, response)

    @app_commands.command(
        name="ask",
        description="Ask Lexus AI Engine a question or request an allowed bot action.",
    )
    @app_commands.describe(prompt="What you want Lexus to inspect or do")
    async def ask_slash(
        self,
        interaction: discord.Interaction,
        prompt: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        channel = (
            interaction.channel
            if isinstance(interaction.channel, discord.abc.GuildChannel)
            else None
        )
        response = await self._run(
            interaction.user,
            interaction.guild,
            channel,
            prompt,
        )

        if not response or not response.strip():
            return
        chunks = [response[i : i + 1900] for i in range(0, len(response), 1900)]
        await interaction.followup.send(chunks[0])
        for chunk in chunks[1:]:
            await interaction.followup.send(chunk)

    @commands.command(name="aistatus", help="Show Lexus AI Engine provider status.")
    @commands.is_owner()
    async def ai_status(self, ctx: commands.Context) -> None:
        providers = self.engine.provider_names or ["none"]
        tools = len(self.engine.tools.names())
        health = self.engine.health()
        embed = discord.Embed(
            title="Lexus AI Engine",
            color=discord.Color.green() if self.engine.available else discord.Color.red(),
        )
        embed.add_field(
            name="Status",
            value="READY" if self.engine.available else "NOT CONFIGURED",
            inline=True,
        )
        embed.add_field(
            name="Providers",
            value="\n".join(str(item) for item in providers),
            inline=False,
        )
        embed.add_field(name="Tools", value=str(tools), inline=True)

        memory_value = (
            "✅ SQLite"
            if health["memory_available"]
            else "❌ SQLite unavailable"
        )
        if health["memory_available"]:
            size_kib = health["memory_size_bytes"] / 1024
            memory_value += f" ({size_kib:.1f} KiB)"

        embed.add_field(name="Memory", value=memory_value, inline=True)
        research = health["research"]
        search_parts = []
        if any(str(item).startswith("groq:") for item in providers):
            search_parts.append("Groq Browser Search")
        if research.get("gemini_google"):
            search_parts.append("Gemini Google (fallback)")
        if research.get("google_cse"):
            search_parts.append("Google CSE")
        embed.add_field(
            name="Research",
            value=("✅ " + " + ".join(search_parts)) if search_parts else "❌ No live search provider",
            inline=False,
        )
        rag = research["rag"]
        embed.add_field(
            name="RAG",
            value=(
                f"✅ SQLite • {rag['items']} items • {rag['embedding_dimensions']}d embeddings"
                if rag["available"]
                else "❌ RAG unavailable"
            ),
            inline=False,
        )

        cooldowns = health["provider_health"]
        cooldown_text = "\n".join(
            f"{name}: {data['cooldown_seconds']:.0f}s"
            for name, data in cooldowns.items()
            if data["cooldown_seconds"] > 0
        ) or "None"
        embed.add_field(
            name="Failover Cooldown",
            value=cooldown_text,
            inline=False,
        )
        jev = health["jev"]
        jev_value = (
            f"✅ {jev['model']} • tool gate enabled"
            if jev["available"] and jev["tool_gate_enabled"]
            else (
                f"✅ {jev['model']} • decision layer"
                if jev["available"]
                else "⚪ Jev decision layer unavailable"
            )
        )
        embed.add_field(
            name="Decision Layer",
            value=jev_value,
            inline=False,
        )
        embed.add_field(
            name="Models",
            value="openai/gpt-oss-120b (Groq primary)\ngemini-3.8-flash (fallback)\ntypesafe-ai/jev (typed decisions)",
            inline=False,
        )
        await ctx.send(embed=embed)

    async def _send_chunked(self, ctx: commands.Context, response: str) -> None:
        if not response or not response.strip():
            return
        chunks = [response[i : i + 1900] for i in range(0, len(response), 1900)]
        for chunk in chunks:
            await ctx.send(chunk)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AIEngineCog(bot))
