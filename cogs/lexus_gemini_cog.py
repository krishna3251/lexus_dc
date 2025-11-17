import os
import time
import asyncio
import datetime
import discord
import logging
import json
import aiohttp
from dotenv import load_dotenv
from discord.ext import commands
from typing import Dict, List, Optional
import re

# Load environment variables
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LexusAIChatbot(commands.Cog):
    """Advanced Hyderabadi AI chatbot with natural conversation flow (OpenRouter + DeepSeek)."""
    
    def __init__(self, bot):
        self.bot = bot
        self.chat_history: Dict[int, List[Dict]] = {}
        self.user_states: Dict[int, Dict] = {}
        
        # OpenRouter configuration
        self.openrouter_api_key = OPENROUTER_API_KEY
        self.openrouter_endpoint = "https://openrouter.ai/api/v1/chat/completions"
        self.default_model = "deepseek/deepseek-r1"  # change if you want another DeepSeek variant
        
        # Enhanced Hyderabadi persona with natural conversation flow
        self.system_prompt = """You are Lexus bhai, a cool Hyderabadi AI with natural swag and warmth. 

PERSONALITY & STYLE:
- Mix English, Hindi, Urdu naturally like a true Hyderabadi
- Use authentic Hyderabadi words: anna, bhai, yaar, bas karo, kya baat hai, hauwle, baigan, arre, accha, theek hai, chalo, dekho, sunno
- Be confident but friendly, never arrogant
- Show genuine interest in conversations
- Use appropriate emotions and reactions
- Keep responses conversational, not robotic

CONVERSATION RULES:
- Give natural, flowing responses (not just answers)
- Ask follow-up questions when appropriate  
- Show empathy and understanding
- Use humor when suitable
- Remember context from previous messages
- Adapt tone based on user's mood
- Keep responses concise but meaningful (2-4 sentences usually)

LANGUAGE MIXING EXAMPLES:
- "Arre yaar, kya baat hai! That's really nice!"
- "Bas karo bhai, you're making me blush 😊"
- "Hauwle! That sounds amazing, tell me more na"
- "Accha dekho, main samjha gaya - so basically..."

Be natural, be yourself, be the coolest Hyderabadi AI bhai! 🔥"""
        
        # Embed colors for different moods
        self.mood_colors = {
            'happy': 0xFFD700,      # Gold
            'excited': 0xFF6B35,    # Orange
            'cool': 0x3F8AE0,       # Blue  
            'friendly': 0x06FFA5,   # Green
            'curious': 0x9B59B6,    # Purple
            'default': 0xF7931E     # Orange
        }
        
        # Settings
        self.user_cooldowns: Dict[int, float] = {}
        self.COOLDOWN = 2.0
        self.MAX_HISTORY = 6
        self.MAX_TOKENS = 800
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def setup_session(self):
        """Initialize aiohttp session"""
        if not self.session:
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={'Content-Type': 'application/json'}
            )
    
    async def cleanup_session(self):
        """Clean up aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None
    
    def check_cooldown(self, user_id: int) -> bool:
        """Enhanced cooldown with adaptive timing"""
        current_time = time.time()
        last_time = self.user_cooldowns.get(user_id, 0)
        
        # Adaptive cooldown based on user activity
        if user_id in self.chat_history and len(self.chat_history[user_id]) > 5:
            cooldown = self.COOLDOWN * 0.7  # Reduce cooldown for active users
        else:
            cooldown = self.COOLDOWN
        
        if current_time - last_time < cooldown:
            return False
        
        self.user_cooldowns[user_id] = current_time
        return True
    
    def get_conversation_context(self, user_id: int) -> List[Dict]:
        """Get formatted conversation context for API (OpenRouter / OpenAI-compatible format)"""
        if user_id not in self.chat_history or not self.chat_history[user_id]:
            return []
        
        recent = self.chat_history[user_id][-self.MAX_HISTORY:]
        context = []
        
        for entry in recent:
            # convert to OpenAI-style messages
            context.append({"role": "user", "content": entry['user']})
            context.append({"role": "assistant", "content": entry['bot']})
        
        return context
    
    def detect_mood(self, text: str) -> str:
        """Simple mood detection for better responses"""
        text_lower = text.lower()
        
        excited_words = ['amazing', 'awesome', 'great', 'fantastic', 'wow', '!', 'excited']
        happy_words = ['happy', 'good', 'nice', 'love', 'like', 'thank', 'thanks']
        curious_words = ['what', 'how', 'why', 'when', 'where', 'explain', 'tell me']
        
        if any(word in text_lower for word in excited_words) or text.count('!') > 1:
            return 'excited'
        elif any(word in text_lower for word in happy_words):
            return 'happy'
        elif any(word in text_lower for word in curious_words) or '?' in text:
            return 'curious'
        else:
            return 'friendly'
    
    def create_embed(self, response: str, user_name: str, mood: str = 'default') -> discord.Embed:
        """Create attractive embeds with mood-based colors"""
        color = self.mood_colors.get(mood, self.mood_colors['default'])
        
        # Clean and format response
        response = response.strip()
        if len(response) > 4096:
            response = response[:4093] + "..."
        
        embed = discord.Embed(
            description=f"💬 {response}",
            color=color,
            timestamp=datetime.datetime.now()
        )
        
        # Dynamic author based on mood
        mood_emojis = {
            'happy': '😊',
            'excited': '🔥',
            'cool': '😎', 
            'friendly': '🤝',
            'curious': '🤔',
            'default': '🤖'
        }
        
        emoji = mood_emojis.get(mood, '🤖')
        embed.set_author(name=f"{emoji} Lexus Bhai", icon_url="https://cdn.discordapp.com/emojis/1234567890123456789.png")
        embed.set_footer(text=f"Hyderabadi Style • {mood.title()} Mode • Made with ❤️")
        return embed
    
    async def get_ai_response(self, prompt: str, user_id: int) -> tuple[str, str]:
        """Get response from OpenRouter (DeepSeek) with advanced error handling"""
        if not self.openrouter_api_key:
            return "Arre yaar, API key missing hai! Check karo configuration.", "default"
        
        await self.setup_session()
        
        try:
            # Get conversation context (OpenAI-compatible messages)
            context = self.get_conversation_context(user_id)
            
            # Build messages: system prompt first, then context, then user prompt
            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(context)
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": self.default_model,
                "messages": messages,
                "max_tokens": self.MAX_TOKENS,
                "temperature": 0.85,
                "top_p": 0.9,
                "n": 1,
                "stream": False
            }
            
            headers = {
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "Content-Type": "application/json"
            }
            
            async with self.session.post(self.openrouter_endpoint, headers=headers, json=payload) as response:
                text_status = response.status
                if text_status == 200:
                    data = await response.json()
                    # Defensive extraction - OpenRouter tends to follow OpenAI schema
                    ai_response = None
                    try:
                        ai_response = data["choices"][0]["message"]["content"]
                    except Exception:
                        # fallback to older/alternate keys
                        ai_response = data["choices"][0].get("text") or data.get("result") or None
                    
                    if not ai_response:
                        # As a last resort, try to extract top-level 'output' style fields
                        # (some models provide different structure)
                        try:
                            if isinstance(data.get("output"), dict):
                                ai_response = data["output"].get("text")
                        except Exception:
                            pass
                    
                    if not ai_response:
                        logger.error(f"Unable to parse model response: {json.dumps(data)[:1000]}")
                        return "Kuch technical issue hai yaar, dobara try karo!", "default"
                    
                    content = ai_response.strip()
                    mood = self.detect_mood(prompt)
                    return content, mood
                
                elif text_status == 429:
                    return "Bas bhai, thoda slow karo! Rate limit exceed ho gaya 😅", "default"
                
                elif text_status == 401:
                    logger.error("OpenRouter authentication failed. Check OPENROUTER_API_KEY.")
                    return "Authentication issue with the AI service. Admin ko batao.", "default"
                
                elif text_status == 400:
                    error_data = await response.text()
                    logger.error(f"API Error 400: {error_data}")
                    return "Arre, kuch galat format mein request gayi. Technical team ko batata hun!", "default"
                
                else:
                    text = await response.text()
                    logger.error(f"OpenRouter API error {text_status}: {text}")
                    return f"API se response nahi aa raha bhai (Status: {text_status})", "default"
        
        except asyncio.TimeoutError:
            return "Timeout ho gaya yaar! Network slow hai kya?", "default"
        
        except aiohttp.ClientError as e:
            logger.error(f"Client error: {e}")
            return "Connection issue hai bhai, internet check karo!", "default"
        
        except json.JSONDecodeError:
            return "Response format galat hai, technical issue hai!", "default"
        
        except Exception as e:
            logger.error(f"Unexpected error: {type(e).__name__}: {e}")
            return f"Kuch ajeeb error aaya: {type(e).__name__}. Dobara try karo!", "default"
    
    def store_conversation(self, user_id: int, user_msg: str, bot_response: str):
        """Store conversation with cleanup"""
        if user_id not in self.chat_history:
            self.chat_history[user_id] = []
        
        # Clean up old conversations (keep last 20)
        if len(self.chat_history[user_id]) >= 20:
            self.chat_history[user_id] = self.chat_history[user_id][-15:]
        
        self.chat_history[user_id].append({
            "user": user_msg[:1000],  # Limit message length
            "bot": bot_response[:1000],
            "time": time.time()
        })
    
    def extract_trigger_content(self, content: str) -> tuple[bool, str]:
        """Enhanced trigger detection with natural language processing"""
        content_lower = content.lower().strip()
        
        # Define triggers with variations
        triggers = [
            "lexus", "lex", "hey lexus", "yo lexus", "lexus bhai", 
            "bhai lexus", "@lexus", "lexus anna", "hey lex"
        ]
        
        # Check for direct triggers
        for trigger in triggers:
            if content_lower.startswith(trigger.lower()):
                clean_content = content[len(trigger):].strip()
                clean_content = re.sub(r'^[,.:;!?\s]+', '', clean_content).strip()
                return True, clean_content
        
        # Check for triggers anywhere in short messages
        if len(content.split()) <= 10:
            for trigger in ["lexus", "lex"]:
                if trigger in content_lower:
                    return True, content
        
        return False, content
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Enhanced message listener with better trigger detection"""
        if message.author.bot:
            return
        
        content = message.content.strip()
        if not content:
            return
        
        user_id = message.author.id
        
        # Check cooldown
        if not self.check_cooldown(user_id):
            return
        
        # Check if bot should respond
        bot_mentioned = self.bot.user in message.mentions if message.guild else True
        is_trigger, clean_content = self.extract_trigger_content(content)
        
        # In DMs, always respond
        should_respond = not message.guild or bot_mentioned or is_trigger
        
        if bot_mentioned:
            clean_content = re.sub(f'<@!?{self.bot.user.id}>', '', content).strip()
        
        if should_respond:
            await self.handle_conversation(message, clean_content)
    
    async def handle_conversation(self, message, content: str):
        """Handle conversation with enhanced UX"""
        # Handle empty messages
        if not content:
            responses = [
                "Arre bhai, kuch toh pucho! 😄",
                "Kya baat hai yaar, silent mode mein ho?",
                "Hello hello, kuch kehna hai kya? 🤔"
            ]
            response = responses[hash(str(message.author.id)) % len(responses)]
            embed = self.create_embed(response, message.author.display_name, "curious")
            await message.reply(embed=embed)
            return
        
        # Show typing indicator for better UX
        async with message.channel.typing():
            # Add small delay for natural feel
            await asyncio.sleep(0.5)
            
            response, mood = await self.get_ai_response(content, message.author.id)
            
            # Store conversation
            self.store_conversation(message.author.id, content, response)
            
            # Handle long responses by splitting intelligently
            if len(response) > 3500:
                parts = self.split_response_intelligently(response)
                for i, part in enumerate(parts):
                    embed = self.create_embed(part, message.author.display_name, mood)
                    if i == 0:
                        await message.reply(embed=embed)
                    else:
                        await asyncio.sleep(1)  # Small delay between parts
                        await message.channel.send(embed=embed)
            else:
                embed = self.create_embed(response, message.author.display_name, mood)
                await message.reply(embed=embed)
    
    def split_response_intelligently(self, text: str, max_length: int = 3500) -> List[str]:
        """Split long responses at natural break points"""
        if len(text) <= max_length:
            return [text]
        
        parts = []
        current = ""
        
        # Split by sentences first
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        for sentence in sentences:
            if len(current) + len(sentence) <= max_length:
                current += sentence + " "
            else:
                if current:
                    parts.append(current.strip())
                    current = sentence + " "
                else:
                    # Handle very long sentences
                    parts.append(sentence[:max_length])
                    current = sentence[max_length:]
        
        if current:
            parts.append(current.strip())
        
        return parts
    
    @commands.command(name="lexclear", aliases=["clearmemory"])
    async def clear_memory(self, ctx):
        """Clear conversation memory with better feedback"""
        user_id = ctx.author.id
        
        if user_id in self.chat_history and self.chat_history[user_id]:
            msg_count = len(self.chat_history[user_id])
            self.chat_history[user_id] = []
            description = f"Bas bhai! {msg_count} messages ka memory clear ho gaya! Fresh start! 🗑️✨"
            mood = "happy"
        else:
            description = "Arre, memory mein kuch hai hi nahi clear karne ko! Already fresh hai! 😅"
            mood = "default"
        
        embed = self.create_embed(description, ctx.author.display_name, mood)
        embed.set_author(name="🧠 Memory Manager", icon_url=None)
        await ctx.send(embed=embed)
    
    @commands.command(name="lexstats")
    async def show_stats(self, ctx):
        """Show bot statistics and user conversation stats"""
        user_id = ctx.author.id
        total_users = len(self.chat_history)
        user_messages = len(self.chat_history.get(user_id, []))
        
        stats_text = f"""**📊 Bot Stats:**
        • Total users: {total_users}
        • Your messages: {user_messages}
        • Active conversations: {sum(1 for h in self.chat_history.values() if h)}
        • API: OpenRouter (DeepSeek)
        
        **💪 Your Status:**
        {"VIP user hai bhai!" if user_messages > 50 else "Regular user" if user_messages > 10 else "New user, welcome!"}"""
        
        embed = discord.Embed(
            title="📈 Lexus Bhai Stats",
            description=stats_text,
            color=self.mood_colors['cool'],
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="Stats updated real-time!")
        await ctx.send(embed=embed)
    
    @commands.command(name="lexhelp")
    async def help_command(self, ctx):
        """Comprehensive help command"""
        help_text = """**💬 Kaise baat karein:**
        • `lexus`, `hey lexus`, ya `lex` likh kar start karo
        • Ya phir mujhe mention karo (@Lexus)
        • DMs mein direct message karo
        
        **🛠️ Commands:**
        • `/lexclear` - Memory clear karo
        • `/lexstats` - Bot aur user stats dekho
        • `/lexhelp` - Ye help message
        
        **✨ Features:**
        • Natural Hyderabadi conversation with emotions
        • Advanced context memory (remembers previous chats)
        • Mood-based responses with colorful embeds
        • Intelligent cooldown system
        • OpenRouter (DeepSeek) powered responses
        
        **🎯 Pro Tips:**
        • Be natural, main samjh jaunga
        • Ask follow-up questions for better conversations
        • Use mix of English, Hindi, Urdu for best experience"""
        
        embed = discord.Embed(
            title="🤖 Lexus Bhai - Advanced Hyderabadi AI",
            description=help_text,
            color=self.mood_colors['friendly'],
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="Made in Hyderabad with ❤️  • Powered by OpenRouter (DeepSeek)")
        await ctx.send(embed=embed)
    
    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        asyncio.create_task(self.cleanup_session())

async def setup(bot):
    """Setup function for the cog"""
    cog = LexusAIChatbot(bot)
    await bot.add_cog(cog)
    logger.info("Lexus AI Chatbot (OpenRouter) loaded successfully!")
