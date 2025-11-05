import discord, asyncio, time, random
from discord.ext import commands, tasks
from typing import Optional, Dict, List
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('GFNMonitor')

# -------------------------
# Customization
# -------------------------
REGION_DISPLAY = {
    "gfn.Georgia": "Georgia 🇺🇸",
    "gfn.Virginia": "Virginia 🇺🇸",
    "gfn.Germany": "Germany 🇩🇪",
    "gfn.France": "France 🇫🇷",
    "gfn.Netherlands North": "Netherlands 🇳🇱",
    "gfn.Japan East": "Japan 🇯🇵",
    "gfn.Canada East": "Canada 🇨🇦",
    "alliance.KR-Seoul": "Korea 🇰🇷",
    "alliance.TH-Bangkok": "Thailand 🇹🇭",
    "alliance.MY-KL": "Malaysia 🇲🇾",
}

# Mock data for demonstration
MOCK = {
    "US": [{"name": "gfn.Georgia", "queue": 26}, {"name": "gfn.Virginia", "queue": 35}],
    "EU": [{"name": "gfn.Germany", "queue": 312}, {"name": "gfn.France", "queue": 411}],
    "JP": [{"name": "gfn.Japan East", "queue": 129}],
    "CA": [{"name": "gfn.Canada East", "queue": 22}],
    "KR": [{"name": "alliance.KR-Seoul", "queue": 398}],
    "TH": [{"name": "alliance.TH-Bangkok", "queue": 145}],
    "MY": [{"name": "alliance.MY-KL", "queue": 502}],
}

# Cached data fallback
CACHED_DATA = None

# Mood ladder
def mood_for(q):
    if q <= 30:   return ("🟢", "BREEZE", 0x00FF7F)
    if q <= 70:   return ("🟡", "MEH", 0xFFD700)
    if q <= 150:  return ("🟠", "STRUGGLE", 0xFFA500)
    if q <= 300:  return ("🔴", "PAIN", 0xFF4500)
    if q <= 500:  return ("🟣", "DEATH", 0x8A2BE2)
    return ("⚫", "VOID", 0x000000)

BANNERS = [
    "System is smooth. Miracles do exist.",
    "Slight congestion detected. Proceed with snacks.",
    "Severe waiting epidemic spreading fast.",
    "Systemic agony. Bring caffeine.",
    "Server meltdown imminent.",
    "We have transcended pain. Only queue remains."
]

FOOTER_QUOTES = [
    "Queue time is temporary. GPU pain is eternal.",
    "Patience: still not a currency.",
    "If you stare into the queue, the queue stares back.",
    "One queue to rule them all.",
    "Somewhere, someone just logged in before you."
]


class GFNMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_id = None
        self.message = None
        self.interval = 120  # seconds
        self.task = None
        self.is_running = False
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        self.last_successful_fetch = None
        self.using_fallback = False

    # -----------------------------
    # Command to start live monitor
    # -----------------------------
    @commands.hybrid_command(name="gfnlive", description="Start live GeForce NOW queue monitor.")
    async def gfn_live(self, ctx: commands.Context):
        """Start the live monitor with error handling"""
        try:
            # Check if already running
            if self.is_running:
                await ctx.reply("⚠️ Monitor is already running! Use `/gfnstop` to stop it first.", ephemeral=True)
                return

            # Validate channel permissions
            if not ctx.channel.permissions_for(ctx.guild.me).send_messages:
                await ctx.reply("❌ I don't have permission to send messages in this channel!", ephemeral=True)
                return

            if not ctx.channel.permissions_for(ctx.guild.me).embed_links:
                await ctx.reply("❌ I need 'Embed Links' permission to display the monitor!", ephemeral=True)
                return

            self.channel_id = ctx.channel.id
            self.is_running = True
            self.consecutive_errors = 0
            
            await ctx.reply("✅ Starting live GeForce NOW queue monitor ⏱️\n*Updates every 2 minutes*")
            
            # Start the background task
            self.task = self.bot.loop.create_task(self.live_loop())
            
        except Exception as e:
            logger.error(f"Error starting monitor: {e}")
            await ctx.reply(f"❌ Failed to start monitor: {str(e)}", ephemeral=True)
            self.is_running = False

    # -----------------------------
    # Command to stop live monitor
    # -----------------------------
    @commands.hybrid_command(name="gfnstop", description="Stop the live GeForce NOW queue monitor.")
    async def gfn_stop(self, ctx: commands.Context):
        """Stop the live monitor"""
        try:
            if not self.is_running:
                await ctx.reply("⚠️ Monitor is not running!", ephemeral=True)
                return

            self.is_running = False
            
            if self.task:
                self.task.cancel()
                self.task = None

            await ctx.reply("✅ Monitor stopped successfully!")
            
        except Exception as e:
            logger.error(f"Error stopping monitor: {e}")
            await ctx.reply(f"❌ Failed to stop monitor: {str(e)}", ephemeral=True)

    # -----------------------------
    # Command to check monitor status
    # -----------------------------
    @commands.hybrid_command(name="gfnstatus", description="Check monitor status and health.")
    async def gfn_status(self, ctx: commands.Context):
        """Display monitor status"""
        try:
            if not self.is_running:
                await ctx.reply("📊 **Monitor Status:** Not running", ephemeral=True)
                return

            status_lines = [
                "📊 **Monitor Status:** Running ✅",
                f"📍 **Channel:** <#{self.channel_id}>",
                f"⏱️ **Update Interval:** {self.interval}s",
                f"⚠️ **Consecutive Errors:** {self.consecutive_errors}/{self.max_consecutive_errors}",
            ]

            if self.last_successful_fetch:
                status_lines.append(f"✅ **Last Successful Fetch:** <t:{self.last_successful_fetch}:R>")
            
            if self.using_fallback:
                status_lines.append("⚠️ **Using Fallback Data** (API unavailable)")

            await ctx.reply("\n".join(status_lines), ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error checking status: {e}")
            await ctx.reply(f"❌ Failed to check status: {str(e)}", ephemeral=True)

    # -----------------------------
    # Background update loop
    # -----------------------------
    async def live_loop(self):
        """Main update loop with comprehensive error handling"""
        channel = None
        
        try:
            channel = self.bot.get_channel(self.channel_id)
            if not channel:
                logger.error(f"Channel {self.channel_id} not found")
                self.is_running = False
                return

            # Send initial message
            data = await self.fetch_data_with_fallback()
            embed = self.build_embed(data, is_initial=True)
            
            try:
                self.message = await channel.send(embed=embed)
            except discord.Forbidden:
                logger.error("Missing permissions to send message")
                self.is_running = False
                return
            except discord.HTTPException as e:
                logger.error(f"HTTP error sending initial message: {e}")
                self.is_running = False
                return

            # Main update loop
            while self.is_running:
                try:
                    await asyncio.sleep(self.interval)
                    
                    if not self.is_running:
                        break

                    # Fetch new data
                    data = await self.fetch_data_with_fallback()
                    embed = self.build_embed(data)

                    # Try to edit existing message
                    try:
                        await self.message.edit(embed=embed)
                        
                    except discord.NotFound:
                        # Message was deleted, send new one
                        logger.warning("Message not found, sending new message")
                        try:
                            self.message = await channel.send(embed=embed)
                        except discord.Forbidden:
                            logger.error("Lost permissions to send messages")
                            self.is_running = False
                            break
                            
                    except discord.Forbidden:
                        logger.error("Lost permissions to edit message")
                        self.is_running = False
                        break
                        
                    except discord.HTTPException as e:
                        logger.error(f"HTTP error editing message: {e}")
                        # Continue loop, will retry next interval
                        
                except asyncio.CancelledError:
                    logger.info("Monitor task cancelled")
                    break
                    
                except Exception as e:
                    logger.error(f"Error in update loop: {e}")
                    self.consecutive_errors += 1
                    
                    if self.consecutive_errors >= self.max_consecutive_errors:
                        logger.error("Max consecutive errors reached, stopping monitor")
                        self.is_running = False
                        
                        # Try to notify in channel
                        try:
                            await channel.send("❌ **Monitor stopped due to repeated errors.** Use `/gfnlive` to restart.")
                        except:
                            pass
                        break
                    
                    # Continue with exponential backoff
                    await asyncio.sleep(min(self.interval * 2, 300))

        except asyncio.CancelledError:
            logger.info("Monitor task cancelled during setup")
            
        except Exception as e:
            logger.error(f"Fatal error in live loop: {e}")
            self.is_running = False
            
            # Try to notify
            if channel:
                try:
                    await channel.send(f"❌ **Monitor crashed:** {str(e)}\nUse `/gfnlive` to restart.")
                except:
                    pass
        
        finally:
            self.is_running = False
            logger.info("Monitor loop ended")

    # -----------------------------
    # Fetch data with fallback
    # -----------------------------
    async def fetch_data_with_fallback(self) -> Dict:
        """Fetch data with automatic fallback to cache and mock data"""
        global CACHED_DATA
        
        try:
            data = await self.fetch_data()
            
            # Validate data structure
            if not self.validate_data(data):
                raise ValueError("Invalid data structure received")
            
            # Success - update cache and reset error counter
            CACHED_DATA = data
            self.last_successful_fetch = int(time.time())
            self.consecutive_errors = 0
            self.using_fallback = False
            
            return data
            
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            self.consecutive_errors += 1
            self.using_fallback = True
            
            # Try cached data first
            if CACHED_DATA and self.validate_data(CACHED_DATA):
                logger.info("Using cached data as fallback")
                return CACHED_DATA
            
            # Fall back to mock data
            logger.warning("Using mock data as fallback")
            return MOCK

    # -----------------------------
    # Mock fetch (replace with real API)
    # -----------------------------
    async def fetch_data(self) -> Dict:
        """
        Replace this with your actual API call
        Example:
            async with aiohttp.ClientSession() as session:
                async with session.get('YOUR_API_URL') as response:
                    return await response.json()
        """
        # TODO: Replace with real JSON API call
        await asyncio.sleep(0.1)  # Simulate network delay
        return MOCK

    # -----------------------------
    # Validate data structure
    # -----------------------------
    def validate_data(self, data: any) -> bool:
        """Validate that data has the expected structure"""
        try:
            if not isinstance(data, dict):
                return False
            
            for region, entries in data.items():
                if not isinstance(entries, list):
                    return False
                
                for entry in entries:
                    if not isinstance(entry, dict):
                        return False
                    if 'name' not in entry or 'queue' not in entry:
                        return False
                    if not isinstance(entry['queue'], (int, float)):
                        return False
            
            return True
            
        except Exception:
            return False

    # -----------------------------
    # Build fancy embed
    # -----------------------------
    def build_embed(self, data: Dict, is_initial: bool = False) -> discord.Embed:
        """Build embed with error indicators"""
        now = int(time.time())
        next_update = now + self.interval

        try:
            # Global average mood
            all_q = [e["queue"] for region in data.values() for e in region]
            
            if not all_q:
                # No data available
                return self.build_error_embed("No queue data available")
            
            global_avg = sum(all_q) / len(all_q)
            emoji, mood, color = mood_for(global_avg)
            banner = self.banner_for(global_avg)

            # Build title with status indicator
            title_emoji = random.choice(['🎮', '⚙️', '🔄'])
            if self.using_fallback:
                title_emoji = '⚠️'
            
            description_parts = [
                f"Updated <t:{now}:R> *(auto-refresh every 2 min)*",
                f"*"{banner}"*"
            ]
            
            if self.using_fallback:
                description_parts.insert(1, "⚠️ **Using cached/fallback data** (API unavailable)")
            
            if is_initial:
                description_parts.append("*Monitor started successfully!*")

            embed = discord.Embed(
                title=f"{title_emoji} GeForce NOW — Queue Monitor Live",
                description="\n".join(description_parts),
                color=color
            )

            # Region cards
            for region, entries in data.items():
                if not entries:
                    continue
                    
                avg = sum(e['queue'] for e in entries) / len(entries)
                emo, mood_name, _ = mood_for(avg)
                lines = []
                
                for e in entries:
                    name = REGION_DISPLAY.get(e['name'], e['name'].replace('gfn.', '').replace('alliance.', ''))
                    queue_val = e['queue']
                    lines.append(f"{name}: **{queue_val}**")
                
                value = "\n".join(lines) if lines else "*No data*"
                
                embed.add_field(
                    name=f"{emo} {region} — *{mood_name}* ({int(avg)} avg)",
                    value=value,
                    inline=False
                )

            # Footer with status
            footer_text = f"Next refresh <t:{next_update}:R> • {random.choice(FOOTER_QUOTES)}"
            if self.consecutive_errors > 0:
                footer_text = f"⚠️ Errors: {self.consecutive_errors} • " + footer_text
            
            embed.set_footer(text=footer_text)
            return embed
            
        except Exception as e:
            logger.error(f"Error building embed: {e}")
            return self.build_error_embed(f"Error displaying data: {str(e)}")

    def build_error_embed(self, error_msg: str) -> discord.Embed:
        """Build an error embed as fallback"""
        embed = discord.Embed(
            title="❌ GeForce NOW Monitor - Error",
            description=f"**Error:** {error_msg}\n\nThe monitor will retry automatically.",
            color=0xFF0000
        )
        embed.set_footer(text="Retrying soon...")
        return embed

    def banner_for(self, avg: float) -> str:
        """Get banner text based on average queue"""
        if avg <= 30: return BANNERS[0]
        if avg <= 70: return BANNERS[1]
        if avg <= 150: return BANNERS[2]
        if avg <= 300: return BANNERS[3]
        if avg <= 500: return BANNERS[4]
        return BANNERS[5]

    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        if self.task:
            self.task.cancel()
        self.is_running = False


async def setup(bot):
    await bot.add_cog(GFNMonitor(bot))
