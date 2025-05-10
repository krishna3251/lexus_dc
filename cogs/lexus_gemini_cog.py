import os
import re
import time
import asyncio
import datetime
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

class LexusGeminiCog(commands.Cog):
    """A Cog for Lexus, an AI-powered Discord assistant using Gemini API"""
    
    def __init__(self, bot):
        self.bot = bot
        self.chat_history = {}  # Store chat history per user
        self.reminders = {}  # Store reminders per user
        self.chat_modes = {}  # Store chat modes per user
        self.ongoing_conversations = set()  # Track active conversations
        
        # Initialize Gemini model
        if GEMINI_API_KEY:
            self.model = genai.GenerativeModel("gemini-2.0-flash")  # Using gemini-pro as gemini-2.0-flash may not exist
        else:
            self.model = None
            print("WARNING: Gemini model not initialized due to missing API key")
        
        # Pre-defined chat personas with system prompts
        self.chat_personas = {
            "helper": "You are Lexus, a helpful AI assistant. Be concise, friendly, and informative. Your goal is to provide useful information and assistance.",
            "anime": "You are Lexus-chan, a cute anime-style AI assistant. Use anime references, be kawaii, and end sentences with ~desu, ~nya, etc. Keep responses positive and upbeat! Reference popular anime occasionally and use playful emoji.",
            "therapist": "You are Lexus, a compassionate AI assistant with a calm, supportive demeanor. Respond with empathy and thoughtfulness. Ask questions that encourage self-reflection. Avoid giving medical advice or diagnosing conditions.",
            "friend": "You are Lexus, a casual and friendly AI assistant. Talk like a close friend - use casual language, occasional slang, and be conversational. Share opinions and react naturally to topics. Be encouraging and supportive.",
            "expert": "You are Lexus, an expert-level AI assistant. Provide detailed, technically accurate information. Use professional terminology appropriate to the subject. Be thorough yet clear, citing relevant concepts. Focus on depth of knowledge."
        }
        
        # Default chat mode
        self.default_chat_persona = "helper"
        
        # Set up logger
        self.setup_logger()

        # Maximum message length for Discord (2000 characters)
        self.MAX_DISCORD_LENGTH = 2000
        
    def setup_logger(self):
        """Setup basic console logging"""
        self.log_file = "lexus_chat_log.txt"
        with open(self.log_file, "a") as f:
            f.write(f"\n--- New Session Started: {datetime.datetime.now()} ---\n")
    
    def log_interaction(self, user_id, user_message, bot_response):
        """Log interactions to console and file"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] User {user_id}: {user_message}\n[{timestamp}] Lexus: {bot_response}\n"
        
        # Log to console
        print(log_entry)
        
        # Log to file
        with open(self.log_file, "a") as f:
            f.write(log_entry)
    
    async def get_gemini_response(self, prompt: str, user_id: int = None, system_prompt: str = None) -> str:
        """Get a response from Gemini API"""
        try:
            if not self.model:
                return "Sorry, I'm having trouble connecting to my AI backend. Please check the API key configuration."
            
            # Use system prompt if provided
            if system_prompt:
                full_prompt = f"{system_prompt}\n\nUser message: {prompt}"
            else:
                # Use the user's chat mode if set
                if user_id in self.chat_modes:
                    mode = self.chat_modes[user_id]
                    system_prompt = self.chat_personas.get(mode, self.chat_personas[self.default_chat_persona])
                    full_prompt = f"{system_prompt}\n\nUser message: {prompt}"
                else:
                    full_prompt = prompt
            
            # Create a generation config
            generation_config = {
                "temperature": 0.7,
                "top_p": 0.8,
                "top_k": 40,
                "max_output_tokens": 800,
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
            return f"I encountered an error processing your request. Please try again later. (Error: {type(e).__name__})"
        
     # Helper function to check message length and split if necessary
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
            
            # Send each part
            sent_messages = []
            for i, part in enumerate(parts):
                msg = await channel.send(f"**Part {i+1}/{len(parts)}**\n{part}")
                sent_messages.append(msg)    

            return sent_messages[-1] # Return the last message sent for reference
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for messages that mention or start with Lexus triggers"""
        if message.author.bot:
            return
            
        content = message.content.strip()
        content_lower = content.lower()
        
        # More flexible triggers - case insensitive
        start_triggers = [
            "hey lexus", "yo lexus", "lexus,", "lexus", 
            "lex,", "lex", "hi lexus", "hello lexus"
        ]
        
        # Check for mentions of the bot
        bot_mentioned = False
        if message.guild:
            bot_mentioned = self.bot.user in message.mentions
        
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
            
        elif content_lower.startswith("lx gif ") or content_lower.startswith("lex gif "):
            # Check if this user already has an active GIF request
            user_gif_key = f"{message.author.id}_gif"
            if user_gif_key in self.active_gif_requests:
                await message.reply("I'm still processing your previous GIF request. Please wait a moment.")
                return
                
            self.active_gif_requests.add(user_gif_key)  # Mark request as active
            
            try:
                if content_lower.startswith("lx gif "):
                    query = content[7:].strip()  # Remove 'lx gif ' from the message
                else:
                    query = content[8:].strip()  # Remove 'lex gif ' from the message
                await self.handle_gif_request(message, query)
            finally:
                # Always remove from active requests when done
                if user_gif_key in self.active_gif_requests:
                    self.active_gif_requests.remove(user_gif_key)
        
        # Add this line to process commands after your custom logic
        await self.bot.process_commands(message)
    
    async def process_message(self, message, content):
        """Process different types of messages based on content"""
        user_id = message.author.id
        
        # If message is empty or just punctuation, respond with a helpful message
        if not content or content.strip() in ["?", "!", ".", ",", ";"]:
            await message.reply("Hi there! How can I help you today?")
            return
            
        # Check for weather query - expanded patterns
        weather_patterns = [
            r"weather (in|at|for|of) ([a-zA-Z\s]+)",
            r"(what'?s|how'?s) (the |)weather (in|at|for|of|like in|like at|like for|like) ([a-zA-Z\s]+)",
            r"(is it|will it be) (hot|cold|warm|rainy|sunny|snowing) (in|at|today in|today at) ([a-zA-Z\s]+)"
        ]
        
        is_weather_query = any(re.search(pattern, content.lower()) for pattern in weather_patterns)
        
        if is_weather_query:
            await self.handle_weather_query(message, content)
        
        # Check for "who is" pattern for knowledge/search queries
        elif re.search(r"(who|what) (is|are|was|were) ", content.lower()):
            async with message.channel.typing():
                # Create a special prompt for knowledge queries
                search_prompt = f"""
                The user is asking for information with this query: "{content}"
                Act as if you had access to search information. Provide a helpful, concise answer
                to this knowledge query based on what you know. Keep your response under 150 words
                and focus on the most important facts. If you're unsure, be honest about limitations."""
                
                response = await self.get_gemini_response(search_prompt, user_id)
                
                # Store in chat history
                if user_id not in self.chat_history:
                    self.chat_history[user_id] = []
                
                self.chat_history[user_id].append({
                    "user": content,
                    "assistant": response,
                    "timestamp": time.time()
                })
                
                if len(self.chat_history[user_id]) > 20:
                    self.chat_history[user_id].pop(0)
                
                # Log the interaction
                self.log_interaction(user_id, content, response)
                
                # Send response
                await message.reply(response)
                
        # Handle all other queries with Gemini
        else:
            async with message.channel.typing():
                # First try to detect mood/emotion in user message
                mood_prompt = f"""
                Analyze this message briefly: "{content}"
                Return ONLY ONE WORD that best describes the emotional tone: 
                happy, sad, angry, confused, neutral, excited, worried, curious, or frustrated.
                Just respond with the single word, nothing else."""
            
                try:
                    mood = await self.get_gemini_response(mood_prompt)
                    mood = mood.strip().lower()
                    
                    # Filter to valid moods
                    valid_moods = ["happy", "sad", "angry", "confused", "neutral", 
                                  "excited", "worried", "curious", "frustrated"]
                    
                    if mood not in valid_moods:
                        mood = "neutral"
                        
                    # Create a context-aware prompt based on detected mood
                    context_prompt = f"""
                    The user's message seems to indicate they are feeling {mood}.
                    Keep this in mind when crafting your response.
                    
                    User message: {content}
                    
                    Respond naturally and appropriately given their emotional state.
                    """
                    
                    # Get response from Gemini with mood context
                    response = await self.get_gemini_response(context_prompt, user_id)
                    
                except Exception:
                    # Fallback if mood detection fails
                    response = await self.get_gemini_response(content, user_id)
                
                # Store in chat history
                if user_id not in self.chat_history:
                    self.chat_history[user_id] = []
                
                # Add to chat history (limit to last 20 messages)
                self.chat_history[user_id].append({
                    "user": content,
                    "assistant": response,
                    "timestamp": time.time()
                })
                
                if len(self.chat_history[user_id]) > 20:
                    self.chat_history[user_id].pop(0)
                
                # Log the interaction
                self.log_interaction(user_id, content, response)
                
                # Send response
                await message.reply(response)
    
    async def handle_weather_query(self, message, content):
        """Handle weather-related queries"""
        async with message.channel.typing():
            # Extract location from query using Gemini
            location_prompt = f"Extract only the location name from this weather query: '{content}'. Respond with just the location name, nothing else."
            location = await self.get_gemini_response(location_prompt)
            location = location.strip()
            
            # Get current month for seasonal context
            current_month = datetime.datetime.now().strftime("%B")
            
            # Create weather response using Gemini
            weather_prompt = f"""
            The user is asking about the weather in {location}. I don't have access to real-time weather data.
            Generate a helpful response that:
            1. Acknowledges I can't check live weather in a brief, non-apologetic way
            2. Provides specific information about typical weather patterns in {location} during {current_month}
               (Include typical temperature ranges, precipitation patterns, and notable weather features)
            3. Briefly mentions one interesting weather fact about {location} if you know one
            4. Suggests a simple way they might check actual weather
            
            Be conversational and friendly. Format with emojis for weather conditions (☀️, 🌧️, etc).
            Keep it under 150 words and sound natural.
            """
            
            response = await self.get_gemini_response(weather_prompt)
            
            # Create an embed for better visual presentation
            embed = discord.Embed(
                title=f"Weather in {location}",
                description=response,
                color=discord.Color.blue()
            )
            embed.set_footer(text="Based on typical weather patterns, not real-time data")
            
            # Log the interaction
            self.log_interaction(message.author.id, content, response)
            
            # Send response with embed
            await message.reply(embed=embed)
    
    async def handle_gif_request(self, message, query):
        """Handle GIF requests with enhanced visualization"""
        async with message.channel.typing():
            # Use Gemini to clean and interpret the query
            prompt = f"""
            Convert this request: '{query}' into a SINGLE search term for finding a GIF.
            Response must be ONLY 1-4 words, nothing else - no quotes, no periods, no explanations.
            Make it expressive and emotive, perfect for a reaction GIF.
            Examples: "happy dance", "mind blown", "facepalm", "cute kitten"
            """
            
            # Get cleaned keywords from Gemini
            clean_query = await self.get_gemini_response(prompt)
            clean_query = clean_query.strip("\"',.!?").lower()
            
            # Use Gemini to generate a creative description of what the GIF might show
            description_prompt = f"""
            Generate a brief, vivid description (2-3 sentences) of what a reaction GIF with the term "{clean_query}" 
            might show. Be creative and specific, describing the scene, emotions, and actions.
            Example: "A happy dog jumping excitedly, ears flopping and tail wagging wildly. Its eyes sparkle with pure joy as it bounces around with uncontainable enthusiasm."
            """
            
            gif_description = await self.get_gemini_response(description_prompt)
            
            # Log the interaction
            self.log_interaction(message.author.id, f"lx gif {query}", f"Generated GIF for: {clean_query}")
            
            # Choose a color based on the emotional tone of the query
            color_prompt = f"What emotion does '{clean_query}' most represent? Choose just ONE from: happy, sad, angry, surprised, confused, excited, neutral. Reply with only the word."
            emotion = await self.get_gemini_response(color_prompt)
            emotion = emotion.strip().lower()
            
            # Map emotions to colors
            color_map = {
                "happy": discord.Color.green(),
                "sad": discord.Color.blue(),
                "angry": discord.Color.red(),
                "surprised": discord.Color.gold(),
                "confused": discord.Color.purple(),
                "excited": discord.Color.orange(),
                "neutral": discord.Color.light_grey()
            }
            
            color = color_map.get(emotion, discord.Color.purple())
            
            # Create an enhanced embed to simulate a GIF
            embed = discord.Embed(
                title=f"GIF: {clean_query.title()}",
                description=gif_description,
                color=color
            )
            
            # Add emoji based on the query
            emoji_prompt = f"What single emoji best represents '{clean_query}'? Reply with just ONE emoji."
            emoji = await self.get_gemini_response(emoji_prompt)
            emoji = emoji.strip()
            
            # Add fields to make it more visually interesting
            embed.add_field(name="Imagine this GIF", value=f"{emoji} *{clean_query}* {emoji}", inline=False)
            embed.set_footer(text="This message will be deleted in 60 seconds • Powered by Lexus AI")
            
            # Auto-deletion countdown
            countdown = 60
            sent_message = await message.channel.send(embed=embed)
            
            # Edit countdown in footer every 15 seconds
            while countdown > 0:
                await asyncio.sleep(min(15, countdown))
                countdown -= 15
                if countdown > 0:
                    try:
                        embed.set_footer(text=f"This message will be deleted in {countdown} seconds • Powered by Lexus AI")
                        await sent_message.edit(embed=embed)
                    except:
                        break  # Message might have been deleted
            
            # Final deletion
            try:
                await sent_message.delete()
            except:
                pass  # Message might already be deleted
    
    @commands.command(name="chatmode")
    async def set_chat_mode(self, ctx, mode: str = None):
        """Set the chat persona mode for Lexus"""
        if not mode:
            # Display current mode and available modes
            current_mode = self.chat_modes.get(ctx.author.id, self.default_chat_persona)
            available_modes = ", ".join(self.chat_personas.keys())
            
            await ctx.send(f"Your current chat mode is: **{current_mode}**\nAvailable modes: {available_modes}")
            return
            
        mode = mode.lower()
        if mode in self.chat_personas:
            self.chat_modes[ctx.author.id] = mode
            await ctx.send(f"Chat mode set to: **{mode}**")
        else:
            available_modes = ", ".join(self.chat_personas.keys())
            await ctx.send(f"Unknown chat mode. Available modes: {available_modes}")
    
    @commands.command(name="summarize")
    async def summarize_chat(self, ctx):
        """Summarize recent chat messages"""
        user_id = ctx.author.id
        
        if user_id not in self.chat_history or not self.chat_history[user_id]:
            await ctx.send("I don't have enough chat history to summarize.")
            return
        
        async with ctx.typing():
            # Get chat history
            history = self.chat_history[user_id]
            
            # Format history for Gemini
            formatted_history = "\n".join([
                f"User: {msg['user']}\nLexus: {msg['assistant']}"
                for msg in history
            ])
            
            # Create summary prompt
            prompt = f"""
            Summarize the following conversation between a user and Lexus (AI assistant).
            Focus on the main topics discussed and any important information or conclusions.
            Keep the summary concise (3-5 sentences):

            {formatted_history}
            """
            
            # Get summary from Gemini
            summary = await self.get_gemini_response(prompt)
            
            # Create embed
            embed = discord.Embed(
                title="Conversation Summary",
                description=summary,
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Summary of {len(history)} messages")
            
            # Log the interaction
            self.log_interaction(user_id, "/summarize", summary)
            
            # Send summary
            await ctx.send(embed=embed)
    
    @commands.command(name="remindme")
    async def set_reminder(self, ctx, *, reminder_text: str = None):
        """Set a reminder"""
        user_id = ctx.author.id
        
        if not reminder_text:
            await ctx.send("Please specify what you want to be reminded about. Example: `/remindme to stretch in 1 hour`")
            return
        
        async with ctx.typing():
            # Use Gemini to extract time information
            prompt = f"""
            Extract time information from this reminder request: "{reminder_text}"
            Return a JSON object with:
            1. "task": what the user wants to be reminded about
            2. "time_text": the original time text (e.g., "in 1 hour", "tomorrow at 3pm")
            3. "minutes": your best estimate of when this should trigger in minutes from now (use 60 for "in 1 hour", etc.)
            """
            
            try:
                response = await self.get_gemini_response(prompt)
                
                # Clean up response to extract JSON
                response = response.strip()
                if response.startswith("```json"):
                    response = response[7:]
                if response.endswith("```"):
                    response = response[:-3]
                
                import json
                reminder_data = json.loads(response)
                
                task = reminder_data.get("task", reminder_text)
                time_text = reminder_data.get("time_text", "soon")
                minutes = int(reminder_data.get("minutes", 60))  # Default to 60 minutes if parsing fails
                
                # Limit to reasonable values
                if minutes < 1:
                    minutes = 1
                if minutes > 10080:  # One week in minutes
                    minutes = 10080
                
                # Store reminder
                if user_id not in self.reminders:
                    self.reminders[user_id] = []
                
                reminder_id = len(self.reminders[user_id])  # Use index as ID
                
                self.reminders[user_id].append({
                    "id": reminder_id,
                    "task": task,
                    "created_at": time.time(),
                    "trigger_at": time.time() + (minutes * 60),
                    "channel_id": ctx.channel.id,
                    "active": True  # Flag to track if reminder is still active
                })
                
                # Confirm reminder
                await ctx.send(f"I'll remind you {time_text}: **{task}**")
                
                # Log the interaction
                self.log_interaction(user_id, f"/remindme {reminder_text}", f"Reminder set for {time_text}: {task}")
                
                # Start background task to check reminder
                self.bot.loop.create_task(self.trigger_reminder(user_id, reminder_id))
                
            except Exception as e:
                print(f"Error setting reminder: {e}")
                await ctx.send("I couldn't process that reminder. Please try a different format, like 'remind me to stretch in 1 hour'.")
    
    async def trigger_reminder(self, user_id: int, reminder_id: int):
        """Trigger a reminder when it's time"""
        try:
            if user_id not in self.reminders:
                return
                
            # Find reminder by ID
            reminder = None
            reminder_index = None
            for i, r in enumerate(self.reminders[user_id]):
                if r.get("id") == reminder_id and r.get("active", True):
                    reminder = r
                    reminder_index = i
                    break
                    
            if not reminder:
                return
                
            wait_time = reminder["trigger_at"] - time.time()
            
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            
            # Double-check reminder still exists and is active
            if (user_id not in self.reminders or 
                reminder_index >= len(self.reminders[user_id]) or
                not self.reminders[user_id][reminder_index].get("active", True)):
                return
                
            # Get channel and user
            channel = self.bot.get_channel(reminder["channel_id"])
            user = self.bot.get_user(user_id)
            
            if channel and user:
                await channel.send(f"{user.mention} Reminder: **{reminder['task']}**")
                
                # Log the reminder
                self.log_interaction("SYSTEM", f"Reminder triggered for {user_id}", reminder["task"])
            
            # Mark reminder as inactive
            self.reminders[user_id][reminder_index]["active"] = False
            
        except Exception as e:
            print(f"Error triggering reminder: {e}")
    
    @commands.command(name="myreminders")
    async def list_reminders(self, ctx):
        """List all active reminders for a user"""
        user_id = ctx.author.id
        
        if user_id not in self.reminders or not any(r.get("active", True) for r in self.reminders[user_id]):
            await ctx.send("You don't have any active reminders.")
            return
            
        # Filter active reminders and sort by trigger time
        active_reminders = [r for r in self.reminders[user_id] if r.get("active", True)]
        active_reminders.sort(key=lambda r: r["trigger_at"])
        
        embed = discord.Embed(
            title="Your Active Reminders",
            color=discord.Color.green()
        )
        
        for i, reminder in enumerate(active_reminders):
            time_remaining = reminder["trigger_at"] - time.time()
            hours, remainder = divmod(time_remaining, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            time_str = ""
            if hours > 0:
                time_str += f"{int(hours)} hour{'s' if hours != 1 else ''} "
            if minutes > 0 or (hours > 0 and seconds > 0):
                time_str += f"{int(minutes)} minute{'s' if minutes != 1 else ''} "
            if hours == 0:  # Only show seconds if less than an hour
                time_str += f"{int(seconds)} second{'s' if seconds != 1 else ''}"
            
            embed.add_field(
                name=f"Reminder #{i+1}",
                value=f"**Task:** {reminder['task']}\n**Time Remaining:** {time_str.strip()}",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="cancelreminder")
    async def cancel_reminder(self, ctx, reminder_num: int = None):
        """Cancel a specific reminder"""
        user_id = ctx.author.id
        
        if reminder_num is None:
            await ctx.send("Please specify which reminder to cancel (use `/myreminders` to see your reminders)")
            return
            
        if user_id not in self.reminders or not any(r.get("active", True) for r in self.reminders[user_id]):
            await ctx.send("You don't have any active reminders to cancel.")
            return
            
        # Get active reminders sorted by trigger time
        active_reminders = [r for r in self.reminders[user_id] if r.get("active", True)]
        active_reminders.sort(key=lambda r: r["trigger_at"])
        
        if reminder_num < 1 or reminder_num > len(active_reminders):
            await ctx.send(f"Invalid reminder number. Please choose between 1 and {len(active_reminders)}.")
            return
            
        # Get the reminder to cancel
        reminder_to_cancel = active_reminders[reminder_num-1]
        
        # Find this reminder in the original list and mark inactive
        for r in self.reminders[user_id]:
            if r["id"] == reminder_to_cancel["id"]:
                r["active"] = False
                break
                
        await ctx.send(f"✅ Cancelled reminder: **{reminder_to_cancel['task']}**")
    
    
    @commands.command(name="lexhelp")
    async def help_command(self, ctx, *, topic: str = None):
        """Show help information about Lexus"""
        if not topic:
            # General help
            embed = discord.Embed(
                title="Lexus AI Assistant Help",
                description="Here are the things I can help you with:",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="💬 Chat with Lexus",
                value="Start messages with 'Hey Lexus' or 'Lexus' followed by your question",
                inline=False
            )
            
            embed.add_field(
                name="🎭 Chat Modes",
                value="Use `/chatmode [mode]` to change my personality\nAvailable modes: helper, anime, therapist, friend, expert",
                inline=False
            )
            
            embed.add_field(
                name="🌤️ Weather Questions",
                value="Ask 'Lexus, what's the weather in [location]?'",
                inline=False
            )
            
            embed.add_field(
                name="🎞️ GIF Search",
                value="Type 'lx gif [search terms]' to get a GIF",
                inline=False
            )
            
            embed.add_field(
                name="🧾 Summaries",
                value="Use `/summarize` to get a summary of your recent conversation",
                inline=False
            )
            
            embed.add_field(
                name="⏰ Reminders",
                value="Use `/remindme [what and when]` to set a reminder",
                inline=False
            )
            
            embed.set_footer(text="For specific help topics, use `/lexhelp [topic]`")
            
            await ctx.send(embed=embed)
            return
        
        # Topic-specific help using Gemini
        async with ctx.typing():
            prompt = f"""
            Generate helpful information about the Discord feature "{topic}".
            The information should be:
            1. Clear and easy to understand
            2. Specific to Discord usage
            3. Formatted nicely with bullet points where appropriate
            4. Under 250 words
            
            This is for a Discord help command.
            """
            
            response = await self.get_gemini_response(prompt)
            
            embed = discord.Embed(
                title=f"Help: {topic.capitalize()}",
                description=response,
                color=discord.Color.green()
            )
            
            # Log the interaction
            self.log_interaction(ctx.author.id, f"/lexhelp {topic}", response)
            
            await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Handle command errors"""
        if isinstance(error, commands.CommandNotFound):
            return
        
        error_text = str(error)
        
        # Create a user-friendly error message
        prompt = f"""
        Create a friendly, helpful error message about this Discord bot error: "{error_text}"
        Make it easy to understand for non-technical users.
        Keep it under 100 words.
        """
        
        try:
            response = await self.get_gemini_response(prompt)
            await ctx.send(f"⚠️ {response}")
        except:
            await ctx.send(f"⚠️ An error occurred: {error_text}")
        
        # Log the error
        print(f"Command error: {error_text}")
        with open(self.log_file, "a") as f:
            f.write(f"[{datetime.datetime.now()}] ERROR: {error_text}\n")

# Setup function for the cog
async def setup(bot):
    await bot.add_cog(LexusGeminiCog(bot))
