import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
import aiohttp
import os
import logging
from datetime import datetime
import json

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Sarcastic color scheme because why not
COLORS = {
    "primary": discord.Color.from_rgb(114, 137, 218),
    "success": discord.Color.from_rgb(87, 242, 135),
    "warning": discord.Color.from_rgb(255, 149, 0),
    "error": discord.Color.from_rgb(255, 89, 89),
    "info": discord.Color.from_rgb(59, 165, 255),
    "cyber": discord.Color.from_rgb(0, 255, 240),
    "sarcasm": discord.Color.from_rgb(170, 0, 255)
}

# Emojis for the peasants who need visual cues
EMOJIS = {
    "Music": "🎵", "Moderation": "🚔", "Fun": "🎪", "Utility": "🔧",
    "GifCog": "📸", "SarcasticPinger": "📡", "SlashCommandsCog": "⚡",
    "General": "💼", "Economy": "💰", "AI": "🤖", "Gaming": "🎮",
    "Stats": "📈", "Help": "❓"
}

# Sarcastic responses because regular help is too mainstream
SARCASTIC_RESPONSES = [
    "Oh look, another person who can't figure out commands...",
    "Wow, using help? Revolutionary thinking right there!",
    "Let me guess, you tried clicking random buttons first?",
    "Amazing! Someone actually reading documentation in 2025!",
    "Help menu activated. Prepare for enlightenment... or disappointment.",
    "Here's your participation trophy for using help.",
    "Congrats! You've discovered the ancient art of RTFM!"
]

# AI sarcasm because regular AI is too polite
AI_SARCASM = [
    "The AI thinks your question is... interesting.",
    "Processing your 'brilliant' query through neural networks...",
    "AI response incoming. Brace for impact.",
    "The machines are judging your question right now...",
    "Loading AI wisdom (this might take a while for you)..."
]

class SarcasticHelpCog(commands.Cog, name="Help"):
    """The help system you never knew you didn't want"""
    
    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.getenv("NVIDIA_API_KEY", "")
        self.ai_client = None
        self.command_cache = {}
        
        if self.api_key and OPENAI_AVAILABLE:
            self._init_ai()
        
        logging.info("🎭  Help System Online - Humanity is doomed")
    
    def _init_ai(self):
        """Initialize AI because humans need artificial help"""
        try:
            self.ai_client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=self.api_key
            )
        except Exception as e:
            logging.error(f"AI failed to initialize. Typical. {e}")
    
    def _build_command_cache(self):
        """Cache commands because loading them every time is for peasants"""
        if self.command_cache:
            return self.command_cache
        
        cache = {}
        for cog_name, cog in self.bot.cogs.items():
            if cog_name == "Help":
                continue
                
            commands = []
            for cmd in cog.get_commands():
                commands.append({
                    "name": cmd.name,
                    "help": cmd.help or "Description MIA (typical)",
                    "usage": f"lx {cmd.name}",
                    "aliases": getattr(cmd, 'aliases', [])
                })
            
            # Add slash commands if they exist
            if hasattr(cog, 'get_app_commands'):
                for app_cmd in cog.get_app_commands():
                    commands.append({
                        "name": app_cmd.name,
                        "help": app_cmd.description or "Another undocumented command",
                        "usage": f"/{app_cmd.name}",
                        "aliases": []
                    })
            
            if commands:
                cache[cog_name] = commands
        
        self.command_cache = cache
        return cache
    
    async def _get_ai_response(self, query):
        """Get AI response with extra sarcasm"""
        if not self.ai_client or not OPENAI_AVAILABLE:
            return "AI is sleeping. Try thinking for yourself for once."
        
        try:
            system_prompt = """You are a sarcastic Discord bot assistant. 
            Keep responses SHORT (max 200 chars), helpful but snarky. 
            Don't be mean, just playfully sarcastic."""
            
            completion = await asyncio.to_thread(
                lambda: self.ai_client.chat.completions.create(
                    model="nvidia/llama-3.1-nemotron-ultra-253b-v1",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": query}
                    ],
                    max_tokens=100,
                    temperature=0.8
                )
            )
            
            return completion.choices[0].message.content[:200]
        except:
            return "AI had an existential crisis. Try again later."

