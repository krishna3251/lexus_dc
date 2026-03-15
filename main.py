import discord
import logging
import os
import time
import threading
import uvicorn
import asyncio
import random
from discord.ext import commands, tasks
from dotenv import load_dotenv

# === Optional imports ===
try:
    import wavelink
    WAVELINK_AVAILABLE = True
except ImportError:
    WAVELINK_AVAILABLE = False

try:
    from api import app as fastapi_app
    API_AVAILABLE = True
except ImportError:
    fastapi_app = None
    API_AVAILABLE = False

try:
    from stats_store import server_stats
except ImportError:
    server_stats = {"members": 0, "channels": 0, "roles": 0, "boosts": 0, "boost_level": 0}

try:
    import mongo_helper
    MONGO_AVAILABLE = True
except ImportError:
    mongo_helper = None
    MONGO_AVAILABLE = False

# === Load env ===
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")  # reads directly from env, NO config.py needed

if not TOKEN:
    logging.critical("❌ DISCORD_TOKEN not set in environment!")
    exit(1)

# === Logging ===
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/bot_log.txt", encoding="utf-8")
    ]
)

BOT_OWNER_ID      = 486555340670894080
BOT_VERSION       = "2.0.0"
LAVALINK_URI      = os.getenv("LAVALINK_URI",      "wss://lavalink-4-production-438b.up.railway.app")
LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD", "lexus123")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds          = True
intents.members         = True


async def _dynamic_prefix(bot, message: discord.Message):
    if not message.guild:
        return commands.when_mentioned_or("lx ")(bot, message)
    try:
        if MONGO_AVAILABLE:
            cfg    = await mongo_helper.get_guild_config(message.guild.id)
            prefix = cfg.get("prefix", "lx ")
        else:
            prefix = "lx "
    except Exception:
        prefix = "lx "
    return commands.when_mentioned_or(prefix)(bot, message)


class Bot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=_dynamic_prefix,
            intents=intents,
            help_command=None,
            owner_id=BOT_OWNER_ID
        )
        self.start_time          = time.time()
        self.commands_used       = 0
        self.status_cycle        = 0
        self.processing_commands = set()

    async def setup_hook(self):
        logging.info("⚙️  Running setup_hook...")

        if MONGO_AVAILABLE:
            try:
                db = await mongo_helper.connect()
                logging.info("✅ MongoDB connected" if db else "⚠️ MongoDB not connected")
            except Exception as e:
                logging.error(f"❌ MongoDB error: {e}")

        if not os.path.exists("cogs"):
            os.makedirs("cogs")

        cog_files = [f for f in os.listdir("cogs") if f.endswith(".py") and f != "__init__.py"]
        priority  = [f for f in cog_files if f.startswith(("help", "admin", "core"))]
        rest      = [f for f in cog_files if f not in priority]

        loaded, failed = [], []
        for filename in priority + rest:
            cog_path = f"cogs.{filename[:-3]}"
            try:
                await self.load_extension(cog_path)
                loaded.append(filename)
                logging.info(f"✅ Loaded: {cog_path}")
            except Exception as e:
                failed.append(filename)
                logging.error(f"❌ Failed {cog_path}: {e}")

        logging.info(f"📦 {len(loaded)} loaded, {len(failed)} failed")
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

    @tasks.loop(minutes=5)
    async def status_rotation(self):
        statuses = [
            "for commands | lx help",
            f"over {len(self.guilds)} servers",
            f"{len(self.users)} users",
            f"{self.commands_used} commands used",
            "LX Bot v2.0 | lx bio",
        ]
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=statuses[self.status_cycle % len(statuses)]
            )
        )
        self.status_cycle += 1

    @status_rotation.before_loop
    async def before_status(self):
        await self.wait_until_ready()


bot = Bot()


async def connect_lavalink():
    if not WAVELINK_AVAILABLE:
        return
    try:
        node = wavelink.Node(uri=LAVALINK_URI, password=LAVALINK_PASSWORD)
        await wavelink.Pool.connect(nodes=[node], client=bot, cache_capacity=100)
        logging.info("✅ Lavalink connected")
    except Exception as e:
        logging.error(f"❌ Lavalink failed: {e}")


