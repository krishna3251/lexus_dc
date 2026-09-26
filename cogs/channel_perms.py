import discord
from discord.ext import commands
from discord import ui, ButtonStyle
import logging

logger = logging.getLogger(__name__)

# Canonical channel permission definitions: (key, label, emoji, style)
COMMON_PANEL_PERMS = [
    ("view_channel", "View Channel", "🔍", ButtonStyle.primary),
    ("send_messages", "Send Messages", "💬", ButtonStyle.primary),
    ("attach_files", "Attach Files", "📁", ButtonStyle.primary),
    ("embed_links", "Embed Links", "🔗", ButtonStyle.primary),
    ("add_reactions", "Add Reactions", "👍", ButtonStyle.secondary),
    ("use_external_emojis", "External Emojis", "😀", ButtonStyle.secondary),
    ("mention_everyone", "Mention Everyone", "📢", ButtonStyle.secondary),
    ("manage_messages", "Manage Messages", "📝", ButtonStyle.secondary),
]

# Canonical lookup mapping for setperm command
PERMISSION_MAP = {
    "view_channel": "view_channel",
    "view channel": "view_channel",
    "send_messages": "send_messages",
    "send messages": "send_messages",
    "read_messages": "read_messages",
    "read messages": "read_messages",
    "manage_messages": "manage_messages",
    "manage messages": "manage_messages",
    "connect": "connect",
    "speak": "speak",
    "mute_members": "mute_members",
    "mute members": "mute_members",
    "deafen_members": "deafen_members",
    "deafen members": "deafen_members",
    "move_members": "move_members",
    "move members": "move_members",
    "manage_roles": "manage_roles",
    "manage roles": "manage_roles",
    "manage_channels": "manage_channels",
    "manage channels": "manage_channels",
    "create_instant_invite": "create_instant_invite",
    "create instant invite": "create_instant_invite",
    "attach_files": "attach_files",
    "attach files": "attach_files",
    "embed_links": "embed_links",
    "embed links": "embed_links",
    "add_reactions": "add_reactions",
    "add reactions": "add_reactions",
    "mention_everyone": "mention_everyone",
    "mention everyone": "mention_everyone",
    "use_external_emojis": "use_external_emojis",
    "use external emojis": "use_external_emojis",
    "use_application_commands": "use_application_commands",
    "use application commands": "use_application_commands",
    "priority_speaker": "priority_speaker",
    "priority speaker": "priority_speaker",
    "stream": "stream",
    "manage_webhooks": "manage_webhooks",
    "manage webhooks": "manage_webhooks",
    "manage_events": "manage_events",
    "manage events": "manage_events",
    "view_audit_log": "view_audit_log",
    "view audit log": "view_audit_log",
    "view_guild_insights": "view_guild_insights",
    "view guild insights": "view_guild_insights",
    "send_tts_messages": "send_tts_messages",
    "send tts messages": "send_tts_messages",
    "moderate_members": "moderate_members",
    "moderate members": "moderate_members",
}


