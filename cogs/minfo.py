import discord
from discord.ext import commands

class MemberInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mod_role = None  # Store the moderator role

    async def get_or_ask_mod_role(self, ctx):
        """Check for an existing Moderator role or ask the user to specify one."""
        if self.mod_role:
            return self.mod_role

        mod_roles = [role for role in ctx.guild.roles if "mod" in role.name.lower() or "admin" in role.name.lower()]
        if mod_roles:
            mod_role = mod_roles[0]
            self.mod_role = mod_role  # Store for future use
            await ctx.send(f"✅ **Moderator role automatically set to:** {mod_role.mention}")
        else:
            await ctx.send("❓ No 'Moderator' role found. Please mention the role you want to use for moderators.")

            def check(m):
                return m.author == ctx.author and m.mentions and isinstance(m.channel, discord.TextChannel)

            try:
                msg = await ctx.bot.wait_for("message", check=check, timeout=30)
                mod_role = msg.mentions[0]
                self.mod_role = mod_role  # Store for future use
                await ctx.send(f"✅ **Moderator role set to:** {mod_role.mention}")
            except Exception:
                await ctx.send("⏳ **No response received.** Please try again and mention a valid role.")

        return self.mod_role

    @commands.command(name="members")
    async def members(self, ctx):
        guild = ctx.guild
        embed = discord.Embed(
            title=f"👥 Members of {guild.name}",
            description=f"Total Members: {len(guild.members)}",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        
        for member in guild.members[:10]:  # Limit display to 10 members for neatness
            embed.add_field(
                name=member.name,
                value=f"🆔 ID: {member.id}\n🎭 Role: {member.top_role.name}",
                inline=True
            )
        
        await ctx.send(embed=embed)

    @commands.command(name="moderators")
    async def moderators(self, ctx):
        mod_role = await self.get_or_ask_mod_role(ctx)
        
        if mod_role:
            embed = discord.Embed(
                title=f"🛡 Moderator Info - {mod_role.name}",
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)
            
            # Optimized to get all members with the role at once
            members_with_role = [member for member in ctx.guild.members if isinstance(member, discord.Member) and mod_role in member.roles]
            
            if members_with_role:
                for member in members_with_role:
                    embed.add_field(
                        name=member.display_name,
                        value=f"🆔 ID: {member.id}\n🔧 Role: {mod_role.name}",
                        inline=True
                    )
            else:
                embed.description = f"No members have the {mod_role.name} role."
                
            await ctx.send(embed=embed)
        else:
            await ctx.send("No Moderator role found.")

    @commands.command(name="userinfo", help="Displays detailed information about a user.")
    async def userinfo(self, ctx, member: discord.Member = None):
        member = member or ctx.author

        # Get Voice Region (If the user is in a voice channel)
        voice_state = member.voice
        voice_region = voice_state.channel.rtc_region if voice_state and voice_state.channel else "Not in a VC"

        # Determine "Power" in the Server (Based on Role Position and Boosts)
        highest_role = member.top_role.name if len(member.roles) > 1 else "@everyone"
        boost_status = "Yes" if member.premium_since else "No"

        embed = discord.Embed(
            title=f"👤 User Info - {member.name}",
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
        embed.add_field(name="🆔 User ID", value=member.id, inline=True)
        embed.add_field(name="🎭 Highest Role", value=highest_role, inline=True)
        embed.add_field(name="💎 Nitro Booster", value=boost_status, inline=True)
        embed.add_field(name="🎤 Voice Region", value=voice_region, inline=True)
        embed.add_field(name="📅 Joined At", value=member.joined_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="📅 Account Created", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
        embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)

        await ctx.send(embed=embed)

# Setup function to load the cog
async def setup(bot):
    await bot.add_cog(MemberInfo(bot))
