"""
Logging Cog — Unified audit log for message edits/deletes, member joins/leaves,
bans, kicks, role changes. Posts rich embeds to a configurable log channel.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
import mongo_helper

logger = logging.getLogger(__name__)


class LoggingCog(commands.Cog, name="Logging"):
    """Server event logging to a configurable channel."""

    def __init__(self, bot):
        self.bot = bot
        self._log_channels: dict[int, int] = {}  # guild_id -> channel_id cache

    async def _get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """Return the configured log channel, or None."""
        if guild.id in self._log_channels:
            ch = guild.get_channel(self._log_channels[guild.id])
            if ch:
                return ch

        cfg = await mongo_helper.get_guild_config(guild.id)
        ch_id = cfg.get("log_channel")
        if ch_id:
            self._log_channels[guild.id] = ch_id
            return guild.get_channel(ch_id)
        return None

    async def _send_log(self, guild: discord.Guild, embed: discord.Embed):
        ch = await self._get_log_channel(guild)
        if ch:
            try:
                await ch.send(embed=embed)
            except discord.Forbidden:
                pass

    # ── Setup command ──────────────────────────────────────────────

    @app_commands.command(name="setlogchannel", description="Set the audit-log channel")
    @app_commands.describe(channel="Channel to post logs in")
    @app_commands.default_permissions(manage_guild=True)
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await mongo_helper.update_guild_config(interaction.guild_id, {"log_channel": channel.id})
        self._log_channels[interaction.guild_id] = channel.id
        await interaction.response.send_message(f"✅ Log channel set to {channel.mention}", ephemeral=True)

    # ── Message events ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        embed = discord.Embed(
            title="🗑️ Message Deleted",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Author", value=message.author.mention, inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        content = message.content[:1024] if message.content else "*No text content*"
        embed.add_field(name="Content", value=content, inline=False)
        embed.set_footer(text=f"User ID: {message.author.id}")
        await self._send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return

        embed = discord.Embed(
            title="✏️ Message Edited",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Author", value=before.author.mention, inline=True)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Before", value=before.content[:1024] or "*empty*", inline=False)
        embed.add_field(name="After", value=after.content[:1024] or "*empty*", inline=False)
        embed.set_footer(text=f"Message ID: {before.id}")
        await self._send_log(before.guild, embed)

    # ── Member events ──────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(
            title="📥 Member Joined",
            description=f"{member.mention} ({member})",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, "R"))
        embed.set_footer(text=f"ID: {member.id} • Members: {member.guild.member_count}")
        await self._send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(
            title="📤 Member Left",
            description=f"{member.mention} ({member})",
            color=discord.Color.dark_grey(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        roles = ", ".join(r.mention for r in member.roles if r != member.guild.default_role) or "None"
        embed.add_field(name="Roles", value=roles[:1024])
        embed.set_footer(text=f"ID: {member.id}")
        await self._send_log(member.guild, embed)

    # ── Ban / Unban ────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(
            title="🔨 Member Banned",
            description=f"{user.mention} ({user})",
            color=discord.Color.dark_red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"ID: {user.id}")
        await self._send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(
            title="🔓 Member Unbanned",
            description=f"{user.mention} ({user})",
            color=discord.Color.teal(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"ID: {user.id}")
        await self._send_log(guild, embed)

    # ── Role changes ───────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles == after.roles:
            return

        added = set(after.roles) - set(before.roles)
        removed = set(before.roles) - set(after.roles)

        if not added and not removed:
            return

        embed = discord.Embed(
            title="🔄 Roles Updated",
            description=after.mention,
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )
        if added:
            embed.add_field(name="Added", value=", ".join(r.mention for r in added), inline=False)
        if removed:
            embed.add_field(name="Removed", value=", ".join(r.mention for r in removed), inline=False)
        embed.set_footer(text=f"ID: {after.id}")
        await self._send_log(after.guild, embed)


async def setup(bot):
    await bot.add_cog(LoggingCog(bot))
    logger.info("✅ Logging cog loaded")
