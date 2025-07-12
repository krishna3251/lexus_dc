import discord
from discord.ext import commands
import asyncio
import json
import logging
import os
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables like a civilized human being
load_dotenv()

# Because apparently some people need their hand held
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AntiNukeCog(commands.Cog):
    """Anti-nuke system that actually works, unlike your last attempt"""
    
    def __init__(self, bot):
        self.bot = bot
        
        # Track violations like we're the Discord police
        self.violations: Dict[int, List[datetime]] = {}
        self.whitelisted_roles: List[int] = []
        self.whitelisted_users: List[int] = []
        
        # Thresholds - adjust these if you want to be more/less trigger happy
        self.MAX_ACTIONS = 3
        self.TIME_WINDOW = 10  # seconds
        
        # Sarcastic punishment GIFs because humor is the best revenge
        self.punishment_gifs = [
            "https://tenor.com/view/banned-anime-gif-19844106",
            "https://tenor.com/view/you-have-been-banned-ban-gif-18150788",
            "https://tenor.com/view/no-nope-wrong-gif-15791964"
        ]

    def is_whitelisted(self, member: discord.Member) -> bool:
        """Check if user is too cool to be punished"""
        if member.id in self.whitelisted_users:
            return True
        return any(role.id in self.whitelisted_roles for role in member.roles)

    def add_violation(self, user_id: int) -> bool:
        """Add a violation and check if user crossed the line"""
        now = datetime.now()
        if user_id not in self.violations:
            self.violations[user_id] = []
        
        # Clean old violations (we're not monsters)
        cutoff = now - timedelta(seconds=self.TIME_WINDOW)
        self.violations[user_id] = [v for v in self.violations[user_id] if v > cutoff]
        
        self.violations[user_id].append(now)
        return len(self.violations[user_id]) >= self.MAX_ACTIONS

    async def punish_user(self, guild: discord.Guild, user_id: int, action: str):
        """Deliver swift justice with extra sass"""
        try:
            member = guild.get_member(user_id)
            if not member:
                logger.warning(f"Can't find member {user_id} to punish. They probably rage quit.")
                return

            # Create that beautiful sarcastic embed
            embed = discord.Embed(
                title="🚫 ANTI-NUKE ACTIVATED 🚫",
                description=f"Congratulations {member.mention}, you've won a free timeout!",
                color=0xFF0000
            )
            embed.add_field(
                name="What you did wrong:",
                value=f"Attempted mass {action} like you own the place",
                inline=False
            )
            embed.add_field(
                name="Punishment:",
                value="Timeout until you learn some manners",
                inline=False
            )
            embed.set_footer(text="Maybe think twice next time? 🤔")
            embed.set_image(url=self.punishment_gifs[0])

            # Actually punish them
            await member.timeout(timedelta(hours=1), reason=f"Anti-nuke: Mass {action}")
            
            # Send the roast to general chat or wherever
            channel = discord.utils.get(guild.channels, name="general")
            if channel:
                await channel.send(embed=embed)
                
        except Exception as e:
            logger.error(f"Failed to punish user {user_id}: {e}")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        """Someone's deleting channels? Not on my watch."""
        async for entry in channel.guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
            if entry.target.id == channel.id:
                member = entry.user
                if self.is_whitelisted(member):
                    return
                
                if self.add_violation(member.id):
                    await self.punish_user(channel.guild, member.id, "channel deletion")

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        """Mass banning? How original."""
        async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=1):
            if entry.target.id == user.id:
                member = entry.user
                if self.is_whitelisted(member):
                    return
                
                if self.add_violation(member.id):
                    await self.punish_user(guild, member.id, "member banning")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        """Deleting roles? That's a paddlin'."""
        async for entry in role.guild.audit_logs(action=discord.AuditLogAction.role_delete, limit=1):
            if entry.target.id == role.id:
                member = entry.user
                if self.is_whitelisted(member):
                    return
                
                if self.add_violation(member.id):
                    await self.punish_user(role.guild, member.id, "role deletion")

    @discord.app_commands.command(name="whitelist_role", description="Add a role to the whitelist")
    @discord.app_commands.describe(role="The role to whitelist")
    async def whitelist_role(self, interaction: discord.Interaction, role: discord.Role):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Nice try, but you need admin perms for this.", ephemeral=True)
            return
        
        if role.id not in self.whitelisted_roles:
            self.whitelisted_roles.append(role.id)
            await interaction.response.send_message(f"✅ {role.name} is now whitelisted. They can wreck stuff in peace.")
        else:
            await interaction.response.send_message(f"🤷 {role.name} is already whitelisted, genius.")

    @discord.app_commands.command(name="whitelist_user", description="Add a user to the whitelist")
    @discord.app_commands.describe(user="The user to whitelist")
    async def whitelist_user(self, interaction: discord.Interaction, user: discord.Member):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Administrator privileges required. Sorry, not sorry.", ephemeral=True)
            return
        
        if user.id not in self.whitelisted_users:
            self.whitelisted_users.append(user.id)
            await interaction.response.send_message(f"✅ {user.mention} is now whitelisted. Try not to abuse it.")
        else:
            await interaction.response.send_message(f"🤷 {user.mention} is already whitelisted. Pay attention.")

    @discord.app_commands.command(name="remove_whitelist_role", description="Remove a role from whitelist")
    @discord.app_commands.describe(role="The role to remove from whitelist")
    async def remove_whitelist_role(self, interaction: discord.Interaction, role: discord.Role):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Admin only, buddy. Nice try though.", ephemeral=True)
            return
        
        if role.id in self.whitelisted_roles:
            self.whitelisted_roles.remove(role.id)
            await interaction.response.send_message(f"❌ {role.name} removed from whitelist. They're on thin ice now.")
        else:
            await interaction.response.send_message(f"🤷 {role.name} wasn't whitelisted anyway. Reading comprehension much?")

    @discord.app_commands.command(name="remove_whitelist_user", description="Remove a user from whitelist")
    @discord.app_commands.describe(user="The user to remove from whitelist")
    async def remove_whitelist_user(self, interaction: discord.Interaction, user: discord.Member):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Administrator privileges required. Shocking, I know.", ephemeral=True)
            return
        
        if user.id in self.whitelisted_users:
            self.whitelisted_users.remove(user.id)
            await interaction.response.send_message(f"❌ {user.mention} removed from whitelist. Hope they behave.")
        else:
            await interaction.response.send_message(f"🤷 {user.mention} wasn't whitelisted. Check your facts.")

    @discord.app_commands.command(name="set_threshold", description="Change detection thresholds")
    @discord.app_commands.describe(
        max_actions="Maximum actions before punishment (1-10)",
        time_window="Time window in seconds (5-60)"
    )
    async def set_threshold(self, interaction: discord.Interaction, max_actions: int, time_window: int):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Admin perms required. Did you really think that would work?", ephemeral=True)
            return
        
        if not (1 <= max_actions <= 10):
            await interaction.response.send_message("Max actions must be between 1-10. Use your brain.", ephemeral=True)
            return
        
        if not (5 <= time_window <= 60):
            await interaction.response.send_message("Time window must be between 5-60 seconds. Be reasonable.", ephemeral=True)
            return
        
        self.MAX_ACTIONS = max_actions
        self.TIME_WINDOW = time_window
        
        await interaction.response.send_message(
            f"✅ Thresholds updated: {max_actions} actions in {time_window} seconds. "
            f"{'Strict mode engaged!' if max_actions <= 2 else 'Reasonable settings.'}"
        )

    @discord.app_commands.command(name="antinuke_config", description="Show current anti-nuke settings")
    async def antinuke_config(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛡️ Anti-Nuke Configuration",
            description="Current settings for keeping idiots in line",
            color=0x00FF00
        )
        embed.add_field(name="Max Actions", value=f"{self.MAX_ACTIONS} actions", inline=True)
        embed.add_field(name="Time Window", value=f"{self.TIME_WINDOW} seconds", inline=True)
        embed.add_field(name="Whitelisted Roles", value=f"{len(self.whitelisted_roles)} roles", inline=True)
        embed.add_field(name="Whitelisted Users", value=f"{len(self.whitelisted_users)} users", inline=True)
        
        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(name="check_violations", description="Check violation history for a user")
    @discord.app_commands.describe(user="User to check violations for")
    async def check_violations(self, interaction: discord.Interaction, user: discord.Member):
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("You need moderation perms for this. Sorry not sorry.", ephemeral=True)
            return
        
        if user.id not in self.violations:
            await interaction.response.send_message(f"✅ {user.mention} has no recent violations. They're clean... for now.")
            return
        
        # Clean old violations first
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.TIME_WINDOW)
        recent_violations = [v for v in self.violations[user.id] if v > cutoff]
        
        if not recent_violations:
            await interaction.response.send_message(f"✅ {user.mention} has no recent violations. Reformed character, perhaps?")
            return
        
        embed = discord.Embed(
            title="🚨 Violation History",
            description=f"Recent violations for {user.mention}",
            color=0xFF9900
        )
        embed.add_field(
            name="Recent Violations",
            value=f"{len(recent_violations)} violations in the last {self.TIME_WINDOW} seconds",
            inline=False
        )
        embed.add_field(
            name="Status",
            value=f"{'⚠️ At risk of punishment' if len(recent_violations) >= self.MAX_ACTIONS - 1 else '✅ Within limits'}",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(name="clear_violations", description="Clear violation history for a user")
    @discord.app_commands.describe(user="User to clear violations for")
    async def clear_violations(self, interaction: discord.Interaction, user: discord.Member):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Admin only. What part of that is confusing?", ephemeral=True)
            return
        
        if user.id in self.violations:
            del self.violations[user.id]
            await interaction.response.send_message(f"✅ Cleared violation history for {user.mention}. Fresh start!")
        else:
            await interaction.response.send_message(f"🤷 {user.mention} has no violations to clear. They're already clean.")

# This is the setup function your cog loader is crying about
async def setup(bot):
    """Load the cog like a functioning human being"""
    await bot.add_cog(AntiNukeCog(bot))
    print("🛡️ Anti-Nuke cog loaded successfully. Server raiders beware!")