class CategorySelect(discord.ui.Select):
    """Dropdown for people who can't remember command names"""
    
    def __init__(self, help_cog):
        self.help_cog = help_cog
        
        # Build options with extra sass
        options = []
        cache = help_cog._build_command_cache()
        
        for cog_name in sorted(cache.keys()):
            emoji = EMOJIS.get(cog_name, "🤷")
            cmd_count = len(cache[cog_name])
            options.append(discord.SelectOption(
                label=cog_name,
                value=cog_name,
                emoji=emoji,
                description=f"{cmd_count} commands (good luck)"
            ))
        
        if not options:
            options.append(discord.SelectOption(
                label="Nothing here",
                value="empty",
                emoji="🗿",
                description="Absolutely nothing to see"
            ))
        
        super().__init__(
            placeholder="🎯 Pick your poison...",
            options=options[:25]  # Discord limit
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle category selection with style"""
        category = self.values[0]
        
        if category == "empty":
            embed = discord.Embed(
                title="🗿 VOID DETECTED",
                description="Congratulations! You found nothing.",
                color=COLORS["warning"]
            )
            await interaction.response.edit_message(embed=embed)
            return
        
        cache = self.help_cog._build_command_cache()
        commands = cache.get(category, [])
        
        if not commands:
            embed = discord.Embed(
                title="🔍 404: COMMANDS NOT FOUND",
                description=f"The '{category}' module is emptier than my patience.",
                color=COLORS["error"]
            )
            await interaction.response.edit_message(embed=embed)
            return
        
        # Create compact command list
        embed = discord.Embed(
            title=f"{EMOJIS.get(category, '📦')} {category.upper()}",
            description=f"*{random.choice(['Here we go again...', 'Buckle up buttercup', 'Another module exploration', 'Let the confusion begin'])}*",
            color=COLORS["primary"]
        )
        
        # Group commands efficiently
        cmd_lines = []
        for cmd in commands[:15]:  # Limit to prevent embed bloat
            aliases = f" ({', '.join(cmd['aliases'])})" if cmd['aliases'] else ""
            cmd_lines.append(f"`{cmd['usage']}`{aliases} - {cmd['help'][:50]}{'...' if len(cmd['help']) > 50 else ''}")
        
        embed.add_field(
            name=f"📋 Commands ({len(commands)} total)",
            value="\n".join(cmd_lines) if cmd_lines else "Empty. Shocking.",
            inline=False
        )
        
        if len(commands) > 15:
            embed.add_field(
                name="⚠️ Truncated",
                value=f"Showing 15/{len(commands)} commands. Use AI help for more.",
                inline=False
            )
        
        embed.set_footer(text=f"Module: {category} • {datetime.now().strftime('%H:%M')} • Try not to break anything")
        await interaction.response.edit_message(embed=embed)

class HelpView(discord.ui.View):
    """Interactive view for the terminally confused"""
    
    def __init__(self, help_cog):
        super().__init__(timeout=60)
        self.help_cog = help_cog
        self.add_item(CategorySelect(help_cog))
    
    @discord.ui.button(label="🏠 HOME", style=discord.ButtonStyle.primary)
    async def home_button(self, interaction: discord.Interaction, button):
        """Return to main menu because people get lost"""
        embed = self._create_main_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="🤖 ASK AI", style=discord.ButtonStyle.secondary)
    async def ai_button(self, interaction: discord.Interaction, button):
        """AI button for the truly desperate"""
        embed = discord.Embed(
            title="🤖 AI CONSULTATION",
            description=f"{random.choice(AI_SARCASM)}\n\nUse `/lex your question here` or `lx  your question`",
            color=COLORS["cyber"]
        )
        
        if not OPENAI_AVAILABLE:
            embed.add_field(
                name="❌ AI Unavailable",
                value="Install OpenAI module first: `pip install openai`",
                inline=False
            )
        elif not self.help_cog.api_key:
            embed.add_field(
                name="🔑 No API Key",
                value="Set NVIDIA_API_KEY environment variable",
                inline=False
            )
        else:
            embed.add_field(
                name="✅  Status",
                value="Ready to judge your questions",
                inline=False
            )
        
        embed.set_footer(text="AI responses may contain traces of sarcasm")
        await interaction.response.edit_message(embed=embed, view=self)
    
    def _create_main_embed(self):
        """Create the main help embed with maximum sass"""
        cache = self.help_cog._build_command_cache()
        total_commands = sum(len(cmds) for cmds in cache.values())
        
        embed = discord.Embed(
            title="🎭 HELP SYSTEM ",
            description=f"*{random.choice(SARCASTIC_RESPONSES)}*\n\n"
                       f"**{total_commands}** commands across **{len(cache)}** modules.",
            color=COLORS["sarcasm"]
        )
        
        # Quick stats
        embed.add_field(
            name="📊 Quick Stats",
            value=f"```yaml\nBot: {self.help_cog.bot.user.name}\n"
                  f"Latency: {round(self.help_cog.bot.latency * 1000)}ms\n"
                  f"Commands: {total_commands}\n"
                  f"Modules: {len(cache)}```",
            inline=True
        )
        
        # Top modules
        top_modules = sorted(cache.items(), key=lambda x: len(x[1]), reverse=True)[:5]
        module_list = "\n".join([f"{EMOJIS.get(name, '📦')} {name}: {len(cmds)} cmds" 
                                for name, cmds in top_modules])
        
        embed.add_field(
            name="🏆 Top Modules",
            value=module_list or "Nothing here",
            inline=True
        )
        
        embed.add_field(
            name="💡 Pro Tips",
            value="• Use dropdown to browse\n• Ask AI for complex help\n• RTFM occasionally",
            inline=False
        )
        
        embed.set_footer(text=f"⏰ Auto-timeout: 60s • {datetime.now().strftime('%H:%M')}")
        
        if self.help_cog.bot.user.display_avatar:
            embed.set_thumbnail(url=self.help_cog.bot.user.display_avatar.url)
        
        return embed

    async def on_timeout(self):
        """Handle timeout with style"""
        try:
            embed = discord.Embed(
                title="⏰ TIMEOUT",
                description="Help interface died from neglect.\nUse help command to resurrect it.",
                color=COLORS["warning"]
            )
            if hasattr(self, 'message') and self.message:
                await self.message.edit(embed=embed, view=None)
        except:
            pass

# Main Help Commands
class SarcasticHelpCog(SarcasticHelpCog):
    """The help system you never knew you didn't want"""
    
    @app_commands.command(name="help", description="🎭 Interactive help system with attitude")
    async def help_slash(self, interaction: discord.Interaction):
        view = HelpView(self)
        embed = view._create_main_embed()
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)
        view.message = await interaction.original_response()
    
    @commands.command(name="help", help="🎭 Interactive help system with maximum sass")
    async def help_prefix(self, ctx):
        view = HelpView(self)
        embed = view._create_main_embed()
        
        message = await ctx.send(embed=embed, view=view)
        view.message = message
    
    # AI Commands with sarcasm
    @app_commands.command(name="ai", description="🤖 Ask about commands (if you dare)")
    async def ai_slash(self, interaction: discord.Interaction, query: str):
        if not OPENAI_AVAILABLE:
            await interaction.response.send_message("AI is MIA. Install OpenAI module.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        response = await self._get_ai_response(query)
        
        embed = discord.Embed(
            title="🤖  VERDICT",
            description=f"**Query:** {query[:100]}{'...' if len(query) > 100 else ''}\n\n**Response:** {response}",
            color=COLORS["cyber"]
        )
        embed.set_footer(text=f"User: {interaction.user} • {datetime.now().strftime('%H:%M')}")
        
        await interaction.followup.send(embed=embed)
    
    @commands.command(name="ai", help="🤖 Ask AI about bot features")
    async def ai_prefix(self, ctx, *, query=None):
        if not query:
            embed = discord.Embed(
                title="🤖  CONSULTATION",
                description="Usage: `lexus  your question here`\n\nExample: `lx ai how do moderation commands work?`",
                color=COLORS["info"]
            )
            await ctx.send(embed=embed)
            return
        
        if not OPENAI_AVAILABLE:
            await ctx.send("AI is taking a nap. Install OpenAI module first.")
            return
        
        async with ctx.typing():
            response = await self._get_ai_response(query)
        
        embed = discord.Embed(
            title="🤖 RESULT",
            description=f"**Your Question:** {query[:150]}{'...' if len(query) > 150 else ''}\n\n**AI Response:** {response}",
            color=COLORS["cyber"]
        )
        embed.set_footer(text=f"Consulted by: {ctx.author} • {datetime.now().strftime('%H:%M')}")
        
        await ctx.send(embed=embed)
    
    # Quick commands for lazy people
    @commands.command(name="commands", help="📝 Quick command list without the interface")
    async def quick_commands(self, ctx, category=None):
        cache = self._build_command_cache()
        
        if not category:
            # List all categories
            categories = list(cache.keys())
            embed = discord.Embed(
                title="📝 COMMAND CATEGORIES",
                description=f"Available categories: `{'`, `'.join(categories)}`\n\nUsage: `lx commands <category>`",
                color=COLORS["info"]
            )
            await ctx.send(embed=embed)
            return
        
        # Find matching category (case insensitive)
        matching_cat = None
        for cat in cache.keys():
            if cat.lower() == category.lower():
                matching_cat = cat
                break
        
        if not matching_cat:
            await ctx.send(f"Category '{category}' not found. Use `lx commands` to see available categories.")
            return
        
        commands = cache[matching_cat]
        cmd_list = "\n".join([f"`{cmd['usage']}` - {cmd['help'][:60]}{'...' if len(cmd['help']) > 60 else ''}" 
                             for cmd in commands[:20]])
        
        embed = discord.Embed(
            title=f"📋 {matching_cat.upper()} COMMANDS",
            description=cmd_list or "Empty category (shocking)",
            color=COLORS["primary"]
        )
        
        if len(commands) > 20:
            embed.set_footer(text=f"Showing 20/{len(commands)} commands")
        
        await ctx.send(embed=embed)
    
    @commands.command(name="refreshhelp", help="🔄 Refresh command cache", hidden=True)
    @commands.is_owner()
    async def refresh_cache(self, ctx):
        """Owner-only command to refresh the cache"""
        old_count = sum(len(cmds) for cmds in self.command_cache.values()) if self.command_cache else 0
        self.command_cache.clear()
        new_cache = self._build_command_cache()
        new_count = sum(len(cmds) for cmds in new_cache.values())
        
        embed = discord.Embed(
            title="🔄 CACHE REFRESHED",
            description=f"Command cache updated successfully.",
            color=COLORS["success"]
        )
        embed.add_field(
            name="📊 Stats",
            value=f"Before: {old_count} commands\nAfter: {new_count} commands",
            inline=False
        )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(SarcasticHelpCog(bot))
    logging.info("🎭 Aap ke liye hazir mailk")
