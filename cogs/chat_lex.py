import discord
from discord.ext import commands
import aiohttp
import asyncio
import random
import time
import os
from typing import Dict, Optional, Set, List


class ComfortBot(commands.Cog):
    """AI-powered comfort and mental health support bot with NVIDIA integration."""
    
    def __init__(self, bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None
        self.nvidia_api_key = os.getenv('NVIDIA_API_KEY')
        self.user_cooldowns: Dict[int, float] = {}
        self.chat_contexts: Dict[int, List[Dict]] = {}  # Store conversation history (10 messages)
        self.comfort_channels: Set[int] = set()
        self.mod_channels: Set[int] = set()
        self.ai_channels: Set[int] = set()  # Dedicated AI chat channels
        
        # Emotion keywords (for crisis detection only)
        self.emotions = {
            'crisis': {'suicide', 'kill myself', 'want to die', 'end it all', 'no point living', 'commit suicide', 'end my life', 'die today', 'better off dead'},
        }
        
        # Quick resources with Indian emergency numbers
        self.resources = {
            'gifs': ['https://media.tenor.com/VcjzHKQVSWgAAAAC/sending-love.gif', 'https://media.tenor.com/7v1HGWwgBUsAAAAC/virtual-hug.gif'],
            'crisis': {
                'India - National Suicide Prevention': '9152987821',
                'India - AASRA Helpline': '91-9820466726', 
                'India - Vandrevala Foundation': '9999666555',
                'India - Emergency Services': '112',
                'US - Crisis Lifeline': '988',
                'UK - Samaritans': '116 123',
                'Canada - Crisis Services': '1-833-456-4566',
                'Australia - Lifeline': '13 11 14'
            },
            'affirmations': [
                "You matter and your life has value.", 
                "This difficult moment will pass.", 
                "You're stronger than you realize.", 
                "Tomorrow brings new possibilities.",
                "You deserve love and happiness.",
                "Your feelings are valid and temporary.",
                "You have people who care about you.",
                "Every day is a chance to start fresh."
            ]
        }

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    def is_cooldown(self, uid: int) -> bool:
        return time.time() - self.user_cooldowns.get(uid, 0) < 180  # 3min cooldown for dedicated channels

    def detect_crisis(self, text: str) -> bool:
        """Only detect crisis situations for emergency response."""
        text = text.lower()
        for word in self.emotions['crisis']:
            if word in text:
                return True
        return False

    async def nvidia_chat(self, user_id: int, message: str, system_prompt: str = None) -> str:
        """Chat with NVIDIA AI API with 10-message memory."""
        if not self.nvidia_api_key:
            return "AI chat is not configured. Please set NVIDIA_API_KEY environment variable."
        
        # Manage conversation context (keep last 10 messages - 5 user + 5 AI)
        if user_id not in self.chat_contexts:
            self.chat_contexts[user_id] = []
        
        context = self.chat_contexts[user_id]
        context.append({"role": "user", "content": message})
        
        # Keep only last 10 messages (5 user + 5 assistant pairs)
        if len(context) > 10:
            context = context[-10:]
        
        # Build messages for API
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.extend(context)
        
        try:
            headers = {
                "Authorization": f"Bearer {self.nvidia_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "meta/llama-3.1-405b-instruct",  # NVIDIA's model
                "messages": messages,
                "max_tokens": 400,
                "temperature": 0.7
            }
            
            async with self.session.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers=headers,
                json=payload
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    ai_response = data["choices"][0]["message"]["content"]
                    
                    # Store AI response in context
                    context.append({"role": "assistant", "content": ai_response})
                    self.chat_contexts[user_id] = context
                    
                    return ai_response
                else:
                    return f"AI service error: {resp.status}"
                    
        except Exception as e:
            return f"Error connecting to AI: {str(e)[:100]}"

    async def get_comfort_content(self) -> tuple:
        """Fetch comfort content from APIs."""
        apis = {
            'advice': 'https://api.adviceslip.com/advice',
            'quote': 'https://zenquotes.io/api/random',
            'joke': 'https://icanhazdadjoke.com/'
        }
        
        content_type = random.choice(list(apis.keys()))
        
        try:
            if content_type == 'joke':
                headers = {'Accept': 'application/json'}
                async with self.session.get(apis[content_type], headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return ("😄 Dad Joke:", data['joke'])
            else:
                async with self.session.get(apis[content_type]) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if content_type == 'advice':
                            return ("💡 Advice:", data['slip']['advice'])
                        else:  # quote
                            return ("🌟 Quote:", f"{data[0]['q']} - {data[0]['a']}")
        except:
            pass
            
        return ("💖 Affirmation:", random.choice(self.resources['affirmations']))

    @commands.Cog.listener()
    async def on_message(self, message):
        """Main message listener - dedicated channel support with crisis detection."""
        if message.author.bot or not message.guild:
            return

        # Check for crisis situations in any channel
        if self.detect_crisis(message.content):
            await self.handle_crisis(message)
            return

        # Handle AI chat in dedicated channels
        if self.ai_channels and message.channel.id in self.ai_channels:
            if not self.is_cooldown(message.author.id):
                await self.handle_ai_chat(message)
                self.user_cooldowns[message.author.id] = time.time()

    async def handle_ai_chat(self, message):
        """Handle AI chat functionality in dedicated channels."""
        query = message.content.strip()
        if not query:
            return
            
        # Enhanced system prompt for mental health support
        system_prompt = """You are a compassionate AI mental health companion. You provide:
        - Emotional support and validation
        - Practical coping strategies
        - Mindfulness and relaxation techniques
        - Positive affirmations when appropriate
        - Gentle guidance without being preachy
        
        Always be warm, empathetic, and supportive. If someone seems in crisis, gently suggest professional help while being caring. Keep responses conversational and not too long."""
        
        async with message.channel.typing():
            response = await self.nvidia_chat(message.author.id, query, system_prompt)
            
        # Split long responses
        if len(response) > 1900:
            chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
            for chunk in chunks:
                await message.channel.send(chunk)
        else:
            await message.channel.send(response)

    async def handle_crisis(self, message):
        """Handle crisis situations with Indian emergency numbers."""
        embed = discord.Embed(
            title="🚨 Crisis Support - You're Not Alone",
            description="I'm concerned about you. Please reach out for immediate help. Your life matters and people care about you.",
            color=discord.Color.red()
        )
        
        # Split crisis numbers into sections for better readability
        indian_numbers = {
            'India - National Suicide Prevention': '9152987821',
            'India - AASRA Mumbai': '91-9820466726', 
            'India - Vandrevala Foundation': '9999666555',
            'India - Emergency Services': '112'
        }
        
        international_numbers = {
            'US - Crisis Lifeline': '988',
            'UK - Samaritans': '116 123',
            'Canada - Crisis Services': '1-833-456-4566',
            'Australia - Lifeline': '13 11 14'
        }
        
        indian_text = "\n".join([f"**{name}:** {number}" for name, number in indian_numbers.items()])
        international_text = "\n".join([f"**{name}:** {number}" for name, number in international_numbers.items()])
        
        embed.add_field(name="🇮🇳 India Crisis Hotlines", value=indian_text, inline=False)
        embed.add_field(name="🌍 International Hotlines", value=international_text, inline=False)
        embed.add_field(name="💬 Online Support", value="• Crisis Text Line: Text HOME to 741741\n• 7 Cups: https://www.7cups.com/", inline=False)
        embed.set_footer(text="You are valuable. You are loved. Help is available 24/7. 💙")
        
        await message.channel.send(embed=embed)
        
        # Alert mods if configured
        for channel_id in self.mod_channels:
            channel = self.bot.get_channel(channel_id)
            if channel:
                mod_embed = discord.Embed(
                    title="⚠️ Crisis Alert",
                    description=f"User {message.author.mention} may need support in {message.channel.mention}",
                    color=discord.Color.orange()
                )
                await channel.send(embed=mod_embed)

    # ADMIN COMMANDS
    @commands.group(name='comfort')
    @commands.has_permissions(administrator=True)
    async def comfort_admin(self, ctx):
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(title="🤖 Comfort Bot Admin Panel", color=discord.Color.blue())
            embed.add_field(name="Channel Management", value="`addai` - Add AI chat channel\n`addmod` - Add mod alert channel\n`channels` - View configured channels", inline=False)
            embed.add_field(name="User Management", value="`reset [user]` - Reset user chat data\n`memory [user]` - View user's message count", inline=False)
            embed.set_footer(text="Note: Crisis detection works in all channels automatically")
            await ctx.send(embed=embed)

    @comfort_admin.command()
    async def addai(self, ctx, channel: discord.TextChannel = None):
        """Add a channel for dedicated AI chat."""
        channel = channel or ctx.channel
        self.ai_channels.add(channel.id)
        await ctx.send(f"✅ {channel.mention} is now a dedicated AI chat channel. Users can chat directly without commands!")

    @comfort_admin.command()
    async def addmod(self, ctx, channel: discord.TextChannel = None):
        """Add a channel for crisis alert notifications."""
        channel = channel or ctx.channel
        self.mod_channels.add(channel.id)
        await ctx.send(f"✅ {channel.mention} will receive crisis alerts.")

    @comfort_admin.command()
    async def removeai(self, ctx, channel: discord.TextChannel = None):
        """Remove AI chat from a channel."""
        channel = channel or ctx.channel
        self.ai_channels.discard(channel.id)
        await ctx.send(f"✅ Removed AI chat from {channel.mention}")

    @comfort_admin.command()
    async def removemod(self, ctx, channel: discord.TextChannel = None):
        """Remove mod alerts from a channel."""
        channel = channel or ctx.channel
        self.mod_channels.discard(channel.id)
        await ctx.send(f"✅ Removed mod alerts from {channel.mention}")

    @comfort_admin.command()
    async def channels(self, ctx):
        """View all configured channels."""
        embed = discord.Embed(title="📋 Configured Channels", color=discord.Color.blue())
        
        ai = [f"<#{cid}>" for cid in self.ai_channels]
        mod = [f"<#{cid}>" for cid in self.mod_channels]
        
        embed.add_field(name="🤖 AI Chat Channels", value=" ".join(ai) or "None configured", inline=False)
        embed.add_field(name="🚨 Mod Alert Channels", value=" ".join(mod) or "None configured", inline=False)
        embed.add_field(name="ℹ️ Info", value="Crisis detection works in ALL channels automatically", inline=False)
        await ctx.send(embed=embed)

    @comfort_admin.command()
    async def reset(self, ctx, user: discord.Member = None):
        """Reset user data (cooldowns and chat memory)."""
        if user:
            self.user_cooldowns.pop(user.id, None)
            messages_cleared = len(self.chat_contexts.get(user.id, []))
            self.chat_contexts.pop(user.id, None)
            await ctx.send(f"✅ Reset data for {user.mention} ({messages_cleared} messages cleared)")
        else:
            total_users = len(self.chat_contexts)
            total_messages = sum(len(msgs) for msgs in self.chat_contexts.values())
            self.user_cooldowns.clear()
            self.chat_contexts.clear()
            await ctx.send(f"✅ Reset all user data ({total_users} users, {total_messages} messages cleared)")

    @comfort_admin.command()
    async def memory(self, ctx, user: discord.Member = None):
        """Check user's chat memory."""
        if not user:
            total_users = len(self.chat_contexts)
            total_messages = sum(len(msgs) for msgs in self.chat_contexts.values())
            embed = discord.Embed(title="💭 Memory Overview", color=discord.Color.purple())
            embed.add_field(name="Total Users", value=str(total_users), inline=True)
            embed.add_field(name="Total Messages", value=str(total_messages), inline=True)
            embed.add_field(name="Memory Limit", value="10 messages per user", inline=True)
            await ctx.send(embed=embed)
        else:
            messages = self.chat_contexts.get(user.id, [])
            embed = discord.Embed(title=f"💭 {user.display_name}'s Memory", color=discord.Color.purple())
            embed.add_field(name="Messages Stored", value=f"{len(messages)}/10", inline=True)
            if messages:
                last_msg = messages[-1]['content'][:100] + "..." if len(messages[-1]['content']) > 100 else messages[-1]['content']
                embed.add_field(name="Last Message", value=last_msg, inline=False)
            await ctx.send(embed=embed)

    # USER COMMANDS
    @commands.command()
    async def chat(self, ctx, *, message):
        """Chat with AI assistant (works in any channel)."""
        if self.is_cooldown(ctx.author.id):
            await ctx.send("Please wait a moment before chatting again. ⏰")
            return
            
        async with ctx.typing():
            system_prompt = "You are a helpful and friendly AI assistant. Be supportive, conversational, and engaging."
            response = await self.nvidia_chat(ctx.author.id, message, system_prompt)
        
        if len(response) > 1900:
            chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
            for chunk in chunks:
                await ctx.send(chunk)
        else:
            await ctx.send(response)
        self.user_cooldowns[ctx.author.id] = time.time()

    @commands.command()
    async def clearmemory(self, ctx):
        """Clear your AI chat history."""
        messages_cleared = len(self.chat_contexts.get(ctx.author.id, []))
        self.chat_contexts.pop(ctx.author.id, None)
        await ctx.send(f"🗑️ Cleared your chat memory! ({messages_cleared} messages removed)")

    @commands.command()
    async def mymemory(self, ctx):
        """Check your chat memory status."""
        messages = self.chat_contexts.get(ctx.author.id, [])
        embed = discord.Embed(title="💭 Your Chat Memory", color=discord.Color.purple())
        embed.add_field(name="Messages Stored", value=f"{len(messages)}/10", inline=True)
        if messages:
            last_msg = messages[-1]['content'][:100] + "..." if len(messages[-1]['content']) > 100 else messages[-1]['content']
            embed.add_field(name="Last Message", value=last_msg, inline=False)
        embed.set_footer(text="Memory automatically manages the last 10 messages")
        await ctx.send(embed=embed)

    @commands.command()
    async def advice(self, ctx):
        """Get random advice."""
        title, content = await self.get_comfort_content()
        if "Advice" in title:
            embed = discord.Embed(title=title, description=content, color=discord.Color.gold())
            await ctx.send(embed=embed)
        else:
            await ctx.invoke(self.advice)  # Retry

    @commands.command()
    async def quote(self, ctx):
        """Get motivational quote."""
        try:
            async with self.session.get('https://zenquotes.io/api/random') as resp:
                if resp.status == 200:
                    data = await resp.json()
                    quote = f"{data[0]['q']} - {data[0]['a']}"
                    embed = discord.Embed(title="🌟 Inspirational Quote", description=quote, color=discord.Color.purple())
                    await ctx.send(embed=embed)
        except:
            await ctx.send("🌟 **Quote:** 'The only way out is through.' - Robert Frost")

    @commands.command()
    async def joke(self, ctx):
        """Get a dad joke to lighten the mood."""
        try:
            headers = {'Accept': 'application/json'}
            async with self.session.get('https://icanhazdadjoke.com/', headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    embed = discord.Embed(title="😄 Dad Joke", description=data['joke'], color=discord.Color.orange())
                    await ctx.send(embed=embed)
        except:
            await ctx.send("😄 **Dad Joke:** Why don't scientists trust atoms? Because they make up everything!")

    @commands.command()
    async def hug(self, ctx, member: discord.Member = None):
        """Send a virtual hug."""
        target = member.mention if member else ctx.author.mention
        embed = discord.Embed(
            title="🤗 Virtual Hug",
            description=f"Sending warm hugs to {target}! 💕",
            color=discord.Color.pink()
        )
        embed.set_image(url=random.choice(self.resources['gifs']))
        await ctx.send(embed=embed)

    @commands.command()
    async def resources(self, ctx):
        """Get comprehensive crisis resources."""
        embed = discord.Embed(title="🆘 Mental Health Resources", color=discord.Color.red())
        
        # Indian resources
        indian_text = "**National Suicide Prevention:** 9152987821\n**AASRA Mumbai:** 91-9820466726\n**Vandrevala Foundation:** 9999666555\n**Emergency Services:** 112"
        embed.add_field(name="🇮🇳 India Crisis Hotlines", value=indian_text, inline=False)
        
        # International
        intl_text = "**US Crisis Lifeline:** 988\n**UK Samaritans:** 116 123\n**Canada Crisis Services:** 1-833-456-4566\n**Australia Lifeline:** 13 11 14"
        embed.add_field(name="🌍 International", value=intl_text, inline=False)
        
        # Online support
        online_text = "• **7 Cups:** https://www.7cups.com/\n• **Crisis Text Line:** Text HOME to 741741\n• **Befrienders Worldwide:** https://www.befrienders.org/"
        embed.add_field(name="💬 Online Support", value=online_text, inline=False)
        
        embed.set_footer(text="You are not alone. Help is available 24/7. Your life has value. 💙")
        await ctx.send(embed=embed)

    @commands.command()
    async def checkin(self, ctx):
        """Daily mood check-in."""
        embed = discord.Embed(
            title="💙 Daily Check-in",
            description=f"Hi {ctx.author.mention}! How are you feeling today?",
            color=discord.Color.blue()
        )
        embed.add_field(name="React with your mood:", value="😊 Great day! • 😐 Doing okay • 😔 Struggling today • ❤️ Need some support", inline=False)
        embed.set_footer(text="Your feelings are valid. We're here for you.")
        
        msg = await ctx.send(embed=embed)
        for emoji in ['😊', '😐', '😔', '❤️']:
            await msg.add_reaction(emoji)

    @commands.command()
    async def affirmation(self, ctx):
        """Get a positive affirmation."""
        affirmation = random.choice(self.resources['affirmations'])
        embed = discord.Embed(title="💖 Daily Affirmation", description=affirmation, color=discord.Color.pink())
        embed.set_footer(text="You are worthy of love and happiness.")
        await ctx.send(embed=embed)

    @commands.command()
    async def breathe(self, ctx):
        """Guided breathing exercise."""
        embed = discord.Embed(
            title="🌸 Breathing Exercise",
            description="Let's do a simple 4-7-8 breathing exercise together:",
            color=discord.Color.green()
        )
        embed.add_field(name="Instructions:", value="1. Inhale for 4 counts\n2. Hold for 7 counts\n3. Exhale for 8 counts\n4. Repeat 3-4 times", inline=False)
        embed.add_field(name="Remember:", value="Focus on your breath and let other thoughts pass by gently.", inline=False)
        embed.set_footer(text="You're taking a positive step by practicing mindfulness.")
        await ctx.send(embed=embed)


# Setup function
async def setup(bot):
    await bot.add_cog(ComfortBot(bot))
