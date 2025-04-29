import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
import aiohttp
import os
import logging
from datetime import datetime

# Enhanced emoji set with futuristic theme
CATEGORY_EMOJIS = {
    "Music": "🎧",
    "Moderation": "🛡️",
    "Fun": "✨",
    "Utility": "⚙️",
    "GifCog": "📱",
    "SarcasticPinger": "📡",
    "SlashCommandsCog": "⚡",
    "General": "🔮",
    "Economy": "💠",
    "AI": "🤖",
    "Gaming": "🎮",
    "Stats": "📊"
}

# Modern animated GIFs for help command
HELP_GIFS = [
    "https://media.tenor.com/5LWyJ6I_8KIAAAAd/xtreme-bot-help.gif",
    "https://media.tenor.com/Tz_GALR2e-QAAAAC/discord-help.gif",
    "https://media.tenor.com/OWU8NpyjTksAAAAC/bot-help-help.gif",
    "https://media.tenor.com/8QzhY8J8RjcAAAAC/help-command-discord.gif"
]

# Consistent color scheme
COLORS = {
    "primary": discord.Color.from_rgb(114, 137, 218),  # Discord blurple
    "secondary": discord.Color.from_rgb(88, 101, 242),  # New Discord blurple
    "success": discord.Color.from_rgb(87, 242, 135),   # Neon green
    "warning": discord.Color.from_rgb(255, 149, 0),    # Cyberpunk orange
    "error": discord.Color.from_rgb(255, 89, 89),      # Neon red
    "info": discord.Color.from_rgb(59, 165, 255),      # Holographic blue
    "tech": discord.Color.from_rgb(32, 34, 37)         # Discord dark
}

# Load webhook URL from environment or use default for testing
WEBHOOK_URL = os.getenv("HELP_WEBHOOK_URL", "")

async def send_webhook_message(content):
    if not WEBHOOK_URL:
        logging.info(f"Would send webhook: {content}")
        return
        
    try:
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(WEBHOOK_URL, session=session)
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_content = f"[{timestamp}] {content}"
            await webhook.send(formatted_content, username="NeoHelpLogger")
    except Exception as e:
        logging.error(f"Failed to send webhook: {e}")

