import discord
from discord import app_commands
from discord.ext import commands
import datetime
import random
import asyncio
import time

class SlashCommandsCog(commands.Cog):
    """Slash command implementations for various bot features"""
    
    def __init__(self, bot):
        self.bot = bot
        self._last_members = {}
        self.start_time = datetime.datetime.utcnow()
        # Register the commands with the bot's tree
        self._register_commands()
        
    def _register_commands(self):
        """Ensure commands are properly registered to the bot's command tree"""
        # This is optional - commands should be registered automatically, but this helps ensure it
        print("Registering slash commands for SlashCommandsCog")
    
    # -------- Ping Command --------
    @app_commands.command(name="pinginfo", description="Check the bot's latency and uptime")
    async def ping_slash(self, interaction: discord.Interaction):
        """Check the bot's latency and uptime"""
        start_time = time.perf_counter()
        
        # Create initial embed
        embed = discord.Embed(
            title="🔄 Pinging...",
            description="Measuring latency...",
            color=discord.Color.blue()
        )
        
        # Send initial response
        await interaction.response.send_message(embed=embed)
        
        # Calculate various latency measurements
        end_time = time.perf_counter()
        api_latency = (end_time - start_time) * 1000
        websocket_latency = self.bot.latency * 1000
        
        # Get database latency (example implementation)
        db_start_time = time.perf_counter()
        try:
            # Placeholder for DB operation
            await asyncio.sleep(0.01)
            db_available = True
        except Exception:
            db_available = False
        db_end_time = time.perf_counter()
        db_latency = (db_end_time - db_start_time) * 1000
        
        # Calculate uptime
        current_time = datetime.datetime.utcnow()
        delta = current_time - self.start_time
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        # Choose color based on websocket latency
        if websocket_latency < 100:
            color = discord.Color.green()
            latency_text = "Excellent"
        elif websocket_latency < 200:
            color = discord.Color.green()
            latency_text = "Good"
        elif websocket_latency < 300:
            color = discord.Color(0xFFA500)  # Orange
            latency_text = "Decent"
        elif websocket_latency < 400:
            color = discord.Color.orange()
            latency_text = "Average"
        elif websocket_latency < 600:
            color = discord.Color.red()
            latency_text = "Poor"
        else:
            color = discord.Color.dark_red()
            latency_text = "Very Poor"
        
        # Create the updated embed
        embed = discord.Embed(
            title="🚀 Pong!",
            description=f"**Status:** {latency_text} ({websocket_latency:.2f}ms)",
            color=color,
            timestamp=current_time
        )
        
        embed.add_field(
            name="⏱️ Latency",
            value=(
                f"**API:** {api_latency:.2f}ms\n"
                f"**WebSocket:** {websocket_latency:.2f}ms\n"
                f"**Database:** {db_latency:.2f}ms"
            ),
            inline=True
        )
        
        embed.add_field(
            name="⬆️ Uptime",
            value=(
                f"**Days:** {days}\n"
                f"**Hours:** {hours}\n"
                f"**Minutes:** {minutes}"
            ),
            inline=True
        )
        
        embed.set_footer(text=f"Bot: {self.bot.user.name} | Discord API Version: {discord.__version__}")
        
        # Update the message
        await interaction.edit_original_response(embed=embed)
    
    # -------- Channel Permission Commands --------
    @app_commands.command(name="lockdown", description="Lock a channel, preventing members from sending messages")
    @app_commands.describe(
        channel="The channel to lock (defaults to current channel)",
        reason="Reason for locking the channel"
    )
    async def lock_slash(self, interaction: discord.Interaction, 
                         channel: discord.TextChannel = None, 
                         reason: str = "No reason provided"):
        """Lock a channel, preventing members from sending messages"""
        # Default to current channel if none provided
        channel = channel or interaction.channel
        
        # Check permissions
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ You don't have permission to manage channels.", ephemeral=True)
            return
            
        # Check if the bot has permissions
        if not interaction.guild.me.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ I don't have permission to manage channels.", ephemeral=True)
            return
        
        # Get the @everyone role
        everyone_role = interaction.guild.default_role
        
        # Update the channel permissions
        await channel.set_permissions(everyone_role, send_messages=False, reason=f"Channel locked by {interaction.user} - {reason}")
        
        # Respond with success message
        embed = discord.Embed(
            title="🔒 Channel Locked",
            description=f"{channel.mention} has been locked.\nReason: {reason}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Locked by {interaction.user}")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="unlockdown", description="Unlock a channel, allowing members to send messages")
    @app_commands.describe(
        channel="The channel to unlock (defaults to current channel)",
        reason="Reason for unlocking the channel"
    )
    async def unlock_slash(self, interaction: discord.Interaction, 
                           channel: discord.TextChannel = None, 
                           reason: str = "No reason provided"):
        """Unlock a channel, allowing members to send messages"""
        # Default to current channel if none provided
        channel = channel or interaction.channel
        
        # Check permissions
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ You don't have permission to manage channels.", ephemeral=True)
            return
            
        # Check if the bot has permissions
        if not interaction.guild.me.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ I don't have permission to manage channels.", ephemeral=True)
            return
        
        # Get the @everyone role
        everyone_role = interaction.guild.default_role
        
        # Update the channel permissions
        await channel.set_permissions(everyone_role, send_messages=None, reason=f"Channel unlocked by {interaction.user} - {reason}")
        
        # Respond with success message
        embed = discord.Embed(
            title="🔓 Channel Unlocked",
            description=f"{channel.mention} has been unlocked.\nReason: {reason}",
            color=discord.Color.green(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Unlocked by {interaction.user}")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="slowmode", description="Set slowmode for a channel")
    @app_commands.describe(
        seconds="Slowmode delay in seconds (0 to disable)",
        channel="The channel to set slowmode for (defaults to current channel)"
    )
    async def slowmode_slash(self, interaction: discord.Interaction, 
                             seconds: int, 
                             channel: discord.TextChannel = None):
        """Set slowmode for a channel"""
        # Default to current channel if none provided
        channel = channel or interaction.channel
        
        # Check permissions
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ You don't have permission to manage channels.", ephemeral=True)
            return
            
        # Check if the bot has permissions
        if not interaction.guild.me.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ I don't have permission to manage channels.", ephemeral=True)
            return
        
        # Validate input
        if seconds < 0:
            await interaction.response.send_message("❌ Slowmode delay must be a positive number or 0.", ephemeral=True)
            return
        
        if seconds > 21600:  # Discord's max is 6 hours (21600 seconds)
            await interaction.response.send_message("❌ Slowmode delay cannot exceed 6 hours (21600 seconds).", ephemeral=True)
            return
        
        # Set slowmode
        await channel.edit(slowmode_delay=seconds)
        
        # Create response message
        if seconds == 0:
            message = f"🕒 Slowmode has been disabled in {channel.mention}."
            color = discord.Color.green()
        else:
            # Format the time in a readable format
            if seconds < 60:
                time_str = f"{seconds} second{'s' if seconds != 1 else ''}"
            elif seconds < 3600:
                minutes = seconds // 60
                time_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
            else:
                hours = seconds // 3600
                time_str = f"{hours} hour{'s' if hours != 1 else ''}"
            
            message = f"🕒 Slowmode set to {time_str} in {channel.mention}."
            color = discord.Color.orange()
        
        # Respond with embed
        embed = discord.Embed(
            title="Slowmode Updated",
            description=message,
            color=color,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Modified by {interaction.user}")
        
        await interaction.response.send_message(embed=embed)
    
    # -------- Moderation Commands --------
    @app_commands.command(name="purge", description="Bulk delete messages from a channel")
    @app_commands.describe(
        amount="Number of messages to delete (1-100)",
        user="Only delete messages from this user (optional)"
    )
    async def purge_slash(self, interaction: discord.Interaction, 
                          amount: int, 
                          user: discord.User = None):
        """Bulk delete messages from a channel"""
        # Check permissions
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You don't have permission to manage messages.", ephemeral=True)
            return
            
        # Check if the bot has permissions
        if not interaction.guild.me.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ I don't have permission to manage messages.", ephemeral=True)
            return
        
        # Validate amount
        if amount < 1 or amount > 100:
            await interaction.response.send_message("❌ You can only delete between 1 and 100 messages at a time.", ephemeral=True)
            return
        
        # Defer the response since this might take a moment
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Define the check function for messages if a user is specified
            def check_user(message):
                return user is None or message.author.id == user.id
            
            # Purge messages
            if user:
                deleted = await interaction.channel.purge(limit=amount, check=check_user)
                count = len(deleted)
                message = f"✅ Successfully deleted {count} message{'s' if count != 1 else ''} from {user.mention}."
            else:
                deleted = await interaction.channel.purge(limit=amount)
                count = len(deleted)
                message = f"✅ Successfully deleted {count} message{'s' if count != 1 else ''}."
            
            # Send confirmation
            await interaction.followup.send(message, ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to delete messages in this channel.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(SlashCommandsCog(bot))