import discord
from discord.ext import commands
from discord import app_commands
import os
import logging
from datetime import datetime
import json
import aiohttp
import asyncio
import google.generativeai as genai

# Enhanced futuristic color scheme
COLORS = {
    "primary": discord.Color.from_rgb(114, 137, 218),  # Discord blurple
    "secondary": discord.Color.from_rgb(88, 101, 242),  # New Discord blurple
    "success": discord.Color.from_rgb(87, 242, 135),   # Neon green
    "warning": discord.Color.from_rgb(255, 149, 0),    # Cyberpunk orange
    "error": discord.Color.from_rgb(255, 89, 89),      # Neon red
    "info": discord.Color.from_rgb(59, 165, 255),      # Holographic blue
    "tech": discord.Color.from_rgb(32, 34, 37),        # Discord dark
    "cyber": discord.Color.from_rgb(0, 255, 240),      # Cyberpunk cyan
    "future": discord.Color.from_rgb(170, 0, 255),     # Futuristic purple
    "neon": discord.Color.from_rgb(255, 0, 127),       # Neon pink
    "matrix": discord.Color.from_rgb(0, 255, 65)       # Matrix green
}

# Command reference dictionary to store command details
# This will be populated when the bot loads
COMMAND_REFERENCE = {}

# ASCII art for futuristic flair
ASCII_ART = """
╔═══════════════════════════════════════════╗
║  █▀▀▀█ █▀▀█ ▀▀█▀▀ ▀█▀ █▀▀ ▀█▀ █▀▀ ▀█▀ █▀▀█ █░░  ║
║  █░░░█ █▄▄▀ ░░█░░ ░█░ █▀▀ ░█░ █░░ ░█░ █░░█ █░░  ║
║  █▄▄▄█ ▀░▀▀ ░░▀░░ ▄█▄ ▀░░ ▄█▄ ▀▀▀ ▀▀▀ █▀▀▀ ▀▀▀  ║
╚═══════════════════════════════════════════╝
"""

