import discord
from discord.ext import commands, tasks
import asyncio
import logging

logger = logging.getLogger("rate-limit-handler")

class RateLimitHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_error(self, event_method, *args, **kwargs):
        logger.error(f"Error in event {event_method}", exc_info=True)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if hasattr(error, "status") and error.status == 429:
            retry_after = getattr(error, "retry_after", 10)
            logger.critical(f"⚠️ Rate limit hit! Sleeping for {retry_after} seconds...")
            await ctx.send(f"⏳ Bot is cooling down for {retry_after} seconds due to rate limit.")
            await asyncio.sleep(retry_after)
        else:
            raise error  # re-raise so normal error handling works

    @commands.Cog.listener()
    async def on_socket_raw_receive(self, msg):
        # This runs on every websocket packet
        if isinstance(msg, str) and "You are being rate limited." in msg:
            logger.critical("⚠️ Global rate limit triggered — sleeping for 60s.")
            await asyncio.sleep(60)

async def setup(bot):
    await bot.add_cog(RateLimitHandler(bot))
