"""
Reminders Cog — Schedule reminders via human-readable durations.
Persisted in MongoDB so reminders survive bot restarts.
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import re
import time
import logging
import mongo_helper

logger = logging.getLogger(__name__)

DURATION_RE = re.compile(r"(\d+)\s*(s|sec|m|min|h|hr|hour|d|day|w|week)", re.IGNORECASE)

UNIT_MAP = {
    "s": 1, "sec": 1,
    "m": 60, "min": 60,
    "h": 3600, "hr": 3600, "hour": 3600,
    "d": 86400, "day": 86400,
    "w": 604800, "week": 604800,
}


def parse_duration(text: str) -> int | None:
    """Parse a human duration string into seconds. Returns None on failure."""
    total = 0
    for match in DURATION_RE.finditer(text):
        val, unit = int(match.group(1)), match.group(2).lower()
        total += val * UNIT_MAP.get(unit, 0)
    return total if total > 0 else None


class RemindersCog(commands.Cog, name="Reminders"):
    """Set timed reminders that DM you when they fire."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.check_reminders.start()

    async def cog_unload(self):
        self.check_reminders.cancel()

    # ── Slash command ──────────────────────────────────────────────

    @app_commands.command(name="remind", description="Set a reminder")
    @app_commands.describe(
        duration="When to remind you (e.g. 2h, 30m, 1d)",
        message="What to remind you about",
    )
    async def remind(self, interaction: discord.Interaction, duration: str, message: str):
        seconds = parse_duration(duration)
        if not seconds:
            await interaction.response.send_message(
                "❌ Invalid duration. Examples: `30m`, `2h`, `1d`", ephemeral=True
            )
            return

        fire_at = time.time() + seconds
        col = mongo_helper.get_collection("reminders")
        if col is None:
            await interaction.response.send_message("❌ Database unavailable.", ephemeral=True)
            return

        await col.insert_one({
            "user_id": interaction.user.id,
            "channel_id": interaction.channel_id,
            "guild_id": interaction.guild_id,
            "message": message,
            "fire_at": fire_at,
            "created_at": time.time(),
        })

        fire_ts = int(fire_at)
        await interaction.response.send_message(
            f"⏰ Reminder set! I'll remind you <t:{fire_ts}:R>: **{message}**",
        )

    @app_commands.command(name="reminders", description="List your active reminders")
    async def list_reminders(self, interaction: discord.Interaction):
        col = mongo_helper.get_collection("reminders")
        if col is None:
            await interaction.response.send_message("❌ Database unavailable.", ephemeral=True)
            return

        cursor = col.find({"user_id": interaction.user.id}).sort("fire_at", 1).limit(10)
        reminders = await cursor.to_list(length=10)

        if not reminders:
            await interaction.response.send_message("No active reminders.", ephemeral=True)
            return

        lines = []
        for i, r in enumerate(reminders, 1):
            ts = int(r["fire_at"])
            lines.append(f"**{i}.** <t:{ts}:R> — {r['message']}")

        embed = discord.Embed(
            title="⏰ Your Reminders",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Background checker ─────────────────────────────────────────

    @tasks.loop(seconds=15)
    async def check_reminders(self):
        col = mongo_helper.get_collection("reminders")
        if col is None:
            return

        now = time.time()
        cursor = col.find({"fire_at": {"$lte": now}})
        fired = await cursor.to_list(length=50)

        for r in fired:
            user = self.bot.get_user(r["user_id"])
            if not user:
                try:
                    user = await self.bot.fetch_user(r["user_id"])
                except Exception:
                    user = None

            if user:
                embed = discord.Embed(
                    title="⏰ Reminder!",
                    description=r["message"],
                    color=discord.Color.gold(),
                )
                try:
                    await user.send(embed=embed)
                except discord.Forbidden:
                    # Try sending in the original channel
                    ch = self.bot.get_channel(r.get("channel_id"))
                    if ch:
                        try:
                            await ch.send(f"{user.mention} ⏰ Reminder: **{r['message']}**")
                        except discord.Forbidden:
                            pass

            await col.delete_one({"_id": r["_id"]})

    @check_reminders.before_loop
    async def before_check_reminders(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(RemindersCog(bot))
    logger.info("✅ Reminders cog loaded")
