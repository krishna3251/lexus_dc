import discord
import logging
import asyncio
from discord.ext import commands

class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldown_active = False
        self.cooldown_seconds = 0
        self.default_status = discord.Game(name="Ready to serve 👌")  # Change to your normal status

    async def countdown_status(self):
        """Live countdown in bot status."""
        while self.cooldown_active and self.cooldown_seconds > 0:
            await self.bot.change_presence(
                activity=discord.Game(name=f"Cooling down ⏳ {self.cooldown_seconds}s")
            )
            await asyncio.sleep(1)
            self.cooldown_seconds -= 1

        # Reset to normal status when cooldown ends
        self.cooldown_active = False
        await self.bot.change_presence(activity=self.default_status)

    @commands.Cog.listener()
    async def on_ready(self):
        """Set default status when bot starts."""
        await self.bot.change_presence(activity=self.default_status)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Global command error handler for rate limits & Cloudflare blocks."""

        # 429 Rate Limit Handling
        if isinstance(error, discord.HTTPException) and error.status == 429:
            retry_after = int(getattr(error, "retry_after", 5))
            logging.critical(f"🚫 Hit Discord rate limit — cooling down for {retry_after} seconds.")

            await ctx.send(f"⚠️ **Too many requests!** Cooling down for `{retry_after}` seconds...", delete_after=10)

            self.cooldown_active = True
            self.cooldown_seconds = retry_after
            asyncio.create_task(self.countdown_status())
            return

        # Cloudflare Access Denied Handling (Error 1015)
        if isinstance(error, discord.HTTPException) and "Cloudflare" in str(error):
            logging.critical("🚫 Cloudflare blocked the bot — cooling down for 60 seconds.")

            await ctx.send("⚠️ **Discord is temporarily blocking requests (Cloudflare)**. Retrying in 60 seconds...", delete_after=15)

            self.cooldown_active = True
            self.cooldown_seconds = 60
            asyncio.create_task(self.countdown_status())
            return

        # Pass any other errors back to the default handler
        raise error

    @commands.Cog.listener()
    async def on_message(self, message):
        """Block command execution during cooldown to prevent spamming API."""
        if self.cooldown_active and message.content.startswith(tuple(self.bot.command_prefix)):
            await message.channel.send(
                f"⏳ Bot is cooling down for **{self.cooldown_seconds}** more seconds due to rate limits.",
                delete_after=5
            )
            return

async def setup(bot):
    await bot.add_cog(ErrorHandler(bot))
