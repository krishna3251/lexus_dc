"""
Autorole Cog — Auto-assign role on join + reaction role panels.
All config stored in MongoDB guild_config.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
import mongo_helper

logger = logging.getLogger(__name__)


class ReactionRoleView(discord.ui.View):
    """Persistent view that never times out — one button per role."""

    def __init__(self, roles: list[dict]):
        super().__init__(timeout=None)
        for r in roles:
            self.add_item(ReactionRoleButton(r["role_id"], r["label"], r.get("emoji")))


class ReactionRoleButton(discord.ui.Button):
    def __init__(self, role_id: int, label: str, emoji: str | None):
        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            custom_id=f"autorole_{role_id}",
        )
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("❌ Role not found.", ephemeral=True)
            return

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role, reason="Reaction role toggle")
            await interaction.response.send_message(f"➖ Removed **{role.name}**", ephemeral=True)
        else:
            await interaction.user.add_roles(role, reason="Reaction role toggle")
            await interaction.response.send_message(f"➕ Added **{role.name}**", ephemeral=True)


class AutoroleCog(commands.Cog, name="Autorole"):
    """Auto-assign roles on join and reaction-role panels."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        """Re-register persistent reaction-role views from DB."""
        col = mongo_helper.get_collection("reaction_roles")
        if col is None:
            return
        async for doc in col.find():
            view = ReactionRoleView(doc.get("roles", []))
            self.bot.add_view(view, message_id=doc.get("message_id"))

    # ── Auto-assign on join ────────────────────────────────────────

    @app_commands.command(name="setautorole", description="Set a role to auto-assign on member join")
    @app_commands.describe(role="Role to assign automatically")
    @app_commands.default_permissions(manage_roles=True)
    async def set_autorole(self, interaction: discord.Interaction, role: discord.Role):
        await mongo_helper.update_guild_config(interaction.guild_id, {"autorole": role.id})
        await interaction.response.send_message(
            f"✅ New members will receive **{role.name}** automatically.", ephemeral=True
        )

    @app_commands.command(name="removeautorole", description="Disable auto-role on join")
    @app_commands.default_permissions(manage_roles=True)
    async def remove_autorole(self, interaction: discord.Interaction):
        await mongo_helper.update_guild_config(interaction.guild_id, {"autorole": None})
        await interaction.response.send_message("✅ Auto-role disabled.", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = await mongo_helper.get_guild_config(member.guild.id)
        role_id = cfg.get("autorole")
        if not role_id:
            return
        role = member.guild.get_role(role_id)
        if role:
            try:
                await member.add_roles(role, reason="Autorole on join")
            except discord.Forbidden:
                logger.warning(f"Cannot assign autorole {role_id} in guild {member.guild.id}")

    # ── Reaction role panel ────────────────────────────────────────

    @app_commands.command(name="reactionrole", description="Create a reaction-role panel")
    @app_commands.describe(
        title="Panel title",
        role1="First role",
        emoji1="Emoji for first role (optional)",
        role2="Second role (optional)",
        emoji2="Emoji for second role (optional)",
        role3="Third role (optional)",
        emoji3="Emoji for third role (optional)",
    )
    @app_commands.default_permissions(manage_roles=True)
    async def reaction_role(
        self,
        interaction: discord.Interaction,
        title: str,
        role1: discord.Role,
        emoji1: str = None,
        role2: discord.Role = None,
        emoji2: str = None,
        role3: discord.Role = None,
        emoji3: str = None,
    ):
        roles_data = [{"role_id": role1.id, "label": role1.name, "emoji": emoji1}]
        desc_lines = [f"{emoji1 or '🔘'} — {role1.mention}"]

        for role, emoji in [(role2, emoji2), (role3, emoji3)]:
            if role:
                roles_data.append({"role_id": role.id, "label": role.name, "emoji": emoji})
                desc_lines.append(f"{emoji or '🔘'} — {role.mention}")

        embed = discord.Embed(
            title=title,
            description="\n".join(desc_lines),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Click a button to toggle the role")

        view = ReactionRoleView(roles_data)
        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()

        # Persist for re-registration on restart
        col = mongo_helper.get_collection("reaction_roles")
        if col:
            await col.insert_one({
                "message_id": msg.id,
                "channel_id": msg.channel.id,
                "guild_id": interaction.guild_id,
                "roles": roles_data,
            })


async def setup(bot):
    await bot.add_cog(AutoroleCog(bot))
    logger.info("✅ Autorole cog loaded")
