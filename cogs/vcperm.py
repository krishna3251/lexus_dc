import discord
from discord.ext import commands

class VCPermissionCog(commands.Cog):
    """⚙️ Voice Channel Permission System - Manage who can join restricted VCs."""

    def __init__(self, bot):
        self.bot = bot
        self.allowed_users = set()  # Store allowed user IDs
        self.restricted_vcs = set()  # Store restricted voice channels where admin is present

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Automatically moves users out of restricted VCs if they are not allowed."""
        if not after.channel:  # User left VC
            return

        # Check if the joined VC is restricted
        if after.channel.id in self.restricted_vcs and member.id not in self.allowed_users:
            await member.move_to(None)  # Kick the user from VC
            await member.send("🚫 You are not allowed to join this VC. Please get permission from an admin.")

    @commands.command(name="restrict_vc", help="🔒 Restrict the VC where the admin is currently in.")
    @commands.has_permissions(administrator=True)
    async def restrict_vc(self, ctx):
        """Restrict the voice channel where the admin is currently in."""
        if ctx.author.voice and ctx.author.voice.channel:
            self.restricted_vcs.add(ctx.author.voice.channel.id)
            await ctx.send(f"🔒 **{ctx.author.voice.channel.name}** is now a restricted VC.")
        else:
            await ctx.send("⚠ **You must be in a voice channel to restrict it.**")

    @commands.command(name="unrestrict_vc", help="🔓 Unrestrict the VC where the admin is currently in.")
    @commands.has_permissions(administrator=True)
    async def unrestrict_vc(self, ctx):
        """Remove restriction from the VC where the admin is currently in."""
        if ctx.author.voice and ctx.author.voice.channel:
            self.restricted_vcs.discard(ctx.author.voice.channel.id)
            await ctx.send(f"✅ **{ctx.author.voice.channel.name}** is no longer restricted.")
        else:
            await ctx.send("⚠ **You must be in a voice channel to unrestrict it.**")

    @commands.command(name="add_vc_user", help="✅ Allow a user to join restricted VCs.")
    @commands.has_permissions(administrator=True)
    async def add_vc_user(self, ctx, user: discord.User):
        """Allow a user to join restricted VCs."""
        self.allowed_users.add(user.id)
        await ctx.send(f"✅ **{user.mention} can now join restricted VCs.**")

    @commands.command(name="remove_vc_user", help="❌ Remove a user's access to restricted VCs.")
    @commands.has_permissions(administrator=True)
    async def remove_vc_user(self, ctx, user: discord.User):
        """Remove a user from the allowed list."""
        self.allowed_users.discard(user.id)
        await ctx.send(f"❌ **{user.mention} has been removed from the allowed list.**")

    @commands.command(name="list_vc_users", help="👥 Show a list of users allowed in restricted VCs.")
    @commands.has_permissions(administrator=True)
    async def list_vc_users(self, ctx):
        """List all users allowed to join restricted VCs."""
        if not self.allowed_users:
            await ctx.send("🚫 **No users have been granted VC access.**")
        else:
            users = [f"<@{user_id}>" for user_id in self.allowed_users]
            await ctx.send("👤 **Allowed VC Users:** " + ", ".join(users))

async def setup(bot):
    await bot.add_cog(VCPermissionCog(bot))
