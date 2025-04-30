import discord
from discord.ext import commands
from discord import ui, ButtonStyle
import asyncio

class PermissionView(ui.View):
    def __init__(self, author_id, role, channel, timeout=180):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.role = role
        self.channel = channel
        
        # Full list of Discord channel permissions with cyberpunk descriptions
        self.perm_mapping = {
            "view_channel": "See holographic displays",
            "send_messages": "Transmit data packets",
            "read_messages": "Access neural datastream",
            "manage_messages": "Override message protocols",
            "connect": "Establish neural connection",
            "speak": "Broadcast vocal transmissions",
            "mute_members": "Silence target interfaces",
            "deafen_members": "Block audio receptors",
            "move_members": "Force neural relocation",
            "manage_roles": "Reconfigure user permissions",
            "manage_channels": "Restructure digital spaces",
            "create_instant_invite": "Generate access codes",
            "attach_files": "Upload binary data",
            "embed_links": "Insert hypermedia links",
            "add_reactions": "Apply emotional indicators",
            "mention_everyone": "Broadcast mass notification",
            "use_external_emojis": "Import foreign glyphs",
            "use_application_commands": "Execute system commands",
            "priority_speaker": "Utilize priority transmission",
            "stream": "Broadcast visual data stream",
            "manage_webhooks": "Control automated interfaces",
            "manage_events": "Program temporal gatherings",
            "view_audit_log": "Access system logs",
            "view_guild_insights": "View collective analytics",
            "send_tts_messages": "Transmit synthetic voice",
            "moderate_members": "Regulate civilian activities"
        }
        
        # Create button rows dynamically based on permission categories
        self.add_common_buttons()
        
    def add_common_buttons(self):
        # Row 1: Common permissions
        self.add_item(PermissionButton(ButtonStyle.primary, "view_channel", self.perm_mapping["view_channel"], "🔍"))
        self.add_item(PermissionButton(ButtonStyle.primary, "send_messages", self.perm_mapping["send_messages"], "📡"))
        self.add_item(PermissionButton(ButtonStyle.primary, "read_messages", self.perm_mapping["read_messages"], "📥"))
        self.add_item(PermissionButton(ButtonStyle.primary, "attach_files", self.perm_mapping["attach_files"], "📁"))
        self.add_item(PermissionButton(ButtonStyle.primary, "embed_links", self.perm_mapping["embed_links"], "🔗"))
        
        # Row 2: More permissions
        self.add_item(PermissionButton(ButtonStyle.secondary, "add_reactions", self.perm_mapping["add_reactions"], "🔄"))
        self.add_item(PermissionButton(ButtonStyle.secondary, "use_external_emojis", self.perm_mapping["use_external_emojis"], "😎"))
        self.add_item(PermissionButton(ButtonStyle.secondary, "mention_everyone", self.perm_mapping["mention_everyone"], "📢"))
        self.add_item(PermissionButton(ButtonStyle.secondary, "manage_messages", self.perm_mapping["manage_messages"], "📝"))
        self.add_item(PermissionButton(ButtonStyle.danger, "more_options", "Show More Controls", "🔧"))
    
    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You aren't authorized to use these controls.", ephemeral=True)
            return False
        return True
    
    async def on_timeout(self):
        # Clear the view when timeout occurs
        for child in self.children:
            child.disabled = True
        
        try:
            await self.message.edit(view=self)
        except:
            pass

