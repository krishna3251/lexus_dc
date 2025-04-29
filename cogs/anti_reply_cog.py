import discord
import asyncio
from datetime import timedelta, datetime, timezone
from discord.ext import commands

class AntiReplyCog(commands.Cog):
    """⚠ Automatically times out users who repeatedly reply to the bot."""

    def __init__(self, bot):
        self.bot = bot
        self.user_violations = {}

    @commands.Cog.listener()
    async def on_message(self, message):
        """Detects when a user replies to the bot and applies punishments."""
        if message.author.bot:
            return  

        if message.reference and message.reference.resolved:
            replied_to = message.reference.resolved.author
            if replied_to == self.bot.user:
                await self.handle_violation(message)  # Now correctly calling the method

    async def handle_violation(self, message):
        """Handles increasing timeout durations for users replying to the bot."""
        user = message.author
        guild = message.guild

        # Increment violation count
        self.user_violations[user.id] = self.user_violations.get(user.id, 0) + 1
        violation_count = self.user_violations[user.id]

        # Timeout durations (1st = 10s, 2nd = 1m, 3rd = 30m, 4th = Warning, 5th = 1 week)
        timeout_durations = [10, 60, 1800, 0, 604800]
        timeout_duration = timeout_durations[min(violation_count - 1, len(timeout_durations) - 1)]

        # Warning messages
        warning_messages = {
            1: "⚠ **Agar aapne mujhe reply kiya, aapko timeout diya jayega!**",
            2: "⏳ **Aapka 1-minute timeout lagaya gaya hai!** Dobara reply mat karein.",
            3: "🚫 **30-minute timeout lagaya gaya hai!** Yeh aapke liye last chance hai.",
            4: "⚠ **Yeh aapki last warning hai!** Agar phir bhi reply kiya to 1 hafte ka timeout milega.",
            5: "⛔ **Aapko 1 hafte ke liye timeout diya gaya hai!** Admin se baat karein agar yeh galti se hua hai."
        }

        embed = discord.Embed(
            title="🚨 Warning!",
            description=warning_messages.get(violation_count, "⚠ Please do not reply to the bot!"),
            color=discord.Color.red()
        )

        await message.reply(embed=embed, delete_after=10)

        # Apply timeout if necessary
        if timeout_duration > 0:
            try:
                until = datetime.now(timezone.utc) + timedelta(seconds=timeout_duration)  # Ensure timezone-aware datetime
                await user.timeout(until, reason="Repeatedly replying to bot")
            except discord.Forbidden:
                print(f"❌ Bot lacks permission to timeout {user.display_name}.")
            except discord.HTTPException as e:
                print(f"❌ Failed to timeout {user.display_name}: {e}")

# Setup function to load the cog
async def setup(bot):
    await bot.add_cog(AntiReplyCog(bot))
