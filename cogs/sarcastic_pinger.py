import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import asyncio
import datetime
import os
import aiohttp
from typing import Dict, Optional

class AIPinger(commands.Cog):
    """Simple AI pinger with just message and GIF"""
    
    def __init__(self, bot):
        self.bot = bot
        self.tenor_api_key = os.getenv('TENOR_API_KEY')
        self.giphy_api_key = os.getenv('GIPHY_API_KEY')
        
        self.server_configs = {}
        
        # Simple Hindi message templates
        self.message_templates = [
    "lagta hai aaj aap nhi dikh rhe",
    "kya baat hai, aaj gayab ho gaye",
    "areh kahan chup gaye aap",
    "lagta hai busy ho aaj",
    "kya haal hai, dikhte nhi aaj",
    "missing in action ho aaj",
    "koi awaz nhi aarhi aapki",
    "silent mode mein ho kya",
    "online aake bhi offline jaise ho",
    "aaj tumhari yaad aa rahi hai",
    "tum ho kaha? server udaas hai",
    "tumhare bina chat adhoori lagti hai",
    "koi to bulao us bhatke hue ko",
    "aaj koi vibes nhi aa rahi",
    "bot bhi soch raha kaha ho aap",
    "tumhare bina sab suna suna lagta hai",
    "dil dhundta hai active members",
    "ghost mode mein mat raho re",
    "tumhare bina notification bhi boring hai",
    "aaj server mein kuch kami si lag rahi"
]

        
        self.gif_terms = [
    "missing", "where are you", "looking for", "searching", "absent",
    "come back", "hiding", "disappeared", "invisible", "ghost",
    "peekaboo", "lost friend", "sad bot", "pinging you", "lonely bot",
    "miss you", "waiting", "anyone there", "wake up", "alert alert"
]

        
        self.ping_loop.start()
    
    def cog_unload(self):
        self.ping_loop.cancel()
    
    def get_config(self, guild_id: int) -> Dict:
        if guild_id not in self.server_configs:
            self.server_configs[guild_id] = {
                "enabled": False, 
                "channels": [], 
                "next_ping": None,
                "interval_hours": 6
            }
        return self.server_configs[guild_id]
    
    async def safe_respond(self, interaction: discord.Interaction, content: str = None, 
                          embed: discord.Embed = None, ephemeral: bool = False):
        try:
            if interaction.response.is_done():
                await interaction.followup.send(content=content, embed=embed, ephemeral=ephemeral)
            else:
                await interaction.response.send_message(content=content, embed=embed, ephemeral=ephemeral)
        except Exception as e:
            print(f"Response error: {e}")
    
    async def get_gif(self, search_term: str) -> Optional[str]:
        """Get random GIF from available APIs"""
        try:
            if self.tenor_api_key and random.choice([True, False]):
                async with aiohttp.ClientSession() as session:
                    url = "https://tenor.googleapis.com/v2/search"
                    params = {"q": search_term, "key": self.tenor_api_key, "limit": 20}
                    async with session.get(url, params=params, timeout=3) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("results"):
                                return random.choice(data["results"])["media_formats"]["gif"]["url"]
            
            if self.giphy_api_key:
                async with aiohttp.ClientSession() as session:
                    url = "https://api.giphy.com/v1/gifs/search"
                    params = {"api_key": self.giphy_api_key, "q": search_term, "limit": 20}
                    async with session.get(url, params=params, timeout=3) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("data"):
                                return random.choice(data["data"])["images"]["original"]["url"]
        except Exception as e:
            print(f"GIF error: {e}")
        return None
    
    @tasks.loop(minutes=10)
    async def ping_loop(self):
        """Main ping loop - simplified"""
        now = datetime.datetime.utcnow()
        
        for guild in self.bot.guilds:
            try:
                config = self.get_config(guild.id)
                
                if (not config["enabled"] or not config["channels"] or 
                    config["next_ping"] and now.timestamp() < config["next_ping"]):
                    continue
                
                # Get valid channel and member
                channels = [guild.get_channel(ch) for ch in config["channels"]]
                valid_channels = [ch for ch in channels if ch and ch.permissions_for(guild.me).send_messages]
                
                if not valid_channels:
                    continue
                
                members = [m for m in guild.members if not m.bot]
                if not members:
                    continue
                
                channel = random.choice(valid_channels)
                member = random.choice(members)
                
                # Get random message and GIF
                message = random.choice(self.message_templates)
                gif_url = await self.get_gif(random.choice(self.gif_terms))
                
                # Send simple message with GIF
                try:
                    content = f"{member.mention} {message}"
                    
                    if gif_url:
                        # Send message with GIF URL
                        await channel.send(content=content + f"\n{gif_url}")
                    else:
                        # Send just the message
                        await channel.send(content=content)
                    
                    print(f"✅ Pinged {member.display_name} in {guild.name}")
                except Exception as e:
                    print(f"❌ Send error in {guild.name}: {e}")
                
                config["next_ping"] = (now + datetime.timedelta(hours=config["interval_hours"])).timestamp()
                
            except Exception as e:
                print(f"Loop error for {guild.name}: {e}")
    
    @ping_loop.before_loop
    async def before_ping_loop(self):
        await self.bot.wait_until_ready()
        print("🤖 Simple Pinger is ready!")
    
    @app_commands.command(name="ping", description="Pinger status")
    async def ping_status(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.followup.send("❌ Need 'Manage Server' permission", ephemeral=True)
            return
            
        config = self.get_config(interaction.guild.id)
        
        status = "🟢 ON" if config["enabled"] else "🔴 OFF"
        channels = len(config["channels"])
        interval = config["interval_hours"]
        
        embed = discord.Embed(title="ping dalne wala 🤡", color=0x00FF41)
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Channels", value=f"{channels} channels", inline=True)
        embed.add_field(name="Interval", value=f"{interval}h", inline=True)
        
        if config["next_ping"]:
            embed.add_field(name="Next Ping", value=f"<t:{int(config['next_ping'])}:R>", inline=True)
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="ping-toggle", description="Toggle pinger on/off")
    async def ping_toggle(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await self.safe_respond(interaction, "❌ Need 'Manage Server' permission", ephemeral=True)
            return
            
        config = self.get_config(interaction.guild.id)
        config["enabled"] = not config["enabled"]
        
        if config["enabled"] and not config["channels"]:
            await self.safe_respond(interaction, "❌ Add channels first with `/ping-channel`", ephemeral=True)
            config["enabled"] = False
            return
        
        if config["enabled"]:
            config["next_ping"] = (datetime.datetime.utcnow() + 
                                 datetime.timedelta(hours=config["interval_hours"])).timestamp()
        
        status = "🟢 ENABLED" if config["enabled"] else "🔴 DISABLED"
        await self.safe_respond(interaction, f"Pinger {status}")
    
    @app_commands.command(name="ping-channel", description="Add/remove ping channel")
    async def ping_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.user.guild_permissions.manage_guild:
            await self.safe_respond(interaction, "❌ Need 'Manage Server' permission", ephemeral=True)
            return
            
        config = self.get_config(interaction.guild.id)
        
        if channel.id in config["channels"]:
            config["channels"].remove(channel.id)
            await self.safe_respond(interaction, f"➖ Removed {channel.mention}")
        else:
            config["channels"].append(channel.id)
            await self.safe_respond(interaction, f"➕ Added {channel.mention}")
    
    @app_commands.command(name="ping-now", description="Force ping now")
    async def ping_now(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await self.safe_respond(interaction, "❌ Need 'Manage Server' permission", ephemeral=True)
            return
            
        config = self.get_config(interaction.guild.id)
        
        if not config["enabled"] or not config["channels"]:
            await self.safe_respond(interaction, "❌ Pinger not enabled or no channels!", ephemeral=True)
            return
        
        config["next_ping"] = datetime.datetime.utcnow().timestamp()
        await self.safe_respond(interaction, "⏰ Ping scheduled for next loop!")
    
    @app_commands.command(name="ping-interval", description="Set ping interval (1-24 hours)")
    async def ping_interval(self, interaction: discord.Interaction, hours: int):
        if not interaction.user.guild_permissions.manage_guild:
            await self.safe_respond(interaction, "❌ Need 'Manage Server' permission", ephemeral=True)
            return
            
        if not 1 <= hours <= 24:
            await self.safe_respond(interaction, "❌ Hours must be 1-24", ephemeral=True)
            return
        
        config = self.get_config(interaction.guild.id)
        config["interval_hours"] = hours
        
        await self.safe_respond(interaction, f"⏱️ Interval set to {hours}h")
    
    @app_commands.command(name="ping-test", description="Test ping message")
    async def ping_test(self, interaction: discord.Interaction):
        """Test ping message"""
        if not interaction.user.guild_permissions.manage_guild:
            await self.safe_respond(interaction, "❌ Need 'Manage Server' permission", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Get test message and GIF
        message = random.choice(self.message_templates)
        gif_url = await self.get_gif(random.choice(self.gif_terms))
        
        # Show what the ping will look like
        test_content = f"{interaction.user.mention} {message}"
        
        if gif_url:
            test_content += f"\n{gif_url}"
        
        await interaction.followup.send(
            content=f"**Test Ping Preview:**\n{test_content}", 
            ephemeral=True
        )

async def setup(bot):
    if not bot.get_cog("AIPinger"):
        await bot.add_cog(AIPinger(bot))
        print("✅ Simple Pinger loaded!")

async def teardown(bot):
    if bot.get_cog("AIPinger"):
        await bot.remove_cog("AIPinger")
        print("❌ Simple Pinger unloaded!")
