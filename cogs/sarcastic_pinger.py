import discord
from discord.ext import commands, tasks
import random
import asyncio
import datetime
from typing import Optional, Dict, List
import json
import os

class SarcasticPinger(commands.Cog):
    """Ping random members with sarcastic comments every 6 hours"""
    
    def __init__(self, bot):
        self.bot = bot
        self.config_dir = "data/sarcastic_pinger"
        self.enabled_guilds = {}  # guild_id: next_ping_time
        
        # Ensure config directory exists
        os.makedirs(self.config_dir, exist_ok=True)
        
        # Start the pinger loop
        self.pinger_loop.start()
        
        # Sarcastic ping messages and GIF URLs to be added by user
        self.ping_messages = [
    "@{member} Oye sab chup kyu ho gye? Group mute kr diya kya? 👀",
    "@{member} Kya kar rahe ho sab? Ya mai hi sirf free hoon? 😅",
    "@{member} Online toh ho, par bol koi nahi raha... ghost mode on hai kya? 👻",
    "@{member} Itna sannata kyun hai bhai... koi to kuch bol do 😭",
    "@{member} Group chat ya museum? Itna silence! 😐",
    "@{member} Lagta hai sab Himalaya chale gaye meditation krne 🧘‍♂️",
    "@{member} Ping ping... check 1 2 3... koi zinda hai kya idhar? 📡",
    "@{member} Main message bhej ke dekh raha hoon ki group abhi bhi kaam kr raha hai ya nahi 😬",
    "@{member} Aisa lag raha hai group me sirf mai hi hoon aur baaki log paid actors the 😭",
    "@{member} Is group ka naam 'Silent Hill' rakh dete hain ab toh 😅",
    "@{member} Chalo koi ek game ya bakchodi shuru karo, boring ho raha hai!",
    "@{member} Vibe check kar raha hoon... alive ho ya bas story daal ke gaayab? 😂",
    "@{member} Group ki hawa kaafi thandi ho gayi hai... thoda garam karo yaar 🔥",
    "@{member} Aaj kis kis ka timepass mood on hai? Mujhe chat fight chahiye 😈"
]
# You'll add these yourself
        self.gif_urls = [
    "https://media.giphy.com/media/3og0IPxMM0erATueVW/giphy.gif",  # Hello? Anyone?
    "https://media.giphy.com/media/l0MYB8Ory7Hqefo9a/giphy.gif",  # Crickets
    "https://media.giphy.com/media/xT5LMzIK1AdZJ5I1So/giphy.gif",  # Ping!
    "https://media.giphy.com/media/l0HlNQ03J5JxX6lva/giphy.gif",  # Waiting...
    "https://media.giphy.com/media/3o7bu3XilJ5BOiSGic/giphy.gif",  # Knock knock
    "https://media.giphy.com/media/d2lcHJTG5Tscg/giphy.gif",       # Waving
    "https://media.giphy.com/media/3oEduQAsYcJKQH2XsI/giphy.gif",  # Hello darkness...
    "https://media.giphy.com/media/3o6Zt481isNVuQI1l6/giphy.gif",  # Where is everyone?
    "https://media.giphy.com/media/l4EoTHjUqNjKaaz2w/giphy.gif",   # Ghost town
    "https://media.giphy.com/media/3o6MbaZBc1BY6A2ZfO/giphy.gif"   # Come out come out...
]
# You'll add these yourself

    def cog_unload(self):
        """Cancel the task when the cog is unloaded"""
        self.pinger_loop.cancel()
    
    def _load_guild_config(self, guild_id: int) -> Dict:
        """Load configuration for a specific guild"""
        config_path = f"{self.config_dir}/{guild_id}.json"
        
        if not os.path.exists(config_path):
            return {
                "enabled": False,
                "channels": [],
                "last_ping": None,
                "next_ping": None,
                "ping_interval": 21600,  # 6 hours in seconds
                "exclude_roles": []
            }
            
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {
                "enabled": False,
                "channels": [],
                "last_ping": None,
                "next_ping": None,
                "ping_interval": 21600,
                "exclude_roles": []
            }
    
    def _save_guild_config(self, guild_id: int, config: Dict) -> None:
        """Save configuration for a specific guild"""
        config_path = f"{self.config_dir}/{guild_id}.json"
        
        try:
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            print(f"Error saving config for guild {guild_id}: {e}")
    
    def _get_next_ping_time(self, config: Dict) -> Optional[datetime.datetime]:
        """Calculate the next ping time based on config"""
        if not config["enabled"]:
            return None
            
        now = datetime.datetime.utcnow()
        
        if config["next_ping"]:
            try:
                # Convert stored timestamp to datetime
                next_time = datetime.datetime.fromtimestamp(config["next_ping"])
                
                # If it's in the past, calculate a new time
                if next_time <= now:
                    interval_seconds = config["ping_interval"]
                    next_time = now + datetime.timedelta(seconds=interval_seconds)
            except (ValueError, TypeError, OverflowError):
                # Handle invalid timestamp
                interval_seconds = config["ping_interval"]
                next_time = now + datetime.timedelta(seconds=interval_seconds)
                
            return next_time
        else:
            # No next ping time set, calculate one
            interval_seconds = config["ping_interval"]
            return now + datetime.timedelta(seconds=interval_seconds)
    
    @tasks.loop(minutes=5)  # Reduced from 10 to 5 minutes to check more frequently
    async def pinger_loop(self):
        """Check and ping members on schedule"""
        now = datetime.datetime.utcnow()
        
        for guild in self.bot.guilds:
            # Load config for this guild
            config = self._load_guild_config(guild.id)
            
            if not config["enabled"]:
                continue
                
            next_ping = self._get_next_ping_time(config)
            
            if not next_ping:
                continue
                
            # Check if it's time to ping
            if now >= next_ping:
                # Get valid channels
                valid_channels = []
                for channel_id in config["channels"]:
                    channel = guild.get_channel(channel_id)
                    if channel and channel.permissions_for(guild.me).send_messages:
                        valid_channels.append(channel)
                
                if not valid_channels:
                    # No valid channels, disable pinging
                    config["enabled"] = False
                    self._save_guild_config(guild.id, config)
                    print(f"Disabled pinger for guild {guild.id}: No valid channels")
                    continue
                
                # Select random channel
                channel = random.choice(valid_channels)
                
                # Get eligible members - excluding bots and members with excluded roles
                # FIXED: Removed the offline status check that was preventing pings
                exclude_role_ids = config["exclude_roles"]
                eligible_members = []
                
                for member in guild.members:
                    if member.bot:
                        continue
                        
                    # Skip members with excluded roles
                    if any(role.id in exclude_role_ids for role in member.roles):
                        continue
                    
                    # IMPORTANT: Removed the offline status check to allow pinging all members
                    eligible_members.append(member)
                
                if not eligible_members:
                    print(f"No eligible members found in guild {guild.id}")
                    
                    # Update last ping time and calculate next ping despite no eligible members
                    config["last_ping"] = now.timestamp()
                    next_ping = now + datetime.timedelta(seconds=config["ping_interval"])
                    config["next_ping"] = next_ping.timestamp()
                    self._save_guild_config(guild.id, config)
                    continue
                
                # Choose a random member
                member = random.choice(eligible_members)
                
                # Ensure we have ping messages to use
                if not self.ping_messages:
                    message_content = "Random ping activated!"
                else:
                    # Choose a random message template and format it
                    message_template = random.choice(self.ping_messages)
                    message_content = message_template.replace("{member}", "")
                
                # Choose a random GIF if available
                gif_url = None
                if self.gif_urls:
                    gif_url = random.choice(self.gif_urls)
                
                # Create embed
                embed = discord.Embed(
                    title="⚡ RANDOM MEMBER DETECTED ⚡",
                    description=message_content,
                    color=0x00FFFF,  # Cyan for futuristic look
                    timestamp=now
                )
                
                # Add a border-like effect with fields
                embed.add_field(name="┌───────────────────┐", value="", inline=False)
                embed.add_field(name="STATUS:", value="PING SUCCESSFUL", inline=True)
                embed.add_field(name="PROTOCOL:", value="RANDOM_SELECT_v2.5", inline=True)
                embed.add_field(name="└───────────────────┘", value="", inline=False)
                
                # Add the GIF if available
                if gif_url:
                    embed.set_image(url=gif_url)
                
                # Add futuristic footer
                embed.set_footer(text=f"SYSTEM: Auto-Ping v3.0 | NEXT SEQUENCE: T+6h")
                
                try:
                    # The member mention is now outside the embed in the message content
                    await channel.send(content=member.mention, embed=embed)
                    print(f"Successfully pinged {member.name} in guild {guild.id}")
                except discord.HTTPException as e:
                    print(f"Error sending ping in guild {guild.id}: {e}")
                
                # Update last ping time and calculate next ping
                config["last_ping"] = now.timestamp()
                next_ping = now + datetime.timedelta(seconds=config["ping_interval"])
                config["next_ping"] = next_ping.timestamp()
                self._save_guild_config(guild.id, config)
    
    @pinger_loop.before_loop
    async def before_pinger_loop(self):
        """Wait for the bot to be ready before starting the loop"""
        await self.bot.wait_until_ready()
        print("Pinger loop is ready")
        
        # Load all guild configs
        for guild in self.bot.guilds:
            config = self._load_guild_config(guild.id)
            
            if config["enabled"]:
                next_ping = self._get_next_ping_time(config)
                if next_ping:
                    # Update config with the calculated next ping time
                    config["next_ping"] = next_ping.timestamp()
                    self._save_guild_config(guild.id, config)
                    print(f"Scheduled next ping for guild {guild.id} at {next_ping}")
    
    @commands.group(name="pinger", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def pinger(self, ctx):
        """Commands to manage the sarcastic member pinger"""
        config = self._load_guild_config(ctx.guild.id)
        
        embed = discord.Embed(
            title="🔔 SARCASTIC PINGER CONTROL PANEL",
            description="The sarcastic pinger randomly pings a server member with a sassy message every 6 hours.",
            color=0x00FFFF,  # Cyan for futuristic look
            timestamp=datetime.datetime.utcnow()
        )
        
        status = "ONLINE ✅" if config["enabled"] else "OFFLINE ❌"
        embed.add_field(name="SYSTEM STATUS", value=status, inline=True)
        
        if config["enabled"] and config["next_ping"]:
            next_ping = datetime.datetime.fromtimestamp(config["next_ping"])
            embed.add_field(
                name="NEXT SCHEDULED PING", 
                value=f"<t:{int(next_ping.timestamp())}:R>", 
                inline=True
            )
        
        channels = []
        for channel_id in config["channels"]:
            channel = ctx.guild.get_channel(channel_id)
            if channel:
                channels.append(channel.mention)
        
        if channels:
            embed.add_field(
                name="DESIGNATED CHANNELS",
                value="\n".join(channels) if len(channels) <= 5 else "\n".join(channels[:5]) + f"\n...and {len(channels) - 5} more",
                inline=False
            )
        else:
            embed.add_field(name="DESIGNATED CHANNELS", value="No channels configured", inline=False)
        
        # Show excluded roles if any
        exclude_roles = []
        for role_id in config["exclude_roles"]:
            role = ctx.guild.get_role(role_id)
            if role:
                exclude_roles.append(role.mention)
        
        if exclude_roles:
            embed.add_field(
                name="EXCLUDED ENTITIES",
                value=", ".join(exclude_roles),
                inline=False
            )
        
        # Add a divider
        embed.add_field(name="┌───────────────────┐", value="", inline=False)
        
        embed.add_field(
            name="COMMAND INTERFACE",
            value=f"`{ctx.prefix}pinger enable` - Activate system\n"
                  f"`{ctx.prefix}pinger disable` - Deactivate system\n"
                  f"`{ctx.prefix}pinger channel add #channel` - Add channel to network\n"
                  f"`{ctx.prefix}pinger channel remove #channel` - Remove channel from network\n"
                  f"`{ctx.prefix}pinger exclude @role` - Exclude role from ping protocol\n"
                  f"`{ctx.prefix}pinger include @role` - Include previously excluded role\n"
                  f"`{ctx.prefix}pinger test` - Test ping system",
            inline=False
        )
        
        # Add another divider
        embed.add_field(name="└───────────────────┘", value="", inline=False)
        
        # Add futuristic footer
        embed.set_footer(text="SARCASTIC PINGER v3.0 | Powered by Advanced AI")
        
        await ctx.send(embed=embed)
    
    @pinger.command(name="enable")
    @commands.has_permissions(manage_guild=True)
    async def pinger_enable(self, ctx):
        """Enable the sarcastic pinger"""
        config = self._load_guild_config(ctx.guild.id)
        
        if not config["channels"]:
            await ctx.send("⚠️ SYSTEM ERROR: No channels detected in configuration. Use `!pinger channel add #channel` to designate target areas.")
            return
        
        if config["enabled"]:
            await ctx.send("⚠️ NOTICE: Sarcastic pinger system is already active.")
            return
        
        config["enabled"] = True
        
        # Calculate next ping time (1 hour from now instead of 6 for faster testing)
        next_ping = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        config["next_ping"] = next_ping.timestamp()
        
        self._save_guild_config(ctx.guild.id, config)
        
        embed = discord.Embed(
            title="✅ SYSTEM ACTIVATION SUCCESSFUL",
            description="The sarcastic pinger protocol has been initialized and will ping members every 6 hours.",
            color=0x00FFFF,  # Cyan for futuristic look
            timestamp=datetime.datetime.utcnow()
        )
        
        # Add a border-like effect with fields
        embed.add_field(name="┌───────────────────┐", value="", inline=False)
        
        embed.add_field(
            name="FIRST SCHEDULED PING",
            value=f"<t:{int(next_ping.timestamp())}:R>",
            inline=True
        )
        
        embed.add_field(
            name="SYSTEM STATUS",
            value="ONLINE ✅",
            inline=True
        )
        
        # Add another divider
        embed.add_field(name="└───────────────────┘", value="", inline=False)
        
        # Add futuristic footer
        embed.set_footer(text="SARCASTIC PINGER v3.0 | Initialization Complete")
        
        await ctx.send(embed=embed)
    
    @pinger.command(name="disable")
    @commands.has_permissions(manage_guild=True)
    async def pinger_disable(self, ctx):
        """Disable the sarcastic pinger"""
        config = self._load_guild_config(ctx.guild.id)
        
        if not config["enabled"]:
            await ctx.send("⚠️ NOTICE: Sarcastic pinger system is already offline.")
            return
        
        config["enabled"] = False
        self._save_guild_config(ctx.guild.id, config)
        
        embed = discord.Embed(
            title="🛑 SYSTEM DEACTIVATION COMPLETE",
            description="The sarcastic pinger protocol has been disabled. All ping operations suspended.",
            color=0xFF0000,  # Red for deactivation
            timestamp=datetime.datetime.utcnow()
        )
        
        # Add a border-like effect with fields
        embed.add_field(name="┌───────────────────┐", value="", inline=False)
        
        embed.add_field(
            name="SYSTEM STATUS",
            value="OFFLINE ❌",
            inline=True
        )
        
        embed.add_field(
            name="PING PROTOCOLS",
            value="SUSPENDED",
            inline=True
        )
        
        # Add another divider
        embed.add_field(name="└───────────────────┘", value="", inline=False)
        
        # Add futuristic footer
        embed.set_footer(text="SARCASTIC PINGER v3.0 | System Shutdown Complete")
        
        await ctx.send(embed=embed)
    
    @pinger.group(name="channel", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def pinger_channel(self, ctx):
        """Manage channels where the pinger can send messages"""
        config = self._load_guild_config(ctx.guild.id)
        
        channels = []
        for channel_id in config["channels"]:
            channel = ctx.guild.get_channel(channel_id)
            if channel:
                channels.append(channel.mention)
        
        embed = discord.Embed(
            title="🔔 DESIGNATED COMMUNICATION CHANNELS",
            description="These are the channels where the pinger can send messages:",
            color=0x00FFFF,  # Cyan for futuristic look
            timestamp=datetime.datetime.utcnow()
        )
        
        # Add a border-like effect with fields
        embed.add_field(name="┌───────────────────┐", value="", inline=False)
        
        if channels:
            embed.add_field(
                name="ACTIVE CHANNELS",
                value="\n".join(channels),
                inline=False
            )
        else:
            embed.add_field(
                name="WARNING",
                value="No channels configured yet. Use `!pinger channel add #channel` to designate communication nodes.",
                inline=False
            )
        
        # Add another divider
        embed.add_field(name="└───────────────────┘", value="", inline=False)
        
        embed.set_footer(text=f"Use {ctx.prefix}pinger channel add/remove to modify the network")
        
        await ctx.send(embed=embed)
    
    @pinger_channel.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def pinger_channel_add(self, ctx, channel: discord.TextChannel):
        """Add a channel to the pinger's list"""
        # Check if the bot has permissions to send messages in the channel
        if not channel.permissions_for(ctx.guild.me).send_messages:
            await ctx.send(f"⚠️ PERMISSION ERROR: Unable to access {channel.mention}. Communication protocols restricted.")
            return
        
        config = self._load_guild_config(ctx.guild.id)
        
        if channel.id in config["channels"]:
            await ctx.send(f"⚠️ NOTICE: {channel.mention} is already connected to the pinger network.")
            return
        
        config["channels"].append(channel.id)
        self._save_guild_config(ctx.guild.id, config)
        
        embed = discord.Embed(
            title="✅ CHANNEL INTEGRATION COMPLETE",
            description=f"{channel.mention} has been successfully added to the pinger network.",
            color=0x00FFFF,  # Cyan for futuristic look
            timestamp=datetime.datetime.utcnow()
        )
        
        # Add a border-like effect with fields
        embed.add_field(name="┌───────────────────┐", value="", inline=False)
        
        embed.add_field(
            name="OPERATION",
            value="CHANNEL_ADD",
            inline=True
        )
        
        embed.add_field(
            name="STATUS",
            value="SUCCESS",
            inline=True
        )
        
        # Add another divider
        embed.add_field(name="└───────────────────┘", value="", inline=False)
        
        embed.set_footer(text="Channel connectivity established")
        
        await ctx.send(embed=embed)
    
    @pinger_channel.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def pinger_channel_remove(self, ctx, channel: discord.TextChannel):
        """Remove a channel from the pinger's list"""
        config = self._load_guild_config(ctx.guild.id)
        
        if channel.id not in config["channels"]:
            await ctx.send(f"⚠️ ERROR: {channel.mention} is not connected to the pinger network.")
            return
        
        config["channels"].remove(channel.id)
        self._save_guild_config(ctx.guild.id, config)
        
        # If no channels left, disable the pinger
        if not config["channels"] and config["enabled"]:
            config["enabled"] = False
            self._save_guild_config(ctx.guild.id, config)
            await ctx.send("⚠️ CRITICAL ALERT: All channels removed. The pinger has been automatically disabled.")
        
        embed = discord.Embed(
            title="🗑️ CHANNEL REMOVED FROM NETWORK",
            description=f"{channel.mention} has been disconnected from the pinger network.",
            color=0xFF0000,  # Red for removal
            timestamp=datetime.datetime.utcnow()
        )
        
        # Add a border-like effect with fields
        embed.add_field(name="┌───────────────────┐", value="", inline=False)
        
        embed.add_field(
            name="OPERATION",
            value="CHANNEL_REMOVE",
            inline=True
        )
        
        embed.add_field(
            name="STATUS",
            value="SUCCESS",
            inline=True
        )
        
        # Add another divider
        embed.add_field(name="└───────────────────┘", value="", inline=False)
        
        embed.set_footer(text="Channel connectivity terminated")
        
        await ctx.send(embed=embed)
    
    @pinger.command(name="exclude")
    @commands.has_permissions(manage_guild=True)
    async def pinger_exclude(self, ctx, role: discord.Role):
        """Exclude a role from receiving pings"""
        config = self._load_guild_config(ctx.guild.id)
        
        if role.id in config["exclude_roles"]:
            await ctx.send(f"⚠️ NOTICE: {role.mention} is already excluded from ping protocols.")
            return
        
        config["exclude_roles"].append(role.id)
        self._save_guild_config(ctx.guild.id, config)
        
        embed = discord.Embed(
            title="🚫 ROLE EXCLUSION PROTOCOL ACTIVATED",
            description=f"Members with {role.mention} will be excluded from the random ping algorithm.",
            color=0x00FFFF,  # Cyan for futuristic look
            timestamp=datetime.datetime.utcnow()
        )
        
        # Add a border-like effect with fields
        embed.add_field(name="┌───────────────────┐", value="", inline=False)
        
        embed.add_field(
            name="OPERATION",
            value="ROLE_EXCLUDE",
            inline=True
        )
        
        embed.add_field(
            name="TARGET",
            value=role.name,
            inline=True
        )
        
        # Add another divider
        embed.add_field(name="└───────────────────┘", value="", inline=False)
        
        embed.set_footer(text="Exclusion protocol active")
        
        await ctx.send(embed=embed)
    
    @pinger.command(name="include")
    @commands.has_permissions(manage_guild=True)
    async def pinger_include(self, ctx, role: discord.Role):
        """Include a previously excluded role"""
        config = self._load_guild_config(ctx.guild.id)
        
        if role.id not in config["exclude_roles"]:
            await ctx.send(f"⚠️ ERROR: {role.mention} is not currently excluded from ping protocols.")
            return
        
        config["exclude_roles"].remove(role.id)
        self._save_guild_config(ctx.guild.id, config)
        
        embed = discord.Embed(
            title="✅ ROLE INCLUSION PROTOCOL ACTIVATED",
            description=f"Members with {role.mention} are now eligible for random pings.",
            color=0x00FFFF,  # Cyan for futuristic look
            timestamp=datetime.datetime.utcnow()
        )
        
        # Add a border-like effect with fields
        embed.add_field(name="┌───────────────────┐", value="", inline=False)
        
        embed.add_field(
            name="OPERATION",
            value="ROLE_INCLUDE",
            inline=True
        )
        
        embed.add_field(
            name="TARGET",
            value=role.name,
            inline=True
        )
        
        # Add another divider
        embed.add_field(name="└───────────────────┘", value="", inline=False)
        
        embed.set_footer(text="Inclusion protocol active")
        
        await ctx.send(embed=embed)
    
    @pinger.command(name="test")
    @commands.has_permissions(manage_guild=True)
    async def pinger_test(self, ctx):
        """Test the pinger with a random message"""
        config = self._load_guild_config(ctx.guild.id)
        
        if not config["channels"]:
            await ctx.send("⚠️ CONFIGURATION ERROR: No channels detected. Use `!pinger channel add #channel` first.")
            return
        
        # Get eligible members - excluding bots and members with excluded roles
        # FIXED: Removed offline check for test command too
        exclude_role_ids = config["exclude_roles"]
        eligible_members = []
        
        for member in ctx.guild.members:
            if member.bot:
                continue
                
            # Skip members with excluded roles
            if any(role.id in exclude_role_ids for role in member.roles):
                continue
            
            # Allow all members regardless of status
            eligible_members.append(member)
        
        if not eligible_members:
            await ctx.send("⚠️ TARGET ERROR: No eligible members found for ping test.")
            return
        
        # Choose a random member
        member = random.choice(eligible_members)
        
        # Choose a random message template if available
        if self.ping_messages:
            message_template = random.choice(self.ping_messages)
            message_content = message_template.replace("{member}", "")
        else:
            message_content = "This is a test ping!"
        
        # Choose a random GIF if available
        gif_url = None
        if self.gif_urls:
            gif_url = random.choice(self.gif_urls)
        
        # Create a test embed with futuristic styling
        embed = discord.Embed(
            title="⚡ TEST PING SEQUENCE INITIATED ⚡",
            description=message_content,
            color=0x00FFFF,  # Cyan for futuristic look
            timestamp=datetime.datetime.utcnow()
        )
        
        # Add a border-like effect with fields
        embed.add_field(name="┌───────────────────┐", value="", inline=False)
        
        embed.add_field(
            name="TEST TYPE",
            value="PING_SIMULATION",
            inline=True
        )
        
        embed.add_field(
            name="STATUS",
            value="EXECUTING",
            inline=True
        )
        
        # Add another divider
        embed.add_field(name="└───────────────────┘", value="", inline=False)
        
        # Add the GIF if available
        if gif_url:
            embed.set_image(url=gif_url)
        
        # Add futuristic footer
        embed.set_footer(text=f"TEST REQUEST: {ctx.author.name} | TIMESTAMP: {datetime.datetime.utcnow().strftime('%H:%M:%S')}")
        
        # Send the user mention outside the embed to trigger a notification
        await ctx.send(content=member.mention, embed=embed)

    @pinger.command(name="ping_now")
    @commands.has_permissions(manage_guild=True)
    async def ping_now(self, ctx):
        """Force an immediate ping"""
        config = self._load_guild_config(ctx.guild.id)
        
        if not config["enabled"]:
            await ctx.send("⚠️ SYSTEM ERROR: Sarcastic pinger is currently offline. Enable it first with `!pinger enable`.")
            return
            
        if not config["channels"]:
            await ctx.send("⚠️ CONFIGURATION ERROR: No channels detected. Use `!pinger channel add #channel` first.")
            return
            
        # Set next ping time to now to trigger immediate ping on next loop
        config["next_ping"] = datetime.datetime.utcnow().timestamp()
        self._save_guild_config(ctx.guild.id, config)
        
        embed = discord.Embed(
            title="⏱️ IMMEDIATE PING SCHEDULED",
            description="A ping has been scheduled to execute on the next system cycle (within 5 minutes).",
            color=0x00FFFF,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Manual override accepted")
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(SarcasticPinger(bot))
