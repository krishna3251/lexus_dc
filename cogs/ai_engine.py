"""Discord interface for the Lexus AI Engine.

This cog exposes the unified V3 AI entry points while keeping existing cogs
coexisting with the engine.
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher

import discord
from discord import app_commands
from discord.ext import commands

from services.ai_engine.engine import AIEngine
from services.ai_engine.models import AIRequest
from services.ai_engine.tools import ToolContext
from services.ai_engine.providers import ProviderError
from services.discord_output import send_reply
from services.cache import TTLCache

logger = logging.getLogger(__name__)


class AIEngineCog(commands.Cog, name="AI Engine"):
    """Lexus V3 agent interface.

    Natural chat accepts the bot's common names and typo variants so users
    do not need to remember one exact spelling to wake Lexus.
    """

    # Explicit variants cover the names people commonly use for Lexus.
    # Fuzzy matching is deliberately limited to the first token so normal
    # conversation is not accidentally routed into the AI engine.
    WAKE_ALIASES = frozenset({
        "lxeus",
        "lex",
        "lexus",
        "luexu",
        "lexiya",
        "lexi",
        "lexu",
        "leks",
        "leksa",
        "luxe",
        "badwr",
        "badwe",
    })
    WAKE_GREETINGS = frozenset({
        "hey", "hi", "hello", "yo", "oye", "ok", "okay", "bro", "bhai"
    })

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.engine = AIEngine()
        self.engine.register_default_tools(bot)
        self._handled_messages: TTLCache[int, bool] = TTLCache(
            max_size=10000,
            default_ttl=90.0,
        )
        self._reply_owners = TTLCache[int, tuple](2000, 900)

    async def cog_load(self) -> None:
        self.bot.ai_engine = self.engine
        await self.engine.memory.initialize()
        try:
            await self.engine.research.initialize()
        except Exception as exc:
            logger.warning("Knowledge store unavailable | type=%s", type(exc).__name__)
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
        try:
            await self.engine.reload_providers()
        except ProviderError as exc:
            await ctx.send(str(exc), allowed_mentions=discord.AllowedMentions.none())
            return
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
        )

        try:
            async with message.channel.typing():
                response = await self._run(
                    message.author,
                    message.guild,
                    channel,
                    prompt,
                )
            await self._send_message_chunks(message.channel, response,
                                            (message.author.id, getattr(message.guild, "id", None), message.channel.id))
        except Exception:
            logger.exception(
                "AI natural chat failed | user=%s guild=%s channel=%s",
                message.author.id,
                getattr(message.guild, "id", None),
                message.channel.id,
            )
            await message.channel.send(
                "I couldn't finish that reply. Try again in a moment."
            )

    @classmethod
    def _normalize_wake_token(cls, token: str) -> str:
        """Normalize punctuation/casing around a spoken-style wake name."""
        return re.sub(r"[^a-z0-9]", "", token.casefold())

    @classmethod
    def _is_wake_alias(cls, token: str) -> bool:
        normalized = cls._normalize_wake_token(token)
        if not normalized:
            return False
        if normalized in cls.WAKE_ALIASES:
            return True

        # Only fuzzy-match plausible names. This catches small typos without
        # turning ordinary words such as "let" or "less" into wake words.
        if len(normalized) < 4:
            return False
        return max(
            SequenceMatcher(None, normalized, alias).ratio()
            for alias in cls.WAKE_ALIASES
        ) >= 0.84

    @classmethod
    def _strip_wake_name(cls, content: str) -> str | None:
        """Return the user prompt when a supported Lexus name wakes the bot."""
        tokens = content.split()
        if not tokens:
            return None

        index = 0
        # Accept natural openers such as "hey lex" and "okay lex".
        if cls._normalize_wake_token(tokens[0]) in cls.WAKE_GREETINGS:
            index = 1
            if len(tokens) <= index:
                return None

        if not cls._is_wake_alias(tokens[index]):
            return None

        prompt = " ".join(tokens[index + 1:]).strip(" ,:;!?")
        return prompt or None

    async def _extract_natural_prompt(self, message: discord.Message) -> str | None:
        """Extract a prompt from mentions, configured prefixes, or Lexus name variants."""
        content = message.content.strip()
        if not content:
            return None
        # Legacy coding workflows own these exact triggers.
        if re.match(r"^lex (?:code|review|analyze|memory)(?:\s|$)", content, re.I):
            return None

        scope = (message.author.id, getattr(message.guild, "id", None), message.channel.id)
        reference_id = getattr(getattr(message, "reference", None), "message_id", None)
        if reference_id and self._reply_owners.get(reference_id) == scope:
            return content
        if message.guild is None:
            return content

        if self.bot.user and self.bot.user in message.mentions:
            pattern = rf"<@!?{self.bot.user.id}>\s*"
            prompt = re.sub(pattern, "", content, count=1).strip(" ,:;!?")
            return prompt or None

        # Natural wake names: "Lex ...", "Luexu ...", "Lexiya ...",
        # "Badwr ...", "Badwe ...", plus small typo variations.
        wake_prompt = self._strip_wake_name(content)
        if wake_prompt:
            logger.debug(
                "AI wake-name matched | message=%s | token=%s",
                message.id,
                content.split()[0],
            )
            return wake_prompt

        try:
            prefixes = await self.bot.get_prefix(message)
        except Exception:
            prefixes = ["lx "]

        if isinstance(prefixes, str):
            prefixes = [prefixes]

        prefixes = list(prefixes) + ["lx ", "lex "]

        for prefix in dict.fromkeys(prefixes):
            if prefix and content.casefold().startswith(prefix.casefold()):
                prompt = content[len(prefix):].strip()
                return prompt or None

        return None

    async def _send_message_chunks(
        self,
        channel: discord.abc.Messageable,
        response: str,
        scope: tuple | None = None,
    ) -> None:
        """Send an AI response without exceeding Discord message limits."""
        if not response or not response.strip():
            return
        for sent in await send_reply(channel.send, response):
            if scope:
                self._reply_owners.set(sent.id, scope)

    @commands.command(
        name="ask",
        help="Ask Lexus AI Engine a question or request an allowed bot action.",
    )
    async def ask_prefix(self, ctx: commands.Context, *, prompt: str) -> None:
        async with ctx.typing():
            response = await self._run(
                ctx.author,
                ctx.guild,
                ctx.channel,
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
        channel = interaction.channel
        response = await self._run(
            interaction.user,
            interaction.guild,
            channel,
            prompt,
        )

        if not response or not response.strip():
            return
        for sent in await send_reply(interaction.followup.send, response, wait=True):
            self._reply_owners.set(sent.id, (interaction.user.id, interaction.guild_id, interaction.channel_id))

    async def _private(self, ctx: commands.Context, text: str) -> None:
        """Memory contents never get posted in a public channel."""
        for offset in range(0, len(text), 1900):
            if ctx.interaction:
                await ctx.send(text[offset:offset+1900], ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
            else:
                try:
                    await ctx.author.send(text[offset:offset+1900], allowed_mentions=discord.AllowedMentions.none())
                except discord.Forbidden:
                    await ctx.send("Enable DMs or use the slash version for a private response.")
                    break

    @commands.hybrid_group(name="aimemory", fallback="status", invoke_without_command=True)
    async def ai_memory(self, ctx: commands.Context) -> None:
        """Private memory settings for you in this server (or your DM scope)."""
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        prefs = await self.engine.memory.preferences(ctx.author.id, getattr(ctx.guild, "id", None))
        await self._private(ctx, f"Persistent chat history: {bool(prefs['history_enabled'])}\nExternal AI allowed: {bool(prefs['external_allowed'])}\nStyle: {prefs['style'] or 'adaptive'}\nAddressed chat uses a temporary RAM session. Approved memories are saved only by `remember`. Use settings, remember, recall, forget, clear, or style.")

    @ai_memory.command(name="settings")
    async def memory_settings(self, ctx: commands.Context, history: bool, external: bool) -> None:
        """Choose persistent chat history and external processing for this scope."""
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        guild = getattr(ctx.guild, "id", None)
        await self.engine.capacity.cancel_user(ctx.author.id, guild)
        prefs = await self.engine.memory.preferences(ctx.author.id, guild)
        ok = await self.engine.memory.set_preferences(ctx.author.id, guild, history_enabled=history,
                                                     external_allowed=external, style=prefs["style"])
        await self._private(ctx, "Settings saved. Previously sent external requests cannot be recalled." if ok else "Settings could not be saved.")

    @ai_memory.command(name="remember")
    async def memory_remember(self, ctx: commands.Context, key: str, *, value: str) -> None:
        """Explicitly approve or replace one personal memory."""
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        ok = await self.engine.memory.remember(ctx.author.id, getattr(ctx.guild, "id", None), key, value)
        await self._private(ctx, "Memory saved for you in this scope." if ok else "Memory could not be saved.")

    @ai_memory.command(name="recall")
    async def memory_recall(self, ctx: commands.Context) -> None:
        """Privately list your approved memories in this scope."""
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        items = await self.engine.memory.memories(ctx.author.id, getattr(ctx.guild, "id", None))
        await self._private(ctx, "\n".join(f"{item['key']}: {item['value']}" for item in items) or "No approved memories saved.")

    @ai_memory.command(name="forget")
    async def memory_forget(self, ctx: commands.Context, key: str) -> None:
        """Delete one approved memory and discard temporary context."""
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        guild = getattr(ctx.guild, "id", None)
        await self.engine.capacity.cancel_user(ctx.author.id, guild)
        self.engine.conversations.clear(ctx.author.id, guild)
        await self.engine.memory.clear_history_user(ctx.author.id, guild)
        ok = await self.engine.memory.forget(ctx.author.id, guild, key)
        await self._private(ctx, "Memory deleted; conversation context cleared." if ok else "That memory was not found or deletion failed.")

    @ai_memory.command(name="clear")
    async def memory_clear(self, ctx: commands.Context) -> None:
        """Delete your history, approved memories and feedback in this scope."""
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        ok = await self.engine.clear_user(ctx.author.id, getattr(ctx.guild, "id", None))
        await self._private(ctx, "Your memories, history and feedback were cleared. Privacy choices were retained." if ok else "Deletion could not be completed.")

    @ai_memory.command(name="style")
    async def memory_style(self, ctx: commands.Context, style: str = "adaptive") -> None:
        """Choose adaptive, casual, friendly, playful, sarcastic, serious, technical, helpful or concise."""
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        guild = getattr(ctx.guild, "id", None)
        prefs = await self.engine.memory.preferences(ctx.author.id, guild)
        ok = await self.engine.memory.set_preferences(ctx.author.id, guild, history_enabled=bool(prefs['history_enabled']),
                                                     external_allowed=bool(prefs['external_allowed']), style="" if style == "adaptive" else style)
        await self._private(ctx, "Style preference saved." if ok else "Unknown style or storage failure.")

    @commands.hybrid_command(name="aicancel")
    async def ai_cancel(self, ctx: commands.Context) -> None:
        """Stop your active Brain requests in this server."""
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        await self.engine.capacity.cancel_user(ctx.author.id, getattr(ctx.guild, "id", None))
        await self._private(ctx, "Stopped active requests. An action already accepted by Discord may have completed.")

    @commands.hybrid_command(name="aiconfirm")
    async def ai_confirm(self, ctx: commands.Context, token: str) -> None:
        """Confirm the exact pending action preview in this channel."""
        if ctx.interaction:
            await ctx.defer()
        result = await self.engine.confirm(token, ToolContext(self.bot, ctx.guild, ctx.channel, ctx.author))
        await self._send_chunked(ctx, result.text)

    @commands.hybrid_command(name="aifeedback")
    async def ai_feedback(self, ctx: commands.Context, helpful: bool) -> None:
        """Save an explicit usefulness signal without storing message content."""
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        ok = await self.engine.memory.feedback(ctx.author.id, getattr(ctx.guild, "id", None), helpful)
        await self._private(ctx, "Feedback saved." if ok else "Feedback could not be saved.")

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
            f"✅ {jev['model']} • explicit evaluations only"
            if jev["available"] else "⚪ Jev decision layer unavailable"
        )
        embed.add_field(
            name="Decision Layer",
            value=jev_value,
            inline=False,
        )
        embed.add_field(
            name="Models",
            value="\n".join(providers)[:1000],
            inline=False,
        )
        metrics = health['provider_metrics']
        embed.add_field(name="Brain limits", value=f"Active: {health['active_requests']}\nExternal calls used: {metrics.get('hourly_calls_used', 0)}/{metrics.get('hourly_call_limit', 0)}\nCache: {health['cache']['hits']} hits, {health['cache']['misses']} misses", inline=False)
        usage = metrics.get("token_usage", [])
        usage_text = "\n".join(
            f"{item['provider']} / {item['model']}: "
            f"{item.get('input_tokens', 0)} in, {item.get('output_tokens', 0)} out "
            f"({item.get('responses_without_usage', 0)} unreported)"
            for item in usage
        )
        embed.add_field(name="Reported token usage", value=usage_text[:1000] or "No reported usage yet.", inline=False)
        await ctx.send(embed=embed)

    async def _send_chunked(self, ctx: commands.Context, response: str) -> None:
        if not response or not response.strip():
            return
        await self._send_message_chunks(ctx.channel, response,
            (ctx.author.id, getattr(ctx.guild, "id", None), ctx.channel.id))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AIEngineCog(bot))
