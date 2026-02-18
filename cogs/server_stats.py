import discord
from discord.ext import commands, tasks
from stats_store import server_stats

GUILD_ID = 1273151341241307187

class ServerStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_stats.start()

    @tasks.loop(seconds=10)
    async def update_stats(self):
        guild = self.bot.get_guild(GUILD_ID)

        if guild is None:
            print("Guild not found")
            return

        server_stats["members"] = guild.member_count
        server_stats["channels"] = len(guild.channels)
        server_stats["roles"] = len(guild.roles)
        server_stats["boosts"] = guild.premium_subscription_count
        server_stats["boost_level"] = guild.premium_tier

        print("Stats updated:", server_stats)

    @update_stats.before_loop
    async def before_update(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(ServerStats(bot))
