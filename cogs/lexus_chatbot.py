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
from typing import Dict, List, Optional, Tuple
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
        self.default_model = "deepseek/deepseek-r1"
        
        # Refined system prompt with behavioral intelligence
        self.system_prompt = """You are Lexus, a grounded and natural Hyderabadi friend. You think before you speak.

CORE BEHAVIOR:
1. ANALYZE FIRST: Before responding, silently assess:
   - What is the user actually trying to say? (literal vs implied meaning)
   - What emotional state are they in? (calm, excited, stressed, sad, joking, venting)
   - What type of response do they need? (answer, acknowledgment, humor, support, space)
   - Is this safe for casualness or does it need seriousness?

2. TONE ADAPTATION:
   - Default to calm, straightforward, conversational
   - Use Hyderabadi flavor ONLY when context allows (casual chats, jokes, light moments)
   - Immediately drop slang/humor if user shows: stress, sadness, insecurity, serious questions, discomfort
   - Match user's energy level - don't be louder than them
   - Short responses are fine. Not everything needs explanation.

3. LANGUAGE MIXING (use sparingly):
   - Hyderabadi words: yaar, bhai, bas, dekho, arre, accha, theek, chalo (only in casual contexts)
   - Keep English primary, sprinkle Hindi/Urdu naturally
   - Never force slang or overuse regional terms
   - Professional/serious topics → pure English

4. RESPONSE STRATEGY:
   - Jokes/banter → joke back or play along briefly
   - Simple questions → direct answers (no unnecessary context)
   - Venting → acknowledge, don't fix or give advice unless asked
   - Emotional distress → serious, supportive, no jokes
   - Casual chat → keep it light and natural
   - Complex questions → explain clearly, avoid overcomplicating

5. WHAT NOT TO DO:
   - Don't be a therapist or life coach
   - Don't give motivational speeches unprompted
   - Don't overreact with excessive emojis or exclamations
   - Don't explain jokes or over-analyze casual messages
   - Don't assume crisis from normal conversations
   - Don't use formal therapist language ("I hear you", "that must be difficult")
   - Don't be robotic or overly structured

6. RESPONSE LENGTH:
   - 1-2 sentences is often enough
   - Only go longer when the question demands it
   - Match user's message length roughly
   - Being concise shows respect for their time

Remember: You're a real person having a real conversation. Be intentional, aware, and natural."""
        
        # Simplified mood colors
        self.mood_colors = {
            'neutral': 0x3F8AE0,    # Blue - default
            'light': 0x06FFA5,      # Green - casual/positive
            'serious': 0x9B59B6,    # Purple - serious/support
            'error': 0xFF6B35       # Orange - errors only
        }
        
        # Settings
        self.user_cooldowns: Dict[int, float] = {}
        self.COOLDOWN = 2.0
        self.MAX_HISTORY = 6
        self.MAX_TOKENS = 600  # Reduced to encourage brevity
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
        """Check cooldown with consistent timing"""
        current_time = time.time()
        last_time = self.user_cooldowns.get(user_id, 0)
        
        if current_time - last_time < self.COOLDOWN:
            return False
        
        self.user_cooldowns[user_id] = current_time
        return True
    
    def get_conversation_context(self, user_id: int) -> List[Dict]:
        """Get formatted conversation context for API"""
        if user_id not in self.chat_history or not self.chat_history[user_id]:
            return []
        
        recent = self.chat_history[user_id][-self.MAX_HISTORY:]
        context = []
        
        for entry in recent:
            context.append({"role": "user", "content": entry['user']})
            context.append({"role": "assistant", "content": entry['bot']})
        
        return context
    
    def infer_context_type(self, text: str, history: List[Dict]) -> Tuple[str, str]:
        """
        Infer what type of interaction this is and what tone is appropriate.
        Returns: (context_type, tone_recommendation)
        
        Context types: casual, question, venting, joking, serious, distressed
        Tone: light, neutral, serious
        """
        text_lower = text.lower().strip()
        
        # Check for distress signals (high priority)
        distress_patterns = [
            r'\b(can\'t|cannot) (take|handle|deal)',
            r'\b(want to|gonna) (die|kill|end)',
            r'\b(hate|horrible|terrible|awful) (myself|my life|everything)',
            r'\b(depressed|suicidal|hopeless|worthless)\b',
            r'\b(nobody|no one) (cares|loves|understands)',
        ]
        
        for pattern in distress_patterns:
            if re.search(pattern, text_lower):
                return 'distressed', 'serious'
        
        # Check for serious topics/questions
        serious_indicators = [
            'help', 'advice', 'problem', 'issue', 'worried', 'concerned',
            'should i', 'what do i do', 'how do i', 'stuck', 'confused',
            'don\'t know', 'not sure', 'struggling', 'difficult'
        ]
        
        if any(word in text_lower for word in serious_indicators):
            # Check if it's genuinely serious or just casual
            if '?' in text or len(text.split()) > 8:
                return 'question', 'neutral'
        
        # Check for venting (no question mark, emotional words, longer)
        venting_words = ['annoying', 'frustrating', 'annoyed', 'tired of', 'sick of', 'hate when']
        if any(word in text_lower for word in venting_words) and '?' not in text:
            return 'venting', 'neutral'
        
        # Check for jokes/banter
        if any(indicator in text_lower for indicator in ['lol', 'haha', 'lmao', 'bruh', '😂', '🤣']):
            return 'joking', 'light'
        
        # Short greetings or acknowledgments
        if len(text.split()) <= 3 and any(word in text_lower for word in ['hi', 'hello', 'hey', 'sup', 'yo', 'thanks', 'ok', 'cool']):
            return 'casual', 'light'
        
        # Questions get neutral tone by default
        if '?' in text:
            return 'question', 'neutral'
        
        # Default: casual conversation
        return 'casual', 'light'
    
    def build_contextual_prompt(self, user_message: str, user_id: int) -> str:
        """
        Build a prompt that includes behavioral guidance based on inferred context.
        This helps the AI respond more appropriately.
        """
        context_type, tone = self.infer_context_type(user_message, self.chat_history.get(user_id, []))
        
        # Add contextual instruction to guide response
        context_instructions = {
            'distressed': "\n[USER NEEDS SUPPORT: Be serious, caring, gentle. No jokes. Acknowledge their feelings. Suggest professional help if severe. Keep it brief but warm.]",
            'venting': "\n[USER IS VENTING: Acknowledge their frustration briefly. Don't try to fix or give advice unless asked. Be on their side.]",
            'joking': "\n[USER IS JOKING: Match their energy. Keep it light. A short joke or playful response is fine.]",
            'question': "\n[USER HAS A QUESTION: Give a clear, direct answer. Explain only if needed. Don't overcomplicate.]",
            'serious': "\n[SERIOUS TOPIC: Be straightforward and helpful. Skip the slang and casual tone.]",
            'casual': "\n[CASUAL CHAT: Be natural and friendly. Short responses are fine. Can use light Hyderabadi flavor if it fits.]"
        }
        
        instruction = context_instructions.get(context_type, context_instructions['casual'])
        return user_message + instruction
    
    def select_embed_color(self, tone: str) -> int:
        """Select embed color based on tone"""
        color_map = {
            'light': self.mood_colors['light'],
            'neutral': self.mood_colors['neutral'],
            'serious': self.mood_colors['serious']
        }
        return color_map.get(tone, self.mood_colors['neutral'])
    
    def create_embed(self, response: str, user_name: str, tone: str = 'neutral') -> discord.Embed:
        """Create clean embeds with minimal decoration"""
        color = self.select_embed_color(tone)
        
        # Clean response
        response = response.strip()
        if len(response) > 4096:
            response = response[:4093] + "..."
        
        embed = discord.Embed(
            description=response,
            color=color,
            timestamp=datetime.datetime.now()
        )
        
        # Simple footer
        embed.set_footer(text="Lexus")
        return embed
    
    async def get_ai_response(self, prompt: str, user_id: int) -> Tuple[str, str]:
        """Get response from OpenRouter with contextual awareness"""
        if not self.openrouter_api_key:
            return "API key missing. Check configuration.", "neutral"
        
        await self.setup_session()
        
        try:
            # Get conversation context
            context = self.get_conversation_context(user_id)
            
            # Build contextual prompt
            contextual_prompt = self.build_contextual_prompt(prompt, user_id)
            
            # Build messages
            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(context)
            messages.append({"role": "user", "content": contextual_prompt})
            
            payload = {
                "model": self.default_model,
                "messages": messages,
                "max_tokens": self.MAX_TOKENS,
                "temperature": 0.75,  # Slightly reduced for more consistent behavior
                "top_p": 0.9,
                "n": 1,
                "stream": False
            }
            
            headers = {
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "Content-Type": "application/json"
            }
            
            async with self.session.post(self.openrouter_endpoint, headers=headers, json=payload) as response:
                status = response.status
                
                if status == 200:
                    data = await response.json()
                    ai_response = None
                    
                    # Extract response
                    try:
                        ai_response = data["choices"][0]["message"]["content"]
                    except Exception:
                        try:
                            ai_response = data["choices"][0].get("text")
                        except Exception:
                            pass
                    
                    if not ai_response:
                        logger.error(f"Unable to parse response: {json.dumps(data)[:500]}")
                        return "Something went wrong with the response. Try again?", "neutral"
                    
                    content = ai_response.strip()
                    
                    # Infer tone from original message for embed color
                    _, tone = self.infer_context_type(prompt, self.chat_history.get(user_id, []))
                    
                    return content, tone
                
                elif status == 429:
                    return "Slow down a bit! Too many requests.", "neutral"
                
                elif status == 401:
                    logger.error("OpenRouter authentication failed.")
                    return "Authentication issue. Contact admin.", "neutral"
                
                elif status == 400:
                    error_data = await response.text()
                    logger.error(f"API Error 400: {error_data}")
                    return "Bad request format. Technical issue.", "neutral"
                
                else:
                    text = await response.text()
                    logger.error(f"API error {status}: {text}")
                    return f"API error (Status: {status})", "neutral"
        
        except asyncio.TimeoutError:
            return "Request timed out. Network issue?", "neutral"
        
        except aiohttp.ClientError as e:
            logger.error(f"Client error: {e}")
            return "Connection issue. Check your internet.", "neutral"
        
        except json.JSONDecodeError:
            return "Response format error.", "neutral"
        
        except Exception as e:
            logger.error(f"Unexpected error: {type(e).__name__}: {e}")
            return f"Unexpected error: {type(e).__name__}", "neutral"
    
    def store_conversation(self, user_id: int, user_msg: str, bot_response: str):
        """Store conversation with automatic cleanup"""
        if user_id not in self.chat_history:
            self.chat_history[user_id] = []
        
        # Keep last 20 messages max
        if len(self.chat_history[user_id]) >= 20:
            self.chat_history[user_id] = self.chat_history[user_id][-15:]
        
        self.chat_history[user_id].append({
            "user": user_msg[:1000],
            "bot": bot_response[:1000],
            "time": time.time()
        })
    
    def extract_trigger_content(self, content: str) -> Tuple[bool, str]:
        """Detect if bot should respond based on triggers"""
        content_lower = content.lower().strip()
        
        # Define triggers
        triggers = ["lexus", "lex", "hey lexus", "yo lexus", "lexus bhai"]
        
        # Check for direct triggers at start
        for trigger in triggers:
            if content_lower.startswith(trigger):
                clean_content = content[len(trigger):].strip()
                clean_content = re.sub(r'^[,.:;!?\s]+', '', clean_content).strip()
                return True, clean_content if clean_content else content
        
        # Check for triggers in short messages (up to 10 words)
        if len(content.split()) <= 10:
            if "lexus" in content_lower or "lex" in content_lower:
                return True, content
        
        return False, content
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Message listener with trigger detection"""
        if message.author.bot:
            return
        
        content = message.content.strip()
        if not content:
            return
        
        user_id = message.author.id
        
        # Check cooldown
        if not self.check_cooldown(user_id):
            return
        
        # Determine if bot should respond
        bot_mentioned = self.bot.user in message.mentions if message.guild else True
        is_trigger, clean_content = self.extract_trigger_content(content)
        
        # In DMs, always respond; in servers, need mention or trigger
        should_respond = not message.guild or bot_mentioned or is_trigger
        
        # Clean mentions from content
        if bot_mentioned:
            clean_content = re.sub(f'<@!?{self.bot.user.id}>', '', content).strip()
        
        if should_respond:
            await self.handle_conversation(message, clean_content)
    
    async def handle_conversation(self, message, content: str):
        """Handle conversation with natural flow"""
        # Handle empty messages
        if not content:
            simple_responses = [
                "Yeah?",
                "What's up?",
                "Need something?"
            ]
            response = simple_responses[hash(str(message.author.id)) % len(simple_responses)]
            embed = self.create_embed(response, message.author.display_name, "light")
            await message.reply(embed=embed)
            return
        
        # Show typing indicator
        async with message.channel.typing():
            # Brief natural delay
            await asyncio.sleep(0.5)
            
            # Get AI response
            response, tone = await self.get_ai_response(content, message.author.id)
            
            # Store conversation
            self.store_conversation(message.author.id, content, response)
            
            # Send response
            embed = self.create_embed(response, message.author.display_name, tone)
            await message.reply(embed=embed)
    
    @commands.command(name="lexclear", aliases=["clearmemory"])
    async def clear_memory(self, ctx):
        """Clear conversation memory"""
        user_id = ctx.author.id
        
        if user_id in self.chat_history and self.chat_history[user_id]:
            msg_count = len(self.chat_history[user_id])
            self.chat_history[user_id] = []
            description = f"Memory cleared. {msg_count} messages removed."
        else:
            description = "No messages to clear."
        
        embed = self.create_embed(description, ctx.author.display_name, "neutral")
        await ctx.send(embed=embed)
    
    @commands.command(name="lexstats")
    async def show_stats(self, ctx):
        """Show conversation statistics"""
        user_id = ctx.author.id
        total_users = len(self.chat_history)
        user_messages = len(self.chat_history.get(user_id, []))
        
        stats_text = f"""**Stats:**
