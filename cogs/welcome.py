"""
Welcome Cog — Customizable welcome/goodbye embeds with user avatar,
join position, account age. Optional DM on join.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
import mongo_helper

logger = logging.getLogger(__name__)


class WelcomeCog(commands.Cog, name="Welcome"):
    """Customizable welcome and goodbye messages."""

    def __init__(self, bot):
        self.bot = bot

    # ── Configuration commands ─────────────────────────────────────

    @app_commands.command(name="setwelcome", description="Set the welcome channel and message")
    @app_commands.describe(
        channel="Channel for welcome messages",
        message="Welcome message ({user} = mention, {server} = server name, {count} = member count)",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def set_welcome(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str = None):
        data = {"welcome_channel": channel.id}
        if message:
            data["welcome_message"] = message
        await mongo_helper.update_guild_config(interaction.guild_id, data)
        preview = message or "Welcome {user} to **{server}**! You are member #{count}."
        await interaction.response.send_message(
            f"✅ Welcome channel set to {channel.mention}\nPreview: {preview}",
            ephemeral=True,
        )

    @app_commands.command(name="setgoodbye", description="Set the goodbye channel and message")
    @app_commands.describe(
        channel="Channel for goodbye messages",
        message="Goodbye message ({user} = name, {server} = server name)",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def set_goodbye(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str = None):
        data = {"goodbye_channel": channel.id}
        if message:
            data["goodbye_message"] = message
        await mongo_helper.update_guild_config(interaction.guild_id, data)
        await interaction.response.send_message(
            f"✅ Goodbye channel set to {channel.mention}", ephemeral=True
        )

    @app_commands.command(name="setwelcomedm", description="Set the DM message sent to new members")
    @app_commands.describe(message="DM message ({user} = name, {server} = server name). Leave empty to disable.")
    @app_commands.default_permissions(manage_guild=True)
    async def set_welcome_dm(self, interaction: discord.Interaction, message: str = None):
        if message:
            await mongo_helper.update_guild_config(interaction.guild_id, {"welcome_dm": message})
            await interaction.response.send_message("✅ Welcome DM set.", ephemeral=True)
        else:
            await mongo_helper.update_guild_config(interaction.guild_id, {"welcome_dm": None})
            await interaction.response.send_message("✅ Welcome DM disabled.", ephemeral=True)

    # ── Events ─────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = await mongo_helper.get_guild_config(member.guild.id)

        # Welcome channel message
        ch_id = cfg.get("welcome_channel")
        if ch_id:
            channel = member.guild.get_channel(ch_id)
            if channel:
                raw_msg = cfg.get(
                    "welcome_message",
                    "Welcome {user} to **{server}**! You are member #{count}. 🎉",
                )
                text = raw_msg.format(
                    user=member.mention,
                    server=member.guild.name,
                    count=member.guild.member_count,
                )

                embed = discord.Embed(
                    description=text,
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow(),
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.add_field(
                    name="Account Age",
                    value=discord.utils.format_dt(member.created_at, "R"),
                    inline=True,
                )
                embed.set_footer(text=f"ID: {member.id}")

                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

        # Welcome DM
        dm_msg = cfg.get("welcome_dm")
        if dm_msg:
            text = dm_msg.format(user=member.name, server=member.guild.name)
            try:
                await member.send(text)
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        cfg = await mongo_helper.get_guild_config(member.guild.id)
        ch_id = cfg.get("goodbye_channel")
        if not ch_id:
            return

        channel = member.guild.get_channel(ch_id)
        if not channel:
            return

        raw_msg = cfg.get("goodbye_message", "**{user}** has left **{server}**. 😢")
        text = raw_msg.format(user=str(member), server=member.guild.name)

        embed = discord.Embed(
            description=text,
            color=discord.Color.dark_grey(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        roles = ", ".join(r.mention for r in member.roles if r != member.guild.default_role) or "None"
        embed.add_field(name="Roles", value=roles[:1024])
        embed.set_footer(text=f"ID: {member.id}")

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass


async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))
    logger.info("✅ Welcome cog loaded")
