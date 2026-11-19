"""
Polls Cog — Slash command polls with up to 10 options, reaction voting,
and optional auto-close after a duration.
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import time
from pymongo.errors import PyMongoError
import logging
import mongo_helper
from services.durations import parse_duration

logger = logging.getLogger(__name__)

NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


class PollsCog(commands.Cog, name="Polls"):
    """Create reaction-based polls."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.poll_closer.start()

    async def cog_unload(self):
        self.poll_closer.cancel()

    @app_commands.command(name="poll", description="Create a poll")
    @app_commands.describe(
        question="The poll question",
        option1="Option 1",
        option2="Option 2",
        option3="Option 3 (optional)",
        option4="Option 4 (optional)",
        option5="Option 5 (optional)",
        duration="Auto-close after (e.g. 1h, 30m). Leave empty for no limit.",
    )
    async def poll(
        self,
        interaction: discord.Interaction,
        question: str,
        option1: str,
        option2: str,
        option3: str = None,
        option4: str = None,
        option5: str = None,
        duration: str = None,
    ):
        seconds = parse_duration(duration) if duration is not None else None
        col = mongo_helper.get_collection("polls") if seconds else None
        if duration is not None and seconds is None:
            await interaction.response.send_message("Invalid duration. Try 30m, 2h or 1d.", ephemeral=True)
            return
        if seconds and col is None:
            await interaction.response.send_message("The database is unavailable for timed polls.", ephemeral=True)
            return
        options = [o for o in [option1, option2, option3, option4, option5] if o]

        description_lines = []
        for i, opt in enumerate(options):
            description_lines.append(f"{NUMBER_EMOJIS[i]} {opt}")

        embed = discord.Embed(
            title=f"📊 {question}",
            description="\n\n".join(description_lines),
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"Poll by {interaction.user.display_name}")

        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()

        if col is not None:
            try:
                await col.insert_one({
                    "message_id": msg.id,
                    "channel_id": msg.channel.id,
                    "guild_id": interaction.guild_id,
                    "question": question,
                    "options": options,
                    "close_at": time.time() + seconds,
                })
            except PyMongoError:
                await msg.delete()
                await interaction.followup.send("I couldn't save the timed poll. Please try again.", ephemeral=True)
                return

        for i in range(len(options)):
            await msg.add_reaction(NUMBER_EMOJIS[i])

    # ── Auto-close loop ────────────────────────────────────────────

    @tasks.loop(seconds=30)
    async def poll_closer(self):
        col = mongo_helper.get_collection("polls")
        if col is None:
            return

        now = time.time()
        cursor = col.find({"close_at": {"$lte": now}})
        expired = await cursor.to_list(length=20)

        for poll in expired:
            try:
                channel = self.bot.get_channel(poll["channel_id"]) or await self.bot.fetch_channel(poll["channel_id"])
                msg = await channel.fetch_message(poll["message_id"])
            except discord.NotFound:
                await col.delete_one({"_id": poll["_id"]})
                continue
            except discord.HTTPException:
                continue

            # Tally votes
            results = []
            for i, opt in enumerate(poll["options"]):
                emoji = NUMBER_EMOJIS[i]
                reaction = discord.utils.get(msg.reactions, emoji=emoji)
                count = (reaction.count - int(reaction.me)) if reaction else 0  # subtract bot's reaction
                results.append((opt, count))

            results.sort(key=lambda x: x[1], reverse=True)

            lines = []
            for opt, count in results:
                bar = "█" * min(count, 20)
                lines.append(f"**{opt}** — {count} vote{'s' if count != 1 else ''} {bar}")

            embed = discord.Embed(
                title=f"📊 Poll Closed: {poll['question']}",
                description="\n".join(lines),
                color=discord.Color.gold(),
            )
            highest = results[0][1] if results else 0
            winners = [option for option, count in results if count == highest]
            if not highest:
                embed.add_field(name="Result", value="No votes")
            else:
                embed.add_field(name="Winner" if len(winners) == 1 else "Tie", value=", ".join(winners))

            try:
                await msg.edit(embed=embed)
            except discord.HTTPException:
                continue

            await col.delete_one({"_id": poll["_id"]})
            try:
                await msg.clear_reactions()
            except discord.HTTPException:
                logger.info("Could not clear reactions on closed poll %s", msg.id)

    @poll_closer.before_loop
    async def before_poll_closer(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(PollsCog(bot))
    logger.info("✅ Polls cog loaded")
