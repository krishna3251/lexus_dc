"""
Tickets Cog — /ticket opens a private thread, staff can close it,
transcript saved and sent to the user.
"""

import discord
from discord.ext import commands
from discord import app_commands
import io
import logging
import mongo_helper

logger = logging.getLogger(__name__)


class CloseButton(discord.ui.View):
    """Persistent view with a Close button attached to ticket threads."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_threads:
            await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
            return

        await interaction.response.defer()
        thread = interaction.channel

        # Build transcript
        messages = []
        async for msg in thread.history(limit=500, oldest_first=True):
            ts = msg.created_at.strftime("%Y-%m-%d %H:%M")
            messages.append(f"[{ts}] {msg.author}: {msg.content}")

        transcript_text = "\n".join(messages) or "No messages."
        transcript_file = discord.File(
            io.BytesIO(transcript_text.encode()), filename=f"ticket-{thread.id}.txt"
        )

        # Send transcript to the ticket opener (first message author)
        opener_id = None
        col = mongo_helper.get_collection("tickets")
        if col:
            doc = await col.find_one({"thread_id": thread.id})
            if doc:
                opener_id = doc.get("user_id")

        if opener_id:
            user = interaction.guild.get_member(opener_id) or await interaction.guild.fetch_member(opener_id)
            if user:
                try:
                    await user.send(
                        f"📋 Your ticket in **{interaction.guild.name}** was closed. Transcript attached.",
                        file=transcript_file,
                    )
                except discord.Forbidden:
                    pass

        await thread.send("🔒 Ticket closed.")
        await thread.edit(archived=True, locked=True)

        if col:
            await col.delete_one({"thread_id": thread.id})


class TicketsCog(commands.Cog, name="Tickets"):
    """Support ticket system using private threads."""

    def __init__(self, bot):
        self.bot = bot
        bot.add_view(CloseButton())  # re-register persistent view

    @app_commands.command(name="ticket", description="Open a support ticket")
    @app_commands.describe(subject="Brief description of your issue")
    async def ticket(self, interaction: discord.Interaction, subject: str = "Support Request"):
        # Check for existing open ticket
        col = mongo_helper.get_collection("tickets")
        if col:
            existing = await col.find_one({
                "user_id": interaction.user.id,
                "guild_id": interaction.guild_id,
            })
            if existing:
                thread = interaction.guild.get_thread(existing["thread_id"])
                if thread and not thread.archived:
                    await interaction.response.send_message(
                        f"❌ You already have an open ticket: {thread.mention}", ephemeral=True
                    )
                    return
                else:
                    # Stale record
                    await col.delete_one({"_id": existing["_id"]})

        # Create private thread
        thread = await interaction.channel.create_thread(
            name=f"ticket-{interaction.user.name}",
            type=discord.ChannelType.private_thread,
            reason=f"Support ticket by {interaction.user}",
        )

        # Opening embed
        embed = discord.Embed(
            title=f"🎫 Ticket: {subject}",
            description=(
                f"Opened by {interaction.user.mention}\n\n"
                "Please describe your issue. A staff member will be with you shortly.\n"
                "Click **Close Ticket** when resolved."
            ),
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )
        await thread.send(embed=embed, view=CloseButton())
        await thread.add_user(interaction.user)

        # Persist
        if col:
            await col.insert_one({
                "thread_id": thread.id,
                "user_id": interaction.user.id,
                "guild_id": interaction.guild_id,
                "subject": subject,
            })

        await interaction.response.send_message(
            f"✅ Ticket created: {thread.mention}", ephemeral=True
        )

    @app_commands.command(name="setticketcategory", description="Set the category for ticket threads (unused for threads, reserved)")
    @app_commands.default_permissions(manage_guild=True)
    async def set_ticket_category(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await mongo_helper.update_guild_config(interaction.guild_id, {"ticket_channel": channel.id})
        await interaction.response.send_message(
            f"✅ Tickets will be created in {channel.mention}", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(TicketsCog(bot))
    logger.info("✅ Tickets cog loaded")
