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
        self.pinger_loop.start()
        
        # Ensure config directory exists
        os.makedirs(self.config_dir, exist_ok=True)
        
        # Sarcastic ping messages - more varied and entertaining
        self.ping_messages = [
            "Hey {member}, just checking if you're still breathing. The silence was deafening.",
            "Knock knock, {member}! Oh wait, you can't answer because you're too busy ignoring us.",
            "{member} has been selected by the algorithm of doom to receive this absolutely vital ping.",
            "Breaking news: {member} exists! Thanks for coming to my TED talk.",
            "Congratulations {member}! You've won the prestigious 'Random Ping of the Day' award!",
            "Esteemed {member}, your presence is cordially requested in this channel... or whatever.",
            "Earth to {member}, come in {member}! Are you receiving our transmission?",
            "The council has spoken, and {member} shall be the chosen one to receive this ping.",
            "{member} probably thought they could lurk forever without being noticed. WRONG!",
            "Alert: Wild {member} spotted in their natural habitat!",
            "According to my calculations, {member} was due for a completely unnecessary ping.",
            "Hey {member}, I'm just pinging you to remind you about your car's extended warranty.",
            "Attention {member}! This is a test of the Emergency Member Notification System.",
            "In today's episode of 'People Who Forgot This Server Exists', we feature {member}!",
            "The ritual is complete. {member} has been summoned.",
            "Plot twist: {member} gets randomly pinged for absolutely no reason!",
            "Breaking the fourth wall to acknowledge that {member} probably hates being pinged.",
            "{member}, are you still with us? This server misses your awkward conversation attempts.",
            "The ancient prophecy foretold that {member} would receive this ping today.",
            "Roses are red, violets are blue, {member} got pinged, and has no clue why too!",
            "Hello {member}, we've been trying to reach you about your server's extended warranty.",
            "Beep boop. {member} has been selected by the random ping algorithm. Beep boop.",
            "Ping! {member} is probably wondering why they joined this server in the first place.",
            "Good news, {member}! You've been randomly selected for a complimentary ping!",
            "Dear {member}, here's your regularly scheduled reminder that you're still in this server.",
            "{member}'s FBI agent told me they were feeling lonely, so here's a ping!",
            "What's that? {member} thought they could escape the random ping? Think again!",
            "Testing... testing... is this {member} still connected to the server?",
            "Legend says if you ping {member} three times in a row, they'll actually respond.",
            "{member}, this ping is sponsored by RAID: Shadow Legends!"
        ]
        self.gif_urls = [
            "https://media.giphy.com/media/3o7abldj0b3rxrZUxW/giphy.gif",  # classic confused John Travolta
            "https://media.giphy.com/media/l0MYC0LajbaPoEADu/giphy.gif",  # awkward silence
            "https://media.giphy.com/media/3o7TKtnuHOHHUjR38Y/giphy.gif",  # you're being watched
            "https://media.giphy.com/media/xUPGcguWZHRC2HyBRS/giphy.gif",  # hello?
            "https://media.giphy.com/media/dzaUX7CAG0Ihi/giphy.gif",       # shocked Pikachu
            "https://media.giphy.com/media/ASd0Ukj0y3qMM/giphy.gif",       # surprised reaction
            "https://media.giphy.com/media/9J7tdYltWyXIY/giphy.gif",       # slow clap
            "https://media.giphy.com/media/hPPx8yk3Bmqys/giphy.gif",       # typing intensely
            "https://media.giphy.com/media/Rkis28kMJd1aE/giphy.gif",       # dramatically waiting
        ]

    
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
            # Convert stored timestamp to datetime
            next_time = datetime.datetime.fromtimestamp(config["next_ping"])
            
            # If it's in the past, calculate a new time
            if next_time <= now:
                interval_seconds = config["ping_interval"]
                next_time = now + datetime.timedelta(seconds=interval_seconds)
                
            return next_time
        else:
            # No next ping time set, calculate one
            interval_seconds = config["ping_interval"]
            return now + datetime.timedelta(seconds=interval_seconds)
    
    @tasks.loop(minutes=10)
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
                    continue
                
                # Select random channel
                channel = random.choice(valid_channels)
                
                # Get eligible members - excluding bots and members with excluded roles
                exclude_role_ids = config["exclude_roles"]
                eligible_members = []
                
                for member in guild.members:
                    if member.bot:
                        continue
                        
                    # Skip members with excluded roles
                    if any(role.id in exclude_role_ids for role in member.roles):
                        continue
                        
                    # Skip offline members
                    if member.status == discord.Status.offline:
                        continue
                        
                    eligible_members.append(member)
                
                if eligible_members:
                    # Choose a random member
                    member = random.choice(eligible_members)
                    
                    # Choose a random ping message
                    message = random.choice(self.ping_messages).format(member=member.mention)
                    
                    # Choose a random GIF
                    gif_url = random.choice(self.gif_urls)
                    
                    # Create a futuristic embed
                    embed = discord.Embed(
                        title="⚡ RANDOM MEMBER DETECTED ⚡",
                        description=message,
                        color=0x00FFFF,  # Cyan for futuristic look
                        timestamp=now
                    )
                    
                    # Add a border-like effect with fields
                    embed.add_field(name="┌───────────────────┐", value="", inline=False)
                    embed.add_field(name="STATUS:", value="PING SUCCESSFUL", inline=True)
                    embed.add_field(name="PROTOCOL:", value="RANDOM_SELECT_v2.5", inline=True)
                    embed.add_field(name="└───────────────────┘", value="", inline=False)
                    
                    # Add the GIF
                    embed.set_image(url=gif_url)
                    
                    # Add futuristic footer
                    embed.set_footer(text=f"SYSTEM: Auto-Ping v3.0 | NEXT SEQUENCE: T+6h")
                    
                    try:
                        await channel.send(embed=embed)
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
        
        # Load all guild configs
        for guild in self.bot.guilds:
            config = self._load_guild_config(guild.id)
            
            if config["enabled"]:
                next_ping = self._get_next_ping_time(config)
                if next_ping:
                    # Update config with the calculated next ping time
                    config["next_ping"] = next_ping.timestamp()
                    self._save_guild_config(guild.id, config)
    
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
                  f"`{ctx.prefix}pinger include @role` - Include previously excluded role",
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
        
        # Calculate next ping time (6 hours from now)
        next_ping = datetime.datetime.utcnow() + datetime.timedelta(hours=6)
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
        exclude_role_ids = config["exclude_roles"]
        eligible_members = []
        
        for member in ctx.guild.members:
            if member.bot:
                continue
                
            # Skip members with excluded roles
            if any(role.id in exclude_role_ids for role in member.roles):
                continue
            
            eligible_members.append(member)
        
        if not eligible_members:
            await ctx.send("⚠️ TARGET ERROR: No eligible members found for ping test.")
            return
        
        # Choose a random member
        member = random.choice(eligible_members)
        
        # Choose a random ping message
        message = random.choice(self.ping_messages).format(member=member.mention)
        
        # Choose a random GIF
        gif_url = random.choice(self.gif_urls)
        
        # Create a test embed with futuristic styling
        embed = discord.Embed(
            title="⚡ TEST PING SEQUENCE INITIATED ⚡",
            description=message,
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
        
        # Add the GIF
        embed.set_image(url=gif_url)
        
        # Add futuristic footer
        embed.set_footer(text=f"TEST REQUEST: {ctx.author.name} | TIMESTAMP: {datetime.datetime.utcnow().strftime('%H:%M:%S')}")
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(SarcasticPinger(bot))