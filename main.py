import discord
import logging
import os
import time
import threading
import uvicorn
import asyncio
import psutil
import platform
import random
from discord.ext import commands, tasks
from dotenv import load_dotenv

# === Optional imports (won't crash if missing) ===
try:
    import wavelink
    WAVELINK_AVAILABLE = True
except ImportError:
    WAVELINK_AVAILABLE = False
    logging.warning("⚠️ wavelink not installed — music features disabled")

try:
    from api import app
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False
    logging.warning("⚠️ api.py not found — /stats endpoint disabled")

try:
    from stats_store import server_stats
    STATS_AVAILABLE = True
except ImportError:
    server_stats = {"members": 0, "channels": 0, "roles": 0}
    STATS_AVAILABLE = False
    logging.warning("⚠️ stats_store.py not found — using in-memory stats")

try:
    import mongo_helper
    MONGO_AVAILABLE = True
except ImportError:
    mongo_helper = None
    MONGO_AVAILABLE = False
    logging.warning("⚠️ mongo_helper.py not found — MongoDB features disabled")

# === Load .env ===
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    logging.critical("❌ DISCORD_TOKEN not found in environment!")
    exit(1)

# === Logging Setup ===
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/bot_log.txt", encoding="utf-8")
    ]
)

# === Bot Config ===
BOT_OWNER_ID = 486555340670894080
BOT_VERSION = "2.0.0"
BOT_DESCRIPTION = "A powerful Discord bot with multiple features and commands!"

# === Lavalink Config ===
LAVALINK_URI      = os.getenv("LAVALINK_URI", "wss://lavalink-4-production-438b.up.railway.app")
LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD", "lexus123")

# === Intents ===
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True


# === Dynamic Prefix ===
async def _dynamic_prefix(bot, message: discord.Message):
    if not message.guild:
        return commands.when_mentioned_or("lx ")(bot, message)
    try:
        if MONGO_AVAILABLE:
            cfg = await mongo_helper.get_guild_config(message.guild.id)
            prefix = cfg.get("prefix", "lx ")
        else:
            prefix = "lx "
    except Exception:
        prefix = "lx "
    return commands.when_mentioned_or(prefix)(bot, message)


# === Bot Class ===
class Bot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=_dynamic_prefix,
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
        logging.info("⚙️  Running setup_hook...")

        # Connect MongoDB
        if MONGO_AVAILABLE:
            try:
                db = await mongo_helper.connect()
                if db:
                    logging.info("✅ MongoDB connected")
                else:
                    logging.warning("⚠️ MongoDB not connected – limited features")
            except Exception as e:
                logging.error(f"❌ MongoDB setup error: {e}")

        # Auto-load ALL cogs from /cogs directory
        if not os.path.exists("cogs"):
            os.makedirs("cogs")
            logging.warning("⚠️ Created missing cogs/ directory")

        cog_files = [
            f for f in os.listdir("cogs")
            if f.endswith(".py") and f != "__init__.py"
        ]

        # Priority cogs load first (help, admin, core)
        priority = [f for f in cog_files if f.startswith(("help", "admin", "core"))]
        rest     = [f for f in cog_files if f not in priority]
        ordered  = priority + rest

        loaded, failed = [], []
        for filename in ordered:
            cog_path = f"cogs.{filename[:-3]}"
            try:
                await self.load_extension(cog_path)
                loaded.append(filename)
                logging.info(f"✅ Loaded cog: {cog_path}")
            except Exception as e:
                failed.append((filename, str(e)))
                logging.error(f"❌ Failed to load {cog_path}: {e}")

        logging.info(f"📦 Cogs: {len(loaded)} loaded, {len(failed)} failed")
        if failed:
            for name, err in failed:
                logging.warning(f"   • {name}: {err}")

        # Start status rotation
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
    hours, minutes   = divmod(minutes, 60)
    days, hours      = divmod(hours, 24)
    return f"{days}d {hours}h {minutes}m {seconds}s"


def get_system_info():
    return {
        "cpu_percent":    psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "platform":       platform.system(),
        "python_version": platform.python_version(),
    }


