import discord
from discord.ext import commands
from discord import app_commands
import os
import logging
import google.generativeai as genai
from datetime import datetime
import json
import aiohttp
import asyncio

# The same color scheme from help.py for consistency
COLORS = {
    "primary": discord.Color.from_rgb(114, 137, 218),  # Discord blurple
    "secondary": discord.Color.from_rgb(88, 101, 242),  # New Discord blurple
    "success": discord.Color.from_rgb(87, 242, 135),   # Neon green
    "warning": discord.Color.from_rgb(255, 149, 0),    # Cyberpunk orange
    "error": discord.Color.from_rgb(255, 89, 89),      # Neon red
    "info": discord.Color.from_rgb(59, 165, 255),      # Holographic blue
    "tech": discord.Color.from_rgb(32, 34, 37)         # Discord dark
}

# Command reference dictionary to store command details
# This will be populated when the bot loads
COMMAND_REFERENCE = {}

class AI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self.model = None
        self.generation_config = {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 1024,
        }
        
        # Initialize model if API key exists
        if self.api_key:
            self._setup_model()
            logging.info("🤖 Gemini AI integration initialized")
        else:
            logging.warning("⚠️ GEMINI_API_KEY not found. AI features will be disabled")
    
    def _setup_model(self):
        """Set up the Gemini AI model with the provided API key"""
        try:
            genai.configure(api_key=self.api_key)
            # You can change this to the model of your choice
            self.model = genai.GenerativeModel(
                model_name="gemini-2.0-flash",
                generation_config=self.generation_config
            )
            return True
        except Exception as e:
            logging.error(f"❌ Failed to initialize Gemini AI: {e}")
            return False
    
    def _build_command_reference(self):
        """Build a comprehensive reference of all commands in the bot"""
        reference = {}
        
        # Iterate through all cogs and commands
        for cog_name, cog in self.bot.cogs.items():
            cog_commands = []
            
            # Get regular commands
            for cmd in cog.get_commands():
                cmd_info = {
                    "name": cmd.name,
                    "description": cmd.help or "No description available.",
                    "usage": f"lx {cmd.name}",
                    "aliases": cmd.aliases if hasattr(cmd, 'aliases') else [],
                    "type": "prefix"
                }
                cog_commands.append(cmd_info)
            
            # Get slash commands if available
            if hasattr(cog, "get_app_commands"):
                for app_cmd in cog.get_app_commands():
                    cmd_info = {
                        "name": app_cmd.name,
                        "description": app_cmd.description or "No description available.",
                        "usage": f"/{app_cmd.name}",
                        "type": "slash"
                    }
                    cog_commands.append(cmd_info)
            
            # Store in reference dictionary if commands exist
            if cog_commands:
                reference[cog_name] = cog_commands
        
        return reference
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Build command reference when bot is ready"""
        global COMMAND_REFERENCE
        COMMAND_REFERENCE = self._build_command_reference()
        logging.info(f"📚 Built command reference with {sum(len(cmds) for cmds in COMMAND_REFERENCE.values())} commands")
    
    async def generate_ai_response(self, query, context=None):
        """Generate a response from Gemini AI model"""
        if not self.model:
            if self._setup_model() is False:
                return "⚠️ AI service is currently unavailable. Please try again later."
        
        try:
            # Prompt engineering for better results
            system_prompt = """
You are Lexus Bot's AI assistant. You provide helpful, accurate and concise information about Discord bot commands.
When explaining commands, format your response in a clear, structured way with the following details:
- Command name and purpose
- Syntax and usage example
- Parameters or arguments
- Any limitations or special notes

