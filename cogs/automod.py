"""
Automod Cog — Spam detection, excessive caps, invite-link blocking,
bad-word filter. Configurable per server via MongoDB guild_config.
"""

import discord
from discord.ext import commands
from discord import app_commands
import re
import time
import logging
import mongo_helper

logger = logging.getLogger(__name__)

INVITE_PATTERN = re.compile(
    r"(discord\.gg|discordapp\.com/invite|discord\.com/invite)/[A-Za-z0-9\-]+",
    re.IGNORECASE,
)

DEFAULT_BAD_WORDS = []  # Servers populate their own list


class AutomodCog(commands.Cog, name="Automod"):
    """Automated message moderation with configurable filters."""

    def __init__(self, bot):
        self.bot = bot
        self.spam_tracker: dict[int, list[float]] = {}  # user_id -> [timestamps]
        self.SPAM_THRESHOLD = 5  # messages
        self.SPAM_WINDOW = 5  # seconds

    async def _get_automod_config(self, guild_id: int) -> dict:
        cfg = await mongo_helper.get_guild_config(guild_id)
        return cfg.get("automod", {})

    # ── Configuration ──────────────────────────────────────────────

    @app_commands.command(name="automod", description="Toggle automod features")
    @app_commands.describe(
        feature="Feature to toggle: spam, caps, invites, badwords",
        enabled="Enable or disable",
    )
    @app_commands.choices(
        feature=[
            app_commands.Choice(name="Spam Detection", value="spam"),
            app_commands.Choice(name="Excessive Caps", value="caps"),
            app_commands.Choice(name="Invite Links", value="invites"),
            app_commands.Choice(name="Bad Words", value="badwords"),
        ]
    )
    @app_commands.default_permissions(manage_guild=True)
    async def automod_toggle(self, interaction: discord.Interaction, feature: str, enabled: bool):
        cfg = await self._get_automod_config(interaction.guild_id)
        cfg[feature] = enabled
        await mongo_helper.update_guild_config(interaction.guild_id, {"automod": cfg})
        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(f"✅ Automod `{feature}` {status}.", ephemeral=True)

    @app_commands.command(name="badwords", description="Manage the bad-word filter list")
    @app_commands.describe(action="add or remove", word="The word/phrase")
    @app_commands.choices(action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Remove", value="remove"),
        app_commands.Choice(name="List", value="list"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def badwords_cmd(self, interaction: discord.Interaction, action: str, word: str = None):
        cfg = await self._get_automod_config(interaction.guild_id)
        words: list = cfg.get("bad_words", [])

        if action == "list":
            if words:
                await interaction.response.send_message(
                    "**Bad words:** " + ", ".join(f"`{w}`" for w in words),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message("No bad words configured.", ephemeral=True)
            return

        if not word:
            await interaction.response.send_message("Please provide a word.", ephemeral=True)
            return

        word_lower = word.lower()
        if action == "add":
            if word_lower not in words:
                words.append(word_lower)
        elif action == "remove":
            words = [w for w in words if w != word_lower]

        cfg["bad_words"] = words
        await mongo_helper.update_guild_config(interaction.guild_id, {"automod": cfg})
        await interaction.response.send_message(f"✅ Bad words updated.", ephemeral=True)

    # ── Listener ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        # Ignore mods
        if message.author.guild_permissions.manage_messages:
            return

        cfg = await self._get_automod_config(message.guild.id)
        if not cfg:
            return

        violations = []

        # Spam detection
        if cfg.get("spam"):
            uid = message.author.id
            now = time.time()
            timestamps = self.spam_tracker.get(uid, [])
            timestamps = [t for t in timestamps if now - t < self.SPAM_WINDOW]
            timestamps.append(now)
            self.spam_tracker[uid] = timestamps
            if len(timestamps) >= self.SPAM_THRESHOLD:
                violations.append("spam")
                self.spam_tracker[uid] = []

        # Excessive caps (>70% caps, min 10 chars)
        if cfg.get("caps") and len(message.content) >= 10:
            alpha = [c for c in message.content if c.isalpha()]
            if alpha and sum(1 for c in alpha if c.isupper()) / len(alpha) > 0.7:
                violations.append("excessive caps")

        # Invite links
        if cfg.get("invites") and INVITE_PATTERN.search(message.content):
            violations.append("invite link")

        # Bad words
        bad_words = cfg.get("bad_words", [])
        if cfg.get("badwords") and bad_words:
            lower = message.content.lower()
            for word in bad_words:
                if word in lower:
                    violations.append("blocked word")
                    break

        if violations:
            try:
                await message.delete()
            except discord.Forbidden:
                pass

            reason = ", ".join(violations)
            embed = discord.Embed(
                description=f"⚠️ {message.author.mention}, your message was removed: **{reason}**",
                color=discord.Color.red(),
            )
            try:
                await message.channel.send(embed=embed, delete_after=5)
            except discord.Forbidden:
                pass


async def setup(bot):
    await bot.add_cog(AutomodCog(bot))
    logger.info("✅ Automod cog loaded")