class PermissionButton(ui.Button):
    def __init__(self, style: ButtonStyle, custom_id: str, label: str, emoji: str = None):
        super().__init__(style=style, label=label, emoji=emoji, custom_id=custom_id)
        self.perm_key = custom_id

    async def callback(self, interaction: discord.Interaction):
        view: PermissionView = self.view

        try:
            role_perms = view.channel.permissions_for(view.role)
            current_value = getattr(role_perms, self.perm_key, False)
            new_value = not current_value

            await view.channel.set_permissions(view.role, **{self.perm_key: new_value})

            state_text = "ENABLED" if new_value else "DISABLED"
            color = discord.Color.green() if new_value else discord.Color.red()

            embed = discord.Embed(
                title="🔐 Permission Updated",
                color=color,
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Role", value=view.role.mention, inline=True)
            embed.add_field(name="Permission", value=f"`{self.label}` (`{self.perm_key}`)", inline=True)
            embed.add_field(name="State", value=f"**{state_text}**", inline=True)
            embed.add_field(name="Channel", value=view.channel.mention, inline=True)
            embed.add_field(name="Modified By", value=interaction.user.mention, inline=True)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except discord.Forbidden:
            await interaction.response.send_message(
                "⚠️ **Access Denied**: Insufficient permissions to modify role permissions in this channel.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error toggling permission {self.perm_key}: {e}", exc_info=True)
            await interaction.response.send_message(
                "⚠️ An error occurred while updating permissions.",
                ephemeral=True
            )


class PermissionView(ui.View):
    def __init__(self, author_id: int, role: discord.Role, channel: discord.TextChannel, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.role = role
        self.channel = channel
        self.message = None

        for perm_key, label, emoji, style in COMMON_PANEL_PERMS:
            self.add_item(PermissionButton(style, perm_key, label, emoji))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ You aren't authorized to use these controls.",
                ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.HTTPException):
                pass


class ChannelPermsCog(commands.Cog, name="ChannelPerms"):
    """Channel Permissions Manager - Modify role permissions easily."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="setperm", help="Change channel permissions for a role.")
    @commands.has_permissions(manage_channels=True)
    async def setperm(self, ctx: commands.Context, role_input: str, permission: str, state: str):
        """Modify a specific permission for a role in the current channel."""
        role = None
        if role_input.startswith("<@&") and role_input.endswith(">"):
            try:
                role_id = int(role_input[3:-1])
                role = ctx.guild.get_role(role_id)
            except ValueError:
                role = None
        else:
            role = discord.utils.get(ctx.guild.roles, name=role_input)

        if not role:
            await ctx.send(f"❌ Role `{role_input}` not found. Make sure it's spelled correctly or mentioned.")
            return

        state_lower = state.lower()
        if state_lower in ("on", "true", "enable", "enabled", "1"):
            state_value = True
        elif state_lower in ("off", "false", "disable", "disabled", "0"):
            state_value = False
        else:
            await ctx.send("❌ Invalid state! Use `on` or `off`.")
            return

        perm_key = PERMISSION_MAP.get(permission.lower())
        if not perm_key:
            await ctx.send("❌ Invalid permission name! Example: `send_messages`, `view_channel`, `embed_links`.")
            return

        try:
            await ctx.channel.set_permissions(role, **{perm_key: state_value})
            color = discord.Color.green() if state_value else discord.Color.red()
            state_label = "ENABLED" if state_value else "DISABLED"

            embed = discord.Embed(
                title="🔐 Permission Updated",
                color=color,
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Role", value=role.mention, inline=True)
            embed.add_field(name="Permission", value=f"`{perm_key}`", inline=True)
            embed.add_field(name="State", value=f"**{state_label}**", inline=True)
            embed.add_field(name="Channel", value=ctx.channel.mention, inline=True)
            embed.set_footer(text=f"Updated by {ctx.author}")

            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ I do not have permission to manage permissions in this channel.")
        except Exception as e:
            logger.error(f"Error setting permission: {e}", exc_info=True)
            await ctx.send("❌ An error occurred while setting the permission.")

    @commands.command(name="permpanel", help="Open the interactive permissions panel for a role.")
    @commands.has_permissions(manage_channels=True)
    async def perm_panel(self, ctx: commands.Context, role: discord.Role):
        """Opens an interactive permission control panel for the specified role."""
        embed = discord.Embed(
            title="🔐 Channel Permission Console",
            description=(
                f"Interactive permission control for **{role.name}** in {ctx.channel.mention}.\n\n"
                "Click a button below to toggle the permission for this role in real time."
            ),
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text="Permissions update immediately upon clicking")

        view = PermissionView(ctx.author.id, role, ctx.channel)
        message = await ctx.send(embed=embed, view=view)
        view.message = message


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelPermsCog(bot))
    logger.info("✅ ChannelPerms cog loaded")