Keep your responses friendly and professional. If you're unsure about a command, say so rather than providing incorrect information.
"""
            # Add command reference context if available
            if context:
                system_prompt += f"\nAdditional context about the command: {context}"
            
            # Prepare the model prompt with the system prompt and user query
            prompt = f"{system_prompt}\n\nUser question: {query}"
            
            # Generate response from Gemini
            response = await asyncio.to_thread(
                lambda: self.model.generate_content(prompt).text
            )
            
            return response
        except Exception as e:
            logging.error(f"❌ Error generating AI response: {e}")
            return f"I encountered an error while processing your request. Please try again later."
    
    def get_command_context(self, query):
        """Extract relevant command information based on user query"""
        query_lower = query.lower()
        context = []
        
        # Look for category/module mentions
        for cog_name, commands in COMMAND_REFERENCE.items():
            if cog_name.lower() in query_lower:
                context.append(f"Module '{cog_name}' contains these commands:")
                for cmd in commands:
                    context.append(f"- {cmd['name']}: {cmd['description']} (Usage: {cmd['usage']})")
                return "\n".join(context)
        
        # Look for specific command mentions
        for cog_name, commands in COMMAND_REFERENCE.items():
            for cmd in commands:
                if cmd['name'].lower() in query_lower:
                    return f"Command '{cmd['name']}' from module '{cog_name}': {cmd['description']} (Usage: {cmd['usage']})"
        
        # If no specific matches, return general command reference
        return None
    
    @commands.command(name="ai", help="🤖 Ask the AI about bot commands and features")
    async def ai_command(self, ctx, *, query=None):
        """Prefix command to interact with the AI assistant"""
        if not query:
            embed = discord.Embed(
                title="🤖 AI ASSISTANT",
                description="Ask me anything about the bot's commands and features!",
                color=COLORS["primary"]
            )
            embed.add_field(
                name="Usage",
                value="```lx ai how do I use moderation commands?```",
                inline=False
            )
            embed.set_footer(text=f"{ctx.author} • {datetime.now().strftime('%H:%M:%S')}")
            await ctx.send(embed=embed)
            return
        
        # Show typing indicator while generating response
        async with ctx.typing():
            # Get command context if available
            context = self.get_command_context(query)
            
            # Generate response
            response = await self.generate_ai_response(query, context)
            
            embed = discord.Embed(
                title="🤖 AI RESPONSE",
                description=response[:4000] if response else "I couldn't generate a response. Please try again.",
                color=COLORS["info"]
            )
            embed.set_footer(text=f"Response for {ctx.author} • {datetime.now().strftime('%H:%M:%S')}")
        
        await ctx.send(embed=embed)
    
    @app_commands.command(name="ai", description="🤖 Ask the AI about bot commands and features")
    async def ai_slash(self, interaction: discord.Interaction, query: str):
        """Slash command to interact with the AI assistant"""
        await interaction.response.defer()
        
        # Get command context if available
        context = self.get_command_context(query)
        
        # Generate response
        response = await self.generate_ai_response(query, context)
        
        embed = discord.Embed(
            title="🤖 AI RESPONSE",
            description=response[:4000] if response else "I couldn't generate a response. Please try again.",
            color=COLORS["info"]
        )
        embed.set_footer(text=f"Response for {interaction.user} • {datetime.now().strftime('%H:%M:%S')}")
        
        await interaction.followup.send(embed=embed)
    
    # Command to rehash AI help database - good for updates
    @commands.command(name="airefresh", help="🔄 Refresh the AI's command knowledge database")
    @commands.is_owner()  # Only bot owner can use this
    async def refresh_ai_database(self, ctx):
        """Refresh the command reference database"""
        global COMMAND_REFERENCE
        old_count = sum(len(cmds) for cmds in COMMAND_REFERENCE.values())
        COMMAND_REFERENCE = self._build_command_reference()
        new_count = sum(len(cmds) for cmds in COMMAND_REFERENCE.values())
        
        embed = discord.Embed(
            title="🔄 AI DATABASE REFRESHED",
            description=f"Command reference database has been updated.",
            color=COLORS["success"]
        )
        embed.add_field(
            name="Statistics",
            value=f"Previous commands: {old_count}\nCurrent commands: {new_count}",
            inline=False
        )
        embed.set_footer(text=f"Refreshed by {ctx.author} • {datetime.now().strftime('%H:%M:%S')}")
        
        await ctx.send(embed=embed)

    # Help command enhancement - enhances the existing help command with AI suggestions
    @commands.command(name="aihelp", help="🧠 Get AI-powered help for a specific command or category")
    async def ai_help(self, ctx, *, query=None):
        """AI-enhanced help command"""
        if not query:
            # Fall back to regular help command
            await ctx.invoke(self.bot.get_command('help'))
            return
        
        async with ctx.typing():
            # Get command context
            context = self.get_command_context(query)
            
            # Generate more detailed help with AI
            response = await self.generate_ai_response(f"Explain how to use {query} in detail", context)
            
            embed = discord.Embed(
                title=f"🧠 AI HELP: {query.upper()}",
                description=response[:4000] if response else "I couldn't generate help for that topic.",
                color=COLORS["info"]
            )
            
            # Add suggestion to use regular help
            embed.add_field(
                name="📚 Need more help?",
                value="Use `lx help` to browse all commands, or ask a more specific question.",
                inline=False
            )
            
            embed.set_footer(text=f"AI Help for {ctx.author} • {datetime.now().strftime('%H:%M:%S')}")
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(AI(bot))
    logging.info("🤖 AI cog has been added to the bot")
