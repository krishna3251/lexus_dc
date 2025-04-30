import discord
from discord.ext import commands
import datetime
import random
import asyncio
from typing import Dict, List

class ServerInfo(commands.Cog):
    """Cyberpunk-themed server information commands"""
    
    def __init__(self, bot):
        self.bot = bot
        # Cyberpunk-themed color palette
        self.cyber_colors = [
            0x00FFFF,  # Neon cyan
            0xFF00FF,  # Neon magenta
            0xFF3366,  # Hot pink
            0x33CCFF,  # Electric blue
            0x00FF99,  # Neon green
            0xFFFF00,  # Neon yellow
        ]
        
    async def get_random_cyber_color(self):
        """Return a random cyberpunk color"""
        return random.choice(self.cyber_colors)
        
    @commands.command(name="netdata", aliases=["serverinfo"], help="Displays cyberpunk-themed server information.")
    async def serverinfo(self, ctx):
        """Display detailed server information with cyberpunk styling"""
        guild = ctx.guild

        if not guild:
            return await ctx.send("⚠️ **CRITICAL ERROR** ⚠️\nServer data corruption detected. Unable to retrieve network information.")

        # Create a typing effect for immersion
        async with ctx.typing():
            await asyncio.sleep(1)

        # Get server owner with error handling
        owner = guild.owner or "UNKNOWN"
        
        # Calculate server age with proper timezone handling
        created_at = guild.created_at
        time_elapsed = (discord.utils.utcnow() - created_at).days
        
        # Calculate bot and human counts
        bot_count = len([m for m in guild.members if m.bot])
        human_count = guild.member_count - bot_count
        
        # Calculate online/offline counts
        online_count = len([m for m in guild.members if m.status != discord.Status.offline])
        offline_count = guild.member_count - online_count
        
        # Get channel statistics
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        forums = len([c for c in guild.channels if isinstance(c, discord.ForumChannel)])
        
        # Get emoji statistics
        static_emojis = len([e for e in guild.emojis if not e.animated])
        animated_emojis = len([e for e in guild.emojis if e.animated])
        
        # Role information with better formatting
        roles = [role for role in guild.roles if role.name != "@everyone"]
        roles.sort(key=lambda x: x.position, reverse=True)  # Sort by position
        role_display = ", ".join([role.name for role in roles[:10]]) + ("..." if len(roles) > 10 else "")

        embed = discord.Embed(
            title="⚡ NETWORK::METADATA_SCAN ⚡",
            description=f"**NETWORK ID: {guild.name}**",
            color=await self.get_random_cyber_color()
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            
        if guild.banner:
            embed.set_image(url=guild.banner.url)

        # Core server information
        embed.add_field(
            name="NETWORK IDENTITY",
            value=f"```ini\n[NAME] {guild.name}\n[ID] {guild.id}\n[OWNER] {owner}\n[REGION] {guild.preferred_locale}```",
            inline=False
        )

        # Server age and verification
        embed.add_field(
            name="NETWORK METRICS",
            value=f"```fix\nCREATION_DATE: {created_at.strftime('%Y-%m-%d %H:%M')}\nUPTIME: {time_elapsed} days\nVERIF_LEVEL: {guild.verification_level.name}```",
            inline=False
        )

        # Population metrics
        embed.add_field(
            name="POPULATION",
            value=f"```yaml\nTOTAL: {guild.member_count}\nHUMANS: {human_count}\nBOTS: {bot_count}\nONLINE: {online_count}\nOFFLINE: {offline_count}```",
            inline=True
        )

        # Server structure metrics  
        embed.add_field(
            name="STRUCTURE",
            value=f"```yaml\nCATEGORIES: {categories}\nTEXT_CHANNELS: {text_channels}\nVOICE_CHANNELS: {voice_channels}\nFORUM_CHANNELS: {forums}```",
            inline=True
        )

        # Nitro boost information
        embed.add_field(
            name="NETWORK ENHANCEMENTS",
            value=f"```arm\nBOOST_LEVEL: {guild.premium_tier}\nBOOST_COUNT: {guild.premium_subscription_count}\nFILE_LIMIT: {round(guild.filesize_limit / 1048576)} MB\nEMOJI_LIMIT: {guild.emoji_limit}\n```",
            inline=False
        )

        # Content statistics
        embed.add_field(
            name="CONTENT METRICS",
            value=f"```cpp\nSTATIC_EMOJIS: {static_emojis}/{guild.emoji_limit}\nANIMATED_EMOJIS: {animated_emojis}/{guild.emoji_limit}\nSTICKERS: {len(guild.stickers)}/{guild.sticker_limit}\nROLES: {len(guild.roles)}\n```",
            inline=False
        )

        # Role information
        if roles:
            # Create a more cyberpunk role display
            top_roles = [f"[{role.name}]" for role in roles[:8]]
            embed.add_field(
                name="ACCESS LEVELS",
                value=f"```ini\n{' '.join(top_roles)}{' [...]' if len(roles) > 8 else ''}```",
                inline=False
            )

        # Features list
        if guild.features:
            features = [f.replace('_', ' ').title() for f in guild.features]
            feature_str = ", ".join(features[:8]) + ("..." if len(features) > 8 else "")
            embed.add_field(
                name="NETWORK FEATURES",
                value=f"```{feature_str}```",
                inline=False
            )

        embed.set_footer(text=f"SCAN REQUESTED BY {ctx.author} • {discord.utils.utcnow().strftime('%H:%M:%S')}", 
                         icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None)

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ServerInfo(bot))
    print("⚡ NETRUNNER MODULE: ServerInfo initialized ⚡")
