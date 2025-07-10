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
    """Simple AI pinger with predefined server configs"""
    
    def __init__(self, bot):
        self.bot = bot
        self.tenor_api_key = os.getenv('TENOR_API_KEY')
        self.giphy_api_key = os.getenv('GIPHY_API_KEY')
        
        # Predefined server configurations with guild IDs
        self.predefined_servers = {
            # Hollow HQ Server
            1273151341241307187: {
                "name": "Hollow HQ",
                "channel_id": 1273151342302724113,
                "enabled": True,
                "interval_hours": 6,
                "next_ping": None
            },
            # WeWake Server
            1283419068656910386: {
                "name": "WeWake",
                "channel_id": 1323720347421511831,
                "enabled": True,
                "interval_hours": 6,
                "next_ping": None
            }
        }
        
        # Message templates - add your own here
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
    
    def get_server_config(self, guild_id: int) -> Optional[Dict]:
        """Get predefined server config by guild ID"""
        return self.predefined_servers.get(guild_id)
    
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
    
    @tasks.loop(minutes=1)  # Changed to 1 minute for instant response
    async def ping_loop(self):
        """Main ping loop - instant pings"""
        now = datetime.datetime.utcnow()
        
        for guild in self.bot.guilds:
            try:
                # Get server config by guild ID
                config = self.get_server_config(guild.id)
                
                if not config or not config["enabled"]:
                    continue
                
                if config["next_ping"] and now.timestamp() < config["next_ping"]:
                    continue
                
                # Get the specific channel
                channel = guild.get_channel(config["channel_id"])
                if not channel or not channel.permissions_for(guild.me).send_messages:
                    continue
                
                # Get random member
                members = [m for m in guild.members if not m.bot]
                if not members:
                    continue
                
                member = random.choice(members)
                
                # Get random message and GIF
                message = random.choice(self.message_templates)
                gif_url = await self.get_gif(random.choice(self.gif_terms))
                
                # Send simple bold message with GIF (no embed)
                try:
                    content = f"**{member.mention} {message}**"
                    
                    if gif_url:
                        content += f"\n{gif_url}"
                    
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
        
        # Get server config
        config = self.get_server_config(interaction.guild.id)
        
        if not config:
            await interaction.followup.send("❌ Server not configured", ephemeral=True)
            return
        
        server_name = config["name"]
        
        # Create embed for status
        embed = discord.Embed(
            title="🤖 Pinger Status",
            color=0x00ff00 if config["enabled"] else 0xff0000
        )
        
        embed.add_field(
            name="Server",
            value=server_name,
            inline=True
        )
        
        embed.add_field(
            name="Status",
            value="🟢 ENABLED" if config["enabled"] else "🔴 DISABLED",
            inline=True
        )
        
        embed.add_field(
            name="Interval",
            value=f"{config['interval_hours']} hours",
            inline=True
        )
        
        embed.add_field(
            name="Channel",
            value=f"<#{config['channel_id']}>",
            inline=True
        )
        
        if config["next_ping"]:
            embed.add_field(
                name="Next Ping",
                value=f"<t:{int(config['next_ping'])}:R>",
                inline=True
            )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="ping-toggle", description="Toggle pinger on/off")
    async def ping_toggle(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await self.safe_respond(interaction, "❌ Need 'Manage Server' permission", ephemeral=True)
            return
        
        # Get server config
        config = self.get_server_config(interaction.guild.id)
        
        if not config:
            await self.safe_respond(interaction, "❌ Server not configured", ephemeral=True)
            return
        
        server_name = config["name"]
        
        config["enabled"] = not config["enabled"]
        
        if config["enabled"]:
            config["next_ping"] = (datetime.datetime.utcnow() + 
                                 datetime.timedelta(hours=config["interval_hours"])).timestamp()
        
        # Create embed response
        embed = discord.Embed(
            title="🤖 Pinger Toggle",
            color=0x00ff00 if config["enabled"] else 0xff0000
        )
        
        embed.add_field(
            name="Server",
            value=server_name,
            inline=True
        )
        
        embed.add_field(
            name="Status",
            value="🟢 ENABLED" if config["enabled"] else "🔴 DISABLED",
            inline=True
        )
        
        await self.safe_respond(interaction, embed=embed)
    
    @app_commands.command(name="ping-now", description="Force ping now")
    async def ping_now(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await self.safe_respond(interaction, "❌ Need 'Manage Server' permission", ephemeral=True)
            return
        
        # Get server config
        config = self.get_server_config(interaction.guild.id)
        
        if not config:
            await self.safe_respond(interaction, "❌ Server not configured", ephemeral=True)
            return
        
        server_name = config["name"]
        
        if not config["enabled"]:
            await self.safe_respond(interaction, "❌ Pinger not enabled for this server!", ephemeral=True)
            return
        
        config["next_ping"] = datetime.datetime.utcnow().timestamp()
        
        # Create embed response
        embed = discord.Embed(
            title="⏰ Ping Scheduled",
            description="Ping will be sent in the next loop cycle!",
            color=0x00ff00
        )
        
        embed.add_field(
            name="Server",
            value=server_name,
            inline=True
        )
        
        embed.add_field(
            name="Channel",
            value=f"<#{config['channel_id']}>",
            inline=True
        )
        
        await self.safe_respond(interaction, embed=embed)
    
    @app_commands.command(name="ping-interval", description="Set ping interval (1-24 hours)")
    async def ping_interval(self, interaction: discord.Interaction, hours: int):
        if not interaction.user.guild_permissions.manage_guild:
            await self.safe_respond(interaction, "❌ Need 'Manage Server' permission", ephemeral=True)
            return
        
        if not 1 <= hours <= 24:
            await self.safe_respond(interaction, "❌ Hours must be 1-24", ephemeral=True)
            return
        
        # Get server config
        config = self.get_server_config(interaction.guild.id)
        
        if not config:
            await self.safe_respond(interaction, "❌ Server not configured", ephemeral=True)
            return
        
        server_name = config["name"]
        
        config["interval_hours"] = hours
        
        # Create embed response
        embed = discord.Embed(
            title="⏱️ Interval Updated",
            color=0x00ff00
        )
        
        embed.add_field(
            name="Server",
            value=server_name,
            inline=True
        )
        
        embed.add_field(
            name="New Interval",
            value=f"{hours} hours",
            inline=True
        )
        
        await self.safe_respond(interaction, embed=embed)
    
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
        
        # Create embed for test preview
        embed = discord.Embed(
            title="🧪 Test Ping Preview",
            description="This is how the ping will look:",
            color=0x0099ff
        )
        
        test_content = f"**{interaction.user.mention} {message}**"
        
        embed.add_field(
            name="Message",
            value=test_content,
            inline=False
        )
        
        if gif_url:
            embed.add_field(
                name="GIF",
                value=f"[Click to view GIF]({gif_url})",
                inline=False
            )
            embed.set_image(url=gif_url)
        
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    if not bot.get_cog("AIPinger"):
        await bot.add_cog(AIPinger(bot))
        print("✅ Simple Pinger loaded!")

async def teardown(bot):
    if bot.get_cog("AIPinger"):
        await bot.remove_cog("AIPinger")
        print("❌ Simple Pinger unloaded!")
