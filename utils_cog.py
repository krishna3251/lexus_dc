import discord
from discord.ext import commands
import re
import asyncio
import json
import os
from typing import Union, Optional, Dict, List, Any
import datetime
import random
import string

# Regular expressions
URL_REGEX = re.compile(r"(https?://[^\s]+)")
INVITE_REGEX = re.compile(r"(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|discordapp\.com/invite)/([a-zA-Z0-9-]+)")
EMOJI_REGEX = re.compile(r"<a?:[a-zA-Z0-9_]+:[0-9]+>")
MENTION_REGEX = re.compile(r"<@!?[0-9]+>|<@&[0-9]+>|<#[0-9]+>")

def is_url(text: str) -> bool:
    """Check if text contains a URL"""
    return bool(URL_REGEX.search(text))

def is_invite(text: str) -> bool:
    """Check if text contains a Discord invite"""
    return bool(INVITE_REGEX.search(text))

def count_emojis(text: str) -> int:
    """Count custom emojis in text"""
    return len(EMOJI_REGEX.findall(text))

def count_mentions(text: str) -> int:
    """Count mentions in text"""
    return len(MENTION_REGEX.findall(text))

def format_time(seconds: int) -> str:
    """Format seconds into a human-readable time string"""
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} and {seconds} second{'s' if seconds != 1 else ''}"
    
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''}, {minutes} minute{'s' if minutes != 1 else ''}"
    
    days, hours = divmod(hours, 24)
    return f"{days} day{'s' if days != 1 else ''}, {hours} hour{'s' if hours != 1 else ''}"

def format_time_short(seconds: int) -> str:
    """Format seconds into a short time string (e.g., 1d 2h 3m 4s)"""
    if seconds < 60:
        return f"{seconds}s"
    
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m"
    
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"

def clean_text(text: str) -> str:
    """Clean text by removing mentions, invite links, etc."""
    # Replace mentions with plain text
    text = MENTION_REGEX.sub("[mention]", text)
    # Replace invite links
    text = INVITE_REGEX.sub("[invite]", text)
    # Replace other URLs
    text = URL_REGEX.sub("[link]", text)
    return text

class Paginator:
    """
    A class that helps paginate embeds
    """
    def __init__(self, ctx, pages: List[discord.Embed], timeout: int = 60):
        self.ctx = ctx
        self.pages = pages
        self.timeout = timeout
        self.current_page = 0
        self.controls = ["⏮️", "◀️", "⏹️", "▶️", "⏭️"]
        self.message = None
    
    async def run(self):
        """Start the paginator"""
        if not self.pages:
            return
        
        if len(self.pages) == 1:
            # Only one page, just send it without controls
            return await self.ctx.send(embed=self.pages[0])
        
        # Set initial page number
        for i, page in enumerate(self.pages):
            footer_text = page.footer.text if page.footer else ""
            if not footer_text.endswith(f"Page {i+1}/{len(self.pages)}"):
                if footer_text:
                    footer_text += f" • Page {i+1}/{len(self.pages)}"
                else:
                    footer_text = f"Page {i+1}/{len(self.pages)}"
                page.set_footer(text=footer_text)
        
        # Send the initial page
        self.message = await self.ctx.send(embed=self.pages[0])
        
        # Add reaction controls
        for control in self.controls:
            await self.message.add_reaction(control)
        
        def check(reaction, user):
            return (
                user == self.ctx.author
                and reaction.message.id == self.message.id
                and str(reaction.emoji) in self.controls
            )
        
        while True:
            try:
                reaction, user = await self.ctx.bot.wait_for(
                    "reaction_add", timeout=self.timeout, check=check
                )
                
                # Remove user's reaction
                try:
                    await self.message.remove_reaction(reaction, user)
                except (discord.Forbidden, discord.HTTPException):
                    pass
                
                # Process the reaction
                if str(reaction.emoji) == "⏮️":  # First page
                    self.current_page = 0
                elif str(reaction.emoji) == "◀️":  # Previous page
                    self.current_page = max(0, self.current_page - 1)
                elif str(reaction.emoji) == "⏹️":  # Stop
                    try:
                        await self.message.clear_reactions()
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                    break
                elif str(reaction.emoji) == "▶️":  # Next page
                    self.current_page = min(len(self.pages) - 1, self.current_page + 1)
                elif str(reaction.emoji) == "⏭️":  # Last page
                    self.current_page = len(self.pages) - 1
                
                # Update the message with the new page
                await self.message.edit(embed=self.pages[self.current_page])
                
            except asyncio.TimeoutError:
                # Timeout, clear reactions
                try:
                    await self.message.clear_reactions()
                except (discord.Forbidden, discord.HTTPException):
                    pass
                break