class PermissionButton(ui.Button):
    def __init__(self, style, custom_id, label, emoji=None):
        super().__init__(style=style, label=label, emoji=emoji, custom_id=custom_id)
        self.perm_key = custom_id
    
    async def callback(self, interaction):
        view = self.view
        if self.perm_key == "more_options":
            # Show advanced permissions menu
            await interaction.response.send_message("Advanced permissions not yet implemented", ephemeral=True)
            return
            
        # Toggle permission
        try:
            # Check current permission value
            role_perms = view.channel.permissions_for(view.role)
            current_value = getattr(role_perms, self.perm_key, False)
            
            # Toggle to opposite
            new_value = not current_value
            
            # Update permission
            await view.channel.set_permissions(view.role, **{self.perm_key: new_value})
            
            # Respond with cyberpunk-themed message
            state = "ENABLED" if new_value else "DISABLED"
            color = 0x00ff9f if new_value else 0xff0055
            
            embed = discord.Embed(
                title=f"🔐 PERMISSION UPDATE",
                description=f"```ansi\n[2;34m[STATUS][0m: Permission override successful\n[2;36m[TARGET][0m: {view.role.name}\n[2;35m[ACTION][0m: {self.perm_key} → {state}\n```",
                color=color
            )
            embed.add_field(name="Channel", value=f"#{view.channel.name}", inline=True)
            embed.add_field(name="Modified By", value=interaction.user.mention, inline=True)
            embed.set_footer(text="NEO-PERMISSIONS SYSTEM v2.0")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except discord.Forbidden:
            await interaction.response.send_message("⚠️ **ACCESS DENIED**: Insufficient permissions to modify role settings.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"⚠️ **SYSTEM ERROR**: {str(e)}", ephemeral=True)

class ChannelPermsCog(commands.Cog):
    """🔒 Channel Permissions Manager - Modify role permissions easily."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="setperm", help="🔧 Change channel permissions for a role.")
    @commands.has_permissions(manage_channels=True)
    async def setperm(self, ctx, role_input: str, permission: str, state: str):
        """Legacy command to modify a specific permission for a role in the current channel."""
        
        # Find the role by mention, ID, or name
        role = None
        
        # If role is mentioned
        if role_input.startswith("<@&") and role_input.endswith(">"):
            role_id = int(role_input[3:-1])  # Extract ID from mention
            role = discord.utils.get(ctx.guild.roles, id=role_id)
        else:
            # Try finding by name
            role = discord.utils.get(ctx.guild.roles, name=role_input)
        
        if not role:
            await ctx.send(f"❌ Role `{role_input}` not found! Make sure it's spelled correctly or mentioned.")
            return

        # Convert input to proper boolean values
        state = state.lower()
        if state == "on":
            state_value = True
        elif state == "off":
            state_value = False
        else:
            await ctx.send("❌ Invalid state! Use `on` or `off`.")
            return

        # Full list of Discord channel permissions
        perm_mapping = {
            "view channel": "view_channel",
            "send messages": "send_messages",
            "read messages": "read_messages",
            "manage messages": "manage_messages",
            "connect": "connect",
            "speak": "speak",
            "mute members": "mute_members",
            "deafen members": "deafen_members",
            "move members": "move_members",
            "manage roles": "manage_roles",
            "manage channels": "manage_channels",
            "create instant invite": "create_instant_invite",
            "attach files": "attach_files",
            "embed links": "embed_links",
            "add reactions": "add_reactions",
            "mention everyone": "mention_everyone",
            "use external emojis": "use_external_emojis",
            "use application commands": "use_application_commands",
            "priority speaker": "priority_speaker",
            "stream": "stream",
            "manage webhooks": "manage_webhooks",
            "manage events": "manage_events",
            "view audit log": "view_audit_log",
            "view guild insights": "view_guild_insights",
            "send tts messages": "send_tts_messages",
            "moderate members": "moderate_members"
        }

        # Check if the provided permission is valid
        perm_key = perm_mapping.get(permission.lower())
        if not perm_key:
            await ctx.send("❌ Invalid permission! Use a valid Discord permission name.")
            return

        # Update permissions for the role in the current channel
        await ctx.channel.set_permissions(role, **{perm_key: state_value})
        
        # Cyberpunk-themed response
        embed = discord.Embed(
            title="🔐 Permission System v2.0",
            description=f"```ansi\n[2;34m[UPDATED][0m: Permission override successful\n```",
            color=0x00ff9f if state_value else 0xff0055
        )
        embed.add_field(name="Role", value=role.mention, inline=True)
        embed.add_field(name="Permission", value=f"`{permission}`", inline=True)
        embed.add_field(name="State", value=f"{'ENABLED' if state_value else 'DISABLED'}", inline=True)
        embed.add_field(name="Channel", value=f"#{ctx.channel.name}", inline=True)
        embed.set_footer(text="NEO-PERMISSIONS SYSTEM v2.0")
        
        await ctx.send(embed=embed)

    @commands.command(name="permpanel", help="🖥️ Open the interactive permissions panel")
    @commands.has_permissions(manage_channels=True)
    async def perm_panel(self, ctx, role: discord.Role):
        """Opens an interactive permission control panel for the specified role."""
        
        embed = discord.Embed(
            title="🔐 NETRUNNER PERMISSION CONSOLE",
            description=f"Interactive permission control for role: **{role.name}**\nChannel: **#{ctx.channel.name}**\n\nSelect permissions to toggle below:",
            color=0x00ffaa
        )
        embed.set_footer(text="NEO-PERMISSIONS SYSTEM v2.0 • Permissions will update in real-time")
        
        view = PermissionView(ctx.author.id, role, ctx.channel)
        message = await ctx.send(embed=embed, view=view)
        view.message = message

async def setup(bot):
    await bot.add_cog(ChannelPermsCog(bot))