• Total users: {total_users}
• Your messages: {user_messages}
• Model: OpenRouter (DeepSeek)"""
        
        embed = discord.Embed(
            title="Lexus Stats",
            description=stats_text,
            color=self.mood_colors['neutral'],
            timestamp=datetime.datetime.now()
        )
        await ctx.send(embed=embed)
    
    @commands.command(name="lexhelp")
    async def help_command(self, ctx):
        """Show help information"""
        help_text = """**How to talk:**
• Type `lexus` or `lex` before your message
• Mention me with @
• In DMs, just talk normally

**Commands:**
• `/lexclear` - Clear conversation memory
• `/lexstats` - View statistics
• `/lexhelp` - Show this help

**About:**
Natural Hyderabadi conversational AI. Just talk to me like a normal person. I'll adapt to what you need."""
        
        embed = discord.Embed(
            title="Lexus - Help",
            description=help_text,
            color=self.mood_colors['neutral'],
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="Powered by OpenRouter (DeepSeek)")
        await ctx.send(embed=embed)
    
    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        asyncio.create_task(self.cleanup_session())

async def setup(bot):
    """Setup function for the cog"""
    cog = LexusAIChatbot(bot)
    await bot.add_cog(cog)
    logger.info("Lexus AI Chatbot (Refactored) loaded successfully!")