async def send_error(ctx, title: str, description: str):
    """Send an error message"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)

async def send_success(ctx, title: str, description: str):
    """Send a success message"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

async def send_info(ctx, title: str, description: str):
    """Send an info message"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=0x3a9efa
    )
    await ctx.send(embed=embed)

async def confirm_action(ctx, title: str, description: str, timeout: int = 60) -> bool:
    """Ask for confirmation before performing an action"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.gold()
    )
    embed.set_footer(text="React with ✅ to confirm or ❌ to cancel")
    
    message = await ctx.send(embed=embed)
    await message.add_reaction("✅")
    await message.add_reaction("❌")
    
    def check(reaction, user):
        return (
            user == ctx.author
            and reaction.message.id == message.id
            and str(reaction.emoji) in ["✅", "❌"]
        )
    
    try:
        reaction, _ = await ctx.bot.wait_for("reaction_add", timeout=timeout, check=check)
        await message.delete()
        return str(reaction.emoji) == "✅"
    except asyncio.TimeoutError:
        await message.delete()
        return False

def load_json(file_path: str, default: Dict = None) -> Dict:
    """Load data from a JSON file"""
    if default is None:
        default = {}
    
    if not os.path.exists(file_path):
        return default
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return default

def save_json(file_path: str, data: Dict) -> bool:
    """Save data to a JSON file"""
    try:
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
            
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return True
    except (IOError, OSError, json.JSONDecodeError):
        return False

def get_guild_data(guild_id: int, file_name: str, default: Dict = None) -> Dict:
    """Get data for a specific guild"""
    if default is None:
        default = {}
    
    if not os.path.exists("data"):
        os.makedirs("data")
        
    file_path = f"data/{guild_id}_{file_name}.json"
    return load_json(file_path, default)

def save_guild_data(guild_id: int, file_name: str, data: Dict) -> bool:
    """Save data for a specific guild"""
    if not os.path.exists("data"):
        os.makedirs("data")
        
    file_path = f"data/{guild_id}_{file_name}.json"
    return save_json(file_path, data)

def generate_id() -> str:
    """Generate a random alphanumeric ID"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

def has_guild_permissions(**perms):
    """Check if the user has guild permissions"""
    original = commands.has_guild_permissions(**perms).predicate
    
    async def extended_check(ctx):
        if ctx.guild is None:
            return False
            
        # Check if the user is the guild owner
        if ctx.author.id == ctx.guild.owner_id:
            return True
            
        # Check the original permissions
        return await original(ctx)
    
    return commands.check(extended_check)

def human_timedelta(dt: datetime.datetime) -> str:
    """Return a human readable time delta from now"""
    now = datetime.datetime.utcnow()
    delta = now - dt
    
    seconds = delta.total_seconds()
    if seconds < 60:
        return f"{int(seconds)} seconds ago"
    
    minutes = seconds / 60
    if minutes < 60:
        return f"{int(minutes)} minutes ago"
    
    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)} hours ago"
    
    days = hours / 24
    if days < 7:
        return f"{int(days)} days ago"
    
    weeks = days / 7
    if weeks < 4:
        return f"{int(weeks)} weeks ago"
    
    months = days / 30.5
    if months < 12:
        return f"{int(months)} months ago"
    
    years = days / 365
    return f"{int(years)} years ago"

def get_emoji_percentage(percentage: float) -> str:
    """Get an emoji representation of a percentage"""
    if percentage >= 90:
        return "🟢"  # Green circle
    elif percentage >= 70:
        return "🟡"  # Yellow circle
    elif percentage >= 40:
        return "🟠"  # Orange circle
    else:
        return "🔴"  # Red circle

def trim_text(text: str, max_length: int = 500) -> str:
    """Trim text to a maximum length"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def create_bar(value: int, max_value: int, size: int = 10) -> str:
    """Create a progress bar"""
    if max_value <= 0:
        return "▒" * size
        
    percentage = min(1, max(0, value / max_value))
    filled = int(size * percentage)
    empty = size - filled
    
    return "█" * filled + "▒" * empty

class EmbedColors:
    """Standard colors for embeds"""
    SUCCESS = 0x2ECC71  # Green
    ERROR = 0xE74C3C    # Red
    WARNING = 0xF1C40F  # Yellow
    INFO = 0x3498DB     # Blue
    DEFAULT = 0x3A9EFA  # Light blue
    PURPLE = 0x9B59B6   # Purple
    ORANGE = 0xE67E22   # Orange
    GRAY = 0x95A5A6     # Gray
