import discord
from discord.ext import commands, tasks
import wavelink
import edge_tts
import redis
import os
import time
import uuid
import asyncio
import logging
from typing import Optional
from pathlib import Path

# Configure logging
logger = logging.getLogger(__name__)

# Configuration
REDIS_URL = os.getenv("REDIS_URL")
TTS_VOICE = "en-US-AriaNeural"
USER_COOLDOWN = 10        # seconds
IDLE_TIMEOUT = 120        # seconds
TMP_DIR = Path("/tmp")
MAX_TEXT_LENGTH = 500     # characters
RECONNECT_ATTEMPTS = 3


class TTSError(Exception):
    """Base exception for TTS operations"""
    pass


class AudioGenerationError(TTSError):
    """Raised when audio generation fails"""
    pass


class RedisConnectionError(TTSError):
    """Raised when Redis operations fail"""
    pass


class RedisManager:
    """Manages Redis operations with error handling"""
    
    def __init__(self, redis_url: str):
        if not redis_url:
            raise ValueError("REDIS_URL environment variable not set")
        try:
            self.db = redis.from_url(redis_url, decode_responses=True)
            self.db.ping()
        except redis.RedisError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise RedisConnectionError(f"Redis connection failed: {e}")
    
    # Redis key generators
    @staticmethod
    def qkey(gid: int) -> str:
        return f"tts:q:{gid}"
    
    @staticmethod
    def enabled_key(gid: int) -> str:
        return f"tts:enabled:{gid}"
    
    @staticmethod
    def cooldown_key(uid: int) -> str:
        return f"tts:cd:{uid}"
    
    @staticmethod
    def last_play_key(gid: int) -> str:
        return f"tts:last:{gid}"
    
    # Safe Redis operations
    def safe_get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        try:
            return self.db.get(key) or default
        except redis.RedisError as e:
            logger.error(f"Redis GET failed for key {key}: {e}")
            return default
    
    def safe_set(self, key: str, value, ex: Optional[int] = None) -> bool:
        try:
            if ex:
                self.db.setex(key, ex, value)
            else:
                self.db.set(key, value)
            return True
        except redis.RedisError as e:
            logger.error(f"Redis SET failed for key {key}: {e}")
            return False
    
    def safe_exists(self, key: str) -> bool:
        try:
            return self.db.exists(key) > 0
        except redis.RedisError as e:
            logger.error(f"Redis EXISTS failed for key {key}: {e}")
            return False
    
    def safe_rpush(self, key: str, value: str) -> bool:
        try:
            self.db.rpush(key, value)
            return True
        except redis.RedisError as e:
            logger.error(f"Redis RPUSH failed for key {key}: {e}")
            return False
    
    def safe_lpop(self, key: str) -> Optional[str]:
        try:
            return self.db.lpop(key)
        except redis.RedisError as e:
            logger.error(f"Redis LPOP failed for key {key}: {e}")
            return None


