import discord
from discord.ext import commands

class ChannelPermsCog(commands.Cog):
    """🔒 Channel Permissions Manager - Modify role permissions easily."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="setperm", help="🔧 Change channel permissions for a role.")
    @commands.has_permissions(manage_channels=True)
    async def setperm(self, ctx, role_input: str, permission: str, state: str):
        """Modifies a specific permission for a role in the current channel."""
        
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
        await ctx.send(f"✅ Successfully set `{permission}` to `{state}` for `{role.name}` in `{ctx.channel.name}`.")

async def setup(bot):
    await bot.add_cog(ChannelPermsCog(bot))
