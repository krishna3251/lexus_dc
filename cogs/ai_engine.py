"""Discord interface for the Lexus AI Engine.

This cog intentionally exposes a single clear entry point: `lx ask ...`
and its slash equivalent. Existing chat/coder cogs remain untouched.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from services.ai_engine.engine import AIEngine
from services.ai_engine.models import AIRequest
from services.ai_engine.tools import ToolContext

logger = logging.getLogger(__name__)


class AIEngineCog(commands.Cog, name="AI Engine"):
    """Lexus V3 agent interface."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.engine = AIEngine()
        self.engine.register_default_tools(bot)

    async def cog_load(self) -> None:
        self.bot.ai_engine = self.engine
        logger.info(
            "🤖 Lexus AI Engine loaded | providers=%s | tools=%d",
            ", ".join(self.engine.provider_names) if self.engine.provider_names else "none",
            len(self.engine.tools.names()),
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
        return result.text or "The AI engine could not complete that request."

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

        chunks = [response[i : i + 1900] for i in range(0, len(response), 1900)] or [response]
        await interaction.followup.send(chunks[0])
        for chunk in chunks[1:]:
            await interaction.followup.send(chunk)

    @commands.command(name="aistatus", help="Show Lexus AI Engine provider status.")
    @commands.is_owner()
    async def ai_status(self, ctx: commands.Context) -> None:
        providers = self.engine.provider_names or ["none"]
        tools = len(self.engine.tools.names())
        embed = discord.Embed(
            title="Lexus AI Engine",
            color=discord.Color.green() if self.engine.available else discord.Color.red(),
        )
        embed.add_field(name="Status", value="READY" if self.engine.available else "NOT CONFIGURED", inline=True)
        embed.add_field(name="Providers", value="\n".join(f"`{item}`" for item in providers), inline=False)
        embed.add_field(name="Tools", value=str(tools), inline=True)
        embed.add_field(
            name="Models",
            value="`gemini-3.8-flash`\n`openai/gpt-oss-120b`",
            inline=False,
        )
        await ctx.send(embed=embed)

    async def _send_chunked(self, ctx: commands.Context, response: str) -> None:
        chunks = [response[i : i + 1900] for i in range(0, len(response), 1900)] or [response]
        for chunk in chunks:
            await ctx.send(chunk)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AIEngineCog(bot))
