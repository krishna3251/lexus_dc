import discord
from discord.ext import commands, tasks
from stats_store import server_stats


class ServerStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_stats.start()

    @tasks.loop(seconds=10)
    async def update_stats(self):
        # Aggregate across ALL guilds the bot is in
        guilds = self.bot.guilds
        if not guilds:
            return

        server_stats["members"] = sum(g.member_count or 0 for g in guilds)
        server_stats["channels"] = sum(len(g.channels) for g in guilds)
        server_stats["roles"] = sum(len(g.roles) for g in guilds)
        server_stats["boosts"] = sum(g.premium_subscription_count or 0 for g in guilds)
        server_stats["boost_level"] = max((g.premium_tier for g in guilds), default=0)

    @update_stats.before_loop
    async def before_update(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(ServerStats(bot))
