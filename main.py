import discord
import logging
import os
import time
import wavelink
import threading
import uvicorn
import asyncio
import psutil
import platform
import random
from discord.ext import commands, tasks
from dotenv import load_dotenv
from keep_alive import keep_alive
from api import app
from stats_store import server_stats

# === Start keep_alive ===
# keep_alive runs Flask on Render's $PORT (the public-facing port, e.g. 10000).
# Uvicorn (FastAPI) runs on a DIFFERENT internal port (8000) to avoid conflict.
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

# === Bot Configuration ===
BOT_OWNER_ID = 486555340670894080
BOT_VERSION = "2.0.0"
BOT_DESCRIPTION = "A powerful Discord bot with multiple features and commands!"

# === Intents & Prefix ===
PREFIX = commands.when_mentioned_or("lx ")
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True


# === Bot class ===
class Bot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=PREFIX,
            intents=intents,
            help_command=None,
            description=BOT_DESCRIPTION,
            owner_id=BOT_OWNER_ID
        )
        self.start_time = time.time()
        self.processing_commands = set()
        self.commands_used = 0
        self.status_cycle = 0

    async def setup_hook(self):
        logging.info("Setting up bot extensions...")
        # NOTE: Lavalink is connected in on_ready (not here) because
        #       setup_hook fires before Discord is fully ready, causing
        #       the Render free-tier Lavalink service to always 429.

        # Load connection handler FIRST
        try:
            await self.load_extension("connection_handler")
            logging.info("✅ Loaded connection handler")
        except Exception as e:
            logging.error(f"❌ Failed to load connection handler: {e}")

        # Load cogs
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

        self.status_rotation.start()

    async def process_commands(self, message):
        if message.id in self.processing_commands:
            return
        self.processing_commands.add(message.id)
        try:
            ctx = await self.get_context(message)
            if ctx.valid:
                await self.invoke(ctx)
                self.commands_used += 1
        finally:
            self.processing_commands.discard(message.id)

    def uptime(self):
        return int(time.time() - self.start_time)

    async def handle_rate_limit_error(self, error):
        if hasattr(error, "response") and error.response:
            retry_after = error.response.headers.get("Retry-After")
            if retry_after:
                wait_time = float(retry_after) + random.uniform(1, 5)
                logging.warning(f"Rate limited during startup. Waiting {wait_time:.2f} seconds...")
                await asyncio.sleep(wait_time)
                return True
        return False

    @tasks.loop(minutes=5)
    async def status_rotation(self):
        statuses = [
            "for commands | lx help",
            f"over {len(self.guilds)} servers",
            f"{len(self.users)} users",
            f"{self.commands_used} commands used",
            "LX Bot v2.0 | lx bio",
        ]
        status = statuses[self.status_cycle % len(statuses)]
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name=status)
        )
        self.status_cycle += 1

    @status_rotation.before_loop
    async def before_status_rotation(self):
        await self.wait_until_ready()


bot = Bot()


# === Utility Functions ===
def format_uptime(seconds):
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h {minutes}m {seconds}s"


def get_system_info():
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "platform": platform.system(),
        "python_version": platform.python_version(),
    }


# === Lavalink ===
# Railway hosts Lavalink with a persistent TLS WebSocket — use wss://, no port needed.
# The URI and password are stored in Render environment variables.
# Wavelink v3 automatically appends /v4/websocket — do NOT add it to the URI.
LAVALINK_URI      = os.getenv("LAVALINK_URI", "wss://lavalink-4-production-438b.up.railway.app")
LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD", "lexus123")


async def connect_lavalink():
    """Connect to the Railway-hosted Lavalink v4 node via wss://"""
    try:
        node = wavelink.Node(uri=LAVALINK_URI, password=LAVALINK_PASSWORD)
        await wavelink.Pool.connect(nodes=[node], client=bot, cache_capacity=100)
        logging.info(f"✅ Lavalink connected → {LAVALINK_URI}")
    except Exception as e:
        logging.error(f"❌ Lavalink connection failed: {e}")


