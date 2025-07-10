import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import asyncio
import datetime
import json
import os
import aiohttp
from typing import Dict, List, Optional

class AIPinger(commands.Cog):
    """AI-powered smart pinger that generates contextual messages"""
    
    def __init__(self, bot):
        self.bot = bot
        self.nvidia_api_key = os.getenv('NVIDIA_API_KEY')  # Set your NVIDIA API key as environment variable
        self.nvidia_base_url = "https://integrate.api.nvidia.com/v1"
        
        # Server-specific configurations stored in memory
        self.server_configs = {}
        
        # Start the ping loop
        self.ping_loop.start()
    
    def cog_unload(self):
        self.ping_loop.cancel()
    
    def get_server_config(self, guild_id: int) -> Dict:
        """Get configuration for a specific server"""
        if guild_id not in self.server_configs:
            self.server_configs[guild_id] = {
                "enabled": False,
                "channels": [],
                "next_ping": None,
                "interval_hours": 6,
                "excluded_roles": [],
                "ai_enabled": True
            }
        return self.server_configs[guild_id]
    
    async def generate_ai_message(self, guild_name: str, member_name: str) -> str:
        """Generate AI-powered sarcastic message using NVIDIA API"""
        if not self.nvidia_api_key:
            # Fallback messages if no API key
            fallback_messages = [
                f"@{member_name} Kya baat hai, ghost mode on hai kya? 👻",
                f"@{member_name} Server itna quiet kyun hai? Sab hibernation mein gaye? 😴",
                f"@{member_name} Ping ping! Koi alive hai ya sab simulation hai? 🤖",
                f"@{member_name} Group chat ya library? Itna silence! 📚",
                f"@{member_name} Timepass ka mood hai kya? Let's chat! 💬"
            ]
            return random.choice(fallback_messages)
        
        try:
            headers = {
                "Authorization": f"Bearer {self.nvidia_api_key}",
                "Content-Type": "application/json"
            }
            
            prompt = f"""Generate a short, funny, and slightly sarcastic message in Hinglish (Hindi + English mix) to ping a Discord user named {member_name} in server '{guild_name}'. The message should be casual, friendly, and encourage conversation. Keep it under 100 characters. Don't include @ symbol, just the message text."""
            
            payload = {
                "model": "meta/llama-3.1-8b-instruct",
                "messages": [
                    {"role": "system", "content": "You are a witty Discord bot that creates funny, sarcastic Hinglish messages to ping users and start conversations."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.8,
                "max_tokens": 100,
                "stream": False
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.nvidia_base_url}/chat/completions", 
                                      headers=headers, json=payload, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        ai_message = data['choices'][0]['message']['content'].strip()
                        return f"@{member_name} {ai_message}"
                    else:
                        raise Exception(f"API returned status {response.status}")
                        
        except Exception as e:
            print(f"AI generation failed: {e}")
            # Fallback to random message
            fallback_messages = [
                f"@{member_name} AI se message generate kar raha tha, but you're too special for AI! 🤖✨",
                f"@{member_name} Server mein kya chal raha hai? Update chahiye! 📱",
                f"@{member_name} Boring ho raha hai yaar, kuch interesting bolo! 🎭"
            ]
            return random.choice(fallback_messages)
    
    @tasks.loop(minutes=10)
    async def ping_loop(self):
        """Main ping loop that checks all servers"""
        now = datetime.datetime.utcnow()
        
        for guild in self.bot.guilds:
            config = self.get_server_config(guild.id)
            
            if not config["enabled"] or not config["channels"]:
                continue
            
            # Check if it's time to ping
            if config["next_ping"] and now.timestamp() < config["next_ping"]:
                continue
            
            # Get valid channels
            valid_channels = [
                guild.get_channel(ch_id) for ch_id in config["channels"]
                if guild.get_channel(ch_id) and guild.get_channel(ch_id).permissions_for(guild.me).send_messages
            ]
            
            if not valid_channels:
                continue
            
            # Get eligible members
            eligible_members = [
                member for member in guild.members
                if not member.bot and 
                not any(role.id in config["excluded_roles"] for role in member.roles)
            ]
            
            if not eligible_members:
                # Update next ping time and continue
                config["next_ping"] = (now + datetime.timedelta(hours=config["interval_hours"])).timestamp()
                continue
            
            # Select random channel and member
            channel = random.choice(valid_channels)
            member = random.choice(eligible_members)
            
            # Generate message
            if config["ai_enabled"]:
                message = await self.generate_ai_message(guild.name, member.display_name)
            else:
                message = f"@{member.display_name} Random ping! Kya chal raha hai? 🎯"
            
            # Create embed
            embed = discord.Embed(
                title="🎯 SMART PING ACTIVATED",
                description=message.replace(f"@{member.display_name}", ""),
                color=0x00FF41,
                timestamp=now
            )
            embed.add_field(name="🤖 AI Status", value="✅ Active" if config["ai_enabled"] else "❌ Disabled", inline=True)
            embed.add_field(name="⏰ Next Ping", value=f"<t:{int((now + datetime.timedelta(hours=config['interval_hours'])).timestamp())}:R>", inline=True)
            embed.set_footer(text=f"Smart Pinger v4.0 | {guild.name}")
            
            try:
                await channel.send(content=member.mention, embed=embed)
                print(f"Pinged {member.display_name} in {guild.name}")
            except Exception as e:
                print(f"Failed to send ping: {e}")
            
            # Update next ping time
            config["next_ping"] = (now + datetime.timedelta(hours=config["interval_hours"])).timestamp()
    
    @ping_loop.before_loop
    async def before_ping_loop(self):
        await self.bot.wait_until_ready()
        print("AI Pinger is ready!")
    
    @app_commands.command(name="ping", description="Show smart pinger control panel")
    @app_commands.describe()
    async def ping_status(self, interaction: discord.Interaction):
        """Smart pinger control panel"""
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need 'Manage Server' permission to use this command.", ephemeral=True)
            return
            
        config = self.get_server_config(interaction.guild.id)
        
        embed = discord.Embed(
            title="🤖 SMART PINGER CONTROL",
            description="AI-powered member pinger with contextual messages",
            color=0x00FF41,
            timestamp=datetime.datetime.utcnow()
        )
        
        embed.add_field(name="📊 Status", value="🟢 Active" if config["enabled"] else "🔴 Inactive", inline=True)
        embed.add_field(name="🤖 AI", value="✅ Enabled" if config["ai_enabled"] else "❌ Disabled", inline=True)
        embed.add_field(name="⏱️ Interval", value=f"{config['interval_hours']} hours", inline=True)
        
        if config["next_ping"]:
            embed.add_field(name="⏰ Next Ping", value=f"<t:{int(config['next_ping'])}:R>", inline=True)
        
        channels = [interaction.guild.get_channel(ch_id).mention for ch_id in config["channels"] if interaction.guild.get_channel(ch_id)]
        embed.add_field(name="📢 Channels", value="\n".join(channels) if channels else "None", inline=False)
        
        embed.add_field(
            name="🔧 Available Commands",
            value="• `/ping-enable` - Enable pinger\n"
                  "• `/ping-disable` - Disable pinger\n"
                  "• `/ping-channel` - Add/remove channel\n"
                  "• `/ping-ai-toggle` - Toggle AI messages\n"
                  "• `/ping-now` - Force ping immediately\n"
                  "• `/ping-interval` - Set ping interval",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="ping-enable", description="Enable the smart pinger")
    async def ping_enable(self, interaction: discord.Interaction):
        """Enable the pinger"""
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need 'Manage Server' permission to use this command.", ephemeral=True)
            return
            
        config = self.get_server_config(interaction.guild.id)
        
        if not config["channels"]:
            await interaction.response.send_message("❌ Add a channel first using `/ping-channel`", ephemeral=True)
            return
        
        config["enabled"] = True
        config["next_ping"] = (datetime.datetime.utcnow() + datetime.timedelta(hours=config["interval_hours"])).timestamp()
        
        embed = discord.Embed(
            title="✅ SMART PINGER ACTIVATED",
            description=f"Pinger will now ping members every {config['interval_hours']} hours",
            color=0x00FF41
        )
        embed.add_field(name="⏰ Next Ping", value=f"<t:{int(config['next_ping'])}:R>", inline=True)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="ping-disable", description="Disable the smart pinger")
    async def ping_disable(self, interaction: discord.Interaction):
        """Disable the pinger"""
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need 'Manage Server' permission to use this command.", ephemeral=True)
            return
            
        config = self.get_server_config(interaction.guild.id)
        config["enabled"] = False
        
        embed = discord.Embed(
            title="❌ SMART PINGER DEACTIVATED",
            description="Pinger has been disabled for this server",
            color=0xFF4444
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="ping-channel", description="Add or remove a channel from ping list")
    @app_commands.describe(channel="Channel to add/remove from ping list")
    async def ping_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Add/remove a channel"""
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need 'Manage Server' permission to use this command.", ephemeral=True)
            return
            
        config = self.get_server_config(interaction.guild.id)
        
        if channel.id in config["channels"]:
            config["channels"].remove(channel.id)
            embed = discord.Embed(
                title="➖ CHANNEL REMOVED",
                description=f"Removed {channel.mention} from ping channels",
                color=0xFF4444
            )
        else:
            config["channels"].append(channel.id)
            embed = discord.Embed(
                title="➕ CHANNEL ADDED",
                description=f"Added {channel.mention} to ping channels",
                color=0x00FF41
            )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="ping-now", description="Force an immediate ping")
    async def ping_now(self, interaction: discord.Interaction):
        """Force an immediate ping"""
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need 'Manage Server' permission to use this command.", ephemeral=True)
            return
            
        config = self.get_server_config(interaction.guild.id)
        
        if not config["enabled"] or not config["channels"]:
            await interaction.response.send_message("❌ Pinger is not enabled or no channels configured!", ephemeral=True)
            return
        
        config["next_ping"] = datetime.datetime.utcnow().timestamp()
        
        embed = discord.Embed(
            title="⏰ IMMEDIATE PING SCHEDULED",
            description="A ping will be sent within the next 10 minutes",
            color=0x00FF41
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="ping-ai-toggle", description="Toggle AI message generation")
    async def ping_ai_toggle(self, interaction: discord.Interaction):
        """Toggle AI message generation"""
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need 'Manage Server' permission to use this command.", ephemeral=True)
            return
            
        config = self.get_server_config(interaction.guild.id)
        config["ai_enabled"] = not config["ai_enabled"]
        
        status = "enabled" if config["ai_enabled"] else "disabled"
        embed = discord.Embed(
            title=f"🤖 AI MESSAGES {status.upper()}",
            description=f"AI message generation is now {status}",
            color=0x00FF41 if config["ai_enabled"] else 0xFF4444
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="ping-interval", description="Set ping interval in hours")
    @app_commands.describe(hours="Interval in hours (1-24)")
    async def ping_interval(self, interaction: discord.Interaction, hours: int):
        """Set ping interval in hours"""
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need 'Manage Server' permission to use this command.", ephemeral=True)
            return
            
        if hours < 1 or hours > 24:
            await interaction.response.send_message("❌ Interval must be between 1-24 hours", ephemeral=True)
            return
        
        config = self.get_server_config(interaction.guild.id)
        config["interval_hours"] = hours
        
        embed = discord.Embed(
            title="⏱️ INTERVAL UPDATED",
            description=f"Ping interval set to {hours} hours",
            color=0x00FF41
        )
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(AIPinger(bot))
