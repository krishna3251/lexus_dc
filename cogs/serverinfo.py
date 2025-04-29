import discord
from discord.ext import commands
import datetime

class ServerInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="serverinfo", help="Displays detailed server information in an elegant embed.")
    async def serverinfo(self, ctx):
        guild = ctx.guild

        if not guild:
            return await ctx.send("Could not retrieve server information.")

        owner = guild.owner
        created_at = guild.created_at
        time_elapsed = (datetime.datetime.now(datetime.timezone.utc) - created_at).days  # ✅ Fixed timezone issue

        bot_count = len([m for m in guild.members if m.bot])
        human_count = guild.member_count - bot_count

        roles = [role.name for role in guild.roles if role.name != "@everyone"]
        role_display = ", ".join(roles[:15]) + ("..." if len(roles) > 15 else "")

        embed = discord.Embed(
            title="🖥️ SERVER INFORMATION 🖥️",
            description=f"Details about **{guild.name}**",
            color=discord.Color.blue()
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="🏷️ Server Name", value=f"```{guild.name}```", inline=True)
        embed.add_field(name="👑 Owner", value=f"```{owner}```", inline=True)
        embed.add_field(name="🆔 Server ID", value=f"```{guild.id}```", inline=True)

        embed.add_field(name="📅 Created On", value=f"```{created_at.strftime('%m/%d/%Y %H:%M')} ({time_elapsed} days ago)```", inline=False)

        embed.add_field(name="👥 Members", value=f"```👤 Humans: {human_count} | 🤖 Bots: {bot_count}```", inline=True)
        embed.add_field(name="🚀 Boosts", value=f"```Level {guild.premium_tier} | Boosts: {guild.premium_subscription_count}```", inline=True)

        embed.add_field(name="📂 Categories & Channels", value=f"```📁 {len(guild.categories)} | 💬 {len(guild.text_channels)} | 🎤 {len(guild.voice_channels)}```", inline=True)

        embed.add_field(name="🎭 Emojis & Stickers", value=f"```😀 {len([e for e in guild.emojis if not e.animated])} | 🎞️ {len([e for e in guild.emojis if e.animated])} | 🏷️ {len(guild.stickers)}```", inline=True)

        embed.add_field(name=f"🔖 Roles [{len(guild.roles)}]", value=f"```{role_display}```", inline=False)

        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ServerInfo(bot))
    print("✅ ServerInfo cog loaded!")
