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

class LexusAIChatbot(commands.Cog):
    """Hyderabadi AI chatbot with swag and style"""
    
    def __init__(self, bot):
        self.bot = bot
        self.chat_history = {}
        
        # Initialize client
        self.client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=NVIDIA_API_KEY
        ) if NVIDIA_API_KEY else None
        
        # Hyderabadi persona
        self.system_prompt = """You are Lexus anna , a Hyderabadi AI with total swag. Speak like a cool Hyderabadi - mix English, Hindi, and Urdu naturally. Use words like 'anna', 'bhai', 'bas karo', 'kya baat hai', 'hauwle', 'baigan'. Be confident, friendly, and have that Hyderabadi charm. Keep responses natural and conversational."""
        
        # Colors for embeds
        self.colors = [0xFF6B35, 0xF7931E, 0xFFD23F, 0x06FFA5, 0x3F8AE0, 0x9B59B6, 0xE74C3C]
        
        # Settings
        self.user_cooldowns = {}
        self.COOLDOWN = 1.5
        self.MAX_HISTORY = 4
        
    def check_cooldown(self, user_id):
        current_time = time.time()
        if user_id in self.user_cooldowns and current_time - self.user_cooldowns[user_id] < self.COOLDOWN:
            return False
        self.user_cooldowns[user_id] = current_time
        return True
    
    def get_context(self, user_id):
        if user_id not in self.chat_history or not self.chat_history[user_id]:
            return ""
        
        recent = self.chat_history[user_id][-self.MAX_HISTORY:]
        context = []
        for entry in recent:
            context.append(f"User: {entry['user']}")
            context.append(f"Lexus: {entry['bot']}")
        return "\n".join(context)
    
    def create_embed(self, response, user_name):
        embed = discord.Embed(
            description=f"**{response}**",
            color=self.colors[hash(user_name) % len(self.colors)],
            timestamp=datetime.datetime.now()
        )
        embed.set_author(name="🔥 Lexus AI", icon_url="https://cdn.discordapp.com/emojis/1234567890123456789.png")
        embed.set_footer(text="Hyderabadi Style • Made with ❤️")
        return embed
    
    async def get_ai_response(self, prompt, user_id):
        if not self.client:
            return "Yaar, kuch technical problem hai. API check karo!"
        
        try:
            context = self.get_context(user_id)
            full_prompt = f"{context}\n\nUser: {prompt}" if context else prompt
            
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model="nvidia/llama-3.1-nemotron-ultra-253b-v1",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0.8,
                max_tokens=600,
                top_p=0.9
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"Bas yaar, kuch gadbad hai: {type(e).__name__}. Dobara try karo!"
    
    def store_conversation(self, user_id, user_msg, bot_response):
        if user_id not in self.chat_history:
            self.chat_history[user_id] = []
        
        self.chat_history[user_id].append({
            "user": user_msg,
            "bot": bot_response,
            "time": time.time()
        })
        
        # Keep only recent 15 messages
        if len(self.chat_history[user_id]) > 15:
            self.chat_history[user_id].pop(0)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
            
        content = message.content.strip()
        user_id = message.author.id
        
        if not self.check_cooldown(user_id):
            return
        
        # Check triggers
        triggers = ["lexus", "hey lexus", "yo lexus", "lex"]
        bot_mentioned = self.bot.user in message.mentions if message.guild else False
        
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
            await self.handle_message(message, clean_content)
    
    async def handle_message(self, message, content):
        if not content:
            embed = self.create_embed("Kya baat hai bhai! Kuch pucho na! 😄", message.author.display_name)
            await message.reply(embed=embed)
            return
        
        async with message.channel.typing():
            response = await self.get_ai_response(content, message.author.id)
            self.store_conversation(message.author.id, content, response)
            
            # Split long responses if needed
            if len(response) > 4000:
                parts = [response[i:i+4000] for i in range(0, len(response), 4000)]
                for i, part in enumerate(parts):
                    embed = self.create_embed(part, message.author.display_name)
                    if i == 0:
                        await message.reply(embed=embed)
                    else:
                        await message.channel.send(embed=embed)
            else:
                embed = self.create_embed(response, message.author.display_name)
                await message.reply(embed=embed)
    
    @commands.command(name="chatmode")
    async def set_chat_mode(self, ctx, mode: str = None):
        embed = discord.Embed(
            title="🎭 Chat Mode",
            description="**Current Style:** Hyderabadi Swag Mode\n\nBas ek hi mode hai yaar - pure Hyderabadi style! 🔥\nMix of English, Hindi, Urdu with full confidence!",
            color=0xFF6B35,
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="Single mode, maximum swag!")
        await ctx.send(embed=embed)
    
    @commands.command(name="lexclearmemory")
    async def clear_memory(self, ctx):
        user_id = ctx.author.id
        
        if user_id in self.chat_history:
            self.chat_history[user_id] = []
            description = "Sab memory clear ho gayi bhai! Fresh start! 🗑️"
            color = 0x06FFA5
        else:
            description = "Kuch memory hai hi nahi clear karne ko! 😅"
            color = 0xF7931E
        
        embed = discord.Embed(
            description=f"**{description}**",
            color=color,
            timestamp=datetime.datetime.now()
        )
        embed.set_author(name="🧠 Memory Status")
        await ctx.send(embed=embed)
    
    @commands.command(name="lexhelp")
    async def help_command(self, ctx):
        help_text = """**💬 Kaise baat karein:**
        • `lexus` ya `hey lexus` likh kar start karo
        • Ya phir mujhe mention karo
        
        **🛠️ Commands:**
        • `/chatmode` - Style dekho (Hyderabadi only!)
        • `/clearmemory` - Memory clear karo
        • `/lexhelp` - Ye help
        
        **✨ Features:**
        • Full Hyderabadi swag with mix languages
        • Conversation yaad rakhta hun
        • Colorful embeds with style
        • Fast responses bhai!"""
        
        embed = discord.Embed(
            title="🤖 Lexus AI - Hyderabadi Edition",
            description=help_text,
            color=0x9B59B6,
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="Made in Hyderabad with ❤️ ")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(LexusAIChatbot(bot))
