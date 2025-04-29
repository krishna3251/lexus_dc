import discord
from discord.ext import commands

class MassRoleAddCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="massrole", help="Adds a role to all members.")
    @commands.has_permissions(manage_roles=True)
    async def mass_role_add(self, ctx, role: discord.Role):
        # Send initial message
        status_message = await ctx.send(f"⏳ Adding role {role.name} to all members. This may take some time...")
        
        # Counter for progress tracking
        success_count = 0
        failure_count = 0
        total_members = len(ctx.guild.members)
        
        # Process members in batches to avoid rate limits
        for i, member in enumerate(ctx.guild.members):
            try:
                if role not in member.roles:  # Only add if they don't have it already
                    await member.add_roles(role)
                    success_count += 1
                
                # Update progress every 10 members
                if i % 10 == 0:
                    await status_message.edit(content=f"⏳ Progress: {i}/{total_members} members processed...")
            except Exception as e:
                failure_count += 1
                print(f"Failed to add role to {member.display_name}: {e}")
        
        # Final report
        await status_message.edit(content=f"✅ Role {role.name} added to {success_count} members.\n❌ Failed for {failure_count} members.")

async def setup(bot):
    await bot.add_cog(MassRoleAddCog(bot))
