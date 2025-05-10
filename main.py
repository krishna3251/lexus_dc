# 📁 main.py
import discord
import logging
import os
import time
import asyncio
from discord.ext import commands
from dotenv import load_dotenv
from keep_alive import keep_alive

# === Start keep_alive ===
keep_alive()

# === Logging setup ===
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/bot_log.txt", encoding="utf-8")
    ]
)

# === Load .env token ===
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    logging.critical("DISCORD_TOKEN not found in .env file!")
    exit(1)

# === Intents & Prefix ===
PREFIX = commands.when_mentioned_or("lx ", "lx","LX","Lx")
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

# === Bot class ===
class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=PREFIX, intents=intents, help_command=None)
        self.start_time = time.time()
        self.processing_commands = set()

    async def setup_hook(self):
        logging.info("Setting up bot extensions...")
        if not os.path.exists("cogs"):
            os.makedirs("cogs")
            logging.warning("Created missing cogs directory")

        for filename in os.listdir("cogs"):
            if filename.endswith(".py"):
                try:
                    await self.load_extension(f"cogs.{filename[:-3]}")
                    logging.info(f"✅ Loaded extension: {filename}")
                except Exception as e:
                    logging.error(f"❌ Failed to load {filename}: {e}")

    async def process_commands(self, message):
        if message.id in self.processing_commands:
            return
        self.processing_commands.add(message.id)
        try:
            await super().process_commands(message)
        finally:
            self.processing_commands.discard(message.id)

    def uptime(self):
        return int(time.time() - self.start_time)

bot = Bot()

# === Events & Commands ===

@bot.event
async def on_ready():
    logging.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    await asyncio.sleep(2)
    try:
        synced = await bot.tree.sync()
        logging.info(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        logging.error(f"❌ Failed to sync slash commands: {e}")
    
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name=f"for commands | lx help"
    ))

    print("🔗 Connected to the following servers:")
    for guild in bot.guilds:
        print(f" - {guild.name} (ID: {guild.id})")

@bot.command(name="uptime")
async def uptime_command(ctx):
    uptime_seconds = bot.uptime()
    minutes, seconds = divmod(uptime_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
    embed = discord.Embed(
        title="🕒 Bot Uptime",
        description=f"Bot has been online for: **{uptime_str}**",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

@bot.command(name="ping")
async def ping_command(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! Latency: {latency}ms")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        logging.info(f"Unknown command: {ctx.message.content}")
        return
    logging.error(f"Command error in {ctx.command}: {error}", exc_info=True)
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"⚠️ Missing required argument: {error.param.name}")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("⚠️ Invalid argument provided")
    else:
        await ctx.send("⚠️ Something went wrong with that command")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    logging.error(f"Slash command error: {error}", exc_info=True)
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message("⚠️ An error occurred with this command", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ An error occurred with this command", ephemeral=True)
    except Exception as e:
        logging.error(f"Error handling slash command error: {e}")

# === Run the bot ===
if __name__ == "__main__":
    try:
        logging.info("Starting bot...")
        asyncio.run(bot.start(TOKEN))
    except KeyboardInterrupt:
        logging.info("Bot shutdown initiated by keyboard interrupt")
    except Exception as e:
        logging.critical(f"Fatal error: {e}", exc_info=True)
