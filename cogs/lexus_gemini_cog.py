import os
import re
import time
import asyncio
import datetime
import random
import discord
from dotenv import load_dotenv
from discord.ext import commands
import google.generativeai as genai
from typing import Dict, List, Optional, Union, Tuple

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Check if API key is available
if not GEMINI_API_KEY:
    print("WARNING: No GEMINI_API_KEY found in environment variables")
    print("Please set the GEMINI_API_KEY in your .env file")
else:
    # Configure the Gemini API with the API key
    genai.configure(api_key=GEMINI_API_KEY)

class LexusAIChatbot(commands.Cog):
    """Enhanced pure AI chatbot using Gemini API with futuristic embedded responses"""
    
    def __init__(self, bot):
        self.bot = bot
        self.chat_history = {}  # Store chat history per user
        self.active_conversations = set()  # Track active conversations
        self.emoji_collection = {
            "positive": ["✨", "🚀", "💫", "⭐", "🌟", "✅", "🔮", "💎"],
            "negative": ["⚠️", "❓", "🔄", "🤔", "📝", "📌"],
            "tech": ["🤖", "💻", "🔧", "⚙️", "🛠️", "🔌", "📡", "🔍"],
            "fun": ["🎮", "🎯", "🎲", "🎭", "🎨", "🎬", "🎵", "🎧"],
            "weather": ["☀️", "🌤️", "⛅", "🌥️", "☁️", "🌦️", "🌧️", "⛈️", "🌩️", "🌨️", "❄️", "🌬️"]
        }
        
        # Initialize Gemini model
        if GEMINI_API_KEY:
            self.model = genai.GenerativeModel("gemini-2.0-flash")  # Using gemini-pro
            print("Gemini model initialized successfully")
        else:
            self.model = None
            print("WARNING: Gemini model not initialized due to missing API key")
        
        # Chat personas with system prompts for different conversation styles
        self.chat_personas = {
            "helper": "You are Lexus, an advanced AI assistant. You provide helpful, accurate, and concise responses with a touch of futuristic flair. Add appropriate emojis to your responses and format your answers in a visually appealing way.  when appropriate and make your answers direct and to the point.",
            "anime": "You are Lexus-chan, an anime-style AI with the personality of Naruto and Luffy. You're cheerful, loyal, goofy, and full of energy. You give short, friendly, and optimistic answers with anime-style flair. Use casual speech and fun expressions like 'dattebayo!' and 'let's gooo!' whenever it fits.",
            "therapist": "You are Lexus, a compassionate AI assistant with a calm, supportive demeanor. Respond with empathy and thoughtfulness. Use a gentle tone and encourage self-reflection through open-ended questions. Avoid giving medical advice or diagnosing any conditions.",
            "friend": "You are Lexus, a casual and friendly AI assistant. Talk like a close friend - use casual language, occasional slang, and be conversational. Share opinions and react naturally to topics. Be encouraging and supportive.",
            "expert": "You are Lexus, an expert-level AI assistant. Provide detailed, technically accurate information. Use professional terminology appropriate to the subject. Be thorough yet clear, citing relevant concepts. Focus on depth of knowledge.",
        }
        
        # Default chat mode - updated to futuristic
        self.default_chat_persona = "futuristic"
        self.chat_modes = {}
        
        # Set up logger
        self.setup_logger()

        # Maximum message length for Discord (2000 characters)
        self.MAX_DISCORD_LENGTH = 2000
        
        # Color themes for different message types
        self.color_themes = {
            "default": discord.Color.from_rgb(32, 156, 238),  # Bright blue
            "error": discord.Color.from_rgb(231, 76, 60),     # Red
            "success": discord.Color.from_rgb(46, 204, 113),  # Green
            "warning": discord.Color.from_rgb(241, 196, 15),  # Yellow
            "info": discord.Color.from_rgb(149, 165, 166),    # Gray
            "futuristic": discord.Color.from_rgb(111, 30, 209) # Purple
        }
        
        # Cooldown to prevent spam
        self.user_cooldowns = {}
        self.COOLDOWN_SECONDS = 1.5
        
    def setup_logger(self):
        """Setup enhanced logging system"""
        self.log_dir = "logs"
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Create log file with timestamp
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d")
        self.log_file = f"{self.log_dir}/lexus_chat_log_{timestamp}.txt"
        
        # Log session start with separator
        with open(self.log_file, "a") as f:
            f.write(f"\n{'='*50}\n")
            f.write(f"  NEW SESSION STARTED: {datetime.datetime.now()}\n")
            f.write(f"{'='*50}\n\n")
    
    def log_interaction(self, user_id, user_message, bot_response):
        """Enhanced logging with better formatting"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] User {user_id}:\n{user_message}\n\n[{timestamp}] Lexus:\n{bot_response}\n\n{'-'*50}\n"
        
        # Log to console with color coding
        print(f"\033[94m[{timestamp}] User {user_id}:\033[0m")
        print(f"\033[37m{user_message}\033[0m")
        print(f"\033[92m[{timestamp}] Lexus:\033[0m")
        print(f"\033[37m{bot_response}\033[0m")
        print(f"\033[90m{'-'*50}\033[0m")
        
        # Log to file
        with open(self.log_file, "a") as f:
            f.write(log_entry)
    
    def get_random_emojis(self, category, count=1):
        """Get random emojis from a category"""
        if category in self.emoji_collection:
            return random.sample(self.emoji_collection[category], min(count, len(self.emoji_collection[category])))
        return []
    
    async def get_gemini_response(self, prompt: str, user_id: int = None, system_prompt: str = None) -> str:
        """Get a response from Gemini API with enhanced error handling"""
        try:
            if not self.model:
                return "⚠️ I'm having trouble connecting to my AI backend. Please check the API key configuration."
            
            # Use system prompt if provided, otherwise use user's chat mode
            if system_prompt:
                full_prompt = f"{system_prompt}\n\nUser message: {prompt}"
            else:
                # Use the user's chat mode if set, otherwise default to futuristic
                mode = self.chat_modes.get(user_id, self.default_chat_persona)
                system_prompt = self.chat_personas.get(mode, self.chat_personas[self.default_chat_persona])
                full_prompt = f"{system_prompt}\n\nUser message: {prompt}"
            
            # Create generation config - enhanced parameters for better responses
            generation_config = {
                "temperature": 0.7,
                "top_p": 0.9,
                "top_k": 40,
                "max_output_tokens": 800,
                "candidate_count": 1,
            }
            
            # Generate content using the Gemini model
            response = await asyncio.to_thread(
                self.model.generate_content,
                full_prompt,
                generation_config=generation_config
            )
            
            # Extract text from response
            if hasattr(response, 'text'):
                return response.text
            elif hasattr(response, 'parts'):
                return ''.join([part.text for part in response.parts])
            else:
                # Fallback for unexpected response format
                return str(response)
                
        except Exception as e:
            print(f"Error getting Gemini response: {e}")
            return f"I encountered an error processing your request. Please try again later. {self.get_random_emojis('negative', 1)[0]} (Error: {type(e).__name__})"
    
    async def send_safe_message(self, channel, content, **kwargs):
        """Send message safely, handling character limit restrictions"""
        if len(content) <= self.MAX_DISCORD_LENGTH:
            return await channel.send(content, **kwargs)
        else:
            # Alert that message is too long and will split
            await channel.send("⚠️ My response is quite long, I'll split it into parts:", **kwargs)
            
            # Split message into parts
            parts = []
            remaining = content
            while remaining:
                if len(remaining) <= self.MAX_DISCORD_LENGTH:
                    parts.append(remaining)
                    remaining = ""
                else:
                    # Find a good split point (newline or space)
                    split_point = remaining[:self.MAX_DISCORD_LENGTH].rfind('\n')
                    if split_point == -1 or split_point < self.MAX_DISCORD_LENGTH // 2:
                        split_point = remaining[:self.MAX_DISCORD_LENGTH].rfind(' ')
                    if split_point == -1:  # If no good split found, force split
                        split_point = self.MAX_DISCORD_LENGTH - 1
                    
                    parts.append(remaining[:split_point])
                    remaining = remaining[split_point:].lstrip()
            
            # Send each part with proper formatting
            sent_messages = []
            for i, part in enumerate(parts):
                msg = await channel.send(f"**Part {i+1}/{len(parts)}**\n{part}")
                sent_messages.append(msg)    

            return sent_messages[-1] # Return the last message sent for reference
    
    def create_smart_embed(self, title, description, color_type="default", fields=None, footer=None, thumbnail=None):
        """Create a visually enhanced embed with futuristic styling"""
        # Select color from themes
        color = self.color_themes.get(color_type, self.color_themes["default"])
        
        # Create embed
        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )
        
        # Add fields if provided
        if fields:
            for field in fields:
                embed.add_field(
                    name=field.get("name", "Information"),
                    value=field.get("value", "No data available"),
                    inline=field.get("inline", False)
                )
        
        # Add footer if provided
        if footer:
            embed.set_footer(text=footer)
            
        # Add thumbnail if provided
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
            
        # Get current time for timestamp
        embed.timestamp = datetime.datetime.now()
        
        return embed
    
    def check_cooldown(self, user_id):
        """Check if user is on cooldown to prevent spam"""
        current_time = time.time()
        if user_id in self.user_cooldowns:
            last_time = self.user_cooldowns[user_id]
            if current_time - last_time < self.COOLDOWN_SECONDS:
                return False
        
        # Update last message time
        self.user_cooldowns[user_id] = current_time
        return True
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Enhanced message listener with better pattern recognition"""
        # Ignore bot messages
        if message.author.bot:
            return
            
        # Initial message processing
        content = message.content.strip()
        content_lower = content.lower()
        user_id = message.author.id
        
        # Check for cooldown to prevent spam
        if not self.check_cooldown(user_id):
            return
            
        # More flexible triggers - case insensitive
        start_triggers = [
            "hey lexus", "yo lexus", "lexus,", "lexus", 
            "lex,", "lex", "hi lexus", "hello lexus"
        ]
        
        # Check for mentions of the bot
        bot_mentioned = self.bot.user in message.mentions if message.guild else False
        
        # Check if message starts with a Lexus trigger
        starts_with_trigger = False
        trigger_used = None
        for trigger in start_triggers:
            if content_lower.startswith(trigger):
                starts_with_trigger = True
                trigger_used = trigger
                break
        
        # Process message if it's addressed to Lexus
        if starts_with_trigger:
            # Remove the trigger from the message
            clean_content = content[len(trigger_used):].strip()
            await self.process_message(message, clean_content)
            
        # Process if Lexus was mentioned
        elif bot_mentioned:
            # Remove the mention from the content
            clean_content = content.replace(f'<@{self.bot.user.id}>', '').strip()
            await self.process_message(message, clean_content)
            
        # Process commands as normal
        await self.bot.process_commands(message)
    
    async def process_message(self, message, content):
        """Process user messages with enhanced response generation"""
        user_id = message.author.id
        
        # If message is empty or just punctuation, respond with a helpful message
        if not content or content.strip() in ["?", "!", ".", ",", ";"]:
            tech_emoji = self.get_random_emojis('tech', 1)[0]
            futuristic_response = f"{tech_emoji} Greetings! How may I assist you today? My systems are operational and ready to serve."
            await message.reply(futuristic_response)
            return
            
        # Process with AI with typing indicator
        async with message.channel.typing():
            # First analyze sentiment/intent of the message
            analysis_prompt = f"""
            Analyze this message briefly: "{content}"
            Provide a JSON object with:
            1. "intent": primary purpose (question, greeting, command, chat, etc)
            2. "complexity": simple, moderate, or complex
            3. "sentiment": positive, negative, neutral, or curious
            4. "key_topic": main subject (if any)
            """
            
            try:
                # Get analysis from Gemini
                analysis_response = await self.get_gemini_response(analysis_prompt)
                
                # Parse JSON (handle potential format issues)
                import json
                
                # Clean response text to extract valid JSON
                json_text = analysis_response.strip()
                if '```json' in json_text:
                    json_text = json_text.split('```json')[1].split('```')[0].strip()
                elif '```' in json_text:
                    json_text = json_text.split('```')[1].split('```')[0].strip()
                
                try:
                    analysis = json.loads(json_text)
                except:
                    # Fallback if JSON parsing fails
                    analysis = {
                        "intent": "chat",
                        "complexity": "moderate",
                        "sentiment": "neutral",
                        "key_topic": "general"
                    }
                
                # Generate enhanced response based on analysis
                mode = self.chat_modes.get(user_id, self.default_chat_persona)
                system_prompt = self.chat_personas.get(mode, self.chat_personas[self.default_chat_persona])
                
                # Add additional context based on analysis
                enhanced_prompt = f"""
                {system_prompt}
                
                The user's message appears to be a {analysis.get('complexity', 'moderate')} {analysis.get('intent', 'question')}
                with a {analysis.get('sentiment', 'neutral')} sentiment about {analysis.get('key_topic', 'general topics')}.
                
                User message: {content}
                
                Respond in a way that's appropriate to their intent and sentiment, while maintaining your persona.
                Format your response with elegant structure and appropriate futuristic elements.
                """
                
                # Get enhanced response
                response = await self.get_gemini_response(enhanced_prompt, user_id)
                
                # Determine if we should use embed based on response length and complexity
                use_embed = len(response) > 100 or analysis.get('complexity') == 'complex'
                
                # Store in chat history
                if user_id not in self.chat_history:
                    self.chat_history[user_id] = []
                
                self.chat_history[user_id].append({
                    "user": content,
                    "assistant": response,
                    "timestamp": time.time(),
                    "analysis": analysis
                })
                
                # Limit history size (keep last 20 messages)
                if len(self.chat_history[user_id]) > 20:
                    self.chat_history[user_id].pop(0)
                
                # Log the interaction
                self.log_interaction(user_id, content, response)
                
                # Send response - either as embed or regular message
                if use_embed:
                    # Create futuristic embed with custom formatting
                    title = f"{self.get_random_emojis('tech', 1)[0]} Lexus AI Response"
                    
                    # Create embed with clean formatting
                    embed = self.create_smart_embed(
                        title=title,
                        description=response,
                        color_type="futuristic",
                        footer=f"Mode: {mode.capitalize()} • {datetime.datetime.now().strftime('%H:%M:%S')}"
                    )
                    
                    await message.reply(embed=embed)
                else:
                    # For shorter responses, just send as regular text
                    await message.reply(response)
                    
            except Exception as e:
                print(f"Error in message processing: {e}")
                error_emoji = self.get_random_emojis('negative', 1)[0]
                await message.reply(f"{error_emoji} I encountered an unexpected glitch in my processing matrix. Please try rephrasing your request.")
    
    @commands.command(name="chatmode")
    async def set_chat_mode(self, ctx, mode: str = None):
        """Set the chat persona mode for Lexus"""
        if not mode:
            # Display current mode and available modes
            current_mode = self.chat_modes.get(ctx.author.id, self.default_chat_persona)
            
            # Create visually appealing embed for mode selection
            modes_list = "\n".join([f"• **{name}**: {desc[:50]}..." for name, desc in self.chat_personas.items()])
            
            embed = self.create_smart_embed(
                title=f"{self.get_random_emojis('tech', 1)[0]} Lexus AI Chat Modes",
                description=f"Your current chat mode is: **{current_mode}**\n\n**Available Modes:**\n{modes_list}",
                color_type="info",
                footer="Use /chatmode [mode] to change"
            )
            
            await ctx.send(embed=embed)
            return
            
        mode = mode.lower()
        if mode in self.chat_personas:
            self.chat_modes[ctx.author.id] = mode
            
            # Send confirmation with futuristic flair
            embed = self.create_smart_embed(
                title=f"{self.get_random_emojis('positive', 1)[0]} Mode Change Successful",
                description=f"Chat mode updated to: **{mode}**\n\nAll future interactions will use this conversational framework.",
                color_type="success"
            )
            
            await ctx.send(embed=embed)
        else:
            available_modes = ", ".join(self.chat_personas.keys())
            
            embed = self.create_smart_embed(
                title=f"{self.get_random_emojis('negative', 1)[0]} Mode Selection Error",
                description=f"Unknown chat mode. Available modes: {available_modes}",
                color_type="error"
            )
            
            await ctx.send(embed=embed)
    
    @commands.command(name="lexhelp")
    async def help_command(self, ctx):
        """Enhanced futuristic help command"""
        # Create a visually appealing help embed
        embed = self.create_smart_embed(
            title=f"{self.get_random_emojis('tech', 1)[0]} LEXUS AI NEURAL INTERFACE",
            description="Welcome to the Lexus AI help system. Below are the available interaction protocols:",
            color_type="futuristic"
        )
        
        # Chat section
        embed.add_field(
            name=f"{self.get_random_emojis('tech', 1)[0]} CONVERSATION PROTOCOLS",
            value="• Start messages with `Hey Lexus`, `Lexus`, or mention me directly\n"
                 "• I can answer questions, provide information, or just chat\n"
                 "• My responses adapt to your message style and content",
            inline=False
        )
        
        # Chat modes
        embed.add_field(
            name=f"{self.get_random_emojis('fun', 1)[0]} PERSONALITY MATRICES",
            value="• `/chatmode [mode]` - Change my conversational style\n"
                 "• Available modes: helper, anime, therapist, friend, expert, futuristic\n"
                 "• Default mode: futuristic",
            inline=False
        )
        
        # Add timestamp and version
        current_time = datetime.datetime.now().strftime("%Y.%m.%d")
        embed.set_footer(text=f"Lexus AI v2.0.7 • Neural Core Active • {current_time}")
        
        await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Handle command errors with futuristic styling"""
        if isinstance(error, commands.CommandNotFound):
            return
        
        error_text = str(error)
        
        # Create a user-friendly error message
        prompt = f"""
        Create a friendly, futuristic error message about this Discord bot error: "{error_text}"
        Make it sound like advanced AI terminology but still understandable.
        Frame it as a 'system anomaly' or similar concept.
        Keep it under 100 words.
        """
        
        try:
            response = await self.get_gemini_response(prompt)
            
            embed = self.create_smart_embed(
                title=f"{self.get_random_emojis('negative', 1)[0]} SYSTEM ANOMALY DETECTED",
                description=response,
                color_type="error",
                footer="Error code: " + str(hash(error_text))[:8].upper()
            )
            
            await ctx.send(embed=embed)
        except:
            # Fallback simple error message
            await ctx.send(f"⚠️ An error occurred in my neural pathways: {error_text}")
        
        # Log the error
        print(f"Command error: {error_text}")
        with open(self.log_file, "a") as f:
            f.write(f"[{datetime.datetime.now()}] ERROR: {error_text}\n")

# Setup function for the cog
async def setup(bot):
    await bot.add_cog(LexusAIChatbot(bot))
