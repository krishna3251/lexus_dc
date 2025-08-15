import discord
from discord.ext import commands
import aiohttp
import asyncio
import random
import time
import os
import logging
from typing import Dict, Optional, Set, List
from dataclasses import dataclass
from collections import deque

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class UserSession:
    """Track user conversation state and context."""
    messages: deque
    last_activity: float
    mood_state: str = "neutral"
    crisis_level: int = 0
    
    def __post_init__(self):
        if not hasattr(self, 'messages'):
            self.messages = deque(maxlen=8)  # Keep last 8 messages for context

class ComfortBot(commands.Cog):
    """Advanced AI mental health companion with natural conversation flow."""
    
    def __init__(self, bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None
        self.nvidia_api_key = os.getenv('NGC_API_KEY')  # Using your env variable
        self.sessions: Dict[int, UserSession] = {}
        self.ai_channels: Set[int] = set()
        self.mod_channels: Set[int] = set()
        
        # Advanced emotion detection with severity levels
        self.crisis_patterns = {
            'severe': ['suicide', 'kill myself', 'want to die', 'end it all', 'no point living'],
            'moderate': ['hopeless', 'worthless', 'cant go on', 'too much pain', 'nobody cares'],
            'mild': ['depressed', 'anxious', 'overwhelmed', 'stressed', 'tired of everything']
        }
        
        # Indian crisis resources (optimized)
        self.crisis_resources = {
            '🇮🇳 **National Suicide Prevention**': '9152987821',
            '🇮🇳 **AASRA Mumbai**': '91-9820466726',
            '🇮🇳 **Vandrevala Foundation**': '9999666555',
            '🚨 **Emergency Services**': '112'
        }

    async def cog_load(self):
        """Initialize session and validate API key."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=10, limit_per_host=5)
        )
        if not self.nvidia_api_key:
            logger.error("NVIDIA API key not found in environment variables!")

    async def cog_unload(self):
        """Clean shutdown."""
        if self.session:
            await self.session.close()

    def get_user_session(self, user_id: int) -> UserSession:
        """Get or create user session with automatic cleanup."""
        current_time = time.time()
        
        # Clean old sessions (inactive for 1 hour)
        to_remove = [uid for uid, session in self.sessions.items() 
                    if current_time - session.last_activity > 3600]
        for uid in to_remove:
            del self.sessions[uid]
        
        if user_id not in self.sessions:
            self.sessions[user_id] = UserSession(
                messages=deque(maxlen=8),
                last_activity=current_time
            )
        
        self.sessions[user_id].last_activity = current_time
        return self.sessions[user_id]

    def analyze_crisis_level(self, text: str) -> tuple[bool, int, str]:
        """Advanced crisis detection with severity assessment."""
        text_lower = text.lower()
        max_level = 0
        detected_type = "none"
        
        for severity, patterns in self.crisis_patterns.items():
            for pattern in patterns:
                if pattern in text_lower:
                    if severity == 'severe':
                        return True, 3, severity
                    elif severity == 'moderate' and max_level < 2:
                        max_level = 2
                        detected_type = severity
                    elif severity == 'mild' and max_level < 1:
                        max_level = 1
                        detected_type = severity
        
        return max_level > 0, max_level, detected_type

    def build_system_prompt(self, session: UserSession, crisis_level: int = 0) -> str:
        """Dynamic system prompt based on user state."""
        base_prompt = """You are Alex, a compassionate AI mental health companion. You communicate naturally and warmly, like talking to a trusted friend.

Core principles:
- Be genuinely empathetic and supportive
- Use natural, conversational language (avoid clinical terms)
- Validate feelings without being dismissive
- Offer practical, gentle suggestions when appropriate
- Remember the conversation context
- Be encouraging but realistic"""

        if crisis_level >= 2:
            base_prompt += "\n\nIMPORTANT: This person may be in crisis. Be extra gentle, validate their pain, and gently suggest professional help while providing emotional support."
        elif session.mood_state in ["sad", "anxious", "stressed"]:
            base_prompt += f"\n\nNote: User seems to be feeling {session.mood_state}. Be extra supportive and gentle."

        base_prompt += "\n\nKeep responses conversational, under 200 words, and genuinely caring. You're here to listen and support, not to fix or diagnose."
        
        return base_prompt

    async def chat_with_ai(self, user_id: int, message: str, session: UserSession, crisis_level: int = 0) -> str:
        """Enhanced AI chat with better error handling and context."""
        if not self.nvidia_api_key:
            return "I'm having trouble connecting to my AI service right now. But I'm still here to listen if you want to talk. 💙"

        # Add user message to session
        session.messages.append({"role": "user", "content": message})
        
        # Build conversation context
        messages = [{"role": "system", "content": self.build_system_prompt(session, crisis_level)}]
        messages.extend(list(session.messages))

        try:
            async with self.session.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.nvidia_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "nvidia/llama-3.3-nemotron-super-49b-v1.5-latest",
                    "messages": messages,
                    "max_tokens": 300,
                    "temperature": 0.8,
                    "top_p": 0.9,
                    "stream": False
                }
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    ai_response = data["choices"][0]["message"]["content"]
                    
                    # Add AI response to session
                    session.messages.append({"role": "assistant", "content": ai_response})
                    return ai_response
                    
                elif resp.status == 429:
                    return "I'm getting a lot of requests right now. Give me a moment to catch my breath, then we can continue talking. 😊"
                elif resp.status == 401:
                    logger.error("Invalid NVIDIA API key")
                    return "I'm having authentication issues. Could you let an admin know? I'm still here to listen though."
                else:
                    logger.error(f"NVIDIA API error: {resp.status}")
                    return f"I'm having some technical difficulties (error {resp.status}), but I'm still here for you. Want to try again in a moment?"
                    
        except asyncio.TimeoutError:
            return "Sorry, that took too long to process. My connection might be slow right now. Want to try again?"
        except Exception as e:
            logger.error(f"AI chat error: {e}")
            return "I'm having some technical issues, but I'm still here to listen. Sometimes just talking helps, even if I can't give the perfect response. 💙"

    @commands.Cog.listener()
    async def on_message(self, message):
        """Natural message handling with context awareness."""
        if message.author.bot or not message.guild:
            return

        # Crisis detection in all channels
        is_crisis, crisis_level, severity = self.analyze_crisis_level(message.content)
        if is_crisis:
            await self.handle_crisis(message, crisis_level, severity)
            return

        # AI chat in dedicated channels
        if message.channel.id in self.ai_channels:
            await self.handle_natural_conversation(message, crisis_level)

    async def handle_natural_conversation(self, message, crisis_level: int = 0):
        """Handle natural AI conversation with typing indicators."""
        session = self.get_user_session(message.author.id)
        
        # Rate limiting (2 messages per minute)
        current_time = time.time()
        if current_time - session.last_activity < 30:
            await message.add_reaction("⏱️")
            return

        async with message.channel.typing():
            # Add small delay for natural feel
            await asyncio.sleep(random.uniform(1, 2))
            response = await self.chat_with_ai(message.author.id, message.content, session, crisis_level)

        # Handle long responses naturally
        if len(response) > 1900:
            parts = [response[i:i+1900] for i in range(0, len(response), 1900)]
            for i, part in enumerate(parts):
                await message.channel.send(part)
                if i < len(parts) - 1:
                    await asyncio.sleep(1)  # Natural pause between parts
        else:
            await message.channel.send(response)

    async def handle_crisis(self, message, level: int, severity: str):
        """Enhanced crisis response with appropriate escalation."""
        session = self.get_user_session(message.author.id)
        session.crisis_level = level

        # Determine response based on severity
        if level >= 3:  # Severe crisis
            embed = discord.Embed(
                title="🚨 I'm really concerned about you",
                description=f"{message.author.mention}, what you're going through sounds incredibly painful. You don't have to face this alone - there are people who want to help.",
                color=discord.Color.red()
            )
            
            # Immediate crisis resources
            crisis_text = "\n".join([f"{name}: `{number}`" for name, number in self.crisis_resources.items()])
            embed.add_field(name="🆘 Immediate Help", value=crisis_text, inline=False)
            embed.add_field(name="💬 Text Support", value="Crisis Text Line: Text **HOME** to **741741**", inline=False)
            
        else:  # Moderate crisis
            embed = discord.Embed(
                title="💙 I hear you",
                description=f"{message.author.mention}, it sounds like you're going through a really tough time. Your feelings are valid, and it's okay to ask for help.",
                color=discord.Color.orange()
            )
            
            support_text = "\n".join([f"{name}: `{number}`" for name, number in list(self.crisis_resources.items())[:2]])
            embed.add_field(name="🤝 Support Available", value=support_text, inline=False)

        embed.set_footer(text="You matter. Your life has value. You are not alone. 💙")
        await message.channel.send(embed=embed)

        # Alert moderators for severe cases
        if level >= 3:
            for channel_id in self.mod_channels:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    alert = discord.Embed(
                        title="⚠️ Crisis Alert - Immediate Attention Needed",
                        description=f"User {message.author.mention} in {message.channel.mention} may be in severe crisis.",
                        color=discord.Color.red()
                    )
                    await channel.send(embed=alert)

    # Streamlined Admin Commands
    @commands.group(name='comfort', invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def comfort(self, ctx):
        """Comfort bot admin panel."""
        embed = discord.Embed(title="🤖 Comfort Bot Control Panel", color=discord.Color.blue())
        embed.add_field(name="Setup", value="`comfort addai` - Enable AI chat in channel\n`comfort addmod` - Add crisis alerts\n`comfort status` - View configuration", inline=False)
        embed.add_field(name="Management", value="`comfort reset [user]` - Clear user data\n`comfort sessions` - View active sessions", inline=False)
        await ctx.send(embed=embed)

    @comfort.command()
    async def addai(self, ctx, channel: discord.TextChannel = None):
        """Enable AI chat in channel."""
        channel = channel or ctx.channel
        self.ai_channels.add(channel.id)
        await ctx.send(f"✅ {channel.mention} is now an AI chat channel!")

    @comfort.command()
    async def addmod(self, ctx, channel: discord.TextChannel = None):
        """Add crisis alert channel."""
        channel = channel or ctx.channel
        self.mod_channels.add(channel.id)
        await ctx.send(f"✅ {channel.mention} will receive crisis alerts.")

    @comfort.command()
    async def status(self, ctx):
        """View bot configuration."""
        embed = discord.Embed(title="📊 Bot Status", color=discord.Color.green())
        embed.add_field(name="AI Channels", value=f"{len(self.ai_channels)} configured", inline=True)
        embed.add_field(name="Active Sessions", value=f"{len(self.sessions)} users", inline=True)
        embed.add_field(name="API Status", value="✅ Connected" if self.nvidia_api_key else "❌ No API Key", inline=True)
        await ctx.send(embed=embed)

    @comfort.command()
    async def reset(self, ctx, user: discord.Member = None):
        """Reset user data."""
        if user:
            self.sessions.pop(user.id, None)
            await ctx.send(f"✅ Reset data for {user.mention}")
        else:
            count = len(self.sessions)
            self.sessions.clear()
            await ctx.send(f"✅ Reset all data ({count} sessions cleared)")

    # Essential User Commands
    @commands.command()
    async def chat(self, ctx, *, message: str):
        """Chat with AI anywhere."""
        session = self.get_user_session(ctx.author.id)
        
        async with ctx.typing():
            response = await self.chat_with_ai(ctx.author.id, message, session)
        
        await ctx.send(response)

    @commands.command()
    async def resources(self, ctx):
        """Get mental health resources."""
        embed = discord.Embed(title="🆘 Mental Health Support", color=discord.Color.red())
        
        crisis_text = "\n".join([f"{name}: `{number}`" for name, number in self.crisis_resources.items()])
        embed.add_field(name="Crisis Hotlines", value=crisis_text, inline=False)
        embed.add_field(name="Online Support", value="• **7 Cups**: https://www.7cups.com/\n• **Crisis Text Line**: Text HOME to 741741", inline=False)
        embed.set_footer(text="You are not alone. Help is available 24/7. 💙")
        
        await ctx.send(embed=embed)

    @commands.command()
    async def checkin(self, ctx):
        """Daily mood check-in."""
        embed = discord.Embed(
            title="💙 How are you feeling today?",
            description="React to let me know how you're doing:",
            color=discord.Color.blue()
        )
        embed.add_field(name="Mood Check", value="😊 Great • 😐 Okay • 😔 Struggling • ❤️ Need support", inline=False)
        
        msg = await ctx.send(embed=embed)
        for emoji in ['😊', '😐', '😔', '❤️']:
            await msg.add_reaction(emoji)

async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(ComfortBot(bot))
