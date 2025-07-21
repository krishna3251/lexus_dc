import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import asyncio
import datetime
import os
import aiohttp
import json
import logging
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ActivityLevel(Enum):
    VERY_ACTIVE = "very_active"
    ACTIVE = "active" 
    MODERATE = "moderate"
    INACTIVE = "inactive"
    DEAD = "dead"

@dataclass
class ServerConfig:
    name: str
    channel_id: int
    enabled: bool = True
    min_interval_hours: int = 4
    max_interval_hours: int = 12
    next_ping: Optional[float] = None
    activity_level: ActivityLevel = ActivityLevel.MODERATE
    last_activity: Optional[float] = None
    ping_count: int = 0
    
    def to_dict(self) -> dict:
        data = asdict(self)
        # Convert enum to string for JSON serialization
        data['activity_level'] = self.activity_level.value
        return data

class SmartPinger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tenor_api_key = os.getenv('TENOR_API_KEY')
        self.giphy_api_key = os.getenv('GIPHY_API_KEY')
        self.config_file = "pinger_config.json"
        
        # Load or initialize server configs
        self.server_configs = self._load_configs()
        
        # Enhanced message templates with varying intensity
        self.message_templates = {
            ActivityLevel.VERY_ACTIVE: [
                "server mein sb active hai, tu kahan gaya bro?",
                "sab chat kar rahe, tu kyun missing hai?",
                "active server mein tu ghost ban gaya?",
                "tere bina toh lagta hai party incomplete hai!",
                "sab tere intezaar mein thak gaye hai",
                "bro tujhe NASA ne space mein bhej diya kya?",
                "kya tere keyboard pe ice age aa gaya?",
                "tere bina chat desert ban gaya hai",
                "server mein aaj silence ka reason tu hai",
                "jaise train mein sab aaye, conductor tu reh gaya"
            ],
            ActivityLevel.ACTIVE: [
                "tera toh scene hi off hai aaj",
                "server mein aake statue kyun ban gaye?",
                "tumhare bina server ka vibe zero hai bro",
                "teri typing dekhne ko aankhein taras gayi",
                "kya kar rahe ho bhai, meditation?",
                "lagta hai tu sirf online aata hai ghost banne",
                "teri online presence aur network kabhi milte nahi",
                "server ki light tu hi toh tha, fuse ho gaya kya?"
            ],
            ActivityLevel.MODERATE: [
                "ghost ban gaye ho kya? kahaan ho!",
                "kya baat hai, discord ne tujhe block maar diya?",
                "server ka missing person award tumhe hi milega",
                "chat mein aake bas ek 'hi' bolde bhai",
                "tu toh lagta hai spy ban gaya hai",
                "server mein tu hai ya bas illusion hai?",
                "tu aata hai sirf presence dikhane jaise politician"
            ],
            ActivityLevel.INACTIVE: [
                "lagta hai aaj ka mute permanent ho gaya",
                "sharam karo kabhi online bhi hua karo",
                "beta online aake bhi kuch bolo toh sahi",
                "teri profile pe cobweb lag gaye",
                "kya tujhe login karna allowed nahi ghar pe?",
                "isse toh better AI bhi reply kar dete",
                "tera mic aur keyboard dono retirement pe gaye kya?"
            ],
            ActivityLevel.DEAD: [
                "server CPR ki zarurat hai, tu toh coma mein hai",
                "tumhare reply ki speed dekh ke snail bhi sharma jaye",
                "archaeology karnii padegi tumhe dhundne ke liye",
                "aakhri baar tujhe kab dekha tha... 1998 mein?",
                "tera ping Mars se aa raha kya?",
                "server tujhse zyada zinda lagta hai",
                "tere status pe likha hona chahiye 'Lost in Time'",
                "kya tere Discord pe museum ban gaya hai?"
            ]
        }

        self.gif_terms = [
            "missing", "where are you", "looking for", "searching", "absent",
            "come back", "hiding", "disappeared", "wake up", "alert",
            "ghost mode", "not seen", "gone", "vanished", "invisible",
            "waiting", "lonely", "offline too long", "nobody home", "hello?",
            "please respond", "dino fossil", "sleeping beauty", "mission lost"
        ]
        
        self.member_activity = {}  # Track member activity
        self.ping_cooldowns = {}   # Individual member cooldowns
        
        self.ping_loop.start()
        self.activity_tracker.start()

    def _load_configs(self) -> Dict[int, ServerConfig]:
        """Load server configurations from file or use defaults"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    configs = {}
                    for k, v in data.items():
                        # Convert string back to enum
                        if 'activity_level' in v and isinstance(v['activity_level'], str):
                            v['activity_level'] = ActivityLevel(v['activity_level'])
                        configs[int(k)] = ServerConfig(**v)
                    return configs
        except Exception as e:
            logger.error(f"Error loading config: {e}")
        
        # Default configurations
        return {
            1273151341241307187: ServerConfig(
                name="Hollow HQ",
                channel_id=1273151342302724113,
                min_interval_hours=4,
                max_interval_hours=8
            ),
            1283419068656910386: ServerConfig(
                name="WeWake", 
                channel_id=1323720347421511831,
                min_interval_hours=6,
                max_interval_hours=12
            )
        }

    def _save_configs(self):
        """Save server configurations to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump({str(k): v.to_dict() for k, v in self.server_configs.items()}, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    def _get_activity_level(self, guild_id: int) -> ActivityLevel:
        """Determine server activity level based on recent messages"""
        if guild_id not in self.member_activity:
            return ActivityLevel.MODERATE
        
        now = datetime.datetime.utcnow().timestamp()
        recent_activity = sum(1 for timestamp in self.member_activity[guild_id].values() 
                             if now - timestamp < 3600)  # Last hour
        
        if recent_activity >= 20:
            return ActivityLevel.VERY_ACTIVE
        elif recent_activity >= 10:
            return ActivityLevel.ACTIVE
        elif recent_activity >= 5:
            return ActivityLevel.MODERATE
        elif recent_activity >= 1:
            return ActivityLevel.INACTIVE
        else:
            return ActivityLevel.DEAD

    def _select_random_member(self, guild: discord.Guild) -> Optional[discord.Member]:
        """Smart member selection based on activity and cooldowns"""
        try:
            eligible_members = []
            now = datetime.datetime.utcnow().timestamp()
            
            for member in guild.members:
                if member.bot:
                    continue
                
                # Check cooldown (minimum 2 hours between pings for same member)
                member_key = f"{guild.id}_{member.id}"
                if member_key in self.ping_cooldowns:
                    if now - self.ping_cooldowns[member_key] < 7200:  # 2 hours
                        continue
                
                # Prefer less active members
                if guild.id in self.member_activity:
                    last_activity = self.member_activity[guild.id].get(member.id, 0)
                    # Higher weight for members who haven't been active recently
                    weight = max(1, int((now - last_activity) / 3600))  # Weight by hours since last activity
                    eligible_members.extend([member] * min(weight, 10))  # Cap weight at 10
                else:
                    eligible_members.append(member)
            
            if not eligible_members:
                # Fallback to any non-bot member if all are on cooldown
                eligible_members = [m for m in guild.members if not m.bot]
            
            return random.choice(eligible_members) if eligible_members else None
            
        except Exception as e:
            logger.error(f"Error selecting member: {e}")
            return None

    async def _get_gif(self, search_term: str) -> Optional[str]:
        """Fetch GIF from Tenor or Giphy with better error handling"""
        try:
            # Try Tenor first
            if self.tenor_api_key:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    url = "https://tenor.googleapis.com/v2/search"
                    params = {"q": search_term, "key": self.tenor_api_key, "limit": 20, "contentfilter": "medium"}
                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("results"):
                                return random.choice(data["results"])["media_formats"]["gif"]["url"]

            # Fallback to Giphy
            if self.giphy_api_key:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    url = "https://api.giphy.com/v1/gifs/search"
                    params = {"api_key": self.giphy_api_key, "q": search_term, "limit": 20, "rating": "pg"}
                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("data"):
                                return random.choice(data["data"])["images"]["original"]["url"]
        
        except Exception as e:
            logger.error(f"GIF fetch error: {e}")
        
        # Fallback GIF
        return "https://media.tenor.com/1kGLOq1f39UAAAAd/hello-is-anybody-there.gif"

    @tasks.loop(minutes=5)
    async def ping_loop(self):
        """Main ping loop with smart timing"""
        now = datetime.datetime.utcnow()
        
        for guild in self.bot.guilds:
            try:
                config = self.server_configs.get(guild.id)
                if not config or not config.enabled:
                    continue

                # Check if it's time to ping
                if config.next_ping and now.timestamp() < config.next_ping:
                    continue

                channel = guild.get_channel(config.channel_id)
                if not channel or not channel.permissions_for(guild.me).send_messages:
                    logger.warning(f"Cannot send messages in {guild.name}")
                    continue

                member = self._select_random_member(guild)
                if not member:
                    continue

                # Update activity level
                activity_level = self._get_activity_level(guild.id)
                config.activity_level = activity_level
                
                # Select appropriate message
                messages = self.message_templates.get(activity_level, self.message_templates[ActivityLevel.MODERATE])
                message = random.choice(messages)
                
                # Get GIF
                gif_url = await self._get_gif(random.choice(self.gif_terms))
                
                # Send ping
                content = f"**{member.mention} {message}**\n{gif_url}"
                await channel.send(content=content)
                
                # Update tracking
                config.ping_count += 1
                config.last_activity = now.timestamp()
                self.ping_cooldowns[f"{guild.id}_{member.id}"] = now.timestamp()
                
                # Calculate next ping time (random interval based on activity)
                base_interval = random.randint(config.min_interval_hours, config.max_interval_hours)
                activity_multiplier = {
                    ActivityLevel.VERY_ACTIVE: 1.5,
                    ActivityLevel.ACTIVE: 1.2,
                    ActivityLevel.MODERATE: 1.0,
                    ActivityLevel.INACTIVE: 0.8,
                    ActivityLevel.DEAD: 0.6
                }.get(activity_level, 1.0)
                
                next_interval = base_interval * activity_multiplier
                config.next_ping = (now + datetime.timedelta(hours=next_interval)).timestamp()
                
                logger.info(f"Pinged {member.display_name} in {guild.name} (Activity: {activity_level.value})")
                
            except Exception as e:
                logger.error(f"Ping loop error for {guild.name}: {e}")
        
        self._save_configs()

    @tasks.loop(minutes=30)
    async def activity_tracker(self):
        """Track server activity levels"""
        try:
            for guild in self.bot.guilds:
                if guild.id not in self.member_activity:
                    self.member_activity[guild.id] = {}
                
                # Clean old activity data (older than 24 hours)
                cutoff = datetime.datetime.utcnow().timestamp() - 86400
                self.member_activity[guild.id] = {
                    k: v for k, v in self.member_activity[guild.id].items() 
                    if v > cutoff
                }
        except Exception as e:
            logger.error(f"Activity tracker error: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Track member activity"""
        if message.author.bot or not message.guild:
            return
        
        try:
            guild_id = message.guild.id
            if guild_id not in self.member_activity:
                self.member_activity[guild_id] = {}
            
            self.member_activity[guild_id][message.author.id] = datetime.datetime.utcnow().timestamp()
        except Exception as e:
            logger.error(f"Activity tracking error: {e}")

    @ping_loop.before_loop
    async def before_ping_loop(self):
        await self.bot.wait_until_ready()
        logger.info("Smart Pinger is ready!")

    def cog_unload(self):
        self.ping_loop.cancel()
        self.activity_tracker.cancel()
        self._save_configs()

    # Slash Commands
    @app_commands.command(name="ping-test", description="Test ping message")
    async def ping_test(self, interaction: discord.Interaction):
        """Test the ping functionality"""
        try:
            if not interaction.user.guild_permissions.manage_guild:
                await interaction.response.send_message("❌ Need 'Manage Server' permission", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)
            
            activity_level = self._get_activity_level(interaction.guild.id)
            messages = self.message_templates.get(activity_level, self.message_templates[ActivityLevel.MODERATE])
            message = random.choice(messages)
            gif_url = await self._get_gif(random.choice(self.gif_terms))
            
            response = f"**{interaction.user.mention} {message}**\n{gif_url}\n\n*Activity Level: {activity_level.value}*"
            await interaction.followup.send(content=response, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Ping test error: {e}")
            await interaction.followup.send("❌ Error occurred during test", ephemeral=True)

    @app_commands.command(name="ping-config", description="Configure ping settings")
    @app_commands.describe(
        enabled="Enable/disable pinging",
        min_hours="Minimum hours between pings",
        max_hours="Maximum hours between pings"
    )
    async def ping_config(self, interaction: discord.Interaction, enabled: bool = None, 
                         min_hours: int = None, max_hours: int = None):
        """Configure ping settings for the server"""
        try:
            if not interaction.user.guild_permissions.manage_guild:
                await interaction.response.send_message("❌ Need 'Manage Server' permission", ephemeral=True)
                return

            guild_id = interaction.guild.id
            config = self.server_configs.get(guild_id)
            
            if not config:
                await interaction.response.send_message("❌ Server not configured for pinging", ephemeral=True)
                return

            changes = []
            
            if enabled is not None:
                config.enabled = enabled
                changes.append(f"Enabled: {enabled}")
            
            if min_hours is not None:
                if min_hours < 1 or min_hours > 24:
                    await interaction.response.send_message("❌ Min hours must be between 1-24", ephemeral=True)
                    return
                config.min_interval_hours = min_hours
                changes.append(f"Min interval: {min_hours}h")
            
            if max_hours is not None:
                if max_hours < 1 or max_hours > 48:
                    await interaction.response.send_message("❌ Max hours must be between 1-48", ephemeral=True)
                    return
                config.max_interval_hours = max_hours
                changes.append(f"Max interval: {max_hours}h")
            
            if config.min_interval_hours > config.max_interval_hours:
                await interaction.response.send_message("❌ Min hours cannot be greater than max hours", ephemeral=True)
                return

            self._save_configs()
            
            if changes:
                await interaction.response.send_message(f"✅ Updated: {', '.join(changes)}", ephemeral=True)
            else:
                await interaction.response.send_message("ℹ️ No changes made", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Config error: {e}")
            await interaction.response.send_message("❌ Error updating config", ephemeral=True)

    @app_commands.command(name="ping-stats", description="Show ping statistics")
    async def ping_stats(self, interaction: discord.Interaction):
        """Show ping statistics for the server"""
        try:
            guild_id = interaction.guild.id
            config = self.server_configs.get(guild_id)
            
            if not config:
                await interaction.response.send_message("❌ Server not configured for pinging", ephemeral=True)
                return

            activity_level = self._get_activity_level(guild_id)
            next_ping = "Not scheduled"
            
            if config.next_ping:
                next_ping_dt = datetime.datetime.fromtimestamp(config.next_ping)
                next_ping = f"<t:{int(config.next_ping)}:R>"
            
            active_members = len(self.member_activity.get(guild_id, {}))
            
            stats = (
                f"**Ping Statistics for {interaction.guild.name}**\n"
                f"Status: {'✅ Enabled' if config.enabled else '❌ Disabled'}\n"
                f"Total Pings: {config.ping_count}\n"
                f"Activity Level: {activity_level.value.title()}\n"
                f"Active Members: {active_members}\n"
                f"Interval: {config.min_interval_hours}-{config.max_interval_hours} hours\n"
                f"Next Ping: {next_ping}"
            )
            
            await interaction.response.send_message(stats, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Stats error: {e}")
            await interaction.response.send_message("❌ Error fetching stats", ephemeral=True)

    @app_commands.command(name="ping-now", description="Trigger immediate ping")
    async def ping_now(self, interaction: discord.Interaction):
        """Manually trigger a ping"""
        try:
            if not interaction.user.guild_permissions.manage_guild:
                await interaction.response.send_message("❌ Need 'Manage Server' permission", ephemeral=True)
                return

            guild_id = interaction.guild.id
            config = self.server_configs.get(guild_id)
            
            if not config or not config.enabled:
                await interaction.response.send_message("❌ Pinging not enabled for this server", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)
            
            member = self._select_random_member(interaction.guild)
            if not member:
                await interaction.followup.send("❌ No eligible members to ping", ephemeral=True)
                return

            channel = interaction.guild.get_channel(config.channel_id)
            if not channel:
                await interaction.followup.send("❌ Ping channel not found", ephemeral=True)
                return

            activity_level = self._get_activity_level(guild_id)
            messages = self.message_templates.get(activity_level, self.message_templates[ActivityLevel.MODERATE])
            message = random.choice(messages)
            gif_url = await self._get_gif(random.choice(self.gif_terms))
            
            content = f"**{member.mention} {message}**\n{gif_url}"
            await channel.send(content=content)
            
            config.ping_count += 1
            self.ping_cooldowns[f"{guild_id}_{member.id}"] = datetime.datetime.utcnow().timestamp()
            self._save_configs()
            
            await interaction.followup.send(f"✅ Pinged {member.display_name}", ephemeral=True)
            
        except Exception as e:
            logger.error(f"Manual ping error: {e}")
            await interaction.followup.send("❌ Error sending ping", ephemeral=True)

async def setup(bot):
    if not bot.get_cog("SmartPinger"):
        await bot.add_cog(SmartPinger(bot))
        logger.info("Smart Pinger loaded successfully!")

async def teardown(bot):
    if bot.get_cog("SmartPinger"):
        await bot.remove_cog("SmartPinger")
        logger.info("Smart Pinger unloaded!")
