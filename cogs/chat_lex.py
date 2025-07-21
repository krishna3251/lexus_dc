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
        self.chat_contexts: Dict[int, List[Dict]] = {}  # Store conversation history
        self.comfort_channels: Set[int] = set()
        self.mod_channels: Set[int] = set()
        self.ai_channels: Set[int] = set()  # Channels where AI chat is enabled
        
        # Emotion keywords (shortened but comprehensive)
        self.emotions = {
            'sad': {'sad', 'depressed', 'lonely', 'down', 'crying', 'hurt', 'miserable', 'hopeless', 'empty', 'worthless'},
            'crisis': {'suicide', 'kill myself', 'want to die', 'end it all', 'no point living'},
            'anxiety': {'anxious', 'worried', 'stressed', 'panic', 'overwhelmed', 'scared'},
            'positive': {'happy', 'excited', 'great', 'awesome', 'love', 'grateful', 'blessed', 'amazing'}
        }
        
        # Quick resources
        self.resources = {
            'gifs': ['https://media.tenor.com/VcjzHKQVSWgAAAAC/sending-love.gif', 'https://media.tenor.com/7v1HGWwgBUsAAAAC/virtual-hug.gif'],
            'crisis': {'US': '988', 'UK': '116 123', 'CA': '1-833-456-4566', 'AU': '13 11 14'},
            'affirmations': ["You matter.", "This too shall pass.", "You're stronger than you know.", "Tomorrow is a new day."]
        }

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    def is_cooldown(self, uid: int) -> bool:
        return time.time() - self.user_cooldowns.get(uid, 0) < 300  # 5min cooldown

    def detect_emotion(self, text: str) -> str:
        text = text.lower()
        for emotion, words in self.emotions.items():
            if any(word in text for word in words):
                return emotion
        return 'neutral'

    async def nvidia_chat(self, user_id: int, message: str, system_prompt: str = None) -> str:
        """Chat with NVIDIA AI API."""
        if not self.nvidia_api_key:
            return "AI chat is not configured. Please set NVIDIA_API_KEY environment variable."
        
        # Manage conversation context (keep last 6 messages)
        if user_id not in self.chat_contexts:
            self.chat_contexts[user_id] = []
        
        context = self.chat_contexts[user_id]
        context.append({"role": "user", "content": message})
        
        if len(context) > 6:
            context = context[-6:]
        
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
                "max_tokens": 300,
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
        """Main message listener with AI integration."""
        if message.author.bot or not message.guild:
            return

        emotion = self.detect_emotion(message.content)
        
        # Handle AI chat
        if message.content.startswith('!chat') or (self.ai_channels and message.channel.id in self.ai_channels):
            if not self.is_cooldown(message.author.id):
                await self.handle_ai_chat(message)
                self.user_cooldowns[message.author.id] = time.time()
            return

        # Handle emotions
        if emotion == 'crisis':
            await self.handle_crisis(message)
        elif emotion in ['sad', 'anxiety'] and not self.is_cooldown(message.author.id):
            if not self.comfort_channels or message.channel.id in self.comfort_channels:
                await self.offer_comfort(message, emotion)
        elif emotion == 'positive' and random.random() < 0.2:
            await message.add_reaction(random.choice(['🎉', '❤️', '🌟']))

    async def handle_ai_chat(self, message):
        """Handle AI chat functionality."""
        query = message.content.replace('!chat', '').strip()
        if not query and not (self.ai_channels and message.channel.id in self.ai_channels):
            await message.channel.send("What would you like to chat about?")
            return
            
        if not query:
            query = message.content
            
        # Emotional context system prompt
        emotion = self.detect_emotion(query)
        system_prompts = {
            'sad': "You are a compassionate AI assistant. The user seems sad. Respond with empathy, validation, and gentle support. Be warm but not overly cheerful.",
            'anxiety': "You are a calming AI assistant. The user seems anxious. Provide reassuring, practical advice and validation. Be gentle and supportive.",
            'crisis': "You are a crisis-aware AI assistant. The user may be in distress. Encourage seeking professional help while being supportive. Mention crisis resources if appropriate.",
            'positive': "You are an enthusiastic AI assistant. The user seems happy. Share in their positivity while being genuine and encouraging.",
            'neutral': "You are a helpful, friendly AI assistant. Be conversational, supportive, and engaging."
        }
        
        system_prompt = system_prompts.get(emotion, system_prompts['neutral'])
        
        async with message.channel.typing():
            response = await self.nvidia_chat(message.author.id, query, system_prompt)
            
        # Split long responses
        if len(response) > 1900:
            chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
            for chunk in chunks:
                await message.channel.send(chunk)
        else:
            await message.channel.send(response)

    async def offer_comfort(self, message, emotion):
        """Offer comfort with AI enhancement."""
        emotion_text = "down" if emotion == "sad" else "anxious"
        
        embed = discord.Embed(
            title=f"💙 I noticed you seem {emotion_text}",
            description=f"Hi {message.author.mention}, I'm here to help. React ✅ for comfort content or 🤖 for AI chat.",
            color=discord.Color.blue()
        )
        
        msg = await message.channel.send(embed=embed)
        await msg.add_reaction('✅')
        await msg.add_reaction('🤖')
        
        def check(reaction, user):
            return (user == message.author and reaction.message.id == msg.id 
                   and str(reaction.emoji) in ['✅', '🤖'])
        
        try:
            reaction, _ = await self.bot.wait_for('reaction_add', check=check, timeout=30.0)
            
            if str(reaction.emoji) == '✅':
                await self.send_comfort(message, msg)
            else:  # 🤖
                await self.start_ai_comfort_chat(message, msg, emotion)
                
            self.user_cooldowns[message.author.id] = time.time()
            
        except asyncio.TimeoutError:
            embed = discord.Embed(title="💙 I'm here when you need me", color=discord.Color.light_grey())
            await msg.edit(embed=embed)
            await msg.clear_reactions()

    async def send_comfort(self, original_msg, comfort_msg):
        """Send comfort content."""
        title, content = await self.get_comfort_content()
        
        embed = discord.Embed(title=title, description=content, color=discord.Color.green())
        embed.set_image(url=random.choice(self.resources['gifs']))
        embed.set_footer(text="You matter. You are loved. 💙")
        
        await comfort_msg.edit(embed=embed)
        await comfort_msg.clear_reactions()

    async def start_ai_comfort_chat(self, message, comfort_msg, emotion):
        """Start AI comfort chat session."""
        await comfort_msg.delete()
        
        prompt = f"The user seems {emotion}. Start a supportive conversation."
        response = await self.nvidia_chat(message.author.id, message.content, 
                                        "You are a compassionate AI counselor. Be supportive and caring.")
        
        embed = discord.Embed(
            title="🤖 AI Comfort Chat Started",
            description=response,
            color=discord.Color.purple()
        )
        embed.set_footer(text="Continue chatting or use !stopchat to end • AI responses may take a moment")
        
        await message.channel.send(embed=embed)

    async def handle_crisis(self, message):
        """Handle crisis situations."""
        embed = discord.Embed(
            title="🚨 Crisis Support",
            description="I'm concerned about you. Please reach out for immediate help:",
            color=discord.Color.red()
        )
        
        crisis_text = "\n".join([f"**{country}:** {number}" for country, number in self.resources['crisis'].items()])
        embed.add_field(name="Crisis Hotlines", value=crisis_text, inline=False)
        embed.add_field(name="Online", value="Crisis Text Line: Text HOME to 741741", inline=False)
        embed.set_footer(text="You are not alone. Your life matters. 💙")
        
        await message.channel.send(embed=embed)
        
        # Alert mods
        for channel_id in self.mod_channels:
            channel = self.bot.get_channel(channel_id)
            if channel:
                mod_embed = discord.Embed(
                    title="⚠️ Crisis Alert",
                    description=f"User {message.author.mention} needs support in {message.channel.mention}",
                    color=discord.Color.orange()
                )
                await channel.send(embed=mod_embed)

    # ADMIN COMMANDS (Shortened)
    @commands.group(name='comfort')
    @commands.has_permissions(administrator=True)
    async def comfort_admin(self, ctx):
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(title="Comfort Bot Admin", color=discord.Color.blue())
            embed.add_field(name="Channels", value="`addchannel` `addmod` `addai` `channels`", inline=False)
            embed.add_field(name="Settings", value="`reset [user]` - Reset user data", inline=False)
            await ctx.send(embed=embed)

    @comfort_admin.command()
    async def addchannel(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        self.comfort_channels.add(channel.id)
        await ctx.send(f"✅ {channel.mention} added to comfort detection.")

    @comfort_admin.command()
    async def addmod(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        self.mod_channels.add(channel.id)
        await ctx.send(f"✅ {channel.mention} added for crisis alerts.")

    @comfort_admin.command()
    async def addai(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        self.ai_channels.add(channel.id)
        await ctx.send(f"✅ {channel.mention} enabled for AI chat.")

    @comfort_admin.command()
    async def channels(self, ctx):
        embed = discord.Embed(title="Configured Channels", color=discord.Color.blue())
        comfort = [f"<#{cid}>" for cid in self.comfort_channels]
        mod = [f"<#{cid}>" for cid in self.mod_channels]  
        ai = [f"<#{cid}>" for cid in self.ai_channels]
        
        embed.add_field(name="Comfort", value=" ".join(comfort) or "All channels", inline=False)
        embed.add_field(name="Mod Alerts", value=" ".join(mod) or "None", inline=False)
        embed.add_field(name="AI Chat", value=" ".join(ai) or "Command only", inline=False)
        await ctx.send(embed=embed)

    @comfort_admin.command()
    async def reset(self, ctx, user: discord.Member = None):
        if user:
            self.user_cooldowns.pop(user.id, None)
            self.chat_contexts.pop(user.id, None)
            await ctx.send(f"✅ Reset data for {user.mention}")
        else:
            self.user_cooldowns.clear()
            self.chat_contexts.clear()
            await ctx.send("✅ Reset all user data")

    # USER COMMANDS (Essential ones)
    @commands.command()
    async def chat(self, ctx, *, message):
        """Chat with AI assistant."""
        if self.is_cooldown(ctx.author.id):
            await ctx.send("Please wait a moment before chatting again.")
            return
            
        async with ctx.typing():
            response = await self.nvidia_chat(ctx.author.id, message)
        await ctx.send(response)
        self.user_cooldowns[ctx.author.id] = time.time()

    @commands.command()
    async def stopchat(self, ctx):
        """Clear AI chat history."""
        self.chat_contexts.pop(ctx.author.id, None)
        await ctx.send("🤖 Chat history cleared!")

    @commands.command()
    async def advice(self, ctx):
        """Get advice."""
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
                    embed = discord.Embed(title="🌟 Quote", description=quote, color=discord.Color.purple())
                    await ctx.send(embed=embed)
        except:
            await ctx.send("🌟 **Quote:** 'The only way out is through.' - Robert Frost")

    @commands.command()
    async def joke(self, ctx):
        """Get a dad joke."""
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
            description=f"Sending warm hugs to {target}!",
            color=discord.Color.pink()
        )
        embed.set_image(url=random.choice(self.resources['gifs']))
        await ctx.send(embed=embed)

    @commands.command()
    async def resources(self, ctx):
        """Get crisis resources."""
        embed = discord.Embed(title="🆘 Crisis Resources", color=discord.Color.red())
        crisis_text = "\n".join([f"**{country}:** {number}" for country, number in self.resources['crisis'].items()])
        embed.add_field(name="Crisis Hotlines", value=crisis_text, inline=False)
        embed.add_field(name="Online Support", value="• 7 Cups: https://www.7cups.com/\n• Crisis Text Line: Text HOME to 741741", inline=False)
        embed.set_footer(text="You are not alone. Help is available. 💙")
        await ctx.send(embed=embed)

    @commands.command()
    async def checkin(self, ctx):
        """Daily mood check-in."""
        embed = discord.Embed(
            title="💙 How are you feeling?",
            description="React with your current mood:",
            color=discord.Color.blue()
        )
        embed.add_field(name="Mood Options", value="😊 Great • 😐 Okay • 😔 Not good • ❤️ Need support", inline=False)
        
        msg = await ctx.send(embed=embed)
        for emoji in ['😊', '😐', '😔', '❤️']:
            await msg.add_reaction(emoji)

    @commands.command()
    async def affirmation(self, ctx):
        """Get a positive affirmation."""
        affirmation = random.choice(self.resources['affirmations'])
        embed = discord.Embed(title="💖 Affirmation", description=affirmation, color=discord.Color.pink())
        await ctx.send(embed=embed)


# Setup function
async def setup(bot):
    await bot.add_cog(ComfortBot(bot))
