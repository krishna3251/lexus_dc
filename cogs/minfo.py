import discord
from discord.ext import commands
import random
import asyncio
from typing import Optional, List

class MemberInfo(commands.Cog):
    """Cyberpunk-themed member information commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.mod_role = None  # Store the moderator role
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
        
    async def get_or_ask_mod_role(self, ctx):
        """Check for an existing Moderator role or ask the user to specify one."""
        if self.mod_role:
            return self.mod_role

        mod_roles = [role for role in ctx.guild.roles if "mod" in role.name.lower() or "admin" in role.name.lower()]
        if mod_roles:
            mod_role = mod_roles[0]
            self.mod_role = mod_role  # Store for future use
            await ctx.send(f"⚡ **NETRUNNER ACCESS GRANTED** ⚡\n{mod_role.mention} identified as admin protocol.")
        else:
            await ctx.send("⚠️ **SYSTEM ERROR: ADMIN PROTOCOL NOT DETECTED** ⚠️\nTag the role you want to authorize as NETRUNNER_ADMIN.")

            def check(m):
                return m.author == ctx.author and m.role_mentions and m.channel.id == ctx.channel.id

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=30)
                mod_role = msg.role_mentions[0]  # Fixed: use role_mentions instead of mentions
                self.mod_role = mod_role  # Store for future use
                await ctx.send(f"✅ **NETRUNNER ACCESS CONFIGURED** ✅\n{mod_role.mention} now has ADMIN_PRIVILEGES.")
            except asyncio.TimeoutError:  # Explicit exception handling
                await ctx.send("⚠️ **CONNECTION TIMEOUT** ⚠️\nAdmin protocol configuration aborted. Try again when ready.")
                return None

        return self.mod_role

    @commands.command(name="netizens", aliases=["members"])
    async def members(self, ctx):
        """Display server members with cyberpunk styling"""
        guild = ctx.guild
        
        # Create a typing effect for immersion
        async with ctx.typing():
            await asyncio.sleep(1)
            
        embed = discord.Embed(
            title=f"⚡ NETIZEN DATABASE: {guild.name} ⚡",
            description=f"**NET::POPULATION_COUNT: {len(guild.members)}**",
            color=await self.get_random_cyber_color()
        )
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        online_count = len([m for m in guild.members if m.status != discord.Status.offline])
        embed.add_field(
            name="NETWORK STATUS",
            value=f"```arm\nONLINE:  {online_count}\nOFFLINE: {len(guild.members) - online_count}```",
            inline=False
        )
        
        # Limited preview of users with better formatting
        member_preview = []
        for member in guild.members[:8]:  # Limit to 8 for cleaner display
            join_days = (discord.utils.utcnow() - member.joined_at).days if member.joined_at else 0
            member_preview.append(f"• {member.name} :: {join_days}d :: {member.top_role.name}")
            
        embed.add_field(
            name="NETIZEN SAMPLE",
            value=f"```yaml\n{chr(10).join(member_preview)}```",
            inline=False
        )
        
        embed.set_footer(text=f"SCAN INITIATED BY {ctx.author.name} • {discord.utils.utcnow().strftime('%H:%M:%S')}")
        
        await ctx.send(embed=embed)

    @commands.command(name="netrunners", aliases=["moderators"])
    async def moderators(self, ctx):
        """Display server moderators with cyberpunk styling"""
        mod_role = await self.get_or_ask_mod_role(ctx)
        
        if mod_role:
            # Create a typing effect for immersion
            async with ctx.typing():
                await asyncio.sleep(1)
                
            embed = discord.Embed(
                title=f"⚡ NETRUNNER ACCESS DIRECTORY ⚡",
                description=f"**AUTHENTICATED USERS WITH {mod_role.name.upper()} CLEARANCE**",
                color=await self.get_random_cyber_color()
            )
            
            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)
            
            # Get all members with the role efficiently
            members_with_role = [member for member in ctx.guild.members if isinstance(member, discord.Member) and mod_role in member.roles]
            
            if members_with_role:
                netrunner_data = []
                for i, member in enumerate(members_with_role, 1):
                    join_days = (discord.utils.utcnow() - member.joined_at).days if member.joined_at else 0
                    netrunner_data.append(f"NETRUNNER_ID_{i:02d} :: {member.name} :: ACCESS LEVEL {member.top_role.position}")
                    netrunner_data.append(f"  ├─ USER_ID: {member.id}")
                    netrunner_data.append(f"  └─ UPTIME: {join_days} DAYS")
                    
                embed.add_field(
                    name="AUTHORIZED PERSONNEL",
                    value=f"```ini\n{chr(10).join(netrunner_data)}```",
                    inline=False
                )
            else:
                embed.description = f"**CRITICAL ERROR: NO USERS WITH {mod_role.name.upper()} CLEARANCE DETECTED**"
                
            embed.set_footer(text=f"SECURITY SCAN BY {ctx.author.name} • {discord.utils.utcnow().strftime('%H:%M:%S')}")
            
            await ctx.send(embed=embed)
        else:
            await ctx.send("⚠️ **SECURITY PROTOCOL FAILURE** ⚠️\nUnable to identify administrator role.")

    @commands.command(name="netprofile", aliases=["userinfo"], help="Displays cyberpunk-themed user profile.")
    async def userinfo(self, ctx, member: Optional[discord.Member] = None):
        """Display detailed user information with cyberpunk styling"""
        member = member or ctx.author

        # Create a typing effect for immersion
        async with ctx.typing():
            await asyncio.sleep(1)

        # Get Voice Channel status with error handling
        voice_state = member.voice
        voice_channel = "NULL" if not voice_state or not voice_state.channel else voice_state.channel.name
        voice_region = "UNKNOWN" if not voice_state or not voice_state.channel else (voice_state.channel.rtc_region or "AUTO")

        # Calculate account age
        account_age_days = (discord.utils.utcnow() - member.created_at).days
        account_age_years = account_age_days // 365
        
        # Calculate server join age
        join_age_days = (discord.utils.utcnow() - member.joined_at).days if member.joined_at else 0
        
        # Determine role status
        roles = [role.name for role in member.roles if role.name != "@everyone"]
        role_count = len(roles)
        roles_display = ", ".join(roles[:3]) + (f" +{role_count-3} more" if role_count > 3 else "")
        
        # Determine boost status
        boost_status = f"YES - {member.premium_since.strftime('%Y-%m-%d')}" if member.premium_since else "NO"

        embed = discord.Embed(
            title=f"⚡ NETIZEN PROFILE: {member.name} ⚡",
            description=f"**DETAILED SCAN RESULTS FOR USER ID: {member.id}**",
            color=await self.get_random_cyber_color()
        )
        
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
            
        # Status indicators with cyberpunk formatting
        status_indicators = {
            discord.Status.online: "🟢 CONNECTED",
            discord.Status.idle: "🟠 LOW_POWER",
            discord.Status.dnd: "🔴 DO_NOT_DISTURB",
            discord.Status.offline: "⚫ DISCONNECTED"
        }
        
        status = status_indicators.get(member.status, "⚪ UNKNOWN")
            
        embed.add_field(
            name="IDENTITY",
            value=f"```ini\n[USERNAME] {member.name}\n[USER_ID] {member.id}\n[STATUS] {status}```",
            inline=False
        )
        
        embed.add_field(
            name="ACCESS METRICS",
            value=f"```yaml\nACCOUNT_AGE: {account_age_days} days ({account_age_years} years)\nSERVER_UPTIME: {join_age_days} days\nROLES_COUNT: {role_count}\nHIGHEST_ROLE: {member.top_role.name}```",
            inline=False
        )
        
        embed.add_field(
            name="NET CONNECTION",
            value=f"```fix\nVOICE_CHANNEL: {voice_channel}\nREGION: {voice_region}\nNITRO_BOOST: {boost_status}```",
            inline=False
        )
        
        embed.set_footer(text=f"SCAN INITIATED BY {ctx.author.name} • {discord.utils.utcnow().strftime('%H:%M:%S')}")
        
        await ctx.send(embed=embed)

# Setup function to load the cog
async def setup(bot):
    await bot.add_cog(MemberInfo(bot))
    print("⚡ NETRUNNER MODULE: MemberInfo initialized ⚡")
