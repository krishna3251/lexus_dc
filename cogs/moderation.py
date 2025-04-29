import discord
from discord.ext import commands

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.muted_role = None  # Store the muted role

    async def get_or_ask_muted_role(self, ctx):
        """Check for an existing Muted role or ask the user to specify one."""
        if self.muted_role:
            return self.muted_role

        muted_role = discord.utils.get(ctx.guild.roles, name="Muted")

        if not muted_role:
            await ctx.send("❓ No 'Muted' role found. Please mention the role you want to use for muting.")

            def check(m):
                return m.author == ctx.author and m.mentions and isinstance(m.channel, discord.TextChannel)

            try:
                msg = await ctx.bot.wait_for("message", check=check, timeout=30)
                muted_role = msg.mentions[0]
                self.muted_role = muted_role  # Store for future use
                await ctx.send(f"✅ **Muted role set to:** {muted_role.mention}")
            except Exception:
                await ctx.send("⏳ **No response received.** Please try again and mention a valid role.")

        return muted_role

    @commands.command(name="warn", help="Warns a member.")
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str):
        embed = discord.Embed(
            title="⚠️ Warning", 
            description=f"{member.mention} has been warned.", 
            color=discord.Color.red()
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_footer(text=f"Warned by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @commands.command(name="purge", help="Deletes messages.")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int):
        if amount <= 0:
            await ctx.send("❌ Please specify a positive number.")
            return
        deleted = await ctx.channel.purge(limit=amount)
        await ctx.send(f"🗑️ Deleted {len(deleted)} messages.", delete_after=5)

    @commands.command(name="kick", help="Kicks a member from the server.")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="No reason provided"):
        await member.kick(reason=reason)
        embed = discord.Embed(
            title="🚨 Member Kicked",
            description=f"**{member.name}** has been kicked.",
            color=discord.Color.orange()
        )
        embed.add_field(name="👮‍♂️ Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="📜 Reason", value=reason, inline=True)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
        await ctx.send(embed=embed)

    @commands.command(name="ban", help="Bans a member from the server.")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason="No reason provided"):
        await member.ban(reason=reason)
        embed = discord.Embed(
            title="⛔ Member Banned",
            description=f"**{member.name}** has been banned.",
            color=discord.Color.red()
        )
        embed.add_field(name="👮‍♂️ Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="📜 Reason", value=reason, inline=True)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
        await ctx.send(embed=embed)

    @commands.command(name="mute", help="Mutes a member in the server.")
    @commands.has_permissions(manage_roles=True)
    async def mute(self, ctx, member: discord.Member):
        muted_role = await self.get_or_ask_muted_role(ctx)
        
        if muted_role and muted_role not in member.roles:
            await member.add_roles(muted_role)
            embed = discord.Embed(
                title="🔇 Member Muted",
                description=f"**{member.name}** has been muted.",
                color=discord.Color.dark_gray()
            )
            embed.add_field(name="👮‍♂️ Moderator", value=ctx.author.mention, inline=True)
            embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"⚠ {member.name} is already muted or role is missing!")

    @commands.command(name="unmute", help="Unmutes a member in the server.")
    @commands.has_permissions(manage_roles=True)
    async def unmute(self, ctx, member: discord.Member):
        muted_role = await self.get_or_ask_muted_role(ctx)

        if muted_role and muted_role in member.roles:
            await member.remove_roles(muted_role)
            embed = discord.Embed(
                title="🔊 Member Unmuted",
                description=f"**{member.name}** has been unmuted.",
                color=discord.Color.green()
            )
            embed.add_field(name="👮‍♂️ Moderator", value=ctx.author.mention, inline=True)
            embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
            await ctx.send(embed=embed)
        else:
            await ctx.send("⚠ User is not muted or muted role is missing!")

async def setup(bot):
    await bot.add_cog(Moderation(bot))
