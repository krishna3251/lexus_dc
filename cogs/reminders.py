"""
Reminders Cog — Schedule reminders via human-readable durations.
Persisted in MongoDB so reminders survive bot restarts.
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import time
import logging
from uuid import uuid4

from pymongo.errors import PyMongoError
import mongo_helper
from services.durations import parse_duration

logger = logging.getLogger(__name__)

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
    async def remind(self, interaction: discord.Interaction, duration: str, message: str, public_fallback: bool = False):
        seconds = parse_duration(duration)
        if not seconds:
            await interaction.response.send_message(
                "❌ Invalid duration. Examples: `30m`, `2h`, `1d`", ephemeral=True
            )
            return

        if len(message) > 1900:
            await interaction.response.send_message("Keep the reminder under 1,900 characters.", ephemeral=True)
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
            "public_fallback": public_fallback,
            "created_at": time.time(),
        })

        fire_ts = int(fire_at)
        await interaction.response.send_message(
            f"⏰ Reminder set for <t:{fire_ts}:R>.", ephemeral=True,
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
            description="\n".join(lines)[:4096],
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Background checker ─────────────────────────────────────────

    @tasks.loop(seconds=15)
    async def check_reminders(self):
        col = mongo_helper.get_collection("reminders")
        if col is None:
            return

        for _ in range(50):
            now = time.time()
            lease_id = uuid4().hex
            try:
                reminder = await col.find_one_and_update(
                    {"fire_at": {"$lte": now}, "failed": {"$ne": True},
                     "$or": [{"lease_until": {"$exists": False}}, {"lease_until": {"$lte": now}}]},
                    {"$set": {"lease_id": lease_id, "lease_until": now + 300}},
                    sort=[("fire_at", 1)],
                )
                if reminder is None:
                    return
                key = {"_id": reminder["_id"], "lease_id": lease_id}
                try:
                    await self._deliver(reminder)
                except discord.HTTPException:
                    attempts = reminder.get("attempts", 0) + 1
                    await col.update_one(key, {
                        "$set": {"attempts": attempts, "failed": attempts >= 3,
                                 "lease_until": now + 60 * attempts},
                        "$unset": {"lease_id": ""},
                    })
                    continue
                await col.delete_one(key)
            except PyMongoError as exc:
                logger.warning("Reminder database operation failed (%s)", type(exc).__name__)
                return

    async def _deliver(self, reminder):
        user = self.bot.get_user(reminder["user_id"]) or await self.bot.fetch_user(reminder["user_id"])
        try:
            await user.send(embed=discord.Embed(
                title="⏰ Reminder!", description=reminder["message"], color=discord.Color.gold(),
            ))
        except discord.Forbidden:
            if not reminder.get("public_fallback") or not reminder.get("channel_id"):
                raise
            channel = self.bot.get_channel(reminder["channel_id"]) or await self.bot.fetch_channel(reminder["channel_id"])
            await channel.send(
                f"{user.mention} ⏰ Reminder: {reminder['message']}",
                allowed_mentions=discord.AllowedMentions(users=[user], roles=False, everyone=False),
            )

    @check_reminders.before_loop
    async def before_check_reminders(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(RemindersCog(bot))
    logger.info("✅ Reminders cog loaded")