class CategorySelect(discord.ui.Select):
    def __init__(self, bot, help_view):
        self.bot = bot
        self.help_view = help_view

        options = []
        for cog_name, cog in bot.cogs.items():
            if cog_name.lower() == "help":
                continue
            emoji = CATEGORY_EMOJIS.get(cog_name, "🔷")
            options.append(discord.SelectOption(
                label=cog_name,
                value=cog_name,
                emoji=emoji,
                description=f"Explore {cog_name} module"
            ))

        # If no cogs found or only Help cog, add a default option
        if not options:
            options.append(discord.SelectOption(
                label="No Modules",
                value="none",
                emoji="❓",
                description="No command modules available"
            ))

        super().__init__(
            placeholder="⚡ SELECT COMMAND MODULE",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        
        if selected == "none":
            embed = discord.Embed(
                title="⚠️ NO MODULES DETECTED",
                description="No command modules are currently loaded in the system.",
                color=COLORS["warning"]
            )
            embed.set_footer(text=f"SYSTEM SCAN COMPLETE • {datetime.now().strftime('%H:%M:%S')}")
            await interaction.response.edit_message(embed=embed, view=self.help_view)
            return
            
        cog = self.bot.get_cog(selected)
        if not cog:
            embed = discord.Embed(
                title="❌ MODULE NOT FOUND",
                description=f"The module '{selected}' could not be located in the system database.",
                color=COLORS["error"]
            )
            embed.set_footer(text=f"ERROR CODE: 404-MODULE-NOT-FOUND • {datetime.now().strftime('%H:%M:%S')}")
            await interaction.response.edit_message(embed=embed, view=self.help_view)
            return

        embed = discord.Embed(
            title=f"{CATEGORY_EMOJIS.get(selected, '🔷')} {selected.upper()} MODULE",
            description="Available commands in this module:",
            color=COLORS["primary"]
        )
        
        # Get commands from cog
        commands_list = cog.get_commands()
        
        if not commands_list:
            embed.description = "No commands registered in this module."
            embed.color = COLORS["warning"]
        else:
            # Fixed line - use default prefix directly since command_prefix is a function
            prefix = "lx "  # Default prefix
            
            # Add cool divider
            embed.description = f"Available commands in this module:\n```yaml\n{'='*40}```"
            
            for cmd in commands_list:
                cmd_help = cmd.help or "No description available."
                embed.add_field(
                    name=f"⌨️ `{prefix}{cmd.name}`",
                    value=f"> {cmd_help}",
                    inline=False
                )
            
            # Add cool ending divider
            embed.add_field(
                name=f"```yaml\n{'='*40}```",
                value=f"Total commands: {len(commands_list)}",
                inline=False
            )

        embed.set_footer(text=f"Module: {selected} • System: Online • {datetime.now().strftime('%H:%M:%S')}")
        await interaction.response.edit_message(embed=embed, view=self.help_view)

class HelpView(discord.ui.View):
    def __init__(self, bot, timeout=60):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.message = None
        self.select_menu = CategorySelect(bot, self)
        self.add_item(self.select_menu)

    async def on_timeout(self):
        if self.message:
            try:
                # Update message to show timeout instead of deleting
                embed = discord.Embed(
                    title="⏰ SYSTEM TIMEOUT",
                    description="Help interface has timed out due to inactivity.",
                    color=COLORS["tech"]
                )
                embed.set_footer(text="Use the help command again to restart the interface")
                await self.message.edit(embed=embed, view=None)
            except:
                # If editing fails, try to delete
                try:
                    await self.message.delete()
                except:
                    pass

    @discord.ui.button(label="◀️ MAIN MENU", style=discord.ButtonStyle.primary, custom_id="main_menu", row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🌐 LEXUS COMMAND INTERFACE",
            description="Welcome to the interactive help system.\nSelect a module from the dropdown menu to explore commands.",
            color=COLORS["primary"]
        )
        
        # Add version info
        embed.add_field(
            name="🔧 SYSTEM INFO",
            value=f"```yaml\nBot: {self.bot.user.name}\nVersion: 2.0.1\nStatus: Online\nLatency: {round(self.bot.latency * 1000)}ms```",
            inline=False
        )
        
        embed.set_footer(text=f"Interface active • {datetime.now().strftime('%H:%M:%S')} • Auto-sleep in 60s")
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_image(url=random.choice(HELP_GIFS))
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="❓ ABOUT", style=discord.ButtonStyle.secondary, custom_id="about_button", row=1)
    async def about_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="ℹ️ ABOUT THIS BOT",
            description="This advanced Discord bot provides various utilities and features to enhance your server experience.",
            color=COLORS["info"]
        )
        
        embed.add_field(
            name="🤖 CORE FEATURES",
            value="• Moderation tools\n• Music playback\n• Utility commands\n• Fun interactions\n• And much more!",
            inline=False
        )
        
        embed.add_field(
            name="📋 USAGE",
            value="Use `lx help` or `/help` to access this interface.\nSelect categories from the dropdown to explore commands.",
            inline=False
        )
        
        embed.set_footer(text=f"Interface active • {datetime.now().strftime('%H:%M:%S')} • Auto-sleep in 60s")
        await interaction.response.edit_message(embed=embed, view=self)

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logging.info("Help cog initialized")

    @app_commands.command(name="help", description="📜 Opens the advanced help interface with interactive modules")
    async def help_slash(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🌐 NEXUS COMMAND INTERFACE",
            description="Welcome to the interactive help system.\nSelect a module from the dropdown menu to explore commands.",
            color=COLORS["primary"]
        )
        
        # Add version info
        embed.add_field(
            name="🔧 SYSTEM INFO",
            value=f"```yaml\nBot: {self.bot.user.name}\nVersion: 2.0.1\nStatus: Online\nLatency: {round(self.bot.latency * 1000)}ms```",
            inline=False
        )
        
        embed.set_footer(text=f"Interface active • {datetime.now().strftime('%H:%M:%S')} • Auto-sleep in 60s")
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_image(url=random.choice(HELP_GIFS))

        view = HelpView(self.bot)
        
        # Use deferred response to prevent timeout
        await interaction.response.defer()
        followup = await interaction.followup.send(embed=embed, view=view)
        view.message = followup
        
        # Log help command usage if logging is enabled
        guild_name = interaction.guild.name if interaction.guild else "DM"
        await send_webhook_message(f"📬 {interaction.user} accessed help interface in {guild_name}.")

    @commands.command(name="help", help="📜 Opens the advanced help interface with interactive modules")
    async def help_prefix(self, ctx):
        embed = discord.Embed(
            title="🌐 NEXUS COMMAND INTERFACE",
            description="Welcome to the interactive help system.\nSelect a module from the dropdown menu to explore commands.",
            color=COLORS["primary"]
        )
        
        # Add version info
        embed.add_field(
            name="🔧 SYSTEM INFO",
            value=f"```yaml\nBot: {ctx.bot.user.name}\nVersion: 2.0.1\nStatus: Online\nLatency: {round(ctx.bot.latency * 1000)}ms```",
            inline=False
        )
        
        embed.set_footer(text=f"Interface active • {datetime.now().strftime('%H:%M:%S')} • Auto-sleep in 60s")
        embed.set_thumbnail(url=ctx.bot.user.display_avatar.url)
        embed.set_image(url=random.choice(HELP_GIFS))

        view = HelpView(self.bot)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
        
        # Log help command usage if logging is enabled
        guild_name = ctx.guild.name if ctx.guild else "DM"
        await send_webhook_message(f"📬 {ctx.author} accessed help interface in {guild_name}.")

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("Help cog is ready")
        try:
            # Syncing is now done in main.py, so we don't need this
            # But we'll keep it here for visibility
            logging.info("Help cog doesn't need to sync commands - already done in main.py")
        except Exception as e:
            logging.error(f"❌ Error in Help cog on_ready: {e}")

async def setup(bot):
    await bot.add_cog(Help(bot))
    logging.info("Help cog has been added to the bot")
