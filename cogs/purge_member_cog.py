import discord
from discord import app_commands
from discord.ext import commands

class PurgeMemberCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="purgeuser", description="Deletes messages from a specific user.")
    @app_commands.describe(member="Select a user", limit="Number of messages to delete")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge_user_messages(self, interaction: discord.Interaction, member: discord.Member, limit: int = 100):
        def is_user_message(msg):
            return msg.author == member
        
        # Acknowledge the interaction immediately
        await interaction.response.defer(ephemeral=True)
        
        deleted = await interaction.channel.purge(limit=limit, check=is_user_message)
        
        await interaction.followup.send(f"🗑️ Deleted {len(deleted)} messages from {member.mention}.", ephemeral=True)
        
    @purge_user_messages.error
    async def purge_user_messages_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("🚫 You don't have permission to use this command.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PurgeMemberCog(bot))
