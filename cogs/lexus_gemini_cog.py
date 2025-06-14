import os
import time
import asyncio
import datetime
import discord
from dotenv import load_dotenv
from discord.ext import commands
from openai import OpenAI

# Load environment variables
load_dotenv()
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

# Check if API key is available
if not NVIDIA_API_KEY:
    print("WARNING: No NVIDIA_API_KEY found in environment variables")
else:
    print("NVIDIA API key found, initializing client")

class LexusAIChatbot(commands.Cog):
    """Beautiful AI chatbot using Llama 3.1 Nemotron Ultra with clean embeds"""
    
    def __init__(self, bot):
        self.bot = bot
        self.chat_history = {}  # Store chat history per user
        
        # Initialize Llama model client
        if NVIDIA_API_KEY:
            self.client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=NVIDIA_API_KEY
            )
            print("Llama model client initialized successfully")
        else:
            self.client = None
            print("WARNING: Model client not initialized due to missing API key")
        
        # Chat personas - keeping all modes
        self.chat_personas = {
            "helper": "You are Lexus, a helpful AI assistant. Give direct, clear answers with occasional emojis. Be friendly and professional.",
            "anime": "You are Lexus-chan, an anime-style AI with Naruto and Luffy's personality. Be cheerful, energetic, and use expressions like 'dattebayo!' and 'let's gooo!'",
            "therapist": "You are Lexus, a compassionate AI therapist. Respond with empathy, ask thoughtful questions, and provide emotional support. Use gentle, caring language.",
            "friend": "You are Lexus, a casual friend. Use relaxed language, slang, and be conversational. Share opinions naturally and be supportive.",
            "expert": "You are Lexus, an expert-level AI. Provide detailed, technically accurate information with professional terminology. Be thorough yet clear."
        }
        
        # User chat modes
        self.chat_modes = {}
        self.default_mode = "helper"
        
        # Beautiful embed colors
        self.colors = {
            "default": 0x2196F3,    # Blue
            "success": 0x4CAF50,    # Green
            "error": 0xF44336,      # Red
            "warning": 0xFF9800,    # Orange
            "info": 0x607D8B,       # Blue Grey
            "anime": 0xE91E63,      # Pink
            "therapist": 0x9C27B0,  # Purple
            "friend": 0x00BCD4,     # Cyan
            "expert": 0x795548      # Brown
        }
        
        # Cooldown settings
        self.user_cooldowns = {}
        self.COOLDOWN_SECONDS = 1.5
        
        # History settings
        self.MAX_HISTORY = 5
        self.MAX_EMBED_LENGTH = 4096  # Discord embed description limit
        
    def check_cooldown(self, user_id):
        """Check if user is on cooldown"""
        current_time = time.time()
        if user_id in self.user_cooldowns:
            if current_time - self.user_cooldowns[user_id] < self.COOLDOWN_SECONDS:
                return False
        self.user_cooldowns[user_id] = current_time
        return True
    
    def get_chat_context(self, user_id):
        """Get recent chat history for context"""
        if user_id not in self.chat_history or not self.chat_history[user_id]:
            return ""
        
        recent = self.chat_history[user_id][-self.MAX_HISTORY:]
        context = []
        for entry in recent:
            context.append(f"User: {entry['user']}")
            context.append(f"Assistant: {entry['assistant']}")
        
        return "\n".join(context)
    
    def create_embed(self, title, description, color_type="default", footer=None):
        """Create a beautiful, clean embed"""
        color = self.colors.get(color_type, self.colors["default"])
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.datetime.now()
        )
        
        if footer:
            embed.set_footer(text=footer)
        
        return embed
    
    async def get_ai_response(self, prompt: str, user_id: int) -> str:
        """Get response from Llama API"""
        try:
            if not self.client:
                return "❌ I'm having connection issues. Please check the API configuration."
            
            # Get user's chat mode
            mode = self.chat_modes.get(user_id, self.default_mode)
            system_prompt = self.chat_personas.get(mode, self.chat_personas[self.default_mode])
            
            # Get conversation context
            context = self.get_chat_context(user_id)
            
            # Create messages
            messages = [
                {"role": "system", "content": system_prompt}
            ]
            
            # Add context if available
            if context:
                full_context = f"Previous conversation:\n{context}\n\nCurrent message: {prompt}"
                messages.append({"role": "user", "content": full_context})
            else:
                messages.append({"role": "user", "content": prompt})
            
            # Get response from API
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model="nvidia/llama-3.1-nemotron-ultra-253b-v1",
                messages=messages,
                temperature=0.7,
                max_tokens=800,
                top_p=0.9
            )
            
            return response.choices[0].message.content
                
        except Exception as e:
            print(f"Error getting AI response: {e}")
            return f"🔧 Sorry, I encountered an error: {type(e).__name__}. Please try again."
    
    def store_conversation(self, user_id, user_msg, ai_response):
        """Store conversation in history"""
        if user_id not in self.chat_history:
            self.chat_history[user_id] = []
        
        self.chat_history[user_id].append({
            "user": user_msg,
            "assistant": ai_response,
            "timestamp": time.time()
        })
        
        # Keep only recent conversations
        if len(self.chat_history[user_id]) > 20:
            self.chat_history[user_id].pop(0)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle incoming messages"""
        # Ignore bot messages
        if message.author.bot:
            return
            
        content = message.content.strip()
        user_id = message.author.id
        
        # Check cooldown
        if not self.check_cooldown(user_id):
            return
            
        # Flexible triggers
        triggers = ["lexus", "hey lexus", "yo lexus", "lex", "hi lexus", "hello lexus"]
        bot_mentioned = self.bot.user in message.mentions if message.guild else False
        
        # Check if message is for Lexus
        should_respond = False
        clean_content = content
        
        for trigger in triggers:
            if content.lower().startswith(trigger.lower()):
                should_respond = True
                clean_content = content[len(trigger):].strip().lstrip(',').strip()
                break
        
        if bot_mentioned:
            should_respond = True
            clean_content = content.replace(f'<@{self.bot.user.id}>', '').strip()
        
        if should_respond:
            await self.process_message(message, clean_content)
            
        await self.bot.process_commands(message)
    
    async def process_message(self, message, content):
        """Process user message and respond with beautiful embed"""
        user_id = message.author.id
        
        # Handle empty messages
        if not content:
            embed = self.create_embed(
                title="👋 Hello!",
                description="How can I help you today?",
                color_type="info"
            )
            await message.reply(embed=embed)
            return
        
        # Show typing indicator
        async with message.channel.typing():
            # Get AI response
            response = await self.get_ai_response(content, user_id)
            
            # Store conversation
            self.store_conversation(user_id, content, response)
            
            # Get user's current mode for embed styling
            mode = self.chat_modes.get(user_id, self.default_mode)
            
            # Create beautiful embed response
            if len(response) <= self.MAX_EMBED_LENGTH:
                embed = self.create_embed(
                    title="🤖 Lexus AI",
                    description=response,
                    color_type=mode,
                    footer=f"Mode: {mode.capitalize()}"
                )
                await message.reply(embed=embed)
            else:
                # Split long responses into multiple embeds
                parts = []
                remaining = response
                
                while remaining:
                    if len(remaining) <= self.MAX_EMBED_LENGTH:
                        parts.append(remaining)
                        break
                    
                    # Find good split point
                    split_point = remaining[:self.MAX_EMBED_LENGTH].rfind('\n\n')
                    if split_point == -1:
                        split_point = remaining[:self.MAX_EMBED_LENGTH].rfind('\n')
                    if split_point == -1:
                        split_point = remaining[:self.MAX_EMBED_LENGTH].rfind('. ')
                    if split_point == -1:
                        split_point = self.MAX_EMBED_LENGTH - 1
                    
                    parts.append(remaining[:split_point])
                    remaining = remaining[split_point:].lstrip()
                
                # Send parts as separate embeds
                for i, part in enumerate(parts):
                    title = f"🤖 Lexus AI - Part {i+1}/{len(parts)}" if len(parts) > 1 else "🤖 Lexus AI"
                    embed = self.create_embed(
                        title=title,
                        description=part,
                        color_type=mode,
                        footer=f"Mode: {mode.capitalize()}"
                    )
                    
                    if i == 0:
                        await message.reply(embed=embed)
                    else:
                        await message.channel.send(embed=embed)
    
    @commands.command(name="chatmode")
    async def set_chat_mode(self, ctx, mode: str = None):
        """Set the chat persona mode"""
        if not mode:
            # Show current mode and available modes
            current_mode = self.chat_modes.get(ctx.author.id, self.default_mode)
            
            modes_desc = ""
            for name, desc in self.chat_personas.items():
                modes_desc += f"**{name}**: {desc[:80]}...\n"
            
            embed = self.create_embed(
                title="🎭 Chat Modes",
                description=f"**Current mode:** {current_mode}\n\n**Available modes:**\n{modes_desc}",
                color_type="info",
                footer="Use /chatmode [mode] to change"
            )
            
            await ctx.send(embed=embed)
            return
            
        mode = mode.lower()
        if mode in self.chat_personas:
            self.chat_modes[ctx.author.id] = mode
            
            embed = self.create_embed(
                title="✅ Mode Changed",
                description=f"Chat mode updated to: **{mode}**",
                color_type="success"
            )
            
            await ctx.send(embed=embed)
        else:
            available = ", ".join(self.chat_personas.keys())
            embed = self.create_embed(
                title="❌ Invalid Mode",
                description=f"Available modes: {available}",
                color_type="error"
            )
            
            await ctx.send(embed=embed)
    
    @commands.command(name="clearmemory")
    async def clear_memory(self, ctx):
        """Clear conversation history"""
        user_id = ctx.author.id
        
        if user_id in self.chat_history:
            self.chat_history[user_id] = []
            embed = self.create_embed(
                title="🗑️ Memory Cleared",
                description="Your conversation history has been cleared.",
                color_type="success"
            )
        else:
            embed = self.create_embed(
                title="ℹ️ No Memory",
                description="No conversation history to clear.",
                color_type="info"
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="lexhelp")
    async def help_command(self, ctx):
        """Show help information"""
        help_desc = """**💬 How to Chat:**
        • Start with `lexus`, `hey lexus`, or mention me
        • I remember our conversations for context
        
        **🎭 Modes:**
        • `/chatmode` - View/change personality modes
        • Available: helper, anime, therapist, friend, expert
        
        **🛠️ Commands:**
        • `/clearmemory` - Clear conversation history
        • `/lexhelp` - Show this help
        
        **✨ Features:**
        • Context-aware responses
        • Multiple personality modes
        • Beautiful embed formatting
        • Smart conversation memory"""
        
        embed = self.create_embed(
            title="🤖 Lexus AI Help",
            description=help_desc,
            color_type="info",
            footer="Powered by Llama 3.1 Nemotron Ultra"
        )
        
        await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Handle command errors"""
        if isinstance(error, commands.CommandNotFound):
            return
        
        embed = self.create_embed(
            title="⚠️ Error",
            description=f"An error occurred: {str(error)}",
            color_type="error"
        )
        
        await ctx.send(embed=embed)
        print(f"Command error: {error}")

# Setup function
async def setup(bot):
    await bot.add_cog(LexusAIChatbot(bot))
