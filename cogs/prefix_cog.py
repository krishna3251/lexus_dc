"""
Prefix Cog — Per-server custom prefix stored in MongoDB.
Bot owner can reset any guild's prefix.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
import mongo_helper

logger = logging.getLogger(__name__)

OWNER_ID = 486555340670894080
DEFAULT_PREFIX = "lx "


async def get_prefix(bot, message: discord.Message):
    """Dynamic prefix resolver called by commands.Bot."""
    if not message.guild:
        return commands.when_mentioned_or(DEFAULT_PREFIX)(bot, message)

    cfg = await mongo_helper.get_guild_config(message.guild.id)
    prefix = cfg.get("prefix", DEFAULT_PREFIX)
    return commands.when_mentioned_or(prefix)(bot, message)


class PrefixCog(commands.Cog, name="Prefix"):
    """Per-server custom command prefix."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setprefix", description="Change the bot prefix for this server")
    @app_commands.describe(prefix="New prefix (max 5 chars)")
    @app_commands.default_permissions(manage_guild=True)
    async def set_prefix(self, interaction: discord.Interaction, prefix: str):
        if len(prefix) > 5:
            await interaction.response.send_message("❌ Prefix must be 5 characters or fewer.", ephemeral=True)
            return

        await mongo_helper.update_guild_config(interaction.guild_id, {"prefix": prefix})
        await interaction.response.send_message(f"✅ Prefix set to `{prefix}`")

    @app_commands.command(name="prefix", description="Show the current prefix")
    async def show_prefix(self, interaction: discord.Interaction):
        cfg = await mongo_helper.get_guild_config(interaction.guild_id)
        prefix = cfg.get("prefix", DEFAULT_PREFIX)
        await interaction.response.send_message(f"Current prefix: `{prefix}`")

    @commands.command(name="resetprefix", hidden=True)
    async def reset_prefix(self, ctx: commands.Context):
        """Owner-only: reset a guild's prefix to default."""
        if ctx.author.id != OWNER_ID:
            return
        await mongo_helper.update_guild_config(ctx.guild.id, {"prefix": DEFAULT_PREFIX})
        await ctx.send(f"✅ Prefix reset to `{DEFAULT_PREFIX}`")


async def setup(bot):
    await bot.add_cog(PrefixCog(bot))
    logger.info("✅ Prefix cog loaded")
