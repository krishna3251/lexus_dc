"""
broadcast.py — Lexus Bot Cog
Allows server admins to broadcast a prefix command string to multiple channels
via a single slash command (/broadcast).

Drop-in usage:
    await bot.load_extension("cogs.broadcast")
"""

from __future__ import annotations

import asyncio
import re
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)

# Regex to extract a channel ID from a mention like <#123456789>
CHANNEL_MENTION_RE = re.compile(r"<#(\d+)>")


class BroadcastCog(commands.Cog):
    """Cog that provides the /broadcast slash command."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def parse_channels(
        self, guild: discord.Guild, raw: str
    ) -> list[discord.TextChannel]:
        """
        Extract TextChannel objects from a comma-separated string that may
        contain channel mentions (<#id>) and/or raw channel IDs.

        Invalid or unresolvable entries are silently skipped so a single
        bad token never aborts the whole broadcast.
        """
        channels: list[discord.TextChannel] = []

        if not raw:
            return channels

        for token in raw.split(","):
            token = token.strip()
            if not token:
                continue

            # Prefer mention format first, fall back to bare ID
            match = CHANNEL_MENTION_RE.search(token)
            raw_id = match.group(1) if match else token

            # raw_id must be a valid integer to be a snowflake
            try:
                channel_id = int(raw_id)
            except ValueError:
                log.debug("parse_channels: skipping non-integer token %r", token)
                continue

            channel = guild.get_channel(channel_id)

            if channel is None:
                log.debug("parse_channels: channel %d not found in guild", channel_id)
                continue

            if not isinstance(channel, discord.TextChannel):
                log.debug("parse_channels: channel %d is not a TextChannel", channel_id)
                continue

            channels.append(channel)

        return channels

    # ------------------------------------------------------------------
    # Slash command
    # ------------------------------------------------------------------

    @app_commands.command(
        name="broadcast",
        description="Send a command string to multiple channels simultaneously.",
    )
    @app_commands.describe(
        command="The exact command string to broadcast (e.g. !lock, !mute all)",
        include="Comma-separated channel mentions or IDs to target (leave blank for all)",
        exclude="Comma-separated channel mentions or IDs to always skip",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.cooldown(1, 30, key=lambda i: (i.guild_id, i.user.id))
    async def broadcast(
        self,
        interaction: discord.Interaction,
        command: str,
        include: Optional[str] = None,
        exclude: Optional[str] = None,
    ) -> None:
        # Defer immediately — sending across many channels can exceed 3 s
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send(
                "❌ This command can only be used inside a server.", ephemeral=True
            )
            return

        # --- Resolve include / exclude lists ---
        include_channels = self.parse_channels(guild, include or "")
        exclude_channels = self.parse_channels(guild, exclude or "")
        exclude_ids = {ch.id for ch in exclude_channels}

        # --- Build the final target channel list ---
        if include_channels:
            # Explicit include: use only the listed channels
            candidates = include_channels
        else:
            # No explicit include: use every text channel in the guild
            candidates = list(guild.text_channels)

        # Filter out excluded channels and channels where the bot cannot speak
        targets: list[discord.TextChannel] = [
            ch
            for ch in candidates
            if ch.id not in exclude_ids
            and ch.permissions_for(guild.me).send_messages
        ]

        # Channels that were explicitly included but the bot has no perms in
        # are already excluded above; their absence will show in fail_count.
        no_perm_count = sum(
            1
            for ch in candidates
            if ch.id not in exclude_ids
            and not ch.permissions_for(guild.me).send_messages
        )

        total_targeted = len(targets) + no_perm_count
        success_count = 0
        fail_count = no_perm_count  # pre-seed with permission failures

        # --- Broadcast loop ---
        for index, channel in enumerate(targets):
            try:
                await channel.send(command)
                success_count += 1
            except discord.Forbidden:
                # Missing permissions at send-time (race condition / webhook only channel)
                log.warning("broadcast: Forbidden in #%s (%d)", channel.name, channel.id)
                fail_count += 1
            except discord.HTTPException as exc:
                log.warning(
                    "broadcast: HTTPException in #%s (%d): %s",
                    channel.name, channel.id, exc
                )
                fail_count += 1
            except Exception as exc:  # noqa: BLE001
                log.error(
                    "broadcast: Unexpected error in #%s (%d): %s",
                    channel.name, channel.id, exc, exc_info=True
                )
                fail_count += 1

            # Respect Discord rate limits; skip the sleep after the last send
            if index < len(targets) - 1:
                await asyncio.sleep(0.5)

        # --- Build summary embed ---
        if fail_count == 0:
            embed_color = discord.Color.green()
        elif success_count == 0:
            embed_color = discord.Color.red()
        else:
            embed_color = discord.Color.orange()

        embed = discord.Embed(title="📡 Broadcast Complete", color=embed_color)
        embed.add_field(
            name="Command Sent",
            value=f"```{command}```",
            inline=False,
        )
        embed.add_field(name="Channels Targeted", value=str(total_targeted), inline=True)
        embed.add_field(name="✅ Successful", value=str(success_count), inline=True)
        embed.add_field(name="❌ Failed / Skipped", value=str(fail_count), inline=True)
        embed.add_field(name="⏱️ Delay Used", value="0.5s between sends", inline=False)
        embed.set_footer(text=f"Triggered by {interaction.user}")

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # Error handler
    # ------------------------------------------------------------------

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """
        Central error handler for all app commands in this cog.
        Sends a user-friendly ephemeral message and prevents the error
        from bubbling up to the global handler.
        """
        # Unwrap CheckFailure wrappers if present
        original = getattr(error, "original", error)

        if isinstance(original, app_commands.CommandOnCooldown):
            retry_after = round(original.retry_after, 1)
            msg = (
                f"⏳ **Cooldown active.** You can use `/broadcast` again "
                f"in **{retry_after}s**."
            )
        elif isinstance(original, app_commands.MissingPermissions):
            missing = ", ".join(
                perm.replace("_", " ").title()
                for perm in original.missing_permissions
            )
            msg = (
                f"🚫 **Missing permissions.** You need **{missing}** "
                f"to use this command."
            )
        else:
            log.error("Unhandled broadcast error: %s", error, exc_info=True)
            msg = "⚠️ An unexpected error occurred. Please try again later."

        # interaction may already be responded to if the error fires after defer
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except discord.HTTPException:
            pass  # Nothing we can do if the interaction itself is broken


# ------------------------------------------------------------------
# Cog loader
# ------------------------------------------------------------------

async def setup(bot: commands.Bot) -> None:
    """Entry point for bot.load_extension('cogs.broadcast')."""
    await bot.add_cog(BroadcastCog(bot))
