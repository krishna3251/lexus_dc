import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import json
import datetime
import os
from typing import Optional

# File to store mod role IDs per guild
MOD_ROLES_FILE = "mod_roles.json"
OWNER_ID = 486555340670894080  # Your Discord user ID

def load_mod_roles():
    """Load mod roles from file"""
    if os.path.exists(MOD_ROLES_FILE):
        with open(MOD_ROLES_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_mod_roles(mod_roles):
    """Save mod roles to file"""
    with open(MOD_ROLES_FILE, 'w') as f:
        json.dump(mod_roles, f)

class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mod_roles = load_mod_roles()
    
    async def cog_check(self, ctx):
        """Check if user has permission to use moderation commands"""
        # Always allow the bot owner
        if ctx.author.id == OWNER_ID:
            return True
            
        # Check if user has mod role
        guild_id = str(ctx.guild.id)
        if guild_id in self.mod_roles:
            mod_role_id = self.mod_roles[guild_id]
            return discord.utils.get(ctx.author.roles, id=mod_role_id) is not None
        return False
    
    async def has_mod_role_or_owner(self, interaction: discord.Interaction):
        """Check if user has mod role or is the owner for app commands"""
        if interaction.user.id == OWNER_ID:
            return True
            
        guild_id = str(interaction.guild_id)
        if guild_id in self.mod_roles:
            mod_role_id = self.mod_roles[guild_id]
            return discord.utils.get(interaction.user.roles, id=mod_role_id) is not None
        return False
    
    @app_commands.command(name="setmodrole", description="Set a role as the moderation role")
    @app_commands.describe(role="The role to set as mod role")
    async def setmodrole(self, interaction: discord.Interaction, role: discord.Role):
        """Set the moderation role for the server"""
        # Only allow owner to set mod role initially
        if interaction.user.id != OWNER_ID and not await self.has_mod_role_or_owner(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return
            
        guild_id = str(interaction.guild_id)
        self.mod_roles[guild_id] = role.id
        save_mod_roles(self.mod_roles)
        
        embed = discord.Embed(
            title="Mod Role Set",
            description=f"The moderation role has been set to {role.mention}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="givemod", description="Give a user the mod role")
    @app_commands.describe(user="The user to give mod role to")
    async def givemod(self, interaction: discord.Interaction, user: discord.Member):
        """Give a user the mod role"""
        if not await self.has_mod_role_or_owner(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return
            
        guild_id = str(interaction.guild_id)
        if guild_id not in self.mod_roles:
            await interaction.response.send_message("No mod role has been set for this server. Use /setmodrole first.", ephemeral=True)
            return
            
        mod_role_id = self.mod_roles[guild_id]
        mod_role = interaction.guild.get_role(mod_role_id)
        
        if not mod_role:
            await interaction.response.send_message("The mod role no longer exists. Please set a new one with /setmodrole.", ephemeral=True)
            return
            
        if mod_role in user.roles:
            await interaction.response.send_message(f"{user.mention} already has the mod role.", ephemeral=True)
            return
            
        # Create confirmation buttons
        confirm_button = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.green)
        cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.red)
        
        view = discord.ui.View()
        view.add_item(confirm_button)
        view.add_item(cancel_button)
        
        embed = discord.Embed(
            title="Confirm Mod Role Assignment",
            description=f"Are you sure you want to give {user.mention} the mod role?",
            color=discord.Color.blue()
        )
        
        async def confirm_callback(interaction):
            await user.add_roles(mod_role)
            result_embed = discord.Embed(
                title="Mod Role Assigned",
                description=f"{user.mention} has been given the mod role.",
                color=discord.Color.green()
            )
            await interaction.response.edit_message(embed=result_embed, view=None)
            
        async def cancel_callback(interaction):
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="Cancelled",
                    description="Mod role assignment cancelled.",
                    color=discord.Color.red()
                ),
                view=None
            )
            
        confirm_button.callback = confirm_callback
        cancel_button.callback = cancel_callback
        
        await interaction.response.send_message(embed=embed, view=view)
    
    @app_commands.command(name="kick", description="Kick a user from the server")
    @app_commands.describe(
        user="The user to kick",
        reason="Reason for kicking the user"
    )
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = "No reason provided"):
        """Kick a user from the server"""
        if not await self.has_mod_role_or_owner(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return
            
        # Check if the bot can kick the user
        if not interaction.guild.me.guild_permissions.kick_members:
            await interaction.response.send_message("I don't have permission to kick members.", ephemeral=True)
            return
            
        # Check if the user is kickable (not higher in hierarchy)
        if user.top_role >= interaction.guild.me.top_role or user.id == interaction.guild.owner_id:
            await interaction.response.send_message("I can't kick this user due to role hierarchy.", ephemeral=True)
            return
            
        if user.id == interaction.user.id:
            await interaction.response.send_message("You can't kick yourself.", ephemeral=True)
            return
            
        # Create confirmation buttons
        confirm_button = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.green)
        cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.red)
        
        view = discord.ui.View()
        view.add_item(confirm_button)
        view.add_item(cancel_button)
        
        embed = discord.Embed(
            title="Confirm Kick",
            description=f"Are you sure you want to kick {user.mention}?\nReason: {reason}",
            color=discord.Color.yellow()
        )
        
        async def confirm_callback(interaction):
            try:
                await user.kick(reason=f"Kicked by {interaction.user} - {reason}")
                result_embed = discord.Embed(
                    title="User Kicked",
                    description=f"{user.mention} has been kicked.\nReason: {reason}",
                    color=discord.Color.green()
                )
                await interaction.response.edit_message(embed=result_embed, view=None)
            except discord.Forbidden:
                await interaction.response.edit_message(
                    embed=discord.Embed(
                        title="Error",
                        description="I don't have permission to kick this user.",
                        color=discord.Color.red()
                    ),
                    view=None
                )
            except Exception as e:
                await interaction.response.edit_message(
                    embed=discord.Embed(
                        title="Error",
                        description=f"An error occurred: {str(e)}",
                        color=discord.Color.red()
                    ),
                    view=None
                )
                
        async def cancel_callback(interaction):
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="Cancelled",
                    description="Kick cancelled.",
                    color=discord.Color.red()
                ),
                view=None
            )
            
        confirm_button.callback = confirm_callback
        cancel_button.callback = cancel_callback
        
        await interaction.response.send_message(embed=embed, view=view)
    
    @app_commands.command(name="ban", description="Ban a user from the server")
    @app_commands.describe(
        user="The user to ban",
        reason="Reason for banning the user",
        delete_days="Number of days of message history to delete (0-7)"
    )
    async def ban(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = "No reason provided", delete_days: Optional[int] = 1):
        """Ban a user from the server"""
        if not await self.has_mod_role_or_owner(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return
            
        # Check if the bot can ban the user
        if not interaction.guild.me.guild_permissions.ban_members:
            await interaction.response.send_message("I don't have permission to ban members.", ephemeral=True)
            return
            
        # Check if the user is bannable (not higher in hierarchy)
        if user.top_role >= interaction.guild.me.top_role or user.id == interaction.guild.owner_id:
            await interaction.response.send_message("I can't ban this user due to role hierarchy.", ephemeral=True)
            return
            
        if user.id == interaction.user.id:
            await interaction.response.send_message("You can't ban yourself.", ephemeral=True)
            return
            
        # Limit delete_days to valid range
        delete_days = max(0, min(7, delete_days))
        
        # Create confirmation buttons
        confirm_button = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.green)
        cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.red)
        
        view = discord.ui.View()
        view.add_item(confirm_button)
        view.add_item(cancel_button)
        
        embed = discord.Embed(
            title="Confirm Ban",
            description=f"Are you sure you want to ban {user.mention}?\nReason: {reason}\nDelete message history: {delete_days} day(s)",
            color=discord.Color.red()
        )
        
        async def confirm_callback(interaction):
            try:
                await user.ban(reason=f"Banned by {interaction.user} - {reason}", delete_message_days=delete_days)
                result_embed = discord.Embed(
                    title="User Banned",
                    description=f"{user.mention} has been banned.\nReason: {reason}",
                    color=discord.Color.green()
                )
                await interaction.response.edit_message(embed=result_embed, view=None)
            except discord.Forbidden:
                await interaction.response.edit_message(
                    embed=discord.Embed(
                        title="Error",
                        description="I don't have permission to ban this user.",
                        color=discord.Color.red()
                    ),
                    view=None
                )
            except Exception as e:
                await interaction.response.edit_message(
                    embed=discord.Embed(
                        title="Error",
                        description=f"An error occurred: {str(e)}",
                        color=discord.Color.red()
                    ),
                    view=None
                )
                
        async def cancel_callback(interaction):
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="Cancelled",
                    description="Ban cancelled.",
                    color=discord.Color.red()
                ),
                view=None
            )
            
        confirm_button.callback = confirm_callback
        cancel_button.callback = cancel_callback
        
        await interaction.response.send_message(embed=embed, view=view)
    
    @app_commands.command(name="timeout", description="Timeout a user")
    @app_commands.describe(
        user="The user to timeout",
        duration="Timeout duration in minutes",
        reason="Reason for the timeout"
    )
    async def timeout(self, interaction: discord.Interaction, user: discord.Member, duration: int, reason: Optional[str] = "No reason provided"):
        """Timeout a user for a specified duration"""
        if not await self.has_mod_role_or_owner(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return
            
        # Check if the bot can timeout the user
        if not interaction.guild.me.guild_permissions.moderate_members:
            await interaction.response.send_message("I don't have permission to timeout members.", ephemeral=True)
            return
            
        # Check if the user can be timed out (not higher in hierarchy)
        if user.top_role >= interaction.guild.me.top_role or user.id == interaction.guild.owner_id:
            await interaction.response.send_message("I can't timeout this user due to role hierarchy.", ephemeral=True)
            return
            
        if user.id == interaction.user.id:
            await interaction.response.send_message("You can't timeout yourself.", ephemeral=True)
            return
            
        # Calculate timeout duration
        timeout_duration = discord.utils.utcnow() + datetime.timedelta(minutes=duration)
        
        # Create confirmation buttons
        confirm_button = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.green)
        cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.red)
        
        view = discord.ui.View()
        view.add_item(confirm_button)
        view.add_item(cancel_button)
        
        embed = discord.Embed(
            title="Confirm Timeout",
            description=f"Are you sure you want to timeout {user.mention} for {duration} minutes?\nReason: {reason}",
            color=discord.Color.orange()
        )
        
        async def confirm_callback(interaction):
            try:
                await user.timeout(timeout_duration, reason=f"Timed out by {interaction.user} - {reason}")
                result_embed = discord.Embed(
                    title="User Timed Out",
                    description=f"{user.mention} has been timed out for {duration} minutes.\nReason: {reason}",
                    color=discord.Color.green()
                )
                await interaction.response.edit_message(embed=result_embed, view=None)
            except discord.Forbidden:
                await interaction.response.edit_message(
                    embed=discord.Embed(
                        title="Error",
                        description="I don't have permission to timeout this user.",
                        color=discord.Color.red()
                    ),
                    view=None
                )
            except Exception as e:
                await interaction.response.edit_message(
                    embed=discord.Embed(
                        title="Error",
                        description=f"An error occurred: {str(e)}",
                        color=discord.Color.red()
                    ),
                    view=None
                )
                
        async def cancel_callback(interaction):
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="Cancelled",
                    description="Timeout cancelled.",
                    color=discord.Color.red()
                ),
                view=None
            )
            
        confirm_button.callback = confirm_callback
        cancel_button.callback = cancel_callback
        
        await interaction.response.send_message(embed=embed, view=view)
    
    @app_commands.command(name="moderate", description="Open moderation panel for a user")
    @app_commands.describe(user="The user to moderate")
    async def moderate(self, interaction: discord.Interaction, user: discord.Member):
        """Open moderation panel with buttons for different actions"""
        if not await self.has_mod_role_or_owner(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return
            
        # Check if the user can be moderated (not higher in hierarchy)
        if user.top_role >= interaction.guild.me.top_role or user.id == interaction.guild.owner_id:
            await interaction.response.send_message("I can't moderate this user due to role hierarchy.", ephemeral=True)
            return
            
        if user.id == interaction.user.id:
            await interaction.response.send_message("You can't moderate yourself.", ephemeral=True)
            return
            
        # Create moderation panel
        embed = discord.Embed(
            title="Moderation Panel",
            description=f"Select an action to perform on {user.mention}",
            color=discord.Color.blue()
        )
        embed.add_field(name="User Info", value=f"**ID:** {user.id}\n**Joined:** {user.joined_at.strftime('%Y-%m-%d')}")
        
        # Create action buttons
        kick_button = discord.ui.Button(label="Kick", style=discord.ButtonStyle.danger, row=0)
        ban_button = discord.ui.Button(label="Ban", style=discord.ButtonStyle.danger, row=0)
        timeout_button = discord.ui.Button(label="Timeout", style=discord.ButtonStyle.secondary, row=0)
        mod_button = discord.ui.Button(label="Give Mod", style=discord.ButtonStyle.primary, row=1)
        
        view = discord.ui.View()
        view.add_item(kick_button)
        view.add_item(ban_button)
        view.add_item(timeout_button)
        
        guild_id = str(interaction.guild_id)
        if guild_id in self.mod_roles:
            view.add_item(mod_button)
        
        # Button callbacks
        async def kick_callback(interaction):
            # Create a text input modal for reason
            class KickModal(discord.ui.Modal, title="Kick User"):
                reason = discord.ui.TextInput(
                    label="Reason",
                    placeholder="Enter reason for kick...",
                    required=False,
                    default="No reason provided"
                )
                
                async def on_submit(self, interaction):
                    reason_text = self.reason.value or "No reason provided"
                    try:
                        await user.kick(reason=f"Kicked by {interaction.user} - {reason_text}")
                        result_embed = discord.Embed(
                            title="User Kicked",
                            description=f"{user.mention} has been kicked.\nReason: {reason_text}",
                            color=discord.Color.green()
                        )
                        await interaction.response.send_message(embed=result_embed)
                    except discord.Forbidden:
                        await interaction.response.send_message(
                            embed=discord.Embed(
                                title="Error",
                                description="I don't have permission to kick this user.",
                                color=discord.Color.red()
                            )
                        )
                    except Exception as e:
                        await interaction.response.send_message(
                            embed=discord.Embed(
                                title="Error",
                                description=f"An error occurred: {str(e)}",
                                color=discord.Color.red()
                            )
                        )
            
            await interaction.response.send_modal(KickModal())
        
        async def ban_callback(interaction):
            # Create a modal for ban reason and delete days
            class BanModal(discord.ui.Modal, title="Ban User"):
                reason = discord.ui.TextInput(
                    label="Reason",
                    placeholder="Enter reason for ban...",
                    required=False,
                    default="No reason provided"
                )
                delete_days = discord.ui.TextInput(
                    label="Delete Message History (days)",
                    placeholder="Enter number of days (0-7)",
                    required=True,
                    default="1"
                )
                
                async def on_submit(self, interaction):
                    reason_text = self.reason.value or "No reason provided"
                    try:
                        delete_days_value = int(self.delete_days.value)
                        delete_days_value = max(0, min(7, delete_days_value))  # Limit to 0-7 range
                    except ValueError:
                        delete_days_value = 1
                        
                    try:
                        await user.ban(reason=f"Banned by {interaction.user} - {reason_text}", delete_message_days=delete_days_value)
                        result_embed = discord.Embed(
                            title="User Banned",
                            description=f"{user.mention} has been banned.\nReason: {reason_text}\nDeleted message history: {delete_days_value} day(s)",
                            color=discord.Color.green()
                        )
                        await interaction.response.send_message(embed=result_embed)
                    except discord.Forbidden:
                        await interaction.response.send_message(
                            embed=discord.Embed(
                                title="Error",
                                description="I don't have permission to ban this user.",
                                color=discord.Color.red()
                            )
                        )
                    except Exception as e:
                        await interaction.response.send_message(
                            embed=discord.Embed(
                                title="Error",
                                description=f"An error occurred: {str(e)}",
                                color=discord.Color.red()
                            )
                        )
            
            await interaction.response.send_modal(BanModal())
        
        async def timeout_callback(interaction):
            # Create a modal for timeout duration and reason
            class TimeoutModal(discord.ui.Modal, title="Timeout User"):
                duration = discord.ui.TextInput(
                    label="Duration (minutes)",
                    placeholder="Enter timeout duration in minutes",
                    required=True,
                    default="60"
                )
                reason = discord.ui.TextInput(
                    label="Reason",
                    placeholder="Enter reason for timeout...",
                    required=False,
                    default="No reason provided"
                )
                
                async def on_submit(self, interaction):
                    reason_text = self.reason.value or "No reason provided"
                    try:
                        duration_value = int(self.duration.value)
                    except ValueError:
                        duration_value = 60
                        
                    timeout_duration = discord.utils.utcnow() + datetime.timedelta(minutes=duration_value)
                        
                    try:
                        await user.timeout(timeout_duration, reason=f"Timed out by {interaction.user} - {reason_text}")
                        result_embed = discord.Embed(
                            title="User Timed Out",
                            description=f"{user.mention} has been timed out for {duration_value} minutes.\nReason: {reason_text}",
                            color=discord.Color.green()
                        )
                        await interaction.response.send_message(embed=result_embed)
                    except discord.Forbidden:
                        await interaction.response.send_message(
                            embed=discord.Embed(
                                title="Error",
                                description="I don't have permission to timeout this user.",
                                color=discord.Color.red()
                            )
                        )
                    except Exception as e:
                        await interaction.response.send_message(
                            embed=discord.Embed(
                                title="Error",
                                description=f"An error occurred: {str(e)}",
                                color=discord.Color.red()
                            )
                        )
            
            await interaction.response.send_modal(TimeoutModal())
        
        async def mod_callback(interaction):
            if guild_id not in self.mod_roles:
                await interaction.response.send_message("No mod role has been set for this server. Use /setmodrole first.", ephemeral=True)
                return
                
            mod_role_id = self.mod_roles[guild_id]
            mod_role = interaction.guild.get_role(mod_role_id)
            
            if not mod_role:
                await interaction.response.send_message("The mod role no longer exists. Please set a new one with /setmodrole.", ephemeral=True)
                return
                
            if mod_role in user.roles:
                await interaction.response.send_message(f"{user.mention} already has the mod role.", ephemeral=True)
                return
                
            # Create confirmation view
            confirm_view = discord.ui.View()
            confirm_button = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.green)
            cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.red)
            
            confirm_view.add_item(confirm_button)
            confirm_view.add_item(cancel_button)
            
            confirm_embed = discord.Embed(
                title="Confirm Mod Role Assignment",
                description=f"Are you sure you want to give {user.mention} the mod role?",
                color=discord.Color.blue()
            )
            
            async def confirm_mod_callback(interaction):
                await user.add_roles(mod_role)
                result_embed = discord.Embed(
                    title="Mod Role Assigned",
                    description=f"{user.mention} has been given the mod role.",
                    color=discord.Color.green()
                )
                await interaction.response.edit_message(embed=result_embed, view=None)
                
            async def cancel_mod_callback(interaction):
                await interaction.response.edit_message(
                    embed=discord.Embed(
                        title="Cancelled",
                        description="Mod role assignment cancelled.",
                        color=discord.Color.red()
                    ),
                    view=None
                )
                
            confirm_button.callback = confirm_mod_callback
            cancel_button.callback = cancel_mod_callback
            
            await interaction.response.send_message(embed=confirm_embed, view=confirm_view, ephemeral=True)
        
        # Assign callbacks
        kick_button.callback = kick_callback
        ban_button.callback = ban_callback
        timeout_button.callback = timeout_callback
        mod_button.callback = mod_callback
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(ModerationCog(bot))

# Don't forget to add these imports at the top
