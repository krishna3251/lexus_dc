import discord
from discord import app_commands, ui
from discord.ext import commands
import datetime
import asyncio

class ConfirmPurgeView(ui.View):
    def __init__(self, member, limit, original_interaction):
        super().__init__(timeout=60)
        self.member = member
        self.limit = limit
        self.original_interaction = original_interaction
        self.value = None

    @ui.button(label="CONFIRM PURGE", style=discord.ButtonStyle.danger, custom_id="confirm_purge", emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        self.value = True
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(view=self)
        self.stop()

    @ui.button(label="CANCEL", style=discord.ButtonStyle.secondary, custom_id="cancel_purge", emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        self.value = False
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(content="**OPERATION ABORTED**", view=self, embed=None)
        self.stop()
    
    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        
        try:
            await self.original_interaction.edit_original_response(content="**OPERATION TIMED OUT**", view=self, embed=None)
        except:
            pass

class PurgeMemberCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.color = 0x00FFFF  # Cyberpunk cyan/blue color

    @app_commands.command(name="purgeuser", description="Delete messages from a specific user with cyberpunk style")
    @app_commands.describe(
        member="Target user for message deletion", 
        limit="Number of messages to scan (default: 100)",
        reason="Reason for purge (optional)"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge_user_messages(self, interaction: discord.Interaction, member: discord.Member, limit: int = 100, reason: str = None):
        # Acknowledge the interaction immediately
        await interaction.response.defer(ephemeral=True)
        
        # Create confirmation embed
        embed = discord.Embed(
            title="⚠️ SECURE MESSAGE PURGE PROTOCOL ⚠️",
            description=f"**TARGET:** {member.mention}\n**SCAN DEPTH:** {limit} messages\n**CHANNEL:** {interaction.channel.mention}",
            color=self.color,
            timestamp=datetime.datetime.now()
        )
        
        if reason:
            embed.add_field(name="REASON", value=reason, inline=False)
            
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        
        # Create confirmation view
        view = ConfirmPurgeView(member, limit, interaction)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        
        # Wait for the user's confirmation
        await view.wait()
        
        if view.value:
            # User confirmed, proceed with purge
            def is_user_message(msg):
                return msg.author == member
            
            try:
                deleted = await interaction.channel.purge(limit=limit, check=is_user_message)
                
                # Create success embed
                success_embed = discord.Embed(
                    title="🔄 NEURAL PURGE COMPLETE",
                    description=f"**{len(deleted)}** messages from **{member.display_name}** have been wiped from the system.",
                    color=self.color,
                    timestamp=datetime.datetime.now()
                )
                success_embed.set_footer(text=f"Executed by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
                
                await interaction.edit_original_response(embed=success_embed, view=None)
                
                # Log the purge to the server's audit log
                try:
                    log_channel = discord.utils.get(interaction.guild.text_channels, name="mod-logs")
                    if log_channel:
                        log_embed = discord.Embed(
                            title="⚡ MESSAGE PURGE EXECUTED",
                            description=f"**Moderator:** {interaction.user.mention}\n**Target:** {member.mention}\n**Channel:** {interaction.channel.mention}\n**Messages Deleted:** {len(deleted)}",
                            color=self.color,
                            timestamp=datetime.datetime.now()
                        )
                        if reason:
                            log_embed.add_field(name="Reason", value=reason, inline=False)
                            
                        await log_channel.send(embed=log_embed)
                except Exception as e:
                    # Silently fail if logging fails
                    pass
                    
            except discord.Forbidden:
                await interaction.edit_original_response(
                    content="**ERROR:** Insufficient permissions to delete messages.",
                    embed=None,
                    view=None
                )
            except discord.HTTPException as e:
                await interaction.edit_original_response(
                    content=f"**SYSTEM ERROR:** Failed to purge messages. Error code: {e.code}",
                    embed=None,
                    view=None
                )
        
    @purge_user_messages.error
    async def purge_user_messages_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title="🔒 ACCESS DENIED",
                description="You lack the necessary clearance level to execute this command.",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title="⚠️ SYSTEM ERROR",
                description=f"Command execution failed: {str(error)}",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(PurgeMemberCog(bot))
