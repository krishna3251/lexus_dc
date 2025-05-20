import os
import re
import time
import asyncio
import datetime
import random
import discord
from dotenv import load_dotenv
from discord.ext import commands
from openai import OpenAI
from typing import Dict, List, Optional, Union, Tuple

# Load environment variables
load_dotenv()
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

# Check if API key is available
if not NVIDIA_API_KEY:
    print("WARNING: No NVIDIA_API_KEY found in environment variables")
    print("Please set the NVIDIA_API_KEY in your .env file")
else:
    # Initialize OpenAI client for NVIDIA API access
    print("NVIDIA API key found, initializing client")

class LexusAIChatbot(commands.Cog):
    """Enhanced pure AI chatbot using Llama 3.1 Nemotron Ultra with futuristic embedded responses"""
    
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
        
        # Initialize Llama model client
        if NVIDIA_API_KEY:
            self.client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=NVIDIA_API_KEY
            )
            print("Llama 3.1 Nemotron Ultra model client initialized successfully")
        else:
            self.client = None
            print("WARNING: Llama model client not initialized due to missing API key")
        
        # Chat personas with system prompts for different conversation styles
        self.chat_personas = {
            "helper": "You are Lexus, an advanced desi Indian AI assistant. You provide helpful, accurate, and concise responses with a touch of futuristic flair. Add appropriate emojis to your responses and format your answers in a visually appealing way.  when appropriate and make your answers direct and to the point.",
            "anime": "You are Lexus-chan, an anime-style AI with the personality of Naruto and Luffy. You're cheerful, loyal, goofy, and full of energy. You give short, friendly, and optimistic answers with anime-style flair. Use casual speech and fun expressions like 'dattebayo!' and 'let's gooo!' whenever it fits.",
            "therapist": "You are Lexus, a compassionate AI assistant with a calm, supportive demeanor. Respond with empathy and thoughtfulness. Use a gentle tone and encourage self-reflection through open-ended questions. Avoid giving medical advice or diagnosing any conditions.",
            "friend": "You are Lexus, a casual and friendly AI assistant. Talk like a close friend - use casual language, occasional slang, and be conversational. Share opinions and react naturally to topics. Be encouraging and supportive.",
            "expert": "You are Lexus, an expert-level AI assistant. Provide detailed, technically accurate information. Use professional terminology appropriate to the subject. Be thorough yet clear, citing relevant concepts. Focus on depth of knowledge.",
        }
        
        # Default chat mode - updated to futuristic
        self.default_chat_persona = "helper"
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
        
        # Track common requests and responses for faster replies
        self.common_requests = {}
        
        # Maximum context history to include
        self.MAX_HISTORY_CONTEXT = 5
        
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
    
    def format_chat_history(self, user_id):
        """Format chat history for context in AI prompts"""
        if user_id not in self.chat_history or not self.chat_history[user_id]:
            return ""
        
        # Get the recent conversation history (limited to prevent token overuse)
        recent_history = self.chat_history[user_id][-self.MAX_HISTORY_CONTEXT:]
        
        # Format the history as a conversation
        formatted_history = []
        for entry in recent_history:
            formatted_history.append(f"User: {entry['user']}")
            formatted_history.append(f"Assistant: {entry['assistant']}")
        
        return "\n".join(formatted_history)
    
    async def get_llama_response(self, prompt: str, user_id: int = None, system_prompt: str = None) -> str:
        """Get a response from Llama 3.1 Nemotron Ultra API with enhanced error handling and memory"""
        try:
            if not self.client:
                return "⚠️ I'm having trouble connecting to my AI backend. Please check the API key configuration."
            
            # Get conversation history
            chat_context = ""
            if user_id is not None:
                chat_context = self.format_chat_history(user_id)
            
            # Use system prompt if provided, otherwise use user's chat mode
            if system_prompt:
                mode_prompt = system_prompt
            else:
                # Use the user's chat mode if set, otherwise default to futuristic
                mode = self.chat_modes.get(user_id, self.default_chat_persona)
                mode_prompt = self.chat_personas.get(mode, self.chat_personas[self.default_chat_persona])
            
            # Check for common requests to provide faster responses
            request_hash = hash(f"{mode_prompt}:{prompt}")
            if request_hash in self.common_requests:
                # If we've seen this exact request before, reuse the response 
                # but tell the model to personalize it slightly
                common_response = self.common_requests[request_hash]
                
                # Only use cached response if it's recent (within last 24 hours)
                if time.time() - common_response["timestamp"] < 86400:  # 24 hours in seconds
                    personalization_prompt = f"""
                    I've answered this question before. Here was my previous response:
                    {common_response["response"]}
                    
                    Keep the same information but make it feel like a fresh response.
                    Try to be direct and reference our conversation history if relevant.
                    """
                    
                    # Use the personalization prompt instead of the original one
                    messages = [
                        {"role": "system", "content": f"{mode_prompt}\n\n{personalization_prompt}"},
                        {"role": "user", "content": prompt}
                    ]
                else:
                    # If cached response is old, create messages with context
                    full_context = f"Previous conversation:\n{chat_context}\n\nUser message: {prompt}"
                    messages = [
                        {"role": "system", "content": mode_prompt},
                        {"role": "user", "content": full_context}
                    ]
            else:
                # First time seeing this request, create messages with context
                full_context = f"Previous conversation:\n{chat_context}\n\nUser message: {prompt}"
                messages = [
                    {"role": "system", "content": mode_prompt},
                    {"role": "user", "content": full_context}
                ]
            
            # Generate content using the Llama model via OpenAI client
            response_stream = await asyncio.to_thread(
                self.client.chat.completions.create,
                model="nvidia/llama-3.1-nemotron-ultra-253b-v1",
                messages=messages,
                temperature=0.7,
                top_p=0.95,
                max_tokens=800,
                frequency_penalty=0,
                presence_penalty=0
            )
            
            # Extract text from response
            result_text = response_stream.choices[0].message.content
            
            # Store in common requests cache for faster future responses
            # Only cache if this is a direct user query (not an internal analysis)
            if "Analyze this message briefly" not in prompt and user_id is not None:
                self.common_requests[request_hash] = {
                    "response": result_text,
                    "timestamp": time.time()
                }
            
            return result_text
                
        except Exception as e:
            print(f"Error getting Llama response: {e}")
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
    
    def find_similar_question(self, user_id, question):
        """Find if a similar question was asked before"""
        if user_id not in self.chat_history or not self.chat_history[user_id]:
            return None
        
        question_lower = question.lower()
        
        # Check recent history for similar questions
        for entry in reversed(self.chat_history[user_id]):
            user_msg = entry['user'].lower()
            
            # Simple similarity check - improve this algorithm as needed
            # Check if messages are substantially similar
            if (user_msg == question_lower or 
                (len(question_lower) > 5 and question_lower in user_msg) or
                (len(user_msg) > 5 and user_msg in question_lower)):
                return entry
                
        return None
    
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
        """Process user messages with enhanced response generation and memory"""
        user_id = message.author.id
        
        # If message is empty or just punctuation, respond with a helpful message
        if not content or content.strip() in ["?", "!", ".", ",", ";"]:
            tech_emoji = self.get_random_emojis('tech', 1)[0]
            futuristic_response = f"{tech_emoji} Greetings! How may I assist you today? My systems are operational and ready to serve."
            await message.reply(futuristic_response)
            return
        
        # First check if this is a repeated question
        similar_entry = self.find_similar_question(user_id, content)
        if similar_entry:
            # User asked a similar question before - respond fast with cached answer
            # but with a personalized intro indicating we remember
            tech_emoji = self.get_random_emojis('tech', 1)[0]
            cached_response = similar_entry['assistant']
            
            # Add a personalized intro referencing the previous question
            intro = f"{tech_emoji} I recall you asked about this before. Here's the information again:"
            
            # Sometimes provide a shorter version of the previous response for variety
            if len(cached_response) > 150 and random.random() > 0.5:
                summarization_prompt = f"""
                Summarize this previous response in a shorter form while maintaining the key information:
                {cached_response}
                
                Keep it concise but accurate.
                """
                
                shortened_response = await self.get_llama_response(summarization_prompt)
                enhanced_response = f"{intro}\n\n{shortened_response}\n\n*Note: This is a summarized version of my previous answer. Let me know if you need more details.*"
            else:
                enhanced_response = f"{intro}\n\n{cached_response}"
            
            # Send the response
            if len(enhanced_response) > 100:
                # For longer responses, use embed
                embed = self.create_smart_embed(
                    title=f"{tech_emoji} Previous Information Retrieved",
                    description=enhanced_response,
                    color_type="futuristic",
                    footer="Memory systems operational • Using cached data"
                )
                await message.reply(embed=embed)
            else:
                # For shorter responses, just send text
                await message.reply(enhanced_response)
            
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
                # Get analysis from Llama
                analysis_response = await self.get_llama_response(analysis_prompt)
                
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
                
                # Add additional context based on analysis and chat history
                chat_context = self.format_chat_history(user_id)
                
                enhanced_prompt = f"""
                {system_prompt}
                
                Previous conversation:
                {chat_context}
                
                The user's message appears to be a {analysis.get('complexity', 'moderate')} {analysis.get('intent', 'question')}
                with a {analysis.get('sentiment', 'neutral')} sentiment about {analysis.get('key_topic', 'general topics')}.
                
                User message: {content}
                
                Respond in a way that's appropriate to their intent and sentiment, while maintaining your persona.
                Format your response with elegant structure and appropriate futuristic elements.
                If you see references to previous conversation in our chat history, make sure to acknowledge and build upon that context.
                """
                
                # Get enhanced response
                response = await self.get_llama_response(enhanced_prompt, user_id)
                
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
    
    @commands.command(name="clearmemory")
    async def clear_memory(self, ctx):
        """Clear your conversation history with Lexus"""
        user_id = ctx.author.id
        
        if user_id in self.chat_history:
            # Clear user's chat history
            self.chat_history[user_id] = []
            
            # Send confirmation
            embed = self.create_smart_embed(
                title=f"{self.get_random_emojis('positive', 1)[0]} Memory Reset Complete",
                description="I've cleared our conversation history. Our future interactions will start fresh.",
                color_type="success"
            )
        else:
            # No history to clear
            embed = self.create_smart_embed(
                title=f"{self.get_random_emojis('tech', 1)[0]} No Memory to Clear",
                description="We don't have any stored conversation history yet.",
                color_type="info"
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
                 "• My responses adapt to your message style and content\n"
                 "• I remember our previous conversations and can reference them",
            inline=False
        )
        
        # Chat modes
        embed.add_field(
            name=f"{self.get_random_emojis('fun', 1)[0]} PERSONALITY MATRICES",
            value="• `/chatmode [mode]` - Change my conversational style\n"
                 "• Available modes: helper, anime, therapist, friend, expert\n"
                 "• Default mode: helper",
            inline=False
        )
        
        # Memory commands
        embed.add_field(
            name=f"{self.get_random_emojis('tech', 1)[0]} MEMORY SYSTEMS",
            value="• I remember our conversations and use them for context\n"
                 "• `/clearmemory` - Clear your conversation history with me\n"
                 "• I can recognize repeated questions and give consistent answers",
            inline=False
        )
        
        # Add timestamp and version
        current_time = datetime.datetime.now().strftime("%Y.%m.%d")
        embed.set_footer(text=f"Lexus AI v3.0.0 • Llama 3.1 Nemotron Ultra Neural Core • {current_time}")
        
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
            response = await self.get_llama_response(prompt)
            
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
