import discord
from discord.ext import commands
from discord import app_commands

class PingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_latency_status(self, latency):
        """Determines status based on latency."""
        if latency < 100:
            return ("🌙 **Shadow Speed** - Unmatched", 0x520a9b)  # Dark Purple Theme
        elif latency < 200:
            return ("⚡ **Hunter-Grade** - Swift", 0x520a9b)
        else:
            return ("💀 **Demon Time** - Slow", 0x520a9b)

    @commands.command(name="ping", help="⚔ Check bot latency in this server")
    async def ping_prefix(self, ctx):
        latency = round(self.bot.latency * 1000)  # Convert to milliseconds
        status_text, color = self.get_latency_status(latency)

        server_name = ctx.guild.name  # Fetches the server name
        server_icon = ctx.guild.icon.url if ctx.guild.icon else None  # Fetches the server icon

        embed = discord.Embed(
            title=f"🔮 **{server_name} Ping Report**",
            description=f"🔹 **Latency:** `{latency}ms`\n🔸 **Status:** {status_text}",
            color=color
        )

        if server_icon:
            embed.set_thumbnail(url=server_icon)  # Server icon as thumbnail
            embed.set_footer(text=f"{server_name} | Shadow Rises", icon_url=server_icon)
        else:
            embed.set_footer(text=f"{server_name} | Shadow Rises")

        await ctx.send(embed=embed)

    @app_commands.command(name="ping", description="⚔ Check bot latency in this server")
    async def ping_slash(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)  # Convert to milliseconds
        status_text, color = self.get_latency_status(latency)

        server_name = interaction.guild.name  # Fetches the server name
        server_icon = interaction.guild.icon.url if interaction.guild.icon else None  # Fetches the server icon

        embed = discord.Embed(
            title=f"🔮 **{server_name} Ping Report**",
            description=f"🔹 **Latency:** `{latency}ms`\n🔸 **Status:** {status_text}",
            color=color
        )

        if server_icon:
            embed.set_thumbnail(url=server_icon)  # Server icon as thumbnail
            embed.set_footer(text=f"{server_name} | Shadow Rises", icon_url=server_icon)
        else:
            embed.set_footer(text=f"{server_name} | Shadow Rises")

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(PingCog(bot))
    print("✅ PingCog cog loaded!")