class TTS(commands.Cog):
    """Text-to-Speech functionality for Discord bot"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.redis = RedisManager(REDIS_URL)
        self.idle_task.start()
        logger.info("TTS Cog initialized")
    
    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        self.idle_task.cancel()
        logger.info("TTS Cog unloaded")
    
    # ---------- TTS Engine ----------
    async def generate_tts(self, text: str) -> str:
        """
        Generate TTS audio file from text.
        
        Args:
            text: Text to convert to speech
            
        Returns:
            Path to generated audio file
            
        Raises:
            AudioGenerationError: If generation fails
        """
        if not text or len(text.strip()) == 0:
            raise AudioGenerationError("Text cannot be empty")
        
        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH] + "..."
        
        file_id = uuid.uuid4().hex
        path = TMP_DIR / f"tts_{file_id}.mp3"
        
        try:
            tts = edge_tts.Communicate(text=text, voice=TTS_VOICE)
            await tts.save(str(path))
            
            if not path.exists() or path.stat().st_size == 0:
                raise AudioGenerationError("Generated file is empty or missing")
            
            logger.info(f"Generated TTS audio: {path}")
            return str(path)
            
        except Exception as e:
            logger.error(f"TTS generation failed: {e}")
            # Cleanup partial file if exists
            if path.exists():
                try:
                    path.unlink()
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup file {path}: {cleanup_error}")
            raise AudioGenerationError(f"Failed to generate audio: {e}")
    
    # ---------- Queue Management ----------
    def enqueue(self, guild_id: int, audio_path: str) -> bool:
        """Add audio file to guild's play queue"""
        return self.redis.safe_rpush(self.redis.qkey(guild_id), audio_path)
    
    def dequeue(self, guild_id: int) -> Optional[str]:
        """Get next audio file from guild's play queue"""
        return self.redis.safe_lpop(self.redis.qkey(guild_id))
    
    def is_tts_enabled(self, guild_id: int) -> bool:
        """Check if TTS is enabled for guild"""
        return self.redis.safe_get(self.redis.enabled_key(guild_id)) == "1"
    
    def is_on_cooldown(self, user_id: int) -> bool:
        """Check if user is on cooldown"""
        return self.redis.safe_exists(self.redis.cooldown_key(user_id))
    
    def set_cooldown(self, user_id: int) -> bool:
        """Set cooldown for user"""
        return self.redis.safe_set(
            self.redis.cooldown_key(user_id), 
            1, 
            ex=USER_COOLDOWN
        )
    
    def update_last_play(self, guild_id: int) -> bool:
        """Update last play timestamp for guild"""
        return self.redis.safe_set(
            self.redis.last_play_key(guild_id), 
            int(time.time())
        )
    
    # ---------- Voice Connection ----------
    async def ensure_voice_connection(
        self, 
        guild: discord.Guild, 
        channel: discord.VoiceChannel
    ) -> Optional[wavelink.Player]:
        """
        Ensure bot is connected to voice channel.
        
        Returns:
            Voice client or None if connection fails
        """
        vc = guild.voice_client
        
        if vc and vc.is_connected():
            return vc
        
        for attempt in range(RECONNECT_ATTEMPTS):
            try:
                logger.info(f"Connecting to voice channel (attempt {attempt + 1}/{RECONNECT_ATTEMPTS})")
                vc = await channel.connect(cls=wavelink.Player, timeout=10.0)
                logger.info(f"Successfully connected to {channel.name}")
                return vc
            except asyncio.TimeoutError:
                logger.warning(f"Voice connection timeout (attempt {attempt + 1})")
                await asyncio.sleep(1)
            except discord.ClientException as e:
                logger.error(f"Discord client error during connection: {e}")
                if "already connected" in str(e).lower():
                    return guild.voice_client
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Unexpected error connecting to voice: {e}")
                await asyncio.sleep(1)
        
        logger.error("Failed to connect to voice after all attempts")
        return None
    
    # ---------- Slash Commands ----------
    @discord.app_commands.command(
        name="tts-toggle", 
        description="Enable or disable TTS in this server"
    )
    @discord.app_commands.checks.has_permissions(administrator=True)
    async def tts_toggle(self, interaction: discord.Interaction, enabled: bool):
        """Toggle TTS functionality for the server"""
        try:
            success = self.redis.safe_set(
                self.redis.enabled_key(interaction.guild.id), 
                int(enabled)
            )
            
            if success:
                status = "enabled" if enabled else "disabled"
                await interaction.response.send_message(
                    f"✅ TTS {status} successfully!", 
                    ephemeral=True
                )
                logger.info(f"TTS {status} for guild {interaction.guild.id}")
            else:
                await interaction.response.send_message(
                    "❌ Failed to update TTS settings. Please try again.", 
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error in tts_toggle: {e}")
            await interaction.response.send_message(
                "❌ An error occurred. Please try again later.", 
                ephemeral=True
            )
    
    @discord.app_commands.command(name="say", description="Make the bot speak")
    async def say(self, interaction: discord.Interaction, text: str):
        """Make the bot speak in voice channel"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Validation checks
            if not interaction.guild:
                return await interaction.followup.send(
                    "❌ This command can only be used in servers.", 
                    ephemeral=True
                )
            
            if not self.is_tts_enabled(interaction.guild.id):
                return await interaction.followup.send(
                    "❌ TTS is disabled in this server.", 
                    ephemeral=True
                )
            
            if self.is_on_cooldown(interaction.user.id):
                return await interaction.followup.send(
                    f"⏱️ Cooldown active. Please wait {USER_COOLDOWN} seconds.", 
                    ephemeral=True
                )
            
            if not interaction.user.voice:
                return await interaction.followup.send(
                    "❌ You must be in a voice channel to use this command.", 
                    ephemeral=True
                )
            
            # Connect to voice
            vc = await self.ensure_voice_connection(
                interaction.guild, 
                interaction.user.voice.channel
            )
            
            if not vc:
                return await interaction.followup.send(
                    "❌ Failed to connect to voice channel.", 
                    ephemeral=True
                )
            
            # Set cooldown
            self.set_cooldown(interaction.user.id)
            
            # Generate and queue audio
            try:
                audio_path = await self.generate_tts(text)
                self.enqueue(interaction.guild.id, audio_path)
                
                await interaction.followup.send("🗣️ Speaking…", ephemeral=True)
                
                # Start playback if not already playing
                if not vc.is_playing():
                    await self.play_next(interaction.guild)
                    
            except AudioGenerationError as e:
                logger.error(f"Audio generation failed: {e}")
                await interaction.followup.send(
                    "❌ Failed to generate audio. Please try again.", 
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error in say command: {e}")
            try:
                await interaction.followup.send(
                    "❌ An unexpected error occurred.", 
                    ephemeral=True
                )
            except:
                pass
    
    # ---------- Playback ----------
    async def play_next(self, guild: discord.Guild):
        """Play next audio file in queue"""
        try:
            player = guild.voice_client
            
            if not player or not player.is_connected():
                logger.warning(f"No voice client for guild {guild.id}")
                return
            
            audio_path = self.dequeue(guild.id)
            if not audio_path:
                logger.debug(f"Queue empty for guild {guild.id}")
                return
            
            # Check if file exists
            if not Path(audio_path).exists():
                logger.error(f"Audio file not found: {audio_path}")
                # Try next in queue
                await self.play_next(guild)
                return
            
            # Load and play track
            try:
                node = wavelink.NodePool.get_node()
                tracks = await node.get_tracks(audio_path)
                
                if not tracks:
                    logger.error(f"No tracks found for {audio_path}")
                    # Cleanup and try next
                    self.cleanup_audio_file(audio_path)
                    await self.play_next(guild)
                    return
                
                self.update_last_play(guild.id)
                await player.play(tracks[0])
                logger.info(f"Playing track in guild {guild.id}")
                
            except wavelink.WavelinkException as e:
                logger.error(f"Wavelink error during playback: {e}")
                self.cleanup_audio_file(audio_path)
                await self.play_next(guild)
                
        except Exception as e:
            logger.error(f"Error in play_next: {e}")
    
    @commands.Cog.listener()
    async def on_wavelink_track_end(
        self, 
        player: wavelink.Player, 
        track, 
        reason
    ):
        """Handle track end event"""
        try:
            # Cleanup audio file
            if hasattr(track, 'uri') and track.uri:
                self.cleanup_audio_file(track.uri)
            
            # Play next in queue
            await self.play_next(player.guild)
            
        except Exception as e:
            logger.error(f"Error in on_wavelink_track_end: {e}")
    
    def cleanup_audio_file(self, path: str):
        """Safely delete audio file"""
        try:
            file_path = Path(path)
            if file_path.exists():
                file_path.unlink()
                logger.debug(f"Cleaned up audio file: {path}")
        except Exception as e:
            logger.error(f"Failed to cleanup file {path}: {e}")
    
    # ---------- Auto Disconnect ----------
    @tasks.loop(seconds=30)
    async def idle_task(self):
        """Disconnect from idle voice channels"""
        try:
            for vc in self.bot.voice_clients:
                if not vc.guild:
                    continue
                
                last_play = self.redis.safe_get(
                    self.redis.last_play_key(vc.guild.id)
                )
                
                if last_play:
                    idle_time = time.time() - int(last_play)
                    if idle_time > IDLE_TIMEOUT:
                        logger.info(
                            f"Disconnecting from {vc.guild.name} due to inactivity"
                        )
                        try:
                            await vc.disconnect(force=False)
                        except Exception as e:
                            logger.error(f"Error disconnecting: {e}")
                            
        except Exception as e:
            logger.error(f"Error in idle_task: {e}")
    
    @idle_task.before_loop
    async def before_idle(self):
        """Wait for bot to be ready before starting idle task"""
        await self.bot.wait_until_ready()
    
    # ---------- AI Integration Hook ----------
    async def ai_speak(
        self, 
        guild: discord.Guild, 
        channel: discord.VoiceChannel, 
        text: str
    ) -> bool:
        """
        Make the bot speak in a voice channel (for AI integration).
        
        Args:
            guild: Discord guild
            channel: Voice channel to speak in
            text: Text to speak
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.is_tts_enabled(guild.id):
                logger.debug(f"TTS disabled for guild {guild.id}")
                return False
            
            vc = await self.ensure_voice_connection(guild, channel)
            if not vc:
                logger.error("Failed to establish voice connection")
                return False
            
            audio_path = await self.generate_tts(text)
            if not self.enqueue(guild.id, audio_path):
                logger.error("Failed to enqueue audio")
                return False
            
            if not vc.is_playing():
                await self.play_next(guild)
            
            return True
            
        except AudioGenerationError as e:
            logger.error(f"AI speak audio generation failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Error in ai_speak: {e}")
            return False


async def setup(bot: commands.Bot):
    """Setup function for loading the cog"""
    try:
        await bot.add_cog(TTS(bot))
        logger.info("TTS cog loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load TTS cog: {e}")
        raise
