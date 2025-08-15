import discord
import logging
import asyncio
import traceback
from discord.ext import commands

class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldown_active = False
        self.cooldown_seconds = 0
        self.default_status = discord.Game(name="Ready to serve 👌")

    async def countdown_status(self):
        while self.cooldown_active and self.cooldown_seconds > 0:
            await self.bot.change_presence(
                activity=discord.Game(name=f"Cooling down ⏳ {self.cooldown_seconds}s")
            )
            await asyncio.sleep(1)
            self.cooldown_seconds -= 1
        self.cooldown_active = False
        await self.bot.change_presence(activity=self.default_status)

    async def trigger_cooldown(self, seconds: int, reason: str):
        """Activate cooldown globally."""
        logging.critical(f"🚫 {reason} — cooling down for {seconds} seconds.")
        self.cooldown_active = True
        self.cooldown_seconds = seconds
        asyncio.create_task(self.countdown_status())

    @commands.Cog.listener()
    async def on_ready(self):
        await self.bot.change_presence(activity=self.default_status)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        await self.handle_error(error, ctx)

    @commands.Cog.listener()
    async def on_error(self, event_method, *args, **kwargs):
        """Catches ALL event errors, even background ones."""
        error = traceback.format_exc()
        logging.error(f"Unhandled error in event {event_method}:\n{error}")
        if "429" in error:
            await self.trigger_cooldown(30, "Rate limit hit in background task")
        elif "Cloudflare" in error or "1015" in error:
            await self.trigger_cooldown(60, "Cloudflare block in background task")

    async def handle_error(self, error, ctx=None):
        """Central error handling logic."""
        if isinstance(error, discord.HTTPException) and error.status == 429:
            retry_after = int(getattr(error, "retry_after", 5))
            await self.trigger_cooldown(retry_after, "Discord API rate limit")
            if ctx:
                await ctx.send(f"⚠️ Too many requests! Cooling down for `{retry_after}`s...", delete_after=10)
            return

        if isinstance(error, discord.HTTPException) and "Cloudflare" in str(error):
            await self.trigger_cooldown(60, "Cloudflare block")
            if ctx:
                await ctx.send("⚠️ Cloudflare blocking requests. Retrying in 60s...", delete_after=10)
            return

        # Log all other errors
        logging.error(f"Unhandled command error: {error}")
        if ctx:
            await ctx.send(f"❌ An unexpected error occurred:\n```{error}```", delete_after=10)

    @commands.Cog.listener()
    async def on_message(self, message):
        if self.cooldown_active and message.content.startswith(tuple(self.bot.command_prefix)):
            await message.channel.send(
                f"⏳ Cooling down for **{self.cooldown_seconds}** more seconds...",
                delete_after=5
            )
            return

async def setup(bot):
    await bot.add_cog(ErrorHandler(bot))
