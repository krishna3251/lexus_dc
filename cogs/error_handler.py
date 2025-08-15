import discord
import logging
import asyncio
from discord.ext import commands

class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldown_active = False
        self.cooldown_seconds = 0

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Global command error handler for rate limits & Cloudflare blocks."""
        
        # 429 Rate Limit Handling
        if isinstance(error, discord.HTTPException) and error.status == 429:
            retry_after = getattr(error, "retry_after", 5)
            self.cooldown_active = True
            self.cooldown_seconds = retry_after
            logging.critical(f"🚫 Hit Discord rate limit — cooling down for {retry_after} seconds.")

            await ctx.send(
                f"⚠️ **Too many requests!** Cooling down for `{retry_after}` seconds...",
                delete_after=10
            )
            await asyncio.sleep(retry_after)
            self.cooldown_active = False
            self.cooldown_seconds = 0
            return

        # Cloudflare Access Denied Handling (Error 1015)
        if isinstance(error, discord.HTTPException) and "Cloudflare" in str(error):
            self.cooldown_active = True
            self.cooldown_seconds = 60
            logging.critical("🚫 Cloudflare blocked the bot — cooling down for 60 seconds.")

            await ctx.send(
                "⚠️ **Discord is temporarily blocking requests (Cloudflare)**. Retrying in 60 seconds...",
                delete_after=15
            )
            await asyncio.sleep(60)
            self.cooldown_active = False
            self.cooldown_seconds = 0
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