@bot.event
async def on_ready():
    logging.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    await asyncio.sleep(2)
    try:
        synced = await bot.tree.sync()
        logging.info(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        logging.error(f"❌ Sync failed: {e}")
    server_stats["members"]  = sum(g.member_count or 0 for g in bot.guilds)
    server_stats["channels"] = sum(len(g.channels)     for g in bot.guilds)
    server_stats["roles"]    = sum(len(g.roles)         for g in bot.guilds)
    await connect_lavalink()
    logging.info(f"🚀 Ready! {len(bot.users)} users across {len(bot.guilds)} servers")


@bot.event
async def on_guild_join(guild):
    server_stats["members"]  = sum(g.member_count or 0 for g in bot.guilds)
    server_stats["channels"] = sum(len(g.channels)     for g in bot.guilds)
    server_stats["roles"]    = sum(len(g.roles)         for g in bot.guilds)
    channel = guild.system_channel or next(
        (ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages), None
    )
    if channel:
        try:
            await channel.send(embed=discord.Embed(
                title="👋 Thanks for adding LX Bot!",
                description="Use `lx help` to see all commands.",
                color=discord.Color.green()
            ))
        except discord.Forbidden:
            pass


@bot.event
async def on_guild_remove(guild):
    server_stats["members"]  = sum(g.member_count or 0 for g in bot.guilds)
    server_stats["channels"] = sum(len(g.channels)     for g in bot.guilds)
    server_stats["roles"]    = sum(len(g.roles)         for g in bot.guilds)


@bot.command(name="bio", aliases=["about", "owner"])
async def bio_command(ctx):
    embed = discord.Embed(title="🤖 About LX Bot", color=discord.Color.green())
    embed.add_field(name="Owner",   value=f"<@{BOT_OWNER_ID}>",       inline=True)
    embed.add_field(name="Version", value=BOT_VERSION,                 inline=True)
    embed.add_field(name="Serving", value=f"{len(bot.guilds)} servers", inline=True)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    await ctx.send(embed=embed)


@bot.command(name="restart")
@commands.is_owner()
async def restart(ctx):
    await ctx.send("🔄 Restarting...")
    import sys
    os.execv(sys.executable, ["python"] + sys.argv)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    embed = discord.Embed(title="⚠️ Error", color=discord.Color.red())
    if isinstance(error, commands.MissingRequiredArgument):
        embed.description = f"Missing argument: **{error.param.name}**"
    elif isinstance(error, commands.MissingPermissions):
        embed.description = "You don't have permission."
    elif isinstance(error, commands.CommandOnCooldown):
        embed.description = f"Cooldown. Retry in **{error.retry_after:.1f}s**"
    else:
        embed.description = "An unexpected error occurred."
        logging.error(f"Command error: {error}", exc_info=True)
    await ctx.send(embed=embed, delete_after=10)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    logging.error(f"Slash error: {error}", exc_info=True)
    embed = discord.Embed(title="⚠️ Error", description="Something went wrong.", color=discord.Color.red())
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception:
        pass


# === API server — binds to $PORT for Render health checks ===
def run_api():
    if not API_AVAILABLE:
        # If api.py is missing, spin up a minimal health-check server
        from fastapi import FastAPI
        import uvicorn
        _app = FastAPI()

        @_app.get("/")
        @_app.head("/")
        def root():
            return {"status": "ok"}

        port = int(os.environ.get("PORT", 10000))
        logging.info(f"🌐 Fallback health server on port {port}")
        uvicorn.run(_app, host="0.0.0.0", port=port, log_level="warning")
        return

    port = int(os.environ.get("PORT", 10000))
    logging.info(f"🌐 API server on port {port}")
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port, log_level="warning")


async def start_bot():
    for attempt in range(1, 6):
        try:
            logging.info(f"🚀 Starting bot (attempt {attempt}/5)")
            await bot.start(TOKEN)
            break
        except discord.LoginFailure:
            logging.critical("❌ Invalid token — check DISCORD_TOKEN env var.")
            return
        except discord.HTTPException as e:
            wait = min(30 * attempt, 300)
            logging.warning(f"⚠️ HTTP {e.status} — retrying in {wait}s")
            await asyncio.sleep(wait)
        except Exception as e:
            wait = min(10 * attempt, 60)
            logging.error(f"❌ {e} — retrying in {wait}s")
            await asyncio.sleep(wait)


if __name__ == "__main__":
    # Start web server first (Render health checks need it)
    threading.Thread(target=run_api, daemon=True).start()

    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logging.info("🛑 Shutdown.")
    except Exception as e:
        logging.critical(f"💥 Fatal: {e}", exc_info=True)
