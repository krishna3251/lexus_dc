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
    """Enhanced AI pinger with engaging messages and GIF support"""
    
    def __init__(self, bot):
        self.bot = bot
        self.nvidia_api_key = os.getenv('NVIDIA_API_KEY')
        self.tenor_api_key = os.getenv('TENOR_API_KEY')
        self.giphy_api_key = os.getenv('GIPHY_API_KEY')
        
        self.server_configs = {}
        
        # Enhanced message templates with more engaging content
        self.message_templates = [
            "Hey {name}! You've entered the chat. Time to flex those skills! 💪",
            "What's up {name}! Ready to show everyone what you're made of? 🔥",
            "Yo {name}! The gang's all here, time to get this party started! 🎉",
            "Hey {name}! Chat's been dead without you - bring the energy! ⚡",
            "Sup {name}! Everyone's waiting for your legendary comeback! 🚀",
            "Oh look, {name} has arrived! Time to spice things up! 🌶️",
            "Hey {name}! Hope you're ready to carry this conversation! 💼",
            "What's good {name}! Chat needs some life - you're our hero! 🦸",
            "Yo {name}! Time to show these rookies how it's done! 🏆",
            "Hey {name}! The squad's incomplete without you! 👥",
            "Wassup {name}! Ready to drop some knowledge bombs? 💣",
            "Hey {name}! Chat's been waiting for the main character! 🎭",
            "Yo {name}! Time to turn this place upside down! 🔄",
            "What's up {name}! Everyone's here for the {name} show! 🎪",
            "Hey {name}! Ready to make some noise? 📢"
        ]
        
        self.gif_terms = [
            "excited", "party", "celebration", "energy", "pumped", "flex",
            "skills", "hero", "champion", "fire", "epic", "legendary",
            "comeback", "spice", "dance", "hype", "ready", "awesome"
        ]
        
        self.ping_loop.start()
    
    def cog_unload(self):
        self.ping_loop.cancel()
    
    def get_config(self, guild_id: int) -> Dict:
        if guild_id not in self.server_configs:
            self.server_configs[guild_id] = {
                "enabled": False, "channels": [], "next_ping": None,
                "interval_hours": 6, "ai_enabled": True, "gif_enabled": True
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
    
    async def generate_message(self, guild_name: str, member_name: str) -> str:
        """Generate engaging message using AI or templates"""
        if not self.nvidia_api_key:
            return random.choice(self.message_templates).format(name=member_name)
        
        try:
            headers = {"Authorization": f"Bearer {self.nvidia_api_key}", "Content-Type": "application/json"}
            
            prompt = f"""Create a short, energetic Discord message to ping {member_name} in {guild_name}. 
            Make it engaging like "Hey {member_name}! You've entered the chat. Time to flex those skills! 💪"
            Keep it under 80 characters, use emojis, be hype and motivational."""
            
            payload = {
                "model": "meta/llama-3.1-8b-instruct",
                "messages": [
                    {"role": "system", "content": "You create hype, engaging Discord ping messages with emojis."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.9, "max_tokens": 80
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post("https://integrate.api.nvidia.com/v1/chat/completions", 
                                      headers=headers, json=payload, timeout=4) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data['choices'][0]['message']['content'].strip()
        except Exception as e:
            print(f"AI error: {e}")
        
        return random.choice(self.message_templates).format(name=member_name)
    
    @tasks.loop(minutes=10)
    async def ping_loop(self):
        """Main ping loop - optimized"""
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
                
                # Generate content concurrently
                tasks = [
                    self.generate_message(guild.name, member.display_name),
                    self.get_gif(random.choice(self.gif_terms)) if config["gif_enabled"] else None
                ]
                
                try:
                    message, gif_url = await asyncio.wait_for(asyncio.gather(*tasks), timeout=8)
                except asyncio.TimeoutError:
                    message = f"Hey {member.display_name}! Time to bring the energy! 🔥"
                    gif_url = None
                
                # Send message
                embed = None
                if gif_url:
                    embed = discord.Embed(color=0x00FF41)
                    embed.set_image(url=gif_url)
                
                try:
                    content = message.replace(member.display_name, "").strip()
                    if embed:
                        await channel.send(content=f"{member.mention} {content}", embed=embed)
                    else:
                        await channel.send(content=f"{member.mention} {content}")
                    
                    print(f"✅ Pinged {member.display_name} in {guild.name}")
                except Exception as e:
                    print(f"❌ Send error in {guild.name}: {e}")
                
                config["next_ping"] = (now + datetime.timedelta(hours=config["interval_hours"])).timestamp()
                
            except Exception as e:
                print(f"Loop error for {guild.name}: {e}")
    
    @ping_loop.before_loop
    async def before_ping_loop(self):
        await self.bot.wait_until_ready()
        print("🤖 Enhanced AI Pinger is ready!")
    
    # Simplified commands
    @app_commands.command(name="ping", description="Pinger control panel")
    async def ping_status(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.followup.send("❌ Need 'Manage Server' permission", ephemeral=True)
            return
            
        config = self.get_config(interaction.guild.id)
        
        embed = discord.Embed(title="🤖 SMART PINGER", color=0x00FF41)
        embed.add_field(name="Status", value="🟢 ON" if config["enabled"] else "🔴 OFF", inline=True)
        embed.add_field(name="AI", value="✅" if config["ai_enabled"] else "❌", inline=True)
        embed.add_field(name="GIF", value="✅" if config["gif_enabled"] else "❌", inline=True)
        embed.add_field(name="Interval", value=f"{config['interval_hours']}h", inline=True)
        
        if config["next_ping"]:
            embed.add_field(name="Next Ping", value=f"<t:{int(config['next_ping'])}:R>", inline=True)
        
        channels = [interaction.guild.get_channel(ch).mention for ch in config["channels"] 
                   if interaction.guild.get_channel(ch)]
        embed.add_field(name="Channels", value="\n".join(channels) or "None", inline=False)
        
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
        embed = discord.Embed(title=f"Pinger {status}", color=0x00FF41 if config["enabled"] else 0xFF4444)
        
        await self.safe_respond(interaction, embed=embed)
    
    @app_commands.command(name="ping-channel", description="Add/remove ping channel")
    async def ping_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.user.guild_permissions.manage_guild:
            await self.safe_respond(interaction, "❌ Need 'Manage Server' permission", ephemeral=True)
            return
            
        config = self.get_config(interaction.guild.id)
        
        if channel.id in config["channels"]:
            config["channels"].remove(channel.id)
            msg = f"➖ Removed {channel.mention}"
            color = 0xFF4444
        else:
            config["channels"].append(channel.id)
            msg = f"➕ Added {channel.mention}"
            color = 0x00FF41
        
        embed = discord.Embed(title=msg, color=color)
        await self.safe_respond(interaction, embed=embed)
    
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
        
        embed = discord.Embed(title="⏰ Ping scheduled!", 
                            description="Will ping within 10 minutes", color=0x00FF41)
        await self.safe_respond(interaction, embed=embed)
    
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
        
        embed = discord.Embed(title=f"⏱️ Interval set to {hours}h", color=0x00FF41)
        await self.safe_respond(interaction, embed=embed)
    
    @app_commands.command(name="ping-test", description="Test ping message (sends to you only)")
    async def ping_test(self, interaction: discord.Interaction):
        """Test ping message to see how it looks"""
        if not interaction.user.guild_permissions.manage_guild:
            await self.safe_respond(interaction, "❌ Need 'Manage Server' permission", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        config = self.get_config(interaction.guild.id)
        
        # Generate test message and GIF
        try:
            tasks = [
                self.generate_message(interaction.guild.name, interaction.user.display_name),
                self.get_gif(random.choice(self.gif_terms)) if config["gif_enabled"] else None
            ]
            
            message, gif_url = await asyncio.wait_for(asyncio.gather(*tasks), timeout=8)
        except asyncio.TimeoutError:
            message = f"Hey {interaction.user.display_name}! Time to bring the energy! 🔥"
            gif_url = None
        
        # Create test embed
        embed = discord.Embed(
            title="🧪 TEST PING PREVIEW",
            description="This is how your ping will look:",
            color=0x00FF41
        )
        
        # Clean message for display
        clean_message = message.replace(interaction.user.display_name, "").strip()
        embed.add_field(
            name="📩 Message", 
            value=f"{interaction.user.mention} {clean_message}", 
            inline=False
        )
        
        # Add settings info
        embed.add_field(name="🤖 AI", value="✅ ON" if config["ai_enabled"] else "❌ OFF", inline=True)
        embed.add_field(name="🎬 GIF", value="✅ ON" if config["gif_enabled"] else "❌ OFF", inline=True)
        embed.add_field(name="⏱️ Interval", value=f"{config['interval_hours']}h", inline=True)
        
        # Add GIF if available
        if gif_url:
            embed.set_image(url=gif_url)
            embed.add_field(name="🎭 GIF", value="✅ Found matching GIF", inline=False)
        else:
            embed.add_field(name="🎭 GIF", value="❌ No GIF found/disabled", inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    if not bot.get_cog("AIPinger"):
        await bot.add_cog(AIPinger(bot))
        print("✅ AIPinger loaded!")

async def teardown(bot):
    if bot.get_cog("AIPinger"):
        await bot.remove_cog("AIPinger")
        print("❌ AIPinger unloaded!")
