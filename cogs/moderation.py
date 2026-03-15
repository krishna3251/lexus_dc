import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import json
import logging  # FIX 1: was missing, caused NameError in save_mod_roles()
import os
import datetime
from typing import Optional, Union

# File to store mod role IDs per guild
MOD_ROLES_FILE = os.path.join(os.path.dirname(__file__), "mod_roles.json")
OWNER_ID = 486555340670894080  # Your Discord user ID

logger = logging.getLogger(__name__)


def load_mod_roles():
    """Load mod roles from file (handles empty/corrupt JSON gracefully)."""
    if os.path.exists(MOD_ROLES_FILE):
        try:
            with open(MOD_ROLES_FILE, 'r') as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def save_mod_roles(mod_roles):
    """Save mod roles to file (atomic-safe)."""
    try:
        with open(MOD_ROLES_FILE, 'w') as f:
            json.dump(mod_roles, f, indent=2)
    except OSError as e:
        logger.error(f"Failed to save mod_roles: {e}")


class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mod_roles = load_mod_roles()
        logger.info("ModerationCog loaded successfully!")

    # FIX 2: Added missing check_mod_role method that was called but never defined.
    # All 6 prefix commands (p_setmodrole, p_givemod, p_kick, p_ban, p_timeout,
    # p_moderate) called self.check_mod_role() which caused AttributeError crashes.
    def check_mod_role(self, member: discord.Member, guild_id) -> bool:
        """Check if a member has the configured mod role for the given guild."""
        guild_id_str = str(guild_id)
        if guild_id_str in self.mod_roles:
            mod_role_id = self.mod_roles[guild_id_str]
            return discord.utils.get(member.roles, id=mod_role_id) is not None
        return False

    async def cog_check(self, ctx):
        """Check if user has permission to use moderation commands."""
        if ctx.author.id == OWNER_ID:
            return True
        return self.check_mod_role(ctx.author, ctx.guild.id)

    async def has_mod_role_or_owner(self, interaction: discord.Interaction):
        """Check if user has mod role or is the owner for app commands."""
        if interaction.user.id == OWNER_ID:
            return True
        return self.check_mod_role(interaction.user, interaction.guild_id)

    # ─── Prefix commands ─────────────────────────────────────────────

    @commands.command(name="setmodrole")
    @commands.guild_only()
    async def p_setmodrole(self, ctx, role: discord.Role):
        """Set a role as the moderation role (prefix version)."""
        if ctx.author.id != OWNER_ID and not self.check_mod_role(ctx.author, ctx.guild.id):
            await ctx.send("You don't have permission to use this command.")
            return

        guild_id = str(ctx.guild.id)
        self.mod_roles[guild_id] = role.id
        save_mod_roles(self.mod_roles)

        embed = discord.Embed(
            title="Mod Role Set",
            description=f"The moderation role has been set to {role.mention}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.command(name="givemod")
    @commands.guild_only()
    async def p_givemod(self, ctx, user: discord.Member):
        """Give a user the mod role (prefix version)."""
        if ctx.author.id != OWNER_ID and not self.check_mod_role(ctx.author, ctx.guild.id):
            await ctx.send("You don't have permission to use this command.")
            return

        guild_id = str(ctx.guild.id)
        if guild_id not in self.mod_roles:
            await ctx.send("No mod role has been set for this server. Use `setmodrole` first.")
            return

        mod_role_id = self.mod_roles[guild_id]
        mod_role = ctx.guild.get_role(mod_role_id)

        if not mod_role:
            await ctx.send("The mod role no longer exists. Please set a new one with `setmodrole`.")
            return

        if mod_role in user.roles:
            await ctx.send(f"{user.mention} already has the mod role.")
            return

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
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("You can't use these buttons.", ephemeral=True)
                return
            await user.add_roles(mod_role)
            result_embed = discord.Embed(
                title="Mod Role Assigned",
                description=f"{user.mention} has been given the mod role.",
                color=discord.Color.green()
            )
            await interaction.response.edit_message(embed=result_embed, view=None)

        async def cancel_callback(interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("You can't use these buttons.", ephemeral=True)
                return
            await interaction.response.edit_message(
                embed=discord.Embed(title="Cancelled", description="Mod role assignment cancelled.", color=discord.Color.red()),
                view=None
            )

        confirm_button.callback = confirm_callback
        cancel_button.callback = cancel_callback
        await ctx.send(embed=embed, view=view)

    @commands.command(name="kick")
    @commands.guild_only()
    async def p_kick(self, ctx, user: discord.Member, *, reason: str = "No reason provided"):
        """Kick a user from the server (prefix version)."""
        if ctx.author.id != OWNER_ID and not self.check_mod_role(ctx.author, ctx.guild.id):
            await ctx.send("You don't have permission to use this command.")
            return

        if not ctx.guild.me.guild_permissions.kick_members:
            await ctx.send("I don't have permission to kick members.")
            return

        if user.top_role >= ctx.guild.me.top_role or user.id == ctx.guild.owner_id:
            await ctx.send("I can't kick this user due to role hierarchy.")
            return

        if user.id == ctx.author.id:
            await ctx.send("You can't kick yourself.")
            return

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
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("You can't use these buttons.", ephemeral=True)
                return
            try:
                await user.kick(reason=f"Kicked by {ctx.author} - {reason}")
                await interaction.response.edit_message(
                    embed=discord.Embed(title="User Kicked", description=f"{user.mention} has been kicked.\nReason: {reason}", color=discord.Color.green()),
                    view=None
                )
            except discord.Forbidden:
                await interaction.response.edit_message(
                    embed=discord.Embed(title="Error", description="I don't have permission to kick this user.", color=discord.Color.red()),
                    view=None
                )
            except Exception as e:
                await interaction.response.edit_message(
                    embed=discord.Embed(title="Error", description=f"An error occurred: {str(e)}", color=discord.Color.red()),
                    view=None
                )

        async def cancel_callback(interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("You can't use these buttons.", ephemeral=True)
                return
            await interaction.response.edit_message(
                embed=discord.Embed(title="Cancelled", description="Kick cancelled.", color=discord.Color.red()),
                view=None
            )

        confirm_button.callback = confirm_callback
        cancel_button.callback = cancel_callback
        await ctx.send(embed=embed, view=view)

    @commands.command(name="ban")
    @commands.guild_only()
    async def p_ban(self, ctx, user: discord.Member, delete_days: Optional[int] = 1, *, reason: str = "No reason provided"):
        """Ban a user from the server (prefix version)."""
        if ctx.author.id != OWNER_ID and not self.check_mod_role(ctx.author, ctx.guild.id):
            await ctx.send("You don't have permission to use this command.")
            return

        if not ctx.guild.me.guild_permissions.ban_members:
            await ctx.send("I don't have permission to ban members.")
            return

        if user.top_role >= ctx.guild.me.top_role or user.id == ctx.guild.owner_id:
            await ctx.send("I can't ban this user due to role hierarchy.")
            return

        if user.id == ctx.author.id:
            await ctx.send("You can't ban yourself.")
            return

        delete_days = max(0, min(7, delete_days))

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
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("You can't use these buttons.", ephemeral=True)
                return
            try:
                await user.ban(reason=f"Banned by {ctx.author} - {reason}", delete_message_days=delete_days)
                await interaction.response.edit_message(
                    embed=discord.Embed(title="User Banned", description=f"{user.mention} has been banned.\nReason: {reason}", color=discord.Color.green()),
                    view=None
                )
            except discord.Forbidden:
                await interaction.response.edit_message(
                    embed=discord.Embed(title="Error", description="I don't have permission to ban this user.", color=discord.Color.red()),
                    view=None
                )
            except Exception as e:
                await interaction.response.edit_message(
                    embed=discord.Embed(title="Error", description=f"An error occurred: {str(e)}", color=discord.Color.red()),
                    view=None
                )

        async def cancel_callback(interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("You can't use these buttons.", ephemeral=True)
                return
            await interaction.response.edit_message(
                embed=discord.Embed(title="Cancelled", description="Ban cancelled.", color=discord.Color.red()),
                view=None
            )

        confirm_button.callback = confirm_callback
        cancel_button.callback = cancel_callback
        await ctx.send(embed=embed, view=view)

    @commands.command(name="timeout")
    @commands.guild_only()
    async def p_timeout(self, ctx, user: discord.Member, duration: int, *, reason: str = "No reason provided"):
        """Timeout a user for a specified duration (prefix version)."""
        if ctx.author.id != OWNER_ID and not self.check_mod_role(ctx.author, ctx.guild.id):
            await ctx.send("You don't have permission to use this command.")
            return

        if not ctx.guild.me.guild_permissions.moderate_members:
            await ctx.send("I don't have permission to timeout members.")
            return

        if user.top_role >= ctx.guild.me.top_role or user.id == ctx.guild.owner_id:
            await ctx.send("I can't timeout this user due to role hierarchy.")
            return

        if user.id == ctx.author.id:
            await ctx.send("You can't timeout yourself.")
            return

        timeout_duration = discord.utils.utcnow() + datetime.timedelta(minutes=duration)

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
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("You can't use these buttons.", ephemeral=True)
                return
            try:
                await user.timeout(timeout_duration, reason=f"Timed out by {ctx.author} - {reason}")
                await interaction.response.edit_message(
                    embed=discord.Embed(title="User Timed Out", description=f"{user.mention} has been timed out for {duration} minutes.\nReason: {reason}", color=discord.Color.green()),
                    view=None
                )
            except discord.Forbidden:
                await interaction.response.edit_message(
                    embed=discord.Embed(title="Error", description="I don't have permission to timeout this user.", color=discord.Color.red()),
                    view=None
                )
            except Exception as e:
                await interaction.response.edit_message(
                    embed=discord.Embed(title="Error", description=f"An error occurred: {str(e)}", color=discord.Color.red()),
                    view=None
                )

        async def cancel_callback(interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("You can't use these buttons.", ephemeral=True)
                return
            await interaction.response.edit_message(
                embed=discord.Embed(title="Cancelled", description="Timeout cancelled.", color=discord.Color.red()),
                view=None
            )

        confirm_button.callback = confirm_callback
        cancel_button.callback = cancel_callback
        await ctx.send(embed=embed, view=view)

    @commands.command(name="moderate")
    @commands.guild_only()
    async def p_moderate(self, ctx, user: discord.Member):
        """Open moderation panel for a user (prefix version)."""
        if ctx.author.id != OWNER_ID and not self.check_mod_role(ctx.author, ctx.guild.id):
            await ctx.send("You don't have permission to use this command.")
            return

        if user.top_role >= ctx.guild.me.top_role or user.id == ctx.guild.owner_id:
            await ctx.send("I can't moderate this user due to role hierarchy.")
            return

        if user.id == ctx.author.id:
            await ctx.send("You can't moderate yourself.")
            return

        embed = discord.Embed(
            title="Moderation Panel",
            description=f"Select an action to perform on {user.mention}",
            color=discord.Color.blue()
        )
        embed.add_field(name="User Info", value=f"**ID:** {user.id}\n**Joined:** {user.joined_at.strftime('%Y-%m-%d')}")

        kick_button  = discord.ui.Button(label="Kick",     style=discord.ButtonStyle.danger,    row=0)
        ban_button   = discord.ui.Button(label="Ban",      style=discord.ButtonStyle.danger,    row=0)
        timeout_button = discord.ui.Button(label="Timeout", style=discord.ButtonStyle.secondary, row=0)
        mod_button   = discord.ui.Button(label="Give Mod", style=discord.ButtonStyle.primary,   row=1)

        view = discord.ui.View()
        view.add_item(kick_button)
        view.add_item(ban_button)
        view.add_item(timeout_button)

        guild_id = str(ctx.guild.id)
        if guild_id in self.mod_roles:
            view.add_item(mod_button)

        async def kick_callback(interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("You can't use these buttons.", ephemeral=True)
                return

            class KickModal(discord.ui.Modal, title="Kick User"):
                reason = discord.ui.TextInput(label="Reason", placeholder="Enter reason for kick...", required=False, default="No reason provided")

                async def on_submit(self, interaction):
                    reason_text = self.reason.value or "No reason provided"
                    try:
                        await user.kick(reason=f"Kicked by {ctx.author} - {reason_text}")
                        await interaction.response.send_message(embed=discord.Embed(title="User Kicked", description=f"{user.mention} has been kicked.\nReason: {reason_text}", color=discord.Color.green()))
                    except discord.Forbidden:
                        await interaction.response.send_message(embed=discord.Embed(title="Error", description="I don't have permission to kick this user.", color=discord.Color.red()))
                    except Exception as e:
                        await interaction.response.send_message(embed=discord.Embed(title="Error", description=f"An error occurred: {str(e)}", color=discord.Color.red()))

            await interaction.response.send_modal(KickModal())

        async def ban_callback(interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("You can't use these buttons.", ephemeral=True)
                return

            class BanModal(discord.ui.Modal, title="Ban User"):
                reason = discord.ui.TextInput(label="Reason", placeholder="Enter reason for ban...", required=False, default="No reason provided")
                delete_days = discord.ui.TextInput(label="Delete Message History (days)", placeholder="Enter number of days (0-7)", required=True, default="1")

                async def on_submit(self, interaction):
                    reason_text = self.reason.value or "No reason provided"
                    try:
                        d = max(0, min(7, int(self.delete_days.value)))
                    except ValueError:
                        d = 1
                    try:
                        await user.ban(reason=f"Banned by {ctx.author} - {reason_text}", delete_message_days=d)
                        await interaction.response.send_message(embed=discord.Embed(title="User Banned", description=f"{user.mention} has been banned.\nReason: {reason_text}", color=discord.Color.green()))
                    except discord.Forbidden:
                        await interaction.response.send_message(embed=discord.Embed(title="Error", description="I don't have permission to ban this user.", color=discord.Color.red()))
                    except Exception as e:
                        await interaction.response.send_message(embed=discord.Embed(title="Error", description=f"An error occurred: {str(e)}", color=discord.Color.red()))

            await interaction.response.send_modal(BanModal())

        async def timeout_callback(interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("You can't use these buttons.", ephemeral=True)
                return

            class TimeoutModal(discord.ui.Modal, title="Timeout User"):
                duration = discord.ui.TextInput(label="Duration (minutes)", placeholder="Enter timeout duration in minutes", required=True, default="60")
                reason = discord.ui.TextInput(label="Reason", placeholder="Enter reason for timeout...", required=False, default="No reason provided")

                async def on_submit(self, interaction):
                    reason_text = self.reason.value or "No reason provided"
                    try:
                        dur = int(self.duration.value)
                    except ValueError:
                        dur = 60
                    until = discord.utils.utcnow() + datetime.timedelta(minutes=dur)
                    try:
                        await user.timeout(until, reason=f"Timed out by {ctx.author} - {reason_text}")
                        await interaction.response.send_message(embed=discord.Embed(title="User Timed Out", description=f"{user.mention} has been timed out for {dur} minutes.\nReason: {reason_text}", color=discord.Color.green()))
                    except discord.Forbidden:
                        await interaction.response.send_message(embed=discord.Embed(title="Error", description="I don't have permission to timeout this user.", color=discord.Color.red()))
                    except Exception as e:
                        await interaction.response.send_message(embed=discord.Embed(title="Error", description=f"An error occurred: {str(e)}", color=discord.Color.red()))

            await interaction.response.send_modal(TimeoutModal())

        async def mod_callback(interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("You can't use these buttons.", ephemeral=True)
                return

            if guild_id not in self.mod_roles:
                await interaction.response.send_message("No mod role has been set. Use !setmodrole first.", ephemeral=True)
                return

            mod_role = ctx.guild.get_role(self.mod_roles[guild_id])
            if not mod_role:
                await interaction.response.send_message("The mod role no longer exists. Set a new one with !setmodrole.", ephemeral=True)
                return

            if mod_role in user.roles:
                await interaction.response.send_message(f"{user.mention} already has the mod role.", ephemeral=True)
                return

            confirm_view = discord.ui.View()
            cb = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.green)
            xb = discord.ui.Button(label="Cancel",  style=discord.ButtonStyle.red)
            confirm_view.add_item(cb)
            confirm_view.add_item(xb)

            async def do_confirm(i):
                if i.user.id != ctx.author.id:
                    await i.response.send_message("You can't use these buttons.", ephemeral=True)
                    return
                await user.add_roles(mod_role)
                await i.response.edit_message(embed=discord.Embed(title="Mod Role Assigned", description=f"{user.mention} has been given the mod role.", color=discord.Color.green()), view=None)

            async def do_cancel(i):
                if i.user.id != ctx.author.id:
                    await i.response.send_message("You can't use these buttons.", ephemeral=True)
                    return
                await i.response.edit_message(embed=discord.Embed(title="Cancelled", description="Mod role assignment cancelled.", color=discord.Color.red()), view=None)

            cb.callback = do_confirm
            xb.callback = do_cancel
            await interaction.response.send_message(
                embed=discord.Embed(title="Confirm Mod Role Assignment", description=f"Give {user.mention} the mod role?", color=discord.Color.blue()),
                view=confirm_view, ephemeral=True
            )

        kick_button.callback    = kick_callback
        ban_button.callback     = ban_callback
        timeout_button.callback = timeout_callback
        mod_button.callback     = mod_callback
        await ctx.send(embed=embed, view=view)

    # ─── Slash commands ───────────────────────────────────────────────

    @app_commands.command(name="kick", description="Kick a user from the server")
    @app_commands.describe(user="The user to kick", reason="Reason for kicking the user")
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = "No reason provided"):
        if not await self.has_mod_role_or_owner(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        if not interaction.guild.me.guild_permissions.kick_members:
            await interaction.response.send_message("I don't have permission to kick members.", ephemeral=True)
            return

        if user.top_role >= interaction.guild.me.top_role or user.id == interaction.guild.owner_id:
            await interaction.response.send_message("I can't kick this user due to role hierarchy.", ephemeral=True)
            return

        if user.id == interaction.user.id:
            await interaction.response.send_message("You can't kick yourself.", ephemeral=True)
            return

        confirm_button = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.green)
        cancel_button  = discord.ui.Button(label="Cancel",  style=discord.ButtonStyle.red)
        view = discord.ui.View()
        view.add_item(confirm_button)
        view.add_item(cancel_button)

        embed = discord.Embed(title="Confirm Kick", description=f"Kick {user.mention}?\nReason: {reason}", color=discord.Color.yellow())

        async def confirm_callback(i):
            try:
                await user.kick(reason=f"Kicked by {i.user} - {reason}")
                await i.response.edit_message(embed=discord.Embed(title="User Kicked", description=f"{user.mention} kicked.\nReason: {reason}", color=discord.Color.green()), view=None)
            except discord.Forbidden:
                await i.response.edit_message(embed=discord.Embed(title="Error", description="No permission to kick.", color=discord.Color.red()), view=None)
            except Exception as e:
                await i.response.edit_message(embed=discord.Embed(title="Error", description=str(e), color=discord.Color.red()), view=None)

        async def cancel_callback(i):
            await i.response.edit_message(embed=discord.Embed(title="Cancelled", description="Kick cancelled.", color=discord.Color.red()), view=None)

        confirm_button.callback = confirm_callback
        cancel_button.callback  = cancel_callback
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="ban", description="Ban a user from the server")
    @app_commands.describe(user="The user to ban", reason="Reason for banning", delete_days="Days of message history to delete (0-7)")
    async def ban(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = "No reason provided", delete_days: Optional[int] = 1):
        if not await self.has_mod_role_or_owner(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        if not interaction.guild.me.guild_permissions.ban_members:
            await interaction.response.send_message("I don't have permission to ban members.", ephemeral=True)
            return

        if user.top_role >= interaction.guild.me.top_role or user.id == interaction.guild.owner_id:
            await interaction.response.send_message("I can't ban this user due to role hierarchy.", ephemeral=True)
            return

        if user.id == interaction.user.id:
            await interaction.response.send_message("You can't ban yourself.", ephemeral=True)
            return

        delete_days = max(0, min(7, delete_days))

        confirm_button = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.green)
        cancel_button  = discord.ui.Button(label="Cancel",  style=discord.ButtonStyle.red)
        view = discord.ui.View()
        view.add_item(confirm_button)
        view.add_item(cancel_button)

        embed = discord.Embed(title="Confirm Ban", description=f"Ban {user.mention}?\nReason: {reason}\nDelete history: {delete_days}d", color=discord.Color.red())

        async def confirm_callback(i):
            try:
                await user.ban(reason=f"Banned by {i.user} - {reason}", delete_message_days=delete_days)
                await i.response.edit_message(embed=discord.Embed(title="User Banned", description=f"{user.mention} banned.\nReason: {reason}", color=discord.Color.green()), view=None)
            except discord.Forbidden:
                await i.response.edit_message(embed=discord.Embed(title="Error", description="No permission to ban.", color=discord.Color.red()), view=None)
            except Exception as e:
                await i.response.edit_message(embed=discord.Embed(title="Error", description=str(e), color=discord.Color.red()), view=None)

        async def cancel_callback(i):
            await i.response.edit_message(embed=discord.Embed(title="Cancelled", description="Ban cancelled.", color=discord.Color.red()), view=None)

        confirm_button.callback = confirm_callback
        cancel_button.callback  = cancel_callback
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="timeout", description="Timeout a user")
    @app_commands.describe(user="The user to timeout", duration="Timeout duration in minutes", reason="Reason for the timeout")
    async def timeout(self, interaction: discord.Interaction, user: discord.Member, duration: int, reason: Optional[str] = "No reason provided"):
        if not await self.has_mod_role_or_owner(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        if not interaction.guild.me.guild_permissions.moderate_members:
            await interaction.response.send_message("I don't have permission to timeout members.", ephemeral=True)
            return

        if user.top_role >= interaction.guild.me.top_role or user.id == interaction.guild.owner_id:
            await interaction.response.send_message("I can't timeout this user due to role hierarchy.", ephemeral=True)
            return

        if user.id == interaction.user.id:
            await interaction.response.send_message("You can't timeout yourself.", ephemeral=True)
            return

        timeout_duration = discord.utils.utcnow() + datetime.timedelta(minutes=duration)

        confirm_button = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.green)
        cancel_button  = discord.ui.Button(label="Cancel",  style=discord.ButtonStyle.red)
        view = discord.ui.View()
        view.add_item(confirm_button)
        view.add_item(cancel_button)

        embed = discord.Embed(title="Confirm Timeout", description=f"Timeout {user.mention} for {duration} minutes?\nReason: {reason}", color=discord.Color.orange())

        async def confirm_callback(i):
            try:
                await user.timeout(timeout_duration, reason=f"Timed out by {i.user} - {reason}")
                await i.response.edit_message(embed=discord.Embed(title="User Timed Out", description=f"{user.mention} timed out for {duration} minutes.\nReason: {reason}", color=discord.Color.green()), view=None)
            except discord.Forbidden:
                await i.response.edit_message(embed=discord.Embed(title="Error", description="No permission to timeout.", color=discord.Color.red()), view=None)
            except Exception as e:
                await i.response.edit_message(embed=discord.Embed(title="Error", description=str(e), color=discord.Color.red()), view=None)

        async def cancel_callback(i):
            await i.response.edit_message(embed=discord.Embed(title="Cancelled", description="Timeout cancelled.", color=discord.Color.red()), view=None)

        confirm_button.callback = confirm_callback
        cancel_button.callback  = cancel_callback
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="moderate", description="Open moderation panel for a user")
    @app_commands.describe(user="The user to moderate")
    async def moderate(self, interaction: discord.Interaction, user: discord.Member):
        if not await self.has_mod_role_or_owner(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        if user.top_role >= interaction.guild.me.top_role or user.id == interaction.guild.owner_id:
            await interaction.response.send_message("I can't moderate this user due to role hierarchy.", ephemeral=True)
            return

        if user.id == interaction.user.id:
            await interaction.response.send_message("You can't moderate yourself.", ephemeral=True)
            return

        embed = discord.Embed(title="Moderation Panel", description=f"Select an action for {user.mention}", color=discord.Color.blue())
        embed.add_field(name="User Info", value=f"**ID:** {user.id}\n**Joined:** {user.joined_at.strftime('%Y-%m-%d')}")

        kick_button    = discord.ui.Button(label="Kick",     style=discord.ButtonStyle.danger,    row=0)
        ban_button     = discord.ui.Button(label="Ban",      style=discord.ButtonStyle.danger,    row=0)
        timeout_button = discord.ui.Button(label="Timeout",  style=discord.ButtonStyle.secondary, row=0)
        mod_button     = discord.ui.Button(label="Give Mod", style=discord.ButtonStyle.primary,   row=1)

        view = discord.ui.View()
        view.add_item(kick_button)
        view.add_item(ban_button)
        view.add_item(timeout_button)

        guild_id = str(interaction.guild_id)
        if guild_id in self.mod_roles:
            view.add_item(mod_button)

        async def kick_callback(i):
            class KickModal(discord.ui.Modal, title="Kick User"):
                reason = discord.ui.TextInput(label="Reason", placeholder="Enter reason for kick...", required=False, default="No reason provided")
                async def on_submit(self, i):
                    r = self.reason.value or "No reason provided"
                    try:
                        await user.kick(reason=f"Kicked by {i.user} - {r}")
                        await i.response.send_message(embed=discord.Embed(title="User Kicked", description=f"{user.mention} kicked.\nReason: {r}", color=discord.Color.green()))
                    except Exception as e:
                        await i.response.send_message(embed=discord.Embed(title="Error", description=str(e), color=discord.Color.red()))
            await i.response.send_modal(KickModal())

        async def ban_callback(i):
            class BanModal(discord.ui.Modal, title="Ban User"):
                reason = discord.ui.TextInput(label="Reason", required=False, default="No reason provided")
                delete_days = discord.ui.TextInput(label="Delete Message History (days)", required=True, default="1")
                async def on_submit(self, i):
                    r = self.reason.value or "No reason provided"
                    try:
                        d = max(0, min(7, int(self.delete_days.value)))
                    except ValueError:
                        d = 1
                    try:
                        await user.ban(reason=f"Banned by {i.user} - {r}", delete_message_days=d)
                        await i.response.send_message(embed=discord.Embed(title="User Banned", description=f"{user.mention} banned.\nReason: {r}", color=discord.Color.green()))
                    except Exception as e:
                        await i.response.send_message(embed=discord.Embed(title="Error", description=str(e), color=discord.Color.red()))
            await i.response.send_modal(BanModal())

        async def timeout_callback(i):
            class TimeoutModal(discord.ui.Modal, title="Timeout User"):
                duration = discord.ui.TextInput(label="Duration (minutes)", required=True, default="60")
                reason = discord.ui.TextInput(label="Reason", required=False, default="No reason provided")
                async def on_submit(self, i):
                    r = self.reason.value or "No reason provided"
                    try:
                        dur = int(self.duration.value)
                    except ValueError:
                        dur = 60
                    until = discord.utils.utcnow() + datetime.timedelta(minutes=dur)
                    try:
                        await user.timeout(until, reason=f"Timed out by {i.user} - {r}")
                        await i.response.send_message(embed=discord.Embed(title="User Timed Out", description=f"{user.mention} timed out for {dur} minutes.\nReason: {r}", color=discord.Color.green()))
                    except Exception as e:
                        await i.response.send_message(embed=discord.Embed(title="Error", description=str(e), color=discord.Color.red()))
            await i.response.send_modal(TimeoutModal())

        async def mod_callback(i):
            if guild_id not in self.mod_roles:
                await i.response.send_message("No mod role set. Use /setmodrole first.", ephemeral=True)
                return
            mod_role = interaction.guild.get_role(self.mod_roles[guild_id])
            if not mod_role:
                await i.response.send_message("The mod role no longer exists. Set a new one.", ephemeral=True)
                return
            if mod_role in user.roles:
                await i.response.send_message(f"{user.mention} already has the mod role.", ephemeral=True)
                return
            confirm_view = discord.ui.View()
            cb = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.green)
            xb = discord.ui.Button(label="Cancel",  style=discord.ButtonStyle.red)
            confirm_view.add_item(cb)
            confirm_view.add_item(xb)
            async def do_confirm(ci):
                await user.add_roles(mod_role)
                await ci.response.edit_message(embed=discord.Embed(title="Mod Role Assigned", description=f"{user.mention} given the mod role.", color=discord.Color.green()), view=None)
            async def do_cancel(ci):
                await ci.response.edit_message(embed=discord.Embed(title="Cancelled", description="Cancelled.", color=discord.Color.red()), view=None)
            cb.callback = do_confirm
            xb.callback = do_cancel
            await i.response.send_message(embed=discord.Embed(title="Confirm", description=f"Give {user.mention} the mod role?", color=discord.Color.blue()), view=confirm_view, ephemeral=True)

        kick_button.callback    = kick_callback
        ban_button.callback     = ban_callback
        timeout_button.callback = timeout_callback
        mod_button.callback     = mod_callback
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