class AIHelp(commands.Cog):
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
                title="🤖 NEURAL INTERFACE ASSISTANT",
                description="Access the AI knowledge matrix about commands and features!",
                color=COLORS["cyber"]
            )
            embed.add_field(
                name="QUERY SYNTAX",
                value="```lx ai how do I use moderation commands?```",
                inline=False
            )
            embed.set_footer(text=f"USER: {ctx.author} • TIME: {datetime.now().strftime('%H:%M:%S')}")
            await ctx.send(embed=embed)
            return
        
        # Show typing indicator while generating response
        async with ctx.typing():
            # Get command context if available
            context = self.get_command_context(query)
            
            # Generate response
            response = await self.generate_ai_response(query, context)
            
            embed = discord.Embed(
                title="🤖 NEURAL INTERFACE RESPONSE",
                description=response[:4000] if response else "I couldn't generate a response. Please try again.",
                color=COLORS["cyber"]
            )
            
            # Add a divider for visual appeal
            embed.add_field(
                name="⚡ CONNECTION STATUS",
                value="```Neural interface active and functioning optimally```",
                inline=False
            )
            
            embed.set_footer(text=f"USER: {ctx.author} • TIMESTAMP: {datetime.now().strftime('%H:%M:%S')}")
        
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
            title="🤖 NEURAL INTERFACE RESPONSE",
            description=response[:4000] if response else "I couldn't generate a response. Please try again.",
            color=COLORS["cyber"]
        )
        
        # Add a divider for visual appeal
        embed.add_field(
            name="⚡ CONNECTION STATUS",
            value="```Neural interface active and functioning optimally```",
            inline=False
        )
        
        embed.set_footer(text=f"USER: {interaction.user} • TIMESTAMP: {datetime.now().strftime('%H:%M:%S')}")
        
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
            title="🔄 NEURAL DATABASE RECALIBRATED",
            description=f"Command reference matrix has been updated and optimized.",
            color=COLORS["success"]
        )
        embed.add_field(
            name="SYSTEM METRICS",
            value=f"```diff\n- Previous commands: {old_count}\n+ Current commands: {new_count}\n```",
            inline=False
        )
        embed.set_footer(text=f"ADMIN: {ctx.author} • TIMESTAMP: {datetime.now().strftime('%H:%M:%S')}")
        
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
                title=f"🧠 NEURAL INTERFACE HELP: {query.upper()}",
                description=response[:4000] if response else "I couldn't generate help for that topic.",
                color=COLORS["cyber"]
            )
            
            # Add suggestion to use regular help
            embed.add_field(
                name="📚 ADDITIONAL PROTOCOLS",
                value="Access command database with `lx help` or request more specific information.",
                inline=False
            )
            
            embed.set_footer(text=f"USER: {ctx.author} • TIMESTAMP: {datetime.now().strftime('%H:%M:%S')}")
        
        await ctx.send(embed=embed)

    @commands.command(name="aistatus", help="📊 Check the status of the AI system")
    async def ai_status(self, ctx):
        """Check the status of the AI system"""
        try:
            # Test the AI with a simple query
            is_working = False
            response = "AI system is unavailable"
            
            if self.model:
                test_response = await asyncio.to_thread(
                    lambda: self.model.generate_content("Say 'AI system online'").text
                )
                if test_response and "AI system online" in test_response:
                    is_working = True
                    response = "AI neural network is online and fully operational"
            
            embed = discord.Embed(
                title="📊 AI NEURAL NETWORK STATUS",
                description=f"```css\n[{response}]```",
                color=COLORS["success"] if is_working else COLORS["error"]
            )
            
            # Add system info
            embed.add_field(
                name="🧠 NEURAL MODEL",
                value=f"```Gemini-2.0-Flash```",
                inline=True
            )
            
            embed.add_field(
                name="🔌 CONNECTION STATUS",
                value=f"```{'Connected ✓' if is_working else 'Disconnected ✗'}```",
                inline=True
            )
            
            # Calculate commands in database
            cmd_count = sum(len(cmds) for cmds in COMMAND_REFERENCE.values())
            embed.add_field(
                name="📚 KNOWLEDGE BASE",
                value=f"```{cmd_count} commands indexed```",
                inline=True
            )
            
            embed.set_footer(text=f"STATUS CHECK: {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            embed = discord.Embed(
                title="⚠️ AI SYSTEM ERROR",
                description=f"An error occurred while checking the AI system status.",
                color=COLORS["error"]
            )
            embed.add_field(
                name="ERROR TRACE",
                value=f"```{str(e)[:1000]}```",
                inline=False
            )
            embed.set_footer(text=f"ERROR TIMESTAMP: {datetime.now().strftime('%H:%M:%S')}")
        
        await ctx.send(embed=embed)

    @commands.command(name="aihelp_all", help="📚 Generate AI help documentation for all commands")
    @commands.is_owner()  # Owner only due to potential API usage
    async def generate_all_help(self, ctx):
        """Generate help documentation for all commands using AI"""
        if not self.model:
            if self._setup_model() is False:
                await ctx.send("⚠️ AI service is unavailable. Cannot generate documentation.")
                return
        
        await ctx.send("🔄 Beginning to generate AI documentation for all commands. This may take some time...")
        
        # Count how many commands we'll process
        total_commands = sum(len(cmds) for cmds in COMMAND_REFERENCE.values())
        processed = 0
        
        # Create a progress embed that we'll update
        progress_embed = discord.Embed(
            title="📊 AI DOCUMENTATION GENERATOR",
            description=f"Generating documentation: 0/{total_commands} commands",
            color=COLORS["info"]
        )
        progress_msg = await ctx.send(embed=progress_embed)
        
        # Dictionary to store generated help
        help_docs = {}
        
        try:
            for cog_name, commands in COMMAND_REFERENCE.items():
                help_docs[cog_name] = {}
                
                for cmd in commands:
                    cmd_name = cmd['name']
                    
                    # Update progress
                    processed += 1
                    if processed % 5 == 0 or processed == total_commands:  # Update every 5 cmds or at the end
                        progress_embed.description = f"Generating documentation: {processed}/{total_commands} commands"
                        await progress_msg.edit(embed=progress_embed)
                    
                    # Get context and generate help
                    context = f"Command '{cmd_name}' from module '{cog_name}': {cmd['description']} (Usage: {cmd['usage']})"
                    response = await self.generate_ai_response(f"Explain how to use the {cmd_name} command in detail", context)
                    
                    # Store the result
                    help_docs[cog_name][cmd_name] = {
                        "description": cmd['description'],
                        "usage": cmd['usage'],
                        "ai_help": response
                    }
                    
                    # Avoid rate limiting
                    await asyncio.sleep(0.5)
            
            # Save the generated help to a file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ai_help_docs_{timestamp}.json"
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(help_docs, f, indent=2)
            
            # Final embed
            final_embed = discord.Embed(
                title="✅ AI DOCUMENTATION COMPLETE",
                description=f"Successfully generated AI documentation for {total_commands} commands.",
                color=COLORS["success"]
            )
            final_embed.add_field(
                name="📁 OUTPUT FILE",
                value=f"`{filename}`",
                inline=False
            )
            final_embed.set_footer(text=f"Completed at: {datetime.now().strftime('%H:%M:%S')}")
            
            # Send the file with the embed
            await ctx.send(embed=final_embed, file=discord.File(filename))
            
        except Exception as e:
            error_embed = discord.Embed(
                title="⚠️ DOCUMENTATION GENERATION ERROR",
                description="An error occurred while generating documentation.",
                color=COLORS["error"]
            )
            error_embed.add_field(
                name="Error Details",
                value=f"```{str(e)[:1000]}```",
                inline=False
            )
            error_embed.add_field(
                name="Progress",
                value=f"Processed {processed}/{total_commands} commands before error occurred",
                inline=False
            )
            await ctx.send(embed=error_embed)

async def setup(bot):
    await bot.add_cog(AIHelp(bot))
    logging.info("🤖 AIHelp cog has been added to the bot")
