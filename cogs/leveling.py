"""
Leveling Cog — XP per message, level-up announcements, /rank and /leaderboard.
All data stored in MongoDB (levels collection).
"""

import discord
from discord.ext import commands
from discord import app_commands
import random
import math
import time
import logging
import mongo_helper

logger = logging.getLogger(__name__)

# XP required for a given level: 5 * level^2 + 50 * level + 100
def xp_for_level(level: int) -> int:
    return 5 * (level ** 2) + 50 * level + 100


class LevelingCog(commands.Cog, name="Leveling"):
    """XP leveling system with per-server leaderboards."""

    def __init__(self, bot):
        self.bot = bot
        self.cooldowns: dict[int, float] = {}  # user_id -> last_xp_time
        self.XP_COOLDOWN = 60  # seconds between XP gains
        self.XP_MIN = 15
        self.XP_MAX = 25

    # ── XP gain on message ─────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        user_id = message.author.id
        guild_id = message.guild.id
        now = time.time()

        # Per-user cooldown
        if now - self.cooldowns.get(user_id, 0) < self.XP_COOLDOWN:
            return
        self.cooldowns[user_id] = now

        xp_gain = random.randint(self.XP_MIN, self.XP_MAX)

        # Fetch current record
        record = await mongo_helper.get_levels(guild_id, user_id)
        current_xp = record.get("current_xp", 0) + xp_gain
        total_xp = record.get("total_xp", 0) + xp_gain
        level = record.get("level", 0)

        # Check level up
        needed = xp_for_level(level)
        leveled_up = False
        while current_xp >= needed:
            current_xp -= needed
            level += 1
            needed = xp_for_level(level)
            leveled_up = True

        await mongo_helper.update_levels(guild_id, user_id, {
            "current_xp": current_xp,
            "total_xp": total_xp,
            "level": level,
            "username": str(message.author),
        })

        if leveled_up:
            # Announce in the same channel
            embed = discord.Embed(
                title="🎉 Level Up!",
                description=f"{message.author.mention} reached **Level {level}**!",
                color=discord.Color.gold(),
            )
            embed.set_thumbnail(url=message.author.display_avatar.url)
            try:
                await message.channel.send(embed=embed)
            except discord.Forbidden:
                pass

    # ── /rank ──────────────────────────────────────────────────────

    @app_commands.command(name="rank", description="Check your XP rank")
    @app_commands.describe(user="User to check (defaults to yourself)")
    async def rank(self, interaction: discord.Interaction, user: discord.Member = None):
        user = user or interaction.user
        record = await mongo_helper.get_levels(interaction.guild_id, user.id)
        level = record.get("level", 0)
        current_xp = record.get("current_xp", 0)
        total_xp = record.get("total_xp", 0)
        needed = xp_for_level(level)

        # Progress bar
        progress = int((current_xp / needed) * 20) if needed else 0
        bar = "█" * progress + "░" * (20 - progress)

        embed = discord.Embed(
            title=f"📊 {user.display_name}'s Rank",
            color=discord.Color.blurple(),
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Level", value=str(level), inline=True)
        embed.add_field(name="Total XP", value=f"{total_xp:,}", inline=True)
        embed.add_field(
            name="Progress",
            value=f"`{bar}` {current_xp}/{needed} XP",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    # ── /leaderboard ──────────────────────────────────────────────

    @app_commands.command(name="leaderboard", description="Server XP leaderboard")
    async def leaderboard(self, interaction: discord.Interaction):
        col = mongo_helper.get_collection("levels")
        if col is None:
            await interaction.response.send_message("Leveling database not available.", ephemeral=True)
            return

        cursor = col.find({"guild_id": interaction.guild_id}).sort("total_xp", -1).limit(10)
        rows = await cursor.to_list(length=10)

        if not rows:
            await interaction.response.send_message("No leveling data yet. Start chatting!", ephemeral=True)
            return

        description_lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, row in enumerate(rows):
            medal = medals[i] if i < 3 else f"**{i+1}.**"
            member = interaction.guild.get_member(row["user_id"])
            name = member.display_name if member else row.get("username", "Unknown")
            description_lines.append(
                f"{medal} **{name}** — Level {row.get('level', 0)} • {row.get('total_xp', 0):,} XP"
            )

        embed = discord.Embed(
            title=f"🏆 {interaction.guild.name} Leaderboard",
            description="\n".join(description_lines),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(LevelingCog(bot))
    logger.info("✅ Leveling cog loaded")
