import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os
import random
import tempfile
from gtts import gTTS
import openai
from typing import Optional
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load API Key
openai.api_key = os.getenv("OPENAI_API_KEY")

# Enhanced roast styles with personality
ROAST_STYLES = {
    "savage": "Be brutally honest and savage but not offensive. Use modern slang.",
    "shakespearean": "Roast in eloquent Shakespearean style with 'thou' and 'thy'.",
    "gamer": "Roast with gaming references, noob calls, and esports trash talk.",
    "desi": "Use Indian humor with 'yaar', 'bhai', mix Hindi-English naturally.",
    "anime": "Channel tsundere energy. Use 'baka', 'senpai', dramatic reactions.",
    "villain": "Be theatrically evil with dramatic flair and 'mwahaha'.",
    "robot": "C0MP_U7E R0A$7... *BEEP BOOP* ERROR: HUMAN.EXE WEAK",
    "pirate": "Arrr! Roast like a salty sea pirate with nautical insults.",
    "therapist": "Roast while pretending to be a concerned therapist."
}

# Roast intensity levels
INTENSITY = {
    "mild": "Keep it light and playful, suitable for all audiences.",
    "spicy": "Add some heat but keep it respectful and clever.",
    "nuclear": "Go hard but avoid truly hurtful personal attacks."
}

class RoastBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.current_style = "savage"
        self.intensity = "spicy"
        self.roast_history = {}  # Track user roast counts
        self.battle_sessions = {}  # Active battle sessions
        
    async def _safe_ai_request(self, prompt: str) -> Optional[str]:
        """Safely make OpenAI request with error handling"""
        try:
            if not openai.api_key:
                return "❌ OpenAI API key not configured!"
                
            response = await asyncio.to_thread(
                openai.ChatCompletion.create,
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.8
            )
            return response.choices[0].message["content"].strip()
        except openai.error.RateLimitError:
            return "🚫 AI is taking a breather. Try again in a moment!"
        except openai.error.InvalidRequestError:
            return "⚠️ Something went wrong with the AI request."
        except Exception as e:
            logger.error(f"AI request failed: {e}")
            return "🤖 My roast circuits are overloaded. Try again!"

    async def _speak_in_vc(self, text: str, voice_client) -> bool:
        """Convert text to speech and play in voice channel"""
        try:
            if not voice_client or not voice_client.is_connected():
                return False
                
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
                tts = gTTS(text=text, lang='en', slow=False)
                tts.save(tmp_file.name)
                
                # Wait for current audio to finish
                while voice_client.is_playing():
                    await asyncio.sleep(0.5)
                
                voice_client.play(
                    discord.FFmpegPCMAudio(tmp_file.name),
                    after=lambda e: os.unlink(tmp_file.name) if e is None else logger.error(f"TTS error: {e}")
                )
                return True
        except Exception as e:
            logger.error(f"TTS failed: {e}")
            return False

    # =============== SLASH COMMANDS ===============

    @app_commands.command(name="join", description="Join your voice channel")
    async def join_vc(self, interaction: discord.Interaction):
        try:
            if not interaction.user.voice:
                return await interaction.response.send_message("❌ You need to be in a voice channel first!", ephemeral=True)
            
            channel = interaction.user.voice.channel
            if interaction.guild.voice_client:
                await interaction.guild.voice_client.move_to(channel)
                message = f"🎵 Moved to **{channel.name}**"
            else:
                await channel.connect()
                message = f"🎤 Joined **{channel.name}** - Ready to roast!"
                
            await interaction.response.send_message(message)
        except discord.errors.ClientException:
            await interaction.response.send_message("❌ Already connected to a voice channel!", ephemeral=True)
        except Exception as e:
            logger.error(f"Join VC error: {e}")
            await interaction.response.send_message("⚠️ Couldn't join voice channel.", ephemeral=True)

    @app_commands.command(name="leave", description="Leave voice channel")
    async def leave_vc(self, interaction: discord.Interaction):
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ Not in a voice channel.", ephemeral=True)
        
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("👋 Left voice channel. Thanks for the roast session!")

    @app_commands.command(name="roast", description="Get roasted by AI")
    @app_commands.describe(target="User to roast (optional)", public="Make roast public (default: private)")
    async def roast_user(self, interaction: discord.Interaction, target: Optional[discord.Member] = None, public: bool = False):
        await interaction.response.defer(ephemeral=not public)
        
        victim = target or interaction.user
        user_id = str(victim.id)
        
        # Track roast count
        self.roast_history[user_id] = self.roast_history.get(user_id, 0) + 1
        count = self.roast_history[user_id]
        
        # Create personalized prompt
        extras = ""
        if count > 5:
            extras = f" (They've been roasted {count} times - they might be a masochist)"
        
        prompt = f"""
        {ROAST_STYLES[self.current_style]}
        {INTENSITY[self.intensity]}
        Target: {victim.display_name}{extras}
        Make it clever and original. Keep it under 100 words.
        """
        
        roast = await self._safe_ai_request(prompt)
        if not roast:
            roast = f"Even my AI circuits refuse to roast {victim.display_name} - that's how unremarkable they are! 🤖"
        
        # Speak in VC if connected
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            await self._speak_in_vc(roast, voice_client)
        
        embed = discord.Embed(
            title="🔥 ROAST DELIVERED 🔥",
            description=roast,
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Style: {self.current_style.title()} | Intensity: {self.intensity.title()} | Roast #{count}")
        
        await interaction.followup.send(f"{victim.mention}", embed=embed)

    @app_commands.command(name="battle", description="Epic roast battle between users")
    @app_commands.describe(user1="First fighter", user2="Second fighter")
    async def roast_battle(self, interaction: discord.Interaction, user1: discord.Member, user2: discord.Member):
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ I need to be in a voice channel for epic battles!", ephemeral=True)
        
        if user1 == user2:
            return await interaction.response.send_message("❌ Can't battle yourself! That's just sad.", ephemeral=True)
        
        session_id = f"{interaction.guild.id}-{interaction.channel.id}"
        if session_id in self.battle_sessions:
            return await interaction.response.send_message("⚠️ Battle already in progress!", ephemeral=True)
        
        self.battle_sessions[session_id] = True
        
        try:
            await interaction.response.send_message(f"⚔️ **ROAST BATTLE ROYALE** ⚔️\n{user1.mention} vs {user2.mention}\n*Let the roasting begin!*")
            
            fighters = [user1, user2]
            for round_num in range(1, 4):
                for fighter in fighters:
                    opponent = fighters[1] if fighter == fighters[0] else fighters[0]
                    
                    prompt = f"""
                    {ROAST_STYLES[self.current_style]}
                    This is round {round_num} of a roast battle.
                    Roast {fighter.display_name} in response to their battle with {opponent.display_name}.
                    Make it punchy and battle-worthy. Under 80 words.
                    """
                    
                    roast = await self._safe_ai_request(prompt)
                    if not roast:
                        roast = f"{fighter.display_name} is so boring, even my AI fell asleep! 😴"
                    
                    # Announce and speak
                    await interaction.followup.send(f"**Round {round_num}** 🥊 {fighter.mention}\n> {roast}")
                    await self._speak_in_vc(roast, interaction.guild.voice_client)
                    await asyncio.sleep(3)
            
            # Battle conclusion
            poll_msg = await interaction.followup.send("🏆 **WHO WON?** Vote now!\n👈 for " + user1.display_name + " | 👉 for " + user2.display_name)
            await poll_msg.add_reaction("👈")
            await poll_msg.add_reaction("👉")
            
        except Exception as e:
            logger.error(f"Battle error: {e}")
            await interaction.followup.send("⚠️ Battle interrupted! Technical difficulties.")
        finally:
            self.battle_sessions.pop(session_id, None)

    @app_commands.command(name="style", description="Change roast personality")
    @app_commands.describe(style="Pick your roast flavor")
    async def change_style(self, interaction: discord.Interaction, style: str):
        style_lower = style.lower()
        if style_lower not in ROAST_STYLES:
            styles_list = ", ".join(ROAST_STYLES.keys())
            return await interaction.response.send_message(f"❌ Unknown style! Available: `{styles_list}`", ephemeral=True)
        
        self.current_style = style_lower
        sample_roast = {
            "savage": "Your new style is almost as basic as your previous choice... almost.",
            "shakespearean": "Thou hast chosen wisely, though thy previous taste was questionable.",
            "gamer": "Nice pick! Your previous choice was straight up noob-tier though.",
            "desi": "Arre waah! Finally some sense aa gayi tumhe.",
            "anime": "B-baka! This style is way better than your last choice!",
            "villain": "Excellent choice... MWAHAHAHA! Your previous selection was pathetic!",
            "robot": "*BEEP* STYLE_UPDATED.EXE... PREVIOUS_CHOICE = TRASH.EXE",
            "pirate": "Arr! A fine choice, ye scurvy dog! Yer last pick was more boring than a dead fish!",
            "therapist": "I think this reflects personal growth. Your last choice... well, we can discuss that later."
        }
        
        await interaction.response.send_message(f"✅ **Style changed to {style_lower.title()}!**\n*{sample_roast[style_lower]}*")

    @app_commands.command(name="intensity", description="Set roast intensity level")
    @app_commands.choices(level=[
        app_commands.Choice(name="Mild - Family Friendly", value="mild"),
        app_commands.Choice(name="Spicy - Just Right", value="spicy"),
        app_commands.Choice(name="Nuclear - No Mercy", value="nuclear")
    ])
    async def set_intensity(self, interaction: discord.Interaction, level: app_commands.Choice[str]):
        self.intensity = level.value
        intensity_msgs = {
            "mild": "🧡 Intensity set to **Mild** - Keeping it wholesome!",
            "spicy": "🌶️ Intensity set to **Spicy** - Perfect balance!",
            "nuclear": "☢️ Intensity set to **Nuclear** - May God have mercy on their souls!"
        }
        await interaction.response.send_message(intensity_msgs[level.value])

    @app_commands.command(name="stats", description="View your roast statistics")
    async def roast_stats(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target = user or interaction.user
        user_id = str(target.id)
        count = self.roast_history.get(user_id, 0)
        
        if count == 0:
            msg = f"{target.display_name} is roast-virgin! 🍃"
        elif count < 5:
            msg = f"{target.display_name} has been roasted **{count}** times - Still tender!"
        elif count < 15:
            msg = f"{target.display_name} has taken **{count}** roasts - Getting crispy! 🔥"
        else:
            msg = f"{target.display_name} has been roasted **{count}** times - Completely charred! ☠️"
        
        embed = discord.Embed(title="📊 Roast Statistics", description=msg, color=discord.Color.orange())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="compliment", description="Get a nice compliment instead")
    async def compliment(self, interaction: discord.Interaction, target: Optional[discord.Member] = None):
        await interaction.response.defer()
        
        recipient = target or interaction.user
        prompt = f"Give a genuine, heartwarming compliment to {recipient.display_name}. Be creative and uplifting!"
        
        compliment = await self._safe_ai_request(prompt)
        if not compliment:
            compliment = f"{recipient.display_name} brings joy to everyone around them! ✨"
        
        embed = discord.Embed(
            title="💖 COMPLIMENT DELIVERED 💖",
            description=compliment,
            color=discord.Color.gold()
        )
        
        await interaction.followup.send(f"{recipient.mention}", embed=embed)

    @app_commands.command(name="help", description="Show all available roast commands")
    async def roast_help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🤖 Roast Bot Commands", 
            description="Your personal AI roast machine!",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🎤 Voice Commands",
            value="`/join` - Join your voice channel\n`/leave` - Leave voice channel",
            inline=False
        )
        
        embed.add_field(
            name="🔥 Roast Commands", 
            value="`/roast [user] [public]` - Roast someone\n`/battle <user1> <user2>` - Epic roast battle\n`/compliment [user]` - Be nice for once",
            inline=False
        )
        
        embed.add_field(
            name="⚙️ Settings",
            value="`/style <style>` - Change personality\n`/intensity <level>` - Set roast intensity\n`/stats [user]` - View roast statistics",
            inline=False
        )
        
        embed.add_field(
            name="🎭 Available Styles",
            value=f"`{', '.join(ROAST_STYLES.keys())}`",
            inline=False
        )
        
        embed.add_field(
            name="🌶️ Intensity Levels", 
            value="`mild` - Family friendly\n`spicy` - Just right\n`nuclear` - No mercy",
            inline=False
        )
        
        embed.set_footer(text=f"Current: {self.current_style.title()} style, {self.intensity.title()} intensity")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="random", description="Get a completely random roast")
    async def random_roast(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        # Pick random style and intensity for this roast
        random_style = random.choice(list(ROAST_STYLES.keys()))
        random_intensity = random.choice(list(INTENSITY.keys()))
        
        prompt = f"""
        {ROAST_STYLES[random_style]}
        {INTENSITY[random_intensity]}
        Give a completely random, creative roast about {interaction.user.display_name}.
        Make it unexpected and original. Under 100 words.
        """
        
        roast = await self._safe_ai_request(prompt)
        if not roast:
            roast = "You're so unremarkable, even my random number generator got bored! 🎲"
        
        embed = discord.Embed(
            title="🎲 RANDOM ROAST GENERATOR 🎲",
            description=roast,
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"Random combo: {random_style.title()} + {random_intensity.title()}")
        
        # Speak if in VC
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            await self._speak_in_vc(roast, voice_client)
        
        await interaction.followup.send(f"{interaction.user.mention}", embed=embed)

    @app_commands.command(name="roastoff", description="Challenge someone to a roast-off")
    @app_commands.describe(opponent="Who dares challenge you?")
    async def roast_off(self, interaction: discord.Interaction, opponent: discord.Member):
        if opponent == interaction.user:
            return await interaction.response.send_message("❌ You can't challenge yourself! That's just sad.", ephemeral=True)
        
        if opponent.bot:
            return await interaction.response.send_message("❌ Bots don't have feelings to hurt!", ephemeral=True)
        
        embed = discord.Embed(
            title="⚔️ ROAST-OFF CHALLENGE ⚔️",
            description=f"{interaction.user.mention} challenges {opponent.mention} to a roast battle!\n\n{opponent.mention}, do you accept?",
            color=discord.Color.red()
        )
        
        message = await interaction.response.send_message(embed=embed)
        await message.add_reaction("✅")  # Accept
        await message.add_reaction("❌")  # Decline
        
        def check(reaction, user):
            return user == opponent and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == message.id
        
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
            
            if str(reaction.emoji) == "✅":
                # Start the battle
                await self.roast_battle(interaction, interaction.user, opponent)
            else:
                embed.description = f"{opponent.mention} chickened out! 🐔"
                embed.color = discord.Color.yellow()
                await message.edit(embed=embed)
                
        except asyncio.TimeoutError:
            embed.description = f"{opponent.mention} didn't respond in time. Coward! 🐔"
            embed.color = discord.Color.greyple()
            await message.edit(embed=embed)

    # Error handler for app commands
    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        logger.error(f"App command error: {error}")
        
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"⏰ Slow down! Try again in {error.retry_after:.1f} seconds.", ephemeral=True)
        elif isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
        elif isinstance(error, app_commands.BotMissingPermissions):
            await interaction.response.send_message("❌ I don't have the required permissions!", ephemeral=True)
        else:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Something went wrong! Please try again.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Something went wrong! Please try again.", ephemeral=True)

    # Auto-disconnect when alone in VC
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not member.bot and self.bot.voice_clients:
            for vc in self.bot.voice_clients:
                if vc.guild == member.guild:
                    # Count non-bot members in VC
                    members = [m for m in vc.channel.members if not m.bot]
                    if len(members) == 0:
                        await asyncio.sleep(10)  # Wait 10 seconds before leaving
                        # Double check nobody joined
                        members = [m for m in vc.channel.members if not m.bot]
                        if len(members) == 0:
                            await vc.disconnect()

# =============== COG SETUP FUNCTION ===============
async def setup(bot: commands.Bot):
    """Setup function to load the RoastBot cog"""
    try:
        await bot.add_cog(RoastBot(bot))
        logger.info("✅ RoastBot cog loaded successfully!")
    except Exception as e:
        logger.error(f"❌ Failed to load RoastBot cog: {e}")
        raise
