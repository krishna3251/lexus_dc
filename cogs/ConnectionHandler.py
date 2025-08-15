import discord
from discord.ext import commands, tasks
import asyncio
import logging
import random
from datetime import datetime, timedelta
import aiohttp

class ConnectionHandler(commands.Cog):
    """
    A cog to handle Discord API connection issues, rate limiting, and reconnection logic.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger('ConnectionHandler')
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.base_delay = 5  # Base delay in seconds
        self.max_delay = 300  # Max delay in seconds (5 minutes)
        self.last_error_time = None
        self.error_count = 0
        self.connection_monitor.start()
        
        # Setup logging
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.connection_monitor.cancel()
    
    async def exponential_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter"""
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        jitter = random.uniform(0.1, 0.9)
        return delay + jitter
    
    async def handle_rate_limit(self, retry_after: float = None):
        """Handle rate limiting with proper delays"""
        if retry_after:
            delay = retry_after + random.uniform(1, 5)  # Add some jitter
        else:
            delay = await self.exponential_backoff(self.reconnect_attempts)
        
        self.logger.warning(f"Rate limited. Waiting {delay:.2f} seconds before retry...")
        await asyncio.sleep(delay)
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Reset connection stats when bot successfully connects"""
        self.reconnect_attempts = 0
        self.error_count = 0
        self.last_error_time = None
        self.logger.info(f"Bot connected successfully as {self.bot.user}")
    
    @commands.Cog.listener()
    async def on_disconnect(self):
        """Log disconnection events"""
        self.logger.warning("Bot disconnected from Discord")
    
    @commands.Cog.listener()
    async def on_resumed(self):
        """Log when bot resumes connection"""
        self.logger.info("Bot resumed connection to Discord")
    
    @commands.Cog.listener()
    async def on_error(self, event, *args, **kwargs):
        """Handle general bot errors"""
        self.error_count += 1
        self.last_error_time = datetime.utcnow()
        self.logger.error(f"Error in {event}: {args}, {kwargs}")
    
    async def safe_reconnect(self):
        """Safely attempt to reconnect with exponential backoff"""
        while self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                self.logger.info(f"Attempting reconnection #{self.reconnect_attempts + 1}")
                
                if self.bot.is_closed():
                    await self.bot.start(self.bot.http.token)
                else:
                    await self.bot.connect(reconnect=True)
                
                self.logger.info("Reconnection successful")
                self.reconnect_attempts = 0
                return True
                
            except discord.HTTPException as e:
                self.reconnect_attempts += 1
                
                if e.status == 429:  # Rate limited
                    retry_after = e.response.headers.get('Retry-After')
                    if retry_after:
                        await self.handle_rate_limit(float(retry_after))
                    else:
                        await self.handle_rate_limit()
                
                elif e.status in [502, 503, 504]:  # Server errors
                    delay = await self.exponential_backoff(self.reconnect_attempts)
                    self.logger.warning(f"Server error {e.status}. Retrying in {delay:.2f}s")
                    await asyncio.sleep(delay)
                
                else:
                    self.logger.error(f"HTTP Exception during reconnect: {e}")
                    delay = await self.exponential_backoff(self.reconnect_attempts)
                    await asyncio.sleep(delay)
            
            except discord.ConnectionClosed as e:
                self.reconnect_attempts += 1
                self.logger.warning(f"Connection closed: {e}. Attempt {self.reconnect_attempts}")
                delay = await self.exponential_backoff(self.reconnect_attempts)
                await asyncio.sleep(delay)
            
            except Exception as e:
                self.reconnect_attempts += 1
                self.logger.error(f"Unexpected error during reconnect: {e}")
                delay = await self.exponential_backoff(self.reconnect_attempts)
                await asyncio.sleep(delay)
        
        self.logger.critical("Max reconnection attempts reached. Bot may be permanently disconnected.")
        return False
    
    @tasks.loop(seconds=60)
    async def connection_monitor(self):
        """Monitor connection health and attempt reconnection if needed"""
        try:
            if not self.bot.is_ready():
                return
            
            # Check if we have recent errors
            if (self.last_error_time and 
                datetime.utcnow() - self.last_error_time < timedelta(minutes=5) and
                self.error_count > 5):
                
                self.logger.warning("High error rate detected, checking connection...")
                
                # Simple ping test
                try:
                    latency = self.bot.latency
                    if latency > 5.0:  # High latency might indicate connection issues
                        self.logger.warning(f"High latency detected: {latency:.2f}s")
                except:
                    self.logger.warning("Could not measure latency")
        
        except Exception as e:
            self.logger.error(f"Error in connection monitor: {e}")
    
    @connection_monitor.before_loop
    async def before_connection_monitor(self):
        """Wait for bot to be ready before starting monitor"""
        await self.bot.wait_until_ready()
    
    @commands.command(name='connection_status', hidden=True)
    @commands.is_owner()
    async def connection_status(self, ctx):
        """Check bot connection status (Owner only)"""
        embed = discord.Embed(
            title="Connection Status",
            color=discord.Color.green() if self.bot.is_ready() else discord.Color.red()
        )
        
        embed.add_field(
            name="Status", 
            value="🟢 Connected" if self.bot.is_ready() else "🔴 Disconnected", 
            inline=True
        )
        embed.add_field(
            name="Latency", 
            value=f"{self.bot.latency * 1000:.2f}ms", 
            inline=True
        )
        embed.add_field(
            name="Reconnect Attempts", 
            value=str(self.reconnect_attempts), 
            inline=True
        )
        embed.add_field(
            name="Error Count", 
            value=str(self.error_count), 
            inline=True
        )
        embed.add_field(
            name="Last Error", 
            value=self.last_error_time.strftime("%Y-%m-%d %H:%M:%S UTC") if self.last_error_time else "None", 
            inline=True
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='force_reconnect', hidden=True)
    @commands.is_owner()
    async def force_reconnect(self, ctx):
        """Force a reconnection attempt (Owner only)"""
        await ctx.send("🔄 Attempting to reconnect...")
        
        success = await self.safe_reconnect()
        
        if success:
            await ctx.send("✅ Reconnection successful!")
        else:
            await ctx.send("❌ Reconnection failed after maximum attempts.")

async def setup(bot):
    """Setup function to load the cog"""
    await bot.add_cog(ConnectionHandler(bot))
