"""
Polls Cog — Slash command polls with up to 10 options, reaction voting,
and optional auto-close after a duration.
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import time
import logging
import mongo_helper

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

        for i in range(len(options)):
            await msg.add_reaction(NUMBER_EMOJIS[i])

        # Save poll for auto-close if duration provided
        if duration:
            from cogs.reminders import parse_duration
            seconds = parse_duration(duration)
            if seconds:
                col = mongo_helper.get_collection("polls")
                if col:
                    await col.insert_one({
                        "message_id": msg.id,
                        "channel_id": msg.channel.id,
                        "guild_id": interaction.guild_id,
                        "question": question,
                        "options": options,
                        "close_at": time.time() + seconds,
                    })

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
            channel = self.bot.get_channel(poll["channel_id"])
            if not channel:
                await col.delete_one({"_id": poll["_id"]})
                continue

            try:
                msg = await channel.fetch_message(poll["message_id"])
            except (discord.NotFound, discord.Forbidden):
                await col.delete_one({"_id": poll["_id"]})
                continue

            # Tally votes
            results = []
            for i, opt in enumerate(poll["options"]):
                emoji = NUMBER_EMOJIS[i]
                reaction = discord.utils.get(msg.reactions, emoji=emoji)
                count = (reaction.count - 1) if reaction else 0  # subtract bot's reaction
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
            if results:
                embed.add_field(name="Winner", value=f"🏆 **{results[0][0]}**")

            try:
                await msg.edit(embed=embed)
                await msg.clear_reactions()
            except discord.Forbidden:
                pass

            await col.delete_one({"_id": poll["_id"]})

    @poll_closer.before_loop
    async def before_poll_closer(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(PollsCog(bot))
    logger.info("✅ Polls cog loaded")