# === Lavalink ===
async def connect_lavalink():
    if not WAVELINK_AVAILABLE:
        logging.warning("⚠️ Skipping Lavalink — wavelink not installed")
        return
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

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        logging.info(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        logging.error(f"❌ Failed to sync slash commands: {e}")

    # Update stats
    server_stats["members"]  = sum(g.member_count or 0 for g in bot.guilds)
    server_stats["channels"] = sum(len(g.channels) for g in bot.guilds)
    server_stats["roles"]    = sum(len(g.roles) for g in bot.guilds)

    # Connect Lavalink
    await connect_lavalink()

    logging.info("🔗 Connected servers:")
    for guild in bot.guilds:
        logging.info(f"   • {guild.name} (ID: {guild.id}) — {guild.member_count} members")
    logging.info(f"🚀 Ready! {len(bot.users)} users across {len(bot.guilds)} servers")


@bot.event
async def on_guild_join(guild):
    logging.info(f"📥 Joined: {guild.name} (ID: {guild.id}) — {guild.member_count} members")
    server_stats["members"]  = sum(g.member_count or 0 for g in bot.guilds)
    server_stats["channels"] = sum(len(g.channels) for g in bot.guilds)
    server_stats["roles"]    = sum(len(g.roles) for g in bot.guilds)

    channel = guild.system_channel or next(
        (ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages),
        None
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
    logging.info(f"📤 Left: {guild.name} (ID: {guild.id})")
    server_stats["members"]  = sum(g.member_count or 0 for g in bot.guilds)
    server_stats["channels"] = sum(len(g.channels) for g in bot.guilds)
    server_stats["roles"]    = sum(len(g.roles) for g in bot.guilds)


@bot.event
async def on_disconnect():
    logging.info("🔌 Bot disconnected")


# === Wavelink Event ===
if WAVELINK_AVAILABLE:
    @bot.event
    async def on_wavelink_node_ready(payload: wavelink.NodeReadyEventPayload):
        logging.info(
            f"🎵 Lavalink node ready | resumed: {payload.resumed} | "
            f"node: {payload.node.identifier}"
        )


# === Commands ===
@bot.command(name="bio", aliases=["about", "owner"])
async def bio_command(ctx):
    embed = discord.Embed(
        title="🤖 About LX Bot",
        description="A powerful and feature-rich Discord bot created with passion!",
        color=discord.Color.green(),
    )
    embed.add_field(name="👨‍💻 Bot Owner",  value=f"<@{BOT_OWNER_ID}>",       inline=True)
    embed.add_field(name="📅 Version",      value=f"**{BOT_VERSION}**",        inline=True)
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


@bot.command(name="restart")
@commands.is_owner()
async def restart(ctx):
    await ctx.send("🔄 Restarting...")
    logging.info("🔄 Restart triggered by owner")
    import sys
    os.execv(sys.executable, ["python"] + sys.argv)


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
        embed.description = f"Command on cooldown. Try again in **{error.retry_after:.2f}s**"
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


# === API Server (Uvicorn) ===
# FIX: moved inside __main__ so it doesn't run on import
def run_api():
    if not API_AVAILABLE:
        logging.warning("⚠️ Skipping API server — api.py not found")
        return
    port = int(os.environ.get("PORT", 10000))
    logging.info(f"🌐 Starting API server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# === Startup with Rate Limit Retry ===
async def start_bot_with_retry():
    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        try:
            logging.info(f"🚀 Starting LX Bot (attempt {attempt}/{max_attempts})")
            await bot.start(TOKEN)
            break

        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = float(
                    getattr(e, "response", None) and
                    e.response.headers.get("Retry-After", 60) or 60
                )
                wait = retry_after + random.uniform(5, 15)
                logging.warning(f"⚠️ Rate limited. Waiting {wait:.1f}s...")
                await asyncio.sleep(wait)
            elif e.status in [502, 503, 504]:
                wait = min(30 * attempt, 300)
                logging.warning(f"⚠️ Discord server error {e.status}. Retrying in {wait}s...")
                await asyncio.sleep(wait)
            else:
                logging.error(f"❌ HTTP Exception: {e}")
                if attempt >= max_attempts:
                    raise
                await asyncio.sleep(10 * attempt)

        except discord.LoginFailure:
            logging.critical("❌ Invalid bot token. Check your DISCORD_TOKEN env var.")
            return

        except Exception as e:
            logging.error(f"❌ Unexpected error: {e}")
            if attempt >= max_attempts:
                raise
            wait = min(10 * attempt, 60)
            await asyncio.sleep(wait)
    else:
        logging.critical("❌ Failed to start after maximum attempts.")


# === Entry Point ===
if __name__ == "__main__":
    try:
        logging.info("⚙️  Initializing LX Bot...")

        # FIX 1: Start keep_alive so Render health checks pass
        try:
            from keep_alive import keep_alive
            keep_alive()
            logging.info("✅ Keep-alive server started")
        except ImportError:
            logging.warning("⚠️ keep_alive.py not found — skipping")

        # FIX 2: Start API thread here, not at module level
        threading.Thread(target=run_api, daemon=True).start()

        asyncio.run(start_bot_with_retry())

    except KeyboardInterrupt:
        logging.info("🛑 Shutdown by keyboard interrupt")
        asyncio.run(bot.close())
    except Exception as e:
        logging.critical(f"💥 Fatal error: {e}", exc_info=True)