# === Events ===


@bot.event
async def on_ready():
    logging.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    await asyncio.sleep(2)
    try:
        synced = await bot.tree.sync()
        logging.info(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        logging.error(f"❌ Failed to sync slash commands: {e}")

    # Update stats_store so /stats API returns real data
    server_stats["members"] = sum(g.member_count or 0 for g in bot.guilds)
    server_stats["channels"] = sum(len(g.channels) for g in bot.guilds)
    server_stats["roles"] = sum(len(g.roles) for g in bot.guilds)

    # Connect to Railway Lavalink — always-on, no cold start delay needed
    await connect_lavalink()

    print("🔗 Connected to the following servers:")
    for guild in bot.guilds:
        print(f" - {guild.name} (ID: {guild.id}) - {guild.member_count} members")

    print(f"🚀 Bot is ready! Serving {len(bot.users)} users across {len(bot.guilds)} servers")



@bot.event
async def on_wavelink_node_ready(payload: wavelink.NodeReadyEventPayload):
    logging.info(f"🎵 Lavalink node ready | resumed: {payload.resumed} | sessions: {payload.session_id}")

@bot.event
async def on_guild_join(guild):
    logging.info(f"📥 Joined guild: {guild.name} (ID: {guild.id}) - {guild.member_count} members")

    # Keep stats up to date
    server_stats["members"] = sum(g.member_count or 0 for g in bot.guilds)
    server_stats["channels"] = sum(len(g.channels) for g in bot.guilds)
    server_stats["roles"] = sum(len(g.roles) for g in bot.guilds)

    if guild.system_channel:
        channel = guild.system_channel
    else:
        channel = next(
            (ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages),
            None,
        )

    if channel:
        embed = discord.Embed(
            title="👋 Thanks for adding me!",
            description=(
                f"Hello **{guild.name}**! I'm LX Bot and I'm here to help!\n\n"
                "• Use `lx help` to see all available commands\n"
                "• Use `lx bio` to learn more about me\n"
                "• Need help? Contact my owner with `lx bio`"
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text="Let's make this server awesome! 🚀")
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass


@bot.event
async def on_guild_remove(guild):
    logging.info(f"📤 Left guild: {guild.name} (ID: {guild.id})")
    server_stats["members"] = sum(g.member_count or 0 for g in bot.guilds)
    server_stats["channels"] = sum(len(g.channels) for g in bot.guilds)
    server_stats["roles"] = sum(len(g.roles) for g in bot.guilds)


# === Commands ===
@bot.command(name="bio", aliases=["about", "owner"])
async def bio_command(ctx):
    embed = discord.Embed(
        title="🤖 About LX Bot",
        description="A powerful and feature-rich Discord bot created with passion!",
        color=discord.Color.green(),
    )
    embed.add_field(name="👨‍💻 Bot Owner", value=f"<@{BOT_OWNER_ID}>", inline=True)
    embed.add_field(name="📅 Version", value=f"**{BOT_VERSION}**", inline=True)
    embed.add_field(
        name="🌐 Serving",
        value=f"**{len(bot.guilds)}** servers\n**{len(bot.users)}** users",
        inline=True,
    )
    embed.add_field(
        name="✨ Features",
        value=(
            "• Multiple command prefixes\n"
            "• Slash command support\n"
            "• Real-time statistics\n"
            "• Auto status rotation\n"
            "• Comprehensive logging"
        ),
        inline=False,
    )
    embed.add_field(
        name="📬 Contact & Support",
        value=(
            "Need help or have suggestions? Feel free to contact my owner!\n"
            "Use `lx help` for all commands or `lx stats` for detailed statistics."
        ),
        inline=False,
    )
    embed.set_footer(text="Thanks for using LX Bot! ❤️")
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    await ctx.send(embed=embed)


# === Error Handling ===
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        embed = discord.Embed(
            title="❓ Unknown Command",
            description=(
                f"The command `{ctx.invoked_with}` doesn't exist!\n"
                "Use `lx help` to see all available commands."
            ),
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed, delete_after=10)
        return

    logging.error(f"Command error in {ctx.command}: {error}", exc_info=True)

    embed = discord.Embed(title="⚠️ Command Error", color=discord.Color.red())

    if isinstance(error, commands.MissingRequiredArgument):
        embed.description = f"Missing required argument: **{error.param.name}**"
    elif isinstance(error, commands.BadArgument):
        embed.description = "Invalid argument provided"
    elif isinstance(error, commands.MissingPermissions):
        embed.description = "You don't have permission to use this command"
    elif isinstance(error, commands.BotMissingPermissions):
        embed.description = "I don't have the required permissions for this command"
    elif isinstance(error, commands.CommandOnCooldown):
        embed.description = f"Command is on cooldown. Try again in {error.retry_after:.2f} seconds"
    else:
        embed.description = "An unexpected error occurred"

    await ctx.send(embed=embed, delete_after=15)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    logging.error(f"Slash command error: {error}", exc_info=True)

    embed = discord.Embed(
        title="⚠️ Command Error",
        description="An error occurred with this slash command",
        color=discord.Color.red(),
    )

    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        logging.error(f"Error handling slash command error: {e}")


# FIX: Uvicorn (FastAPI) runs on port 8000 — a different internal port from
#      keep_alive's Flask which binds to Render's $PORT (typically 10000).
#      daemon=True ensures this thread doesn't block clean shutdown.
def run_api():
    uvicorn.run(app, host="0.0.0.0", port=8000)

threading.Thread(target=run_api, daemon=True).start()


# === Shutdown Handler ===
@bot.event
async def on_disconnect():
    logging.info("🔌 Bot disconnected")


async def shutdown_handler():
    logging.info("🛑 Shutting down bot...")
    await bot.close()


# === Bot Startup with Rate Limit Handling ===
async def start_bot_with_retry():
    max_startup_attempts = 5
    startup_attempt = 0

    while startup_attempt < max_startup_attempts:
        try:
            startup_attempt += 1
            logging.info(f"Starting LX Bot (attempt {startup_attempt}/{max_startup_attempts})")
            await bot.start(TOKEN)
            break

        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e.response.headers, "get", lambda x, y=60: y)("Retry-After", 60)
                wait_time = float(retry_after) + random.uniform(5, 15)
                logging.warning(f"Rate limited during startup. Waiting {wait_time:.2f} seconds...")
                await asyncio.sleep(wait_time)

            elif e.status in [502, 503, 504]:
                wait_time = min(30 * startup_attempt, 300)
                logging.warning(f"Discord server error {e.status}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)

            else:
                logging.error(f"HTTP Exception during startup: {e}")
                if startup_attempt >= max_startup_attempts:
                    logging.critical("Max startup attempts reached. Exiting.")
                    raise
                await asyncio.sleep(10 * startup_attempt)

        except discord.LoginFailure:
            logging.critical("Invalid bot token. Please check your DISCORD_TOKEN.")
            return

        except Exception as e:
            logging.error(f"Unexpected error during startup: {e}")
            if startup_attempt >= max_startup_attempts:
                logging.critical("Max startup attempts reached. Exiting.")
                raise
            wait_time = min(10 * startup_attempt, 60)
            await asyncio.sleep(wait_time)

    else:
        logging.critical("Failed to start bot after maximum attempts.")


# === Run the bot ===
if __name__ == "__main__":
    try:
        logging.info("Initializing LX Bot with enhanced connection handling...")
        asyncio.run(start_bot_with_retry())
    except KeyboardInterrupt:
        logging.info("Bot shutdown initiated by keyboard interrupt")
        asyncio.run(shutdown_handler())
    except Exception as e:
        logging.critical(f"Fatal error: {e}", exc_info=True)
